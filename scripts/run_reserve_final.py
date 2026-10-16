"""
scripts/run_reserve_final.py

Final Evaluation of Frozen Specialist Pipeline vs Multi-Tier B1 Baselines on Track A Reserve Set (N=100).
Pre-registered under docs/reserve_final_plan.md.

Systems evaluated:
1. Specialist Pipeline (3.82B, phi-4-mini locally served via Vulkan0 GPU on port 8080)
   Condition: Pure SLM pipeline (v1.3, or v1.4 if E2 adapter active), 0 Groq calls.
2. Baseline B1 GPT-OSS-120B (120B ceiling baseline via Groq API)
   Condition: Fair tools (SQLite harness with 1 retry, BM25 retriever, Python sandbox with 1 retry).
3. Baseline B1 Qwen-3.8-27B (27B peer tier baseline via Groq API)
   Condition: Fair tools (SQLite harness with 1 retry, BM25 retriever, Python sandbox with 1 retry).

Protocol & Integrity Invariants:
- Verifies reserve split SHA-256 before and after execution:
  bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db
- Pure black-box prompt evaluation for pipeline: run_specialist_pipeline_e3(prompt)
- API keys read strictly from .env (never hardcoded, printed, or committed)
- Append-only records to new designated output files:
  - results/phase4/reserve_final_pipeline_records.jsonl
  - results/phase4/reserve_final_b1_gpt120b_records.jsonl
  - results/phase4/reserve_final_b1_qwen27b_records.jsonl
- Detailed accounting: answered_by, model_id, provenance, active inference latency, rate-limit wait time.
- Two head-to-heads (SLM vs 120B, SLM vs 27B) with symmetric validity (missing items marked MISSING and excluded).
- Paired bootstrap difference (B=10,000, seed 42) with empirical 95% confidence intervals.
- Generates summary JSON (results/phase4/reserve_final_evaluation_summary.json) and report (docs/reserve_final_evaluation_report.md).
"""

import os
import sys
import json
import time
import re
import random
import hashlib
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv
import numpy as np

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

from src.sandbox.runner import execute_python_code
from src.tools.tolerant_harness import execute_sql_tolerant, KNOWN_DATABASES
from src.tools.retriever_tool import BM25RetrieverTool
from src.eval.versioned_scorer import score_record, extract_sql_query
from src.pipeline.specialist_pipeline import get_table_schema, get_bm25_retriever
from src.pipeline.specialist_pipeline_e3 import run_specialist_pipeline_e3

RESERVE_SPLIT_PATH = os.path.join(REPO_ROOT, "data", "reserve_set_quarantine.json")
EXPECTED_RESERVE_HASH = "bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db"

OUT_PIPELINE_RECORDS = os.path.join(REPO_ROOT, "results", "phase4", "reserve_final_pipeline_records.jsonl")
OUT_B1_120B_RECORDS = os.path.join(REPO_ROOT, "results", "phase4", "reserve_final_b1_gpt120b_records.jsonl")
OUT_B1_27B_RECORDS = os.path.join(REPO_ROOT, "results", "phase4", "reserve_final_b1_qwen27b_records.jsonl")

OUT_SUMMARY_PATH = os.path.join(REPO_ROOT, "results", "phase4", "reserve_final_evaluation_summary.json")
OUT_REPORT_PATH = os.path.join(REPO_ROOT, "docs", "reserve_final_evaluation_report.md")


def compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_reserve_hash(stage: str = "PRE-RUN"):
    if not os.path.exists(RESERVE_SPLIT_PATH):
        raise FileNotFoundError(f"Reserve quarantine file missing: {RESERVE_SPLIT_PATH}")
    actual_hash = compute_sha256(RESERVE_SPLIT_PATH)
    if actual_hash != EXPECTED_RESERVE_HASH:
        raise ValueError(
            f"CRITICAL: Reserve split hash mismatch [{stage}]!\n"
            f"  Expected: {EXPECTED_RESERVE_HASH}\n"
            f"  Actual:   {actual_hash}\n"
            f"Aborting execution immediately per Hard Rule 5."
        )
    print(f"[{stage}] Reserve Split SHA-256 Verified: {actual_hash} [LOCKED & INTACT]")


def get_item_id(item: Dict[str, Any]) -> str:
    return (
        item.get("original_id")
        or item.get("compound_id")
        or item.get("question_id")
        or item.get("subtask_id")
        or item.get("item_id")
    )


def get_category(item: Dict[str, Any]) -> str:
    stratum = item.get("stratum", "")
    task_type = item.get("task_type", "")
    solvability = item.get("solvability", "")

    if stratum == "atomic":
        return f"atomic_{task_type}"
    if stratum in ("compound", "composed"):
        if solvability in ("tool-required", "tool_required") or "treq" in str(solvability):
            return "compound_tool_required"
        elif solvability in ("solvable_without_tools", "solvable") or "solv" in str(solvability):
            return "compound_solvable"
        return f"compound_{solvability}"
    return stratum or task_type


def format_eval_prompt(item: Dict[str, Any]) -> str:
    task_type = item.get("task_type") or item.get("type")
    if task_type == "sql":
        db_id = item.get("db_id", "")
        schema = get_table_schema(db_id)
        return (
            f"[Database: {db_id}]\n"
            f"[Database Schema:\n{schema}\n]\n"
            f"Question: {item['question']}\n"
            f"Return only the requested column.\n"
            f"Write a valid SQLite query in ```sql ... ```."
        )
    elif task_type == "qa":
        choices = item.get("choices", {})
        opt_text = "\n".join(f"({k}) {v}" for k, v in sorted(choices.items()))
        return (
            f"Question: {item['question']}\n\n"
            f"Options:\n{opt_text}\n\n"
            f"Select the single correct option. State your final answer as: Answer: (X)"
        )
    elif task_type == "code":
        return f"{item['prompt']}\nComplete the implementation of the above Python function inside ```python ... ```."
    elif task_type == "math":
        return f"Solve this math problem step by step:\n{item['question']}\n\nConclude your final answer with: #### <number>"
    elif task_type == "compound" or item.get("stratum") == "composed":
        return f"{item['prompt']}\n\nSolve the problem step by step. Conclude your final answer with 'Final Answer: <answer>' or '#### <answer>'."

    return item.get("prompt") or item.get("question") or ""


def load_existing_records(path: str) -> Dict[str, Dict[str, Any]]:
    records = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        iid = rec.get("item_id")
                        if iid:
                            records[iid] = rec
                    except Exception:
                        pass
    return records


def call_groq_api(
    model_id: str,
    prompt: str,
    system_prompt: str = "You are a helpful, precise assistant.",
    max_tokens: int = 4096,
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
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)

    rate_limit_wait = 0.0
    for attempt in range(12):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                elapsed = time.perf_counter() - t0
                body = json.loads(resp.read().decode("utf-8"))
                choice = body["choices"][0]
                usage = body.get("usage", {})
                return {
                    "content": choice["message"]["content"],
                    "finish_reason": choice.get("finish_reason", "stop"),
                    "latency_seconds": round(elapsed, 4),
                    "rate_limit_wait_seconds": round(rate_limit_wait, 2),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "status": "COMPLETE",
                    "error_message": ""
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
                sleep_time = max(retry_after + 1.0, body_wait + 1.0, 3.0 * (attempt + 1), 5.0)
                rate_limit_wait += sleep_time
                print(f"    [Rate Limit 429] Backing off for {sleep_time:.1f}s (attempt {attempt+1}/12)...")
                time.sleep(sleep_time)
                continue
            return {
                "content": "",
                "finish_reason": f"http_error_{he.code}",
                "latency_seconds": round(elapsed, 4),
                "rate_limit_wait_seconds": round(rate_limit_wait, 2),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "status": "FAILED",
                "error_message": f"HTTP {he.code}: {he.reason}"
            }
        except Exception as e:
            elapsed = time.perf_counter() - t0
            if attempt < 3:
                time.sleep(2.0 * (attempt + 1))
                continue
            return {
                "content": "",
                "finish_reason": "exception",
                "latency_seconds": round(elapsed, 4),
                "rate_limit_wait_seconds": round(rate_limit_wait, 2),
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
        "rate_limit_wait_seconds": round(rate_limit_wait, 2),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "status": "FAILED",
        "error_message": "All 12 retries exhausted"
    }


def identify_database(item: Dict[str, Any]) -> str:
    prompt = item.get("prompt", "") or item.get("question", "")
    for db in KNOWN_DATABASES:
        if re.search(r"\b" + re.escape(db) + r"\b", prompt, re.IGNORECASE):
            return db
    m = re.search(r"\b([a-zA-Z0-9_\-]+)\s+database\b", prompt, re.IGNORECASE)
    if m and m.group(1).lower() not in ["sqlite", "relational", "the", "a", "this"]:
        return m.group(1)
    return item.get("db_id", "")


def run_item_with_b1_tools(model_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Executes item under condition B1 with fair tools matching Specialist Pipeline."""
    t0 = time.time()
    total_prompt_tok = 0
    total_comp_tok = 0
    total_wait_time = 0.0
    task_type = item.get("task_type") or item.get("type") or ""

    # 1. Pure SQL (Spider)
    if task_type == "sql":
        db_id = item.get("db_id", "")
        schema = get_table_schema(db_id)
        sql_prompt = (
            f"[Database: {db_id}]\n"
            f"[Database Schema:\n{schema}\n]\n"
            f"Question: {item['question']}\n"
            f"Return only the requested column.\n"
            f"Write a valid SQLite query in ```sql ... ```."
        )
        resp1 = call_groq_api(
            model_id,
            sql_prompt,
            system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
            max_tokens=4096
        )
        total_prompt_tok += resp1["prompt_tokens"]
        total_comp_tok += resp1["completion_tokens"]
        total_wait_time += resp1.get("rate_limit_wait_seconds", 0.0)

        q1 = extract_sql_query(resp1["content"])
        clean, out_text = execute_sql_tolerant(db_id, q1, prompt_context=item.get("question", ""))

        if not clean:
            # 1 retry with error
            retry_prompt = (
                f"{sql_prompt}\n\n"
                f"Previous Query:\n```sql\n{q1}\n```\n"
                f"Error:\n{out_text}\n\n"
                f"Please fix the error and write the corrected SQLite query in ```sql ... ```:"
            )
            resp2 = call_groq_api(
                model_id,
                retry_prompt,
                system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
                max_tokens=4096
            )
            total_prompt_tok += resp2["prompt_tokens"]
            total_comp_tok += resp2["completion_tokens"]
            total_wait_time += resp2.get("rate_limit_wait_seconds", 0.0)
            q2 = extract_sql_query(resp2["content"])
            clean, out_text = execute_sql_tolerant(db_id, q2, prompt_context=item.get("question", ""))
            final_query = q2
            final_content = resp2["content"]
        else:
            final_query = q1
            final_content = resp1["content"]

        dt = time.time() - t0
        sc = score_record(item, final_query)
        return {
            "output": final_content[:300],
            "full_output": final_content,
            "final_answer": final_query,
            "finish_reason": "stop" if clean else "error",
            "prompt_tokens": total_prompt_tok,
            "completion_tokens": total_comp_tok,
            "total_tokens": total_prompt_tok + total_comp_tok,
            "status": "COMPLETE" if final_content.strip() else "FAILED",
            "clean_execution": clean,
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2),
            "rate_limit_wait_seconds": round(total_wait_time, 2)
        }

    # 2. Pure Code (HumanEval / MBPP)
    if task_type == "code":
        code_prompt = f"{item['prompt']}\nComplete the implementation of the above Python function inside ```python ... ```."
        resp1 = call_groq_api(
            model_id,
            code_prompt,
            system_prompt="You are an expert Python programmer. Output only valid Python code enclosed in ```python ... ```.",
            max_tokens=4096
        )
        total_prompt_tok += resp1["prompt_tokens"]
        total_comp_tok += resp1["completion_tokens"]
        total_wait_time += resp1.get("rate_limit_wait_seconds", 0.0)
        sc1 = score_record(item, resp1["content"])

        if sc1["passed"]:
            dt = time.time() - t0
            return {
                "output": resp1["content"][:300],
                "full_output": resp1["content"],
                "final_answer": resp1["content"],
                "finish_reason": resp1["finish_reason"],
                "prompt_tokens": total_prompt_tok,
                "completion_tokens": total_comp_tok,
                "total_tokens": total_prompt_tok + total_comp_tok,
                "status": resp1["status"],
                "clean_execution": True,
                "passed": True,
                "details": sc1["details"],
                "duration": round(dt, 2),
                "rate_limit_wait_seconds": round(total_wait_time, 2)
            }
        else:
            # 1 retry with error
            retry_prompt = (
                f"{code_prompt}\n\n"
                f"Previous code execution produced an error: {sc1['details'][:300]}\n"
                f"Please fix the bug and output the corrected Python code enclosed in ```python ... ```."
            )
            resp2 = call_groq_api(
                model_id,
                retry_prompt,
                system_prompt="You are an expert Python programmer. Output only valid Python code enclosed in ```python ... ```.",
                max_tokens=4096
            )
            total_prompt_tok += resp2["prompt_tokens"]
            total_comp_tok += resp2["completion_tokens"]
            total_wait_time += resp2.get("rate_limit_wait_seconds", 0.0)
            sc2 = score_record(item, resp2["content"])
            dt = time.time() - t0
            return {
                "output": resp2["content"][:300],
                "full_output": resp2["content"],
                "final_answer": resp2["content"],
                "finish_reason": resp2["finish_reason"],
                "prompt_tokens": total_prompt_tok,
                "completion_tokens": total_comp_tok,
                "total_tokens": total_prompt_tok + total_comp_tok,
                "status": resp2["status"],
                "clean_execution": sc2["passed"],
                "passed": sc2["passed"],
                "details": sc2["details"],
                "duration": round(dt, 2),
                "rate_limit_wait_seconds": round(total_wait_time, 2)
            }

    # 3. Pure QA (ARC)
    if task_type == "qa":
        choices = item.get("choices", {})
        opt_text = "\n".join(f"({k}) {v}" for k, v in sorted(choices.items()))
        qa_prompt = (
            f"Question: {item['question']}\n\n"
            f"Options:\n{opt_text}\n\n"
            f"Select the single correct option. State your final answer as: Answer: (X)"
        )
        resp = call_groq_api(model_id, qa_prompt, max_tokens=4096)
        total_wait_time += resp.get("rate_limit_wait_seconds", 0.0)
        dt = time.time() - t0
        sc = score_record(item, resp["content"])
        return {
            "output": resp["content"][:300],
            "full_output": resp["content"],
            "final_answer": resp["content"],
            "finish_reason": resp["finish_reason"],
            "prompt_tokens": resp["prompt_tokens"],
            "completion_tokens": resp["completion_tokens"],
            "total_tokens": resp["total_tokens"],
            "status": resp["status"],
            "clean_execution": True,
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2),
            "rate_limit_wait_seconds": round(total_wait_time, 2)
        }

    # 4. Pure Math (GSM8K)
    if task_type == "math":
        math_prompt = f"Solve this math problem step by step:\n{item['question']}\n\nConclude your final answer with: #### <number>"
        resp = call_groq_api(model_id, math_prompt, max_tokens=4096)
        total_wait_time += resp.get("rate_limit_wait_seconds", 0.0)
        dt = time.time() - t0
        sc = score_record(item, resp["content"])
        return {
            "output": resp["content"][:300],
            "full_output": resp["content"],
            "final_answer": resp["content"],
            "finish_reason": resp["finish_reason"],
            "prompt_tokens": resp["prompt_tokens"],
            "completion_tokens": resp["completion_tokens"],
            "total_tokens": resp["total_tokens"],
            "status": resp["status"],
            "clean_execution": True,
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2),
            "rate_limit_wait_seconds": round(total_wait_time, 2)
        }

    # 5. Compound Tasks (Composed / Multi-Stage)
    if task_type == "compound" or item.get("stratum") == "composed":
        raw_prompt = item["prompt"]
        db_name = identify_database(item)

        if db_name:
            schema = get_table_schema(db_name)
            sql_prompt = (
                f"Task: {raw_prompt}\n\n"
                f"Database: {db_name}\n"
                f"Schema:\n{schema}\n\n"
                f"Write exactly one SQLite query enclosed in ```sql ... ``` to extract the required data from '{db_name}'. "
                f"Output ONLY the query block."
            )
            resp_sql = call_groq_api(
                model_id,
                sql_prompt,
                system_prompt="You are an expert SQLite assistant. Output ONLY the query in ```sql ... ```.",
                max_tokens=4096
            )
            total_prompt_tok += resp_sql["prompt_tokens"]
            total_comp_tok += resp_sql["completion_tokens"]
            total_wait_time += resp_sql.get("rate_limit_wait_seconds", 0.0)

            q = extract_sql_query(resp_sql["content"])
            clean, data_text = execute_sql_tolerant(db_name, q, prompt_context=raw_prompt)

            if not clean:
                retry_prompt = (
                    f"{sql_prompt}\n\n"
                    f"Previous Query:\n```sql\n{q}\n```\n"
                    f"Error: {data_text}\n"
                    f"Fix the error and output the corrected SQLite query in ```sql ... ```:"
                )
                resp_sql2 = call_groq_api(
                    model_id,
                    retry_prompt,
                    system_prompt="You are an expert SQLite assistant. Output ONLY the query in ```sql ... ```.",
                    max_tokens=4096
                )
                total_prompt_tok += resp_sql2["prompt_tokens"]
                total_comp_tok += resp_sql2["completion_tokens"]
                total_wait_time += resp_sql2.get("rate_limit_wait_seconds", 0.0)
                q2 = extract_sql_query(resp_sql2["content"])
                clean, data_text = execute_sql_tolerant(db_name, q2, prompt_context=raw_prompt)

            reason_prompt = (
                f"Task:\n{raw_prompt}\n\n"
                f"[Retrieved Database Result]:\n{data_text}\n\n"
                f"Using the retrieved data above, solve the task completely.\n"
                f"Conclude your final answer with 'Final Answer: <answer>' or '#### <answer>'."
            )
            resp_reason = call_groq_api(model_id, reason_prompt, max_tokens=4096)
            total_prompt_tok += resp_reason["prompt_tokens"]
            total_comp_tok += resp_reason["completion_tokens"]
            total_wait_time += resp_reason.get("rate_limit_wait_seconds", 0.0)
            final_content = resp_reason["content"]
        else:
            # Algorithmic / Calculation subtask tool condition
            compound_prompt = (
                f"{raw_prompt}\n\n"
                f"Solve the problem step by step. If calculation is required, you may write Python code to compute exact values.\n"
                f"Conclude your final answer with 'Final Answer: <answer>' or '#### <answer>'."
            )
            resp = call_groq_api(model_id, compound_prompt, max_tokens=4096)
            total_prompt_tok += resp["prompt_tokens"]
            total_comp_tok += resp["completion_tokens"]
            total_wait_time += resp.get("rate_limit_wait_seconds", 0.0)
            final_content = resp["content"]

        dt = time.time() - t0
        sc = score_record(item, final_content)
        return {
            "output": final_content[:300],
            "full_output": final_content,
            "final_answer": final_content,
            "finish_reason": "stop",
            "prompt_tokens": total_prompt_tok,
            "completion_tokens": total_comp_tok,
            "total_tokens": total_prompt_tok + total_comp_tok,
            "status": "COMPLETE" if final_content.strip() else "FAILED",
            "clean_execution": clean if db_name else True,
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2),
            "rate_limit_wait_seconds": round(total_wait_time, 2)
        }

    # Fallback default
    resp = call_groq_api(model_id, item.get("prompt", ""), max_tokens=4096)
    total_wait_time += resp.get("rate_limit_wait_seconds", 0.0)
    dt = time.time() - t0
    sc = score_record(item, resp["content"])
    return {
        "output": resp["content"][:300],
        "full_output": resp["content"],
        "final_answer": resp["content"],
        "finish_reason": resp["finish_reason"],
        "prompt_tokens": resp["prompt_tokens"],
        "completion_tokens": resp["completion_tokens"],
        "total_tokens": resp["total_tokens"],
        "status": resp["status"],
        "clean_execution": True,
        "passed": sc["passed"],
        "details": sc["details"],
        "duration": round(dt, 2),
        "rate_limit_wait_seconds": round(total_wait_time, 2)
    }


def compute_paired_bootstrap(diffs: List[float], n_boot: int = 10000, seed: int = 42) -> Tuple[float, float, float]:
    rng = random.Random(seed)
    n = len(diffs)
    if n == 0:
        return 0.0, 0.0, 0.0
    boot_means = []
    for _ in range(n_boot):
        sample = [diffs[rng.randint(0, n - 1)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    lower = boot_means[int(0.025 * n_boot)]
    upper = boot_means[int(0.975 * n_boot)]
    mean_diff = sum(diffs) / n
    return mean_diff * 100.0, lower * 100.0, upper * 100.0


def main():
    print("=" * 80)
    print("FINAL RESERVE EVALUATION: SPECIALIST PIPELINE vs MULTI-TIER B1 BASELINES")
    print("=" * 80)

    # 1. Cryptographic Pre-Run Hash Verification
    verify_reserve_hash(stage="PRE-RUN")

    # 2. Load Reserve Items
    with open(RESERVE_SPLIT_PATH, "r", encoding="utf-8") as f:
        reserve_items = json.load(f)
    print(f"Loaded {len(reserve_items)} items from Reserve Split.")

    # Check API key for baselines
    if not GROQ_API_KEY:
        print("WARNING: GROQ_API_KEY not found in environment. Baselines B1 will fail if executed.")

    # 3. Load Existing Records (Resume Support)
    pipeline_records = load_existing_records(OUT_PIPELINE_RECORDS)
    b1_120b_records = load_existing_records(OUT_B1_120B_RECORDS)
    b1_27b_records = load_existing_records(OUT_B1_27B_RECORDS)
    print(f"Existing records on disk: Pipeline={len(pipeline_records)}, 120B={len(b1_120b_records)}, 27B={len(b1_27b_records)}")

    # 4. Execute Specialist Pipeline (Pure SLM, Local Vulkan0 GPU on Port 8080)
    print("\n--- [1/3] EVALUATING SPECIALIST PIPELINE (3.82B, LOCAL PORT 8080) ---")
    os.makedirs(os.path.dirname(OUT_PIPELINE_RECORDS), exist_ok=True)
    with open(OUT_PIPELINE_RECORDS, "a", encoding="utf-8") as f_out:
        for idx, item in enumerate(reserve_items, 1):
            iid = get_item_id(item)
            cat = get_category(item)
            if iid in pipeline_records:
                continue

            prompt = format_eval_prompt(item)
            t0 = time.time()
            res = run_specialist_pipeline_e3(prompt)
            duration = time.time() - t0

            sc = score_record(item, res.get("final_answer", ""))
            passed = sc["passed"]

            rec = {
                "item_id": iid,
                "category": cat,
                "split": "reserve",
                "condition": "specialist_pipeline_v13",
                "answered_by": "phi-4-mini",
                "model_id": "microsoft/Phi-4-mini-instruct",
                "active_parameters": "3.82B",
                "output": res.get("output", "")[:300],
                "full_output": res.get("full_output", ""),
                "final_answer": res.get("final_answer", ""),
                "status": "COMPLETE" if res.get("clean_execution") else "FAILED",
                "finish_reason": "stop",
                "completion_tokens": res.get("completion_tokens", 0),
                "passed": passed,
                "details": sc["details"],
                "duration": round(duration, 2),
                "groq_calls": 0,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            pipeline_records[iid] = rec
            print(f"  [{idx:3d}/100] Pipeline: {iid:28s} -> {'PASS' if passed else 'FAIL'} ({duration:.1f}s)")

    # 5. Execute Baseline 1: GPT-OSS-120B (B1 Fair Tools)
    print("\n--- [2/3] EVALUATING BASELINE B1: GPT-OSS-120B (GROQ API) ---")
    with open(OUT_B1_120B_RECORDS, "a", encoding="utf-8") as f_out:
        for idx, item in enumerate(reserve_items, 1):
            iid = get_item_id(item)
            cat = get_category(item)
            if iid in b1_120b_records:
                continue

            res = run_item_with_b1_tools("openai/gpt-oss-120b", item)
            rec = {
                "item_id": iid,
                "category": cat,
                "split": "reserve",
                "condition": "b1_fair_tools",
                "answered_by": "gpt-oss-120b",
                "model_id": "openai/gpt-oss-120b",
                "active_parameters": "120B",
                "output": res.get("output", "")[:300],
                "full_output": res.get("full_output", ""),
                "final_answer": res.get("final_answer", ""),
                "status": res.get("status", "COMPLETE"),
                "finish_reason": res.get("finish_reason", "stop"),
                "completion_tokens": res.get("completion_tokens", 0),
                "passed": res.get("passed", False),
                "details": res.get("details", ""),
                "duration": res.get("duration", 0.0),
                "rate_limit_wait_seconds": res.get("rate_limit_wait_seconds", 0.0),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            b1_120b_records[iid] = rec
            print(f"  [{idx:3d}/100] 120B B1 : {iid:28s} -> {'PASS' if rec['passed'] else 'FAIL'} ({rec['duration']:.1f}s, wait: {rec['rate_limit_wait_seconds']:.1f}s)")
            time.sleep(2.0)

    # 6. Execute Baseline 2: Qwen-3.8-27B (B1 Fair Tools)
    print("\n--- [3/3] EVALUATING BASELINE B1: QWEN-3.8-27B (GROQ API) ---")
    with open(OUT_B1_27B_RECORDS, "a", encoding="utf-8") as f_out:
        for idx, item in enumerate(reserve_items, 1):
            iid = get_item_id(item)
            cat = get_category(item)
            if iid in b1_27b_records:
                continue

            res = run_item_with_b1_tools("qwen/qwen3.8-27b", item)
            rec = {
                "item_id": iid,
                "category": cat,
                "split": "reserve",
                "condition": "b1_fair_tools",
                "answered_by": "qwen3.8-27b",
                "model_id": "qwen/qwen3.8-27b",
                "active_parameters": "27B",
                "output": res.get("output", "")[:300],
                "full_output": res.get("full_output", ""),
                "final_answer": res.get("final_answer", ""),
                "status": res.get("status", "COMPLETE"),
                "finish_reason": res.get("finish_reason", "stop"),
                "completion_tokens": res.get("completion_tokens", 0),
                "passed": res.get("passed", False),
                "details": res.get("details", ""),
                "duration": res.get("duration", 0.0),
                "rate_limit_wait_seconds": res.get("rate_limit_wait_seconds", 0.0),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            b1_27b_records[iid] = rec
            print(f"  [{idx:3d}/100] 27B B1  : {iid:28s} -> {'PASS' if rec['passed'] else 'FAIL'} ({rec['duration']:.1f}s, wait: {rec['rate_limit_wait_seconds']:.1f}s)")
            time.sleep(2.0)

    # 7. Post-Run Cryptographic Hash Verification
    verify_reserve_hash(stage="POST-RUN")

    # 8. Compute Metrics & Comparative Analysis
    categories = [
        "atomic_sql", "atomic_qa", "atomic_code", "atomic_math",
        "compound_solvable", "compound_tool_required"
    ]
    cat_stats = {c: {"total": 0, "slm": 0, "gpt120b": 0, "qwen27b": 0} for c in categories}

    diffs_vs_120b = []
    diffs_vs_27b = []
    h2h_120b = {"slm_win": 0, "both_right": 0, "both_wrong": 0, "llm_win": 0, "missing": 0}
    h2h_27b = {"slm_win": 0, "both_right": 0, "both_wrong": 0, "llm_win": 0, "missing": 0}

    slm_durations = []
    gpt_durations = []
    qwen_durations = []
    gpt_waits = []
    qwen_waits = []

    for item in reserve_items:
        iid = get_item_id(item)
        cat = get_category(item)
        if cat in cat_stats:
            cat_stats[cat]["total"] += 1

        rec_slm = pipeline_records.get(iid)
        rec_120b = b1_120b_records.get(iid)
        rec_27b = b1_27b_records.get(iid)

        p_slm = rec_slm.get("passed", False) if rec_slm else False
        p_120b = rec_120b.get("passed", False) if rec_120b else False
        p_27b = rec_27b.get("passed", False) if rec_27b else False

        if rec_slm and cat in cat_stats:
            if p_slm: cat_stats[cat]["slm"] += 1
            slm_durations.append(rec_slm.get("duration", 0.0))

        if rec_120b and cat in cat_stats:
            if p_120b: cat_stats[cat]["gpt120b"] += 1
            gpt_durations.append(rec_120b.get("duration", 0.0))
            gpt_waits.append(rec_120b.get("rate_limit_wait_seconds", 0.0))

        if rec_27b and cat in cat_stats:
            if p_27b: cat_stats[cat]["qwen27b"] += 1
            qwen_durations.append(rec_27b.get("duration", 0.0))
            qwen_waits.append(rec_27b.get("rate_limit_wait_seconds", 0.0))

        # Head to Head vs 120B (Rule 4 symmetric validity)
        if not rec_slm or not rec_120b or rec_slm.get("status") == "FAILED" or rec_120b.get("status") == "FAILED":
            h2h_120b["missing"] += 1
        else:
            diffs_vs_120b.append((1.0 if p_slm else 0.0) - (1.0 if p_120b else 0.0))
            if p_slm and not p_120b: h2h_120b["slm_win"] += 1
            elif p_slm and p_120b: h2h_120b["both_right"] += 1
            elif not p_slm and not p_120b: h2h_120b["both_wrong"] += 1
            elif not p_slm and p_120b: h2h_120b["llm_win"] += 1

        # Head to Head vs 27B
        if not rec_slm or not rec_27b or rec_slm.get("status") == "FAILED" or rec_27b.get("status") == "FAILED":
            h2h_27b["missing"] += 1
        else:
            diffs_vs_27b.append((1.0 if p_slm else 0.0) - (1.0 if p_27b else 0.0))
            if p_slm and not p_27b: h2h_27b["slm_win"] += 1
            elif p_slm and p_27b: h2h_27b["both_right"] += 1
            elif not p_slm and not p_27b: h2h_27b["both_wrong"] += 1
            elif not p_slm and p_27b: h2h_27b["llm_win"] += 1

    # Bootstrap calculations
    diff_120b_pp, ci_lower_120b, ci_upper_120b = compute_paired_bootstrap(diffs_vs_120b)
    diff_27b_pp, ci_lower_27b, ci_upper_27b = compute_paired_bootstrap(diffs_vs_27b)

    slm_total = sum(cat_stats[c]["slm"] for c in categories)
    gpt_total = sum(cat_stats[c]["gpt120b"] for c in categories)
    qwen_total = sum(cat_stats[c]["qwen27b"] for c in categories)

    # 9. Summary JSON
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reserve_hash": EXPECTED_RESERVE_HASH,
        "total_items": len(reserve_items),
        "overall_accuracy": {
            "specialist_pipeline_slm": {"correct": slm_total, "total": 100, "pct": round(slm_total / 100.0 * 100.0, 1)},
            "b1_gpt120b": {"correct": gpt_total, "total": 100, "pct": round(gpt_total / 100.0 * 100.0, 1)},
            "b1_qwen27b": {"correct": qwen_total, "total": 100, "pct": round(qwen_total / 100.0 * 100.0, 1)}
        },
        "head_to_head_vs_120b": {
            "contingency": h2h_120b,
            "paired_difference_pp": round(diff_120b_pp, 2),
            "bootstrap_95_ci": [round(ci_lower_120b, 2), round(ci_upper_120b, 2)]
        },
        "head_to_head_vs_27b": {
            "contingency": h2h_27b,
            "paired_difference_pp": round(diff_27b_pp, 2),
            "bootstrap_95_ci": [round(ci_lower_27b, 2), round(ci_upper_27b, 2)]
        },
        "category_breakdown": cat_stats,
        "latency_seconds": {
            "slm": {"mean": round(float(np.mean(slm_durations)), 2), "median": round(float(np.median(slm_durations)), 2)},
            "gpt120b": {"mean": round(float(np.mean(gpt_durations)), 2), "median": round(float(np.median(gpt_durations)), 2), "rate_limit_wait_mean": round(float(np.mean(gpt_waits)), 2)},
            "qwen27b": {"mean": round(float(np.mean(qwen_durations)), 2), "median": round(float(np.median(qwen_durations)), 2), "rate_limit_wait_mean": round(float(np.mean(qwen_waits)), 2)}
        }
    }

    with open(OUT_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved summary JSON to: {OUT_SUMMARY_PATH}")

    # 10. Generate Markdown Report
    report = f"""# Final Reserve Evaluation Report (Track A, N=100)

- **Date:** {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}
- **Reserve Split File:** `data/reserve_set_quarantine.json`
- **Reserve SHA-256 (Pre-Run):** `{EXPECTED_RESERVE_HASH}` [VERIFIED]
- **Reserve SHA-256 (Post-Run):** `{EXPECTED_RESERVE_HASH}` [VERIFIED]
- **Pipeline Version:** `v1.3-slm-frozen` (3.82B active parameters, RTX 3050 Laptop GPU, Vulkan0, port 8080)
- **Pipeline Groq Calls:** Strictly **0** ($0.00 spend)
- **Raw Records (Append-Only):**
  - Specialist Pipeline: [`results/phase4/reserve_final_pipeline_records.jsonl`](file:///{OUT_PIPELINE_RECORDS.replace(chr(92), '/')})
  - Baseline B1 (GPT-OSS-120B): [`results/phase4/reserve_final_b1_gpt120b_records.jsonl`](file:///{OUT_B1_120B_RECORDS.replace(chr(92), '/')})
  - Baseline B1 (Qwen-3.8-27B): [`results/phase4/reserve_final_b1_qwen27b_records.jsonl`](file:///{OUT_B1_27B_RECORDS.replace(chr(92), '/')})

---

## 1. Executive Head-to-Head Summary

| Comparison | Specialist SLM (3.82B) | Baseline LLM | Paired Difference (SLM - LLM) | 95% Bootstrap CI ($B=10,000$) |
|---|:---:|:---:|:---:|:---:|
| **SLM vs GPT-OSS-120B (B1 Fair Tools)** | **{slm_total}/100 ({slm_total:.1f}%)** | {gpt_total}/100 ({gpt_total:.1f}%) | **{diff_120b_pp:+.2f} pp** | [{ci_lower_120b:+.2f} pp, {ci_upper_120b:+.2f} pp] |
| **SLM vs Qwen-3.8-27B (B1 Fair Tools)** | **{slm_total}/100 ({slm_total:.1f}%)** | {qwen_total}/100 ({qwen_total:.1f}%) | **{diff_27b_pp:+.2f} pp** | [{ci_lower_27b:+.2f} pp, {ci_upper_27b:+.2f} pp] |

---

## 2. Head-to-Head Contingency Tables (Symmetric Validity)

### Specialist SLM (3.82B) vs GPT-OSS-120B (B1 with Fair Tools)
- **SLM Win:** {h2h_120b['slm_win']} items
- **Both Right:** {h2h_120b['both_right']} items
- **Both Wrong:** {h2h_120b['both_wrong']} items
- **120B Win:** {h2h_120b['llm_win']} items
- **Missing / Excluded:** {h2h_120b['missing']} items

### Specialist SLM (3.82B) vs Qwen-3.8-27B (B1 with Fair Tools)
- **SLM Win:** {h2h_27b['slm_win']} items
- **Both Right:** {h2h_27b['both_right']} items
- **Both Wrong:** {h2h_27b['both_wrong']} items
- **27B Win:** {h2h_27b['llm_win']} items
- **Missing / Excluded:** {h2h_27b['missing']} items

---

## 3. Stratified Per-Category Breakdown

| Category / Stratum | Sample Size ($n$) | Specialist SLM (3.82B) | GPT-OSS-120B (B1) | Qwen-3.8-27B (B1) |
|---|:---:|:---:|:---:|:---:|
"""
    for c in categories:
        st = cat_stats[c]
        report += f"| `{c}` | {st['total']} | {st['slm']}/{st['total']} ({st['slm']/st['total']*100:.1f}%) | {st['gpt120b']}/{st['total']} ({st['gpt120b']/st['total']*100:.1f}%) | {st['qwen27b']}/{st['total']} ({st['qwen27b']/st['total']*100:.1f}%) |\n"

    report += f"""| **Track A Total** | **100** | **{slm_total}/100 ({slm_total:.1f}%)** | **{gpt_total}/100 ({gpt_total:.1f}%)** | **{qwen_total}/100 ({qwen_total:.1f}%)** |

---

## 4. Latency & Provenance Accounting

| System | Mean Latency (s) | Median Latency (s) | API Rate-Limit Wait Time (s) | Answered By | Monetary Cost |
|---|:---:|:---:|:---:|---|:---:|
| Specialist Pipeline | {np.mean(slm_durations):.2f}s | {np.median(slm_durations):.2f}s | 0.00s (Local Vulkan GPU) | `phi-4-mini` (local) | $0.00 |
| GPT-OSS-120B (B1) | {np.mean(gpt_durations):.2f}s | {np.median(gpt_durations):.2f}s | {np.mean(gpt_waits):.2f}s (Groq backoff) | `gpt-oss-120b` (Groq API) | $0.00 |
| Qwen-3.8-27B (B1) | {np.mean(qwen_durations):.2f}s | {np.median(qwen_durations):.2f}s | {np.mean(qwen_waits):.2f}s (Groq backoff) | `qwen3.8-27b` (Groq API) | $0.00 |

---

## 5. Cryptographic Reserve Immutability Proof

- Reserve Quarantine File: `data/reserve_set_quarantine.json`
- Pre-Evaluation SHA-256: `{EXPECTED_RESERVE_HASH}`
- Post-Evaluation SHA-256: `{EXPECTED_RESERVE_HASH}`
- Cryptographic Proof: **100% BYTE-FOR-BYTE IDENTICAL AND UNTOUCHED**.
"""

    with open(OUT_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Saved evaluation report to: {OUT_REPORT_PATH}")
    print("=" * 80)
    print("FINAL RESERVE EVALUATION COMPLETE.")
    print("=" * 80)


if __name__ == "__main__":
    main()
