"""
Evaluate C0 (Phi-4-mini without tools) on the 40 Hard Compound Dev items.
Budget: 4,096 completion tokens.
Appends records to results/phase4/c0_phi4_mini_dev_records.jsonl.
Evaluates Difficulty Gate 1: C0 Compound Total Acc <= 60.0%.
"""

import os
import sys
import json
import time
import urllib.request
from typing import Dict, Any, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.eval.versioned_scorer import score_record

DEV_FILE = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
RESULTS_FILE = os.path.join(REPO_ROOT, "results", "phase4", "c0_phi4_mini_dev_records.jsonl")


def call_llama_server(prompt: str, port: int = 8080, max_tokens: int = 4096) -> Dict[str, Any]:
    url = f"http://127.0.0.1:{port}/v1/chat/completions"
    payload = {
        "model": "phi-4-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as resp:
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
            "completion_tokens": usage.get("completion_tokens", 0)
        }


def main():
    with open(DEV_FILE, "r", encoding="utf-8") as f:
        dev_items = json.load(f)

    compound_items = [x for x in dev_items if x.get("stratum") == "composed"]
    print(f"Loaded {len(compound_items)} compound items from Dev split.")
    assert len(compound_items) == 40, f"Expected 40 compound items, got {len(compound_items)}"

    records = []
    print("\nEvaluating C0 on 40 Hard Compound Dev items...")

    for idx, item in enumerate(compound_items, 1):
        item_id = item["subtask_id"]
        prompt = item["prompt"]
        formatted_prompt = f"{prompt}\nSolve the problem step by step. Conclude your final answer with: #### <final integer answer>"
        solvability = item.get("solvability", "unknown")
        num_stages = item.get("num_stages", 0)

        print(f"[{idx}/40] {item_id} ({num_stages}-stage, {solvability})...", end="", flush=True)

        res = call_llama_server(formatted_prompt, port=8080, max_tokens=4096)
        output = res["content"]
        finish_reason = res["finish_reason"]
        truncated = finish_reason != "stop"
        status = "FAILED" if truncated else "COMPLETE"

        # Score output
        score = score_record(item, output)
        passed = score["passed"] if not truncated else False
        recall = score["recall"] if not truncated else 0.0

        record = {
            "item_id": item_id,
            "track": "A",
            "task_type": "composed",
            "stratum": "composed",
            "solvability": solvability,
            "num_stages": num_stages,
            "model_id": "microsoft/Phi-4-mini-instruct",
            "condition": "C0",
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

    # Summary statistics
    total = len(records)
    passed_cnt = sum(1 for r in records if r["passed"])
    trunc_cnt = sum(1 for r in records if r["truncated"])
    total_acc = (passed_cnt / total) * 100

    tool_req = [r for r in records if r["solvability"] == "tool-required"]
    solv_no_tool = [r for r in records if r["solvability"] == "solvable_without_tools"]
    s2 = [r for r in records if r["num_stages"] == 2]
    s3 = [r for r in records if r["num_stages"] == 3]

    print("\n" + "=" * 60)
    print("C0 EVALUATION SUMMARY ON NEW HARD COMPOUND DEV STRATUM")
    print("=" * 60)
    print(f"Total Items: {total}")
    print(f"Passed: {passed_cnt} / {total} ({total_acc:.1f}%)")
    print(f"Truncated: {trunc_cnt} / {total} ({trunc_cnt/total*100:.1f}%)")
    print(f"Tool-required Acc (w/o tools): {sum(1 for r in tool_req if r['passed'])} / {len(tool_req)} ({sum(1 for r in tool_req if r['passed'])/len(tool_req)*100:.1f}%)")
    print(f"Solvable w/o tools Acc: {sum(1 for r in solv_no_tool if r['passed'])} / {len(solv_no_tool)} ({sum(1 for r in solv_no_tool if r['passed'])/len(solv_no_tool)*100:.1f}%)")
    print(f"2-stage Acc: {sum(1 for r in s2 if r['passed'])} / {len(s2)} ({sum(1 for r in s2 if r['passed'])/len(s2)*100:.1f}%)")
    print(f"3-stage Acc: {sum(1 for r in s3 if r['passed'])} / {len(s3)} ({sum(1 for r in s3 if r['passed'])/len(s3)*100:.1f}%)")

    gate_1_pass = total_acc <= 60.0
    print(f"\nDifficulty Gate 1 (C0 Compound Total Acc <= 60.0%): {'PASS' if gate_1_pass else 'FAIL'} ({total_acc:.1f}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()

