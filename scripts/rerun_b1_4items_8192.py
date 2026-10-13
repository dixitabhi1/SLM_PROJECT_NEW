"""
scripts/rerun_b1_4items_8192.py

Reruns the 4 truncated compound items for B1 Qwen-27B at 8,192 tokens:
- compound_heldout_v2_0003
- compound_heldout_v2_0005
- compound_heldout_v2_0017
- compound_heldout_v2_0026

Appends new rows to results/phase4/b1_qwen27b_heldout_records.jsonl.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
from typing import Dict, Any
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
load_dotenv()

from src.pipeline.specialist_pipeline import get_table_schema
from src.tools.tolerant_harness import execute_sql_tolerant, KNOWN_DATABASES
from src.eval.versioned_scorer import score_record
from scripts.run_b1_qwen_track_b_and_track_a import identify_database, extract_sql_query

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
B1_QWEN_PATH = os.path.join(RESULTS_DIR, "b1_qwen27b_heldout_records.jsonl")
TRACK_A_PATH = os.path.join(REPO_ROOT, "data", "track_a_heldout_split.json")

TARGET_IDS = [
    "compound_heldout_v2_0003",
    "compound_heldout_v2_0005",
    "compound_heldout_v2_0017",
    "compound_heldout_v2_0026",
]


def call_groq_api_robust_8192(
    model_id: str,
    prompt: str,
    system_prompt: str = "You are a helpful, precise assistant.",
    max_tokens: int = 8192,
    seed: int = 42
) -> Dict[str, Any]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": seed
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    for attempt in range(20):
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
                status = "COMPLETE" if finish_reason in ["stop", "length"] and content else "FAILED"
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
            elapsed = time.perf_counter() - t0
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
                sleep_time = max(retry_after + 2.0, body_wait + 2.0, 5.0 * (attempt + 1), 10.0)
                if "OTPM" in err_body or "output tokens per minute" in err_body:
                    sleep_time = max(sleep_time, 75.0)
                print(f"    [Rate limit 429] Sleeping {sleep_time:.1f}s before retry {attempt+1}/20... ({err_body[:100]})", flush=True)
                time.sleep(sleep_time)
            else:
                print(f"    [HTTP {he.code}] Error: {he.reason}", flush=True)
                time.sleep(5.0 * (attempt + 1))
        except Exception as e:
            print(f"    [Network Error] {e}", flush=True)
            time.sleep(5.0 * (attempt + 1))

    return {
        "content": "",
        "finish_reason": "error",
        "latency_seconds": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "status": "FAILED",
        "error_message": "Exceeded max retries"
    }


def run_item_8192(item: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.time()
    total_prompt_tok = 0
    total_comp_tok = 0
    raw_prompt = item["prompt"]
    db_name = identify_database(item)

    if db_name:
        schema = get_table_schema(db_name)
        sql_prompt = (
            f"Task: {raw_prompt}\n\n"
            f"Database: {db_name}\n"
            f"Schema:\n{schema}\n\n"
            f"Write exactly one SQLite query enclosed in ```sql ... ``` to extract the required data from '{db_name}'. "
            f"Select ONLY the single requested column."
        )
        resp_sql = call_groq_api_robust_8192(
            "qwen/qwen3.8-27b",
            sql_prompt,
            system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
            max_tokens=8192
        )
        total_prompt_tok += resp_sql["prompt_tokens"]
        total_comp_tok += resp_sql["completion_tokens"]
        q = extract_sql_query(resp_sql["content"])
        clean, out_text = execute_sql_tolerant(db_name, q, prompt_context=raw_prompt)

        if not clean:
            retry_sql = (
                f"{sql_prompt}\n\n"
                f"Previous query produced error: {out_text}\n"
                f"Please output the corrected SQLite query in ```sql ... ```:"
            )
            resp_sql2 = call_groq_api_robust_8192(
                "qwen/qwen3.8-27b",
                retry_sql,
                system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
                max_tokens=8192
            )
            total_prompt_tok += resp_sql2["prompt_tokens"]
            total_comp_tok += resp_sql2["completion_tokens"]
            q2 = extract_sql_query(resp_sql2["content"])
            clean, out_text = execute_sql_tolerant(db_name, q2, prompt_context=raw_prompt)

        downstream_prompt = (
            f"Task: {raw_prompt}\n\n"
            f"Database Query Executed: {q}\n"
            f"Retrieved Query Data: {out_text}\n\n"
            f"Based on the retrieved data, solve the problem step by step.\n"
            f"Conclude your final answer with: 'Final Answer: <answer>' or '#### <answer>'."
        )
        resp_reason = call_groq_api_robust_8192(
            "qwen/qwen3.8-27b",
            downstream_prompt,
            system_prompt="You are an expert mathematical and logical reasoning assistant.",
            max_tokens=8192
        )
        total_prompt_tok += resp_reason["prompt_tokens"]
        total_comp_tok += resp_reason["completion_tokens"]
        dt = time.time() - t0

        sc = score_record(item, resp_reason["content"])
        return {
            "output": resp_reason["content"][:300],
            "full_output": resp_reason["content"],
            "finish_reason": resp_reason["finish_reason"],
            "prompt_tokens": total_prompt_tok,
            "completion_tokens": total_comp_tok,
            "total_tokens": total_prompt_tok + total_comp_tok,
            "status": resp_reason["status"],
            "clean_execution": clean and resp_reason["status"] == "COMPLETE",
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2)
        }
    else:
        direct_prompt = (
            f"{raw_prompt}\n\n"
            f"Solve the problem step by step. Conclude your final answer with 'Final Answer: <answer>' or '#### <answer>'."
        )
        resp = call_groq_api_robust_8192(
            "qwen/qwen3.8-27b",
            direct_prompt,
            system_prompt="You are a helpful, precise assistant. Reason step-by-step and provide your final answer in the requested format.",
            max_tokens=8192
        )
        dt = time.time() - t0
        sc = score_record(item, resp["content"])
        return {
            "output": resp["content"][:300],
            "full_output": resp["content"],
            "finish_reason": resp["finish_reason"],
            "prompt_tokens": resp["prompt_tokens"],
            "completion_tokens": resp["completion_tokens"],
            "total_tokens": resp["total_tokens"],
            "status": resp["status"],
            "clean_execution": resp["status"] == "COMPLETE",
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2)
        }


def main():
    print(f"=== RERUNNING 4 B1 ITEMS AT 8,192 TOKENS ===", flush=True)
    with open(TRACK_A_PATH, "r", encoding="utf-8") as f:
        track_a_items = json.load(f)
    tra_by_id = {(it.get("item_id") or it.get("original_id") or it.get("subtask_id")): it for it in track_a_items}

    # Load existing 8192 reruns if already executed
    already_done = set()
    if os.path.exists(B1_QWEN_PATH):
        with open(B1_QWEN_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        r = json.loads(line)
                        if r.get("rerun_8192"):
                            iid = r.get("item_id") or r.get("question_id")
                            already_done.add(iid)
                    except Exception:
                        pass

    with open(B1_QWEN_PATH, "a", encoding="utf-8") as f_out:
        for idx, iid in enumerate(TARGET_IDS, 1):
            if iid in already_done:
                print(f"[{idx}/4] {iid}: already completed with rerun_8192, skipping.", flush=True)
                continue
            it = tra_by_id[iid]
            print(f"[{idx}/4] Running {iid} at max_tokens=8192...", flush=True)
            res = run_item_8192(it)
            rec = {
                "item_id": iid,
                "split": "heldout",
                "track": "A",
                "task_type": it.get("task_type") or it.get("type", "compound"),
                "stratum": it.get("stratum", "compound_track_a"),
                "solvability": it.get("solvability", ""),
                "model_id": "qwen/qwen3.8-27b",
                "model": "qwen/qwen3.8-27b",
                "condition": "B1",
                "output": res["output"],
                "full_output": res["full_output"],
                "finish_reason": res["finish_reason"],
                "prompt_tokens": res["prompt_tokens"],
                "completion_tokens": res["completion_tokens"],
                "total_tokens": res["total_tokens"],
                "status": res["status"],
                "clean_execution": res["clean_execution"],
                "passed": res["passed"],
                "details": res["details"],
                "duration": res["duration"],
                "rerun_8192": True,
                "max_tokens": 8192,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  Result: passed={res['passed']}, finish_reason={res['finish_reason']}, tokens={res['completion_tokens']}, status={res['status']}", flush=True)
            time.sleep(5.0)

    print("\n=== COMPLETED 8192 RERUNS ===", flush=True)


if __name__ == "__main__":
    main()

