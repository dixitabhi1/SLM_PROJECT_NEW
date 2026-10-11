"""
Rerun failed and truncated items with 4,096 token answer budget.

Rules:
1. Append-only: New rows appended to existing results files; raw records never overwritten.
2. Budget: Strictly 4,096 tokens.
3. Reruns:
   - Qwen-27B: 22 failed/truncated items.
   - GPT-OSS-120B: 1 truncated item (compound_dev_0024).
4. Pacing: 5.0s inter-request sleep with adaptive 429 backoff.
5. Updates results hash journal upon completion.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.audit.audit_rules import audit_results_journal
from scripts.run_phase4_dev_eval import format_prompt

RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
TRACK_A_DEV_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
TRACK_B_DEV_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_dev_split.json")


def call_groq_api_4096(
    model_id: str,
    prompt: str,
    api_key: str,
    max_tokens: int = 4096,
    seed: int = 42
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": seed
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    rate_headers = {}

    for attempt in range(10):
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                elapsed = time.perf_counter() - t0
                for k, v in resp.headers.items():
                    if "ratelimit" in k.lower():
                        rate_headers[k.lower()] = v
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "").strip()
                finish_reason = choice.get("finish_reason", "stop")
                usage = data.get("usage", {})
                status = "COMPLETE" if finish_reason == "stop" and content else "FAILED"
                return {
                    "content": content,
                    "finish_reason": finish_reason,
                    "latency_seconds": round(elapsed, 4),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "status": status,
                    "error_message": None
                }, rate_headers
        except urllib.error.HTTPError as he:
            elapsed = time.perf_counter() - t0
            for k, v in he.headers.items():
                if "ratelimit" in k.lower():
                    rate_headers[k.lower()] = v
            if he.code == 429:
                retry_after_str = he.headers.get("retry-after")
                try:
                    retry_after = float(retry_after_str) if retry_after_str else 0.0
                except (ValueError, TypeError):
                    retry_after = 0.0
                err_body = ""
                try:
                    err_body = he.read().decode("utf-8")
                except Exception:
                    pass
                wait_match = re.search(r"try again in (\d+(?:\.\d+)?)s", err_body)
                body_wait = float(wait_match.group(1)) if wait_match else 0.0
                sleep_time = max(retry_after + 1.5, body_wait + 1.5, 4.0 * (attempt + 1), 8.0)
                print(f"[Rate Limit 429] Backing off for {sleep_time:.1f}s (attempt {attempt+1}/10)...")
                time.sleep(sleep_time)
                continue
            return {
                "content": "",
                "finish_reason": f"http_error_{he.code}",
                "latency_seconds": round(elapsed, 4),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "status": "FAILED",
                "error_message": f"HTTP {he.code}: {he.reason}"
            }, rate_headers
        except Exception as e:
            elapsed = time.perf_counter() - t0
            return {
                "content": "",
                "finish_reason": "exception",
                "latency_seconds": round(elapsed, 4),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "status": "FAILED",
                "error_message": str(e)
            }, rate_headers

    return {
        "content": "",
        "finish_reason": "retries_exhausted",
        "latency_seconds": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "status": "FAILED",
        "error_message": "Exceeded 10 retries on rate limit"
    }, rate_headers


def main():
    from dotenv import load_dotenv
    load_dotenv()
    groq_api_key = os.getenv("GROQ_API_KEY", "")
    if not groq_api_key:
        print("ERROR: GROQ_API_KEY not found.")
        sys.exit(1)

    with open(TRACK_A_DEV_PATH, "r", encoding="utf-8") as f:
        track_a_items = json.load(f)
    dev_by_id = {}
    for it in track_a_items:
        key = it.get("subtask_id") or it.get("original_id")
        dev_by_id[key] = it

    # 1. Rerun GPT-OSS-120B truncated item (compound_dev_0024)
    gpt_file = os.path.join(RESULTS_DIR, "b0_gpt120b_dev_records.jsonl")
    gpt_items_to_rerun = ["compound_dev_0024"]

    print("\n==========================================")
    print("RERUNNING GPT-OSS-120B TRUNCATED ITEMS (BUDGET=4096)")
    print("==========================================")
    with open(gpt_file, "a", encoding="utf-8") as f_out:
        for it_id in gpt_items_to_rerun:
            item = dev_by_id[it_id]
            prompt = format_prompt(item)
            resp, ratelimits = call_groq_api_4096("openai/gpt-oss-120b", prompt, groq_api_key, max_tokens=4096)
            truncated = (resp["finish_reason"] == "length")
            rec = {
                "item_id": it_id,
                "track": "A",
                "task_type": item.get("task_type"),
                "stratum": item.get("stratum"),
                "solvability": item.get("solvability"),
                "num_stages": len(item.get("component_parts", [])),
                "model_id": "openai/gpt-oss-120b",
                "condition": "B0_GPT120B",
                "max_tokens_budget": 4096,
                "prompt": prompt,
                "output": resp["content"],
                "finish_reason": resp["finish_reason"],
                "truncated": truncated,
                "latency_seconds": resp["latency_seconds"],
                "prompt_tokens": resp["prompt_tokens"],
                "completion_tokens": resp["completion_tokens"],
                "status": resp["status"],
                "passed": False,  # Will be scored by versioned scorer
                "recall": 0.0,
                "checker": "pending_rescore",
                "checker_details": "Generated under 4096 budget"
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"GPT Rerun {it_id}: Status={resp['status']}, Finish={resp['finish_reason']}, CompTokens={resp['completion_tokens']}")
            time.sleep(3.0)

    # 2. Rerun Qwen-27B failed and truncated items
    qwen_items_to_rerun = [
        "compound_dev_0003", "compound_dev_0005", "compound_dev_0006", "compound_dev_0007",
        "compound_dev_0008", "compound_dev_0011", "compound_dev_0012", "compound_dev_0013",
        "compound_dev_0015", "compound_dev_0016", "compound_dev_0018", "compound_dev_0023",
        "compound_dev_0024", "compound_dev_0025", "compound_dev_0026", "compound_dev_0027",
        "compound_dev_0028", "compound_dev_0032", "compound_dev_0033", "compound_dev_0035",
        "compound_dev_0036", "compound_dev_0037"
    ]

    print("\n==========================================")
    print(f"RERUNNING QWEN-27B FAILED & TRUNCATED ITEMS ({len(qwen_items_to_rerun)} items, BUDGET=4096)")
    print("==========================================")
    qwen_file = os.path.join(RESULTS_DIR, "b0_qwen27b_dev_records.jsonl")
    with open(qwen_file, "a", encoding="utf-8") as f_out:
        for idx, it_id in enumerate(qwen_items_to_rerun, 1):
            item = dev_by_id[it_id]
            prompt = format_prompt(item)
            resp, ratelimits = call_groq_api_4096("qwen/qwen3.8-27b", prompt, groq_api_key, max_tokens=4096)
            truncated = (resp["finish_reason"] == "length")
            rec = {
                "item_id": it_id,
                "track": "A",
                "task_type": item.get("task_type"),
                "stratum": item.get("stratum"),
                "solvability": item.get("solvability"),
                "num_stages": len(item.get("component_parts", [])),
                "model_id": "qwen/qwen3.8-27b",
                "condition": "B0_Qwen27B",
                "max_tokens_budget": 4096,
                "prompt": prompt,
                "output": resp["content"],
                "finish_reason": resp["finish_reason"],
                "truncated": truncated,
                "latency_seconds": resp["latency_seconds"],
                "prompt_tokens": resp["prompt_tokens"],
                "completion_tokens": resp["completion_tokens"],
                "status": resp["status"],
                "passed": False,  # Will be scored by versioned scorer
                "recall": 0.0,
                "checker": "pending_rescore",
                "checker_details": "Generated under 4096 budget"
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"Qwen Rerun [{idx}/{len(qwen_items_to_rerun)}] {it_id}: Status={resp['status']}, Finish={resp['finish_reason']}, CompTokens={resp['completion_tokens']}")
            time.sleep(5.0)

    # Update hash journal
    audit_results_journal(REPO_ROOT)
    print("\nReruns complete. Results journal updated.")


if __name__ == "__main__":
    main()

