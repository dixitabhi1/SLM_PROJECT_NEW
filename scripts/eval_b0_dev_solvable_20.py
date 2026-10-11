"""
Evaluate B0 (openai/gpt-oss-120b on Groq API without tools) on the 20 Solvable-Without-Tools Hard Compound Dev items.
Budget: 4,096 completion tokens.
Appends records to results/phase4/b0_gpt120b_dev_records.jsonl.
Evaluates Difficulty Gate 2: B0 Compound Solvable-without-tools Total Acc <= 90.0%.
Enforces 65s pacing to strictly respect Groq free-tier rate limits (1,000 completion tokens per minute).
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv
load_dotenv()

from src.eval.versioned_scorer import score_record

DEV_FILE = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
RESULTS_FILE = os.path.join(REPO_ROOT, "results", "phase4", "b0_gpt120b_dev_records.jsonl")


def call_groq_api(prompt: str, api_key: str, max_tokens: int = 4096) -> Dict[str, Any]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "SLM-Bench"
    }

    # Retry with exponential backoff on rate limits
    for attempt in range(10):
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                elapsed = time.perf_counter() - t0
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "").strip()
                finish_reason = choice.get("finish_reason", "stop")
                usage = data.get("usage", {})
                return {
                    "content": content,
                    "finish_reason": finish_reason,
                    "latency": elapsed,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "error": None
                }
        except urllib.error.HTTPError as he:
            elapsed = time.perf_counter() - t0
            err_body = he.read().decode("utf-8", errors="ignore")
            if he.code == 429:
                wait_time = 65 * (attempt + 1)
                print(f" [Rate-limit 429: waiting {wait_time}s...]", end="", flush=True)
                time.sleep(wait_time)
            else:
                print(f" [HTTP {he.code}: {err_body[:100]}]", end="", flush=True)
                time.sleep(10)
        except Exception as e:
            time.sleep(10)

    return {
        "content": "",
        "finish_reason": "error",
        "latency": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "error": "Exhausted retries"
    }


def main():
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing!")

    with open(DEV_FILE, "r", encoding="utf-8") as f:
        dev_items = json.load(f)

    # Filter to the 20 solvable-without-tools compound items
    solvable_items = [
        x for x in dev_items
        if x.get("stratum") == "composed" and x.get("solvability") == "solvable_without_tools"
    ]
    print(f"Loaded {len(solvable_items)} solvable-without-tools compound items from Dev split.")
    assert len(solvable_items) == 20, f"Expected 20 items, got {len(solvable_items)}"

    records = []
    print("\nEvaluating B0 (GPT-120B) on 20 Solvable-Without-Tools Hard Compound Dev items...")

    for idx, item in enumerate(solvable_items, 1):
        item_id = item["subtask_id"]
        prompt = item["prompt"]
        formatted_prompt = f"{prompt}\nSolve the problem step by step. Conclude your final answer with: #### <final integer answer>"
        num_stages = item.get("num_stages", 0)

        print(f"[{idx}/20] {item_id} ({num_stages}-stage)...", end="", flush=True)

        res = call_groq_api(formatted_prompt, api_key=api_key, max_tokens=4096)
        output = res["content"]
        finish_reason = res["finish_reason"]
        truncated = finish_reason != "stop"
        status = "FAILED" if (truncated or res["error"]) else "COMPLETE"

        # Score output
        score = score_record(item, output)
        passed = score["passed"] if (status == "COMPLETE") else False
        recall = score["recall"] if (status == "COMPLETE") else 0.0

        record = {
            "item_id": item_id,
            "track": "A",
            "task_type": "composed",
            "stratum": "composed",
            "solvability": "solvable_without_tools",
            "num_stages": num_stages,
            "model_id": "openai/gpt-oss-120b",
            "condition": "B0",
            "max_tokens_budget": 4096,
            "prompt": formatted_prompt,
            "output": output,
            "finish_reason": finish_reason,
            "truncated": truncated,
            "latency_seconds": round(res["latency"], 4),
            "prompt_tokens": res["prompt_tokens"],
            "completion_tokens": res["completion_tokens"],
            "status": status,
            "passed": passed,
            "recall": recall,
            "checker": score["checker"],
            "checker_details": score["details"]
        }
        records.append(record)

        # Append immediately to results file (Hard Rule 2)
        with open(RESULTS_FILE, "a", encoding="utf-8") as out_f:
            out_f.write(json.dumps(record) + "\n")

        print(f" {'PASS' if passed else 'FAIL'} (tok: {res['completion_tokens']}, time: {res['latency']:.1f}s)")

        # Pacing between calls if not last item
        if idx < len(solvable_items):
            print(f"       Pacing 65s for Groq quota...", end="", flush=True)
            time.sleep(65)
            print(" ready.", flush=True)

    # Summary statistics
    total = len(records)
    passed_cnt = sum(1 for r in records if r["passed"])
    trunc_cnt = sum(1 for r in records if r["truncated"])
    total_acc = (passed_cnt / total) * 100

    s2 = [r for r in records if r["num_stages"] == 2]
    s3 = [r for r in records if r["num_stages"] == 3]

    print("\n" + "=" * 60)
    print("B0 (GPT-120B) EVALUATION SUMMARY ON SOLVABLE-WITHOUT-TOOLS DEV STRATUM")
    print("=" * 60)
    print(f"Total Items: {total}")
    print(f"Passed: {passed_cnt} / {total} ({total_acc:.1f}%)")
    print(f"Truncated: {trunc_cnt} / {total} ({trunc_cnt/total*100:.1f}%)")
    print(f"2-stage Acc: {sum(1 for r in s2 if r['passed'])} / {len(s2)} ({sum(1 for r in s2 if r['passed'])/len(s2)*100:.1f}%)")
    print(f"3-stage Acc: {sum(1 for r in s3 if r['passed'])} / {len(s3)} ({sum(1 for r in s3 if r['passed'])/len(s3)*100:.1f}%)")

    gate_2_pass = total_acc <= 90.0
    print(f"\nDifficulty Gate 2 (B0 Compound Solvable-without-tools Total Acc <= 90.0%): {'PASS' if gate_2_pass else 'FAIL'} ({total_acc:.1f}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()

