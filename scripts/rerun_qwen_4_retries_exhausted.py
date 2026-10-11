"""
Rerun the 4 Qwen-27B items that hit 'retries_exhausted' due to OTPM rolling window.
Pacing: 65s pause before each call ensures Groq's rolling OTPM used tokens is strictly 0.
Strictly append-only to results/phase4/b0_qwen27b_dev_records.jsonl.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
from typing import Dict, Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.run_phase4_dev_eval import format_prompt
from src.audit.audit_rules import audit_results_journal

RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
TRACK_A_DEV_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
QWEN_FILE = os.path.join(RESULTS_DIR, "b0_qwen27b_dev_records.jsonl")

ITEMS_TO_RERUN = [
    "compound_dev_0007",
    "compound_dev_0018",
    "compound_dev_0026",
    "compound_dev_0036"
]


def call_groq_single(model_id: str, prompt: str, api_key: str, max_tokens: int = 4096) -> Dict[str, Any]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": 42
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    for attempt in range(12):
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                elapsed = time.perf_counter() - t0
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
                }
        except urllib.error.HTTPError as he:
            if he.code == 429:
                err_body = he.read().decode("utf-8")
                wait_match = re.search(r"try again in (\d+(?:\.\d+)?)s", err_body)
                body_wait = float(wait_match.group(1)) if wait_match else 0.0
                sleep_time = max(body_wait + 3.0, 15.0 * (attempt + 1), 60.0)
                print(f"[Rate Limit 429] Sleeping {sleep_time:.1f}s (attempt {attempt+1}/12)...")
                time.sleep(sleep_time)
                continue
            return {
                "content": "",
                "finish_reason": f"http_error_{he.code}",
                "latency_seconds": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "status": "FAILED",
                "error_message": f"HTTP {he.code}: {he.reason}"
            }
        except Exception as e:
            return {
                "content": "",
                "finish_reason": "exception",
                "latency_seconds": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "status": "FAILED",
                "error_message": str(e)
            }
    return {
        "content": "",
        "finish_reason": "retries_exhausted",
        "latency_seconds": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "status": "FAILED",
        "error_message": "Exceeded 12 retries"
    }


def main():
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        print("ERROR: GROQ_API_KEY not found.")
        sys.exit(1)

    with open(TRACK_A_DEV_PATH, "r", encoding="utf-8") as f:
        track_a_items = json.load(f)
    dev_by_id = {}
    for it in track_a_items:
        key = it.get("subtask_id") or it.get("original_id")
        dev_by_id[key] = it

    print(f"Rerunning {len(ITEMS_TO_RERUN)} items with 65s spacing...")

    with open(QWEN_FILE, "a", encoding="utf-8") as f_out:
        for idx, it_id in enumerate(ITEMS_TO_RERUN, 1):
            item = dev_by_id[it_id]
            prompt = format_prompt(item)
            print(f"\n[{idx}/{len(ITEMS_TO_RERUN)}] Sleeping 65s to clear OTPM window before {it_id}...")
            time.sleep(65.0)

            resp = call_groq_single("qwen/qwen3.8-27b", prompt, api_key, max_tokens=4096)
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
                "passed": False,
                "recall": 0.0,
                "checker": "pending_rescore",
                "checker_details": f"Rerun under 4096 budget with 65s spacing: {resp['finish_reason']}"
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"Result {it_id}: Status={resp['status']}, Finish={resp['finish_reason']}, CompTokens={resp['completion_tokens']}")

    audit_results_journal()
    print("Completed targeted reruns. Results journal verified.")


if __name__ == "__main__":
    main()

