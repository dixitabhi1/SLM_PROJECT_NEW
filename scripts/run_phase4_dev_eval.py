"""
Phase 4 Dev Evaluation Script: C0 & B0 Baseline Benchmark (2,048 Token Budget).

Evaluates on Dev Split (100 Track A items + 50 Track B items = 150 items):
- C0: Base Phi-4-mini (Local llama-server on Vulkan GPU, port 8080, no tools, greedy temp=0.0, max_tokens=2048)
- B0 Tier 1: qwen/qwen3.8-27b (Groq API, no tools, greedy temp=0.0, max_tokens=2048)
- B0 Tier 3 Ceiling: openai/gpt-oss-120b (Groq API, no tools, greedy temp=0.0, max_tokens=2048)

Enforces:
- Hard Rule 1: No fabricated numbers (computed from append-only raw JSONL files).
- Hard Rule 2: Raw results are strictly append-only with resume; files never shrink or disappear.
- Hard Rule 3: Fail loudly (finish_reason != 'stop' marked FAILED and excluded from valid).
- Hard Rule 4: Symmetric validity (both ways reported: valid-only and total).
- Hard Rule 6: No benchmark leakage in prompts.
- Answer budget: strictly 2,048 tokens across all models and conditions.
- Difficulty Gates evaluated strictly on TOTAL accuracy (truncated items count as failures):
    Gate 1: C0 Compound Total Acc <= 60.0%
    Gate 2: Baseline B0 Compound Solvable-without-tools Total Acc <= 90.0%
- 95% Bootstrap Confidence Intervals (B=10,000 resamples).
- Rate-limit tracking and daily quota reporting (no API key details printed).
"""

import os
import sys
import json
import time
import re
import sqlite3
import random
import urllib.request
import urllib.error
import concurrent.futures
from typing import Dict, Any, List, Tuple, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.eval.subtask_checkers import evaluate_subtask
from src.eval.fact_checklist_scorer import score_fact_checklist
from src.audit.audit_rules import audit_results_journal

TRACK_A_DEV_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
TRACK_B_DEV_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_dev_split.json")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
os.makedirs(RESULTS_DIR, exist_ok=True)


def format_prompt(item: Dict[str, Any]) -> str:
    """Constructs prompt for evaluation without leaking any answers or keywords."""
    task_type = item.get("task_type") or item.get("type")

    if task_type == "sql":
        db_id = item.get("db_id")
        db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_id, f"{db_id}.sqlite")
        schema_text = ""
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL;")
                tables = [r[0] for r in cur.fetchall()]
                conn.close()
                schema_text = "\n".join(" ".join(t.split()) for t in tables)
            except Exception:
                schema_text = ""
        question = item.get("question")
        return (
            f"[Database: {db_id}]\n"
            f"[Database Schema:\n{schema_text}\n]\n"
            f"Question: {question}\n"
            f"Write a valid SQLite SQL query to answer the question. Return ONLY the requested column(s). Do not select any extra columns. Enclose your SQL query in ```sql ... ```."
        )

    elif task_type == "qa":
        question = item.get("question")
        choices = item.get("choices", {})
        options_text = "\n".join(f"({k}) {v}" for k, v in sorted(choices.items()))
        return (
            f"Question: {question}\n"
            f"Options:\n{options_text}\n"
            f"Select the single correct option. State your final answer as: Answer: (X)"
        )

    elif task_type == "code":
        prompt = item.get("prompt")
        return f"{prompt}\nComplete the implementation of the above Python function. Provide only valid Python code enclosed in ```python ... ```."

    elif task_type == "math":
        question = item.get("question")
        return f"Solve this math problem step by step:\n{question}\nConclude your final answer with: #### <number>"

    elif task_type == "composed":
        prompt = item.get("prompt")
        return f"{prompt}\nSolve the problem step by step. Conclude your final answer with: #### <final integer answer>"

    elif "checklist" in item:
        # Track B item
        prompt = item.get("prompt")
        expected_format = item.get("expected_answer_format", "key: value structured pairs (max 75 words)")
        word_cap = item.get("word_cap", 75)
        return (
            f"{prompt}\n"
            f"Format requirements: {expected_format}\n"
            f"Length limit: strictly at most {word_cap} words."
        )

    return item.get("prompt") or item.get("question") or ""


def call_llama_server(prompt: str, port: int = 8080, max_tokens: int = 2048) -> Dict[str, Any]:
    """Queries local llama-server on port 8080 with 2,048 token budget."""
    url = f"http://127.0.0.1:{port}/v1/chat/completions"
    payload = {
        "model": "phi4-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": 42
    }
    t0 = time.perf_counter()
    data = {}
    error_msg = None
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        error_msg = str(e)
    elapsed = time.perf_counter() - t0

    choices = data.get("choices", [{}])
    choice = choices[0] if choices else {}
    content = choice.get("message", {}).get("content", "").strip()
    finish_reason = choice.get("finish_reason", "unknown")
    usage = data.get("usage", {})

    status = "COMPLETE" if finish_reason == "stop" and content else "FAILED"
    if error_msg:
        status = "FAILED"
        finish_reason = "error"

    return {
        "content": content,
        "finish_reason": finish_reason,
        "latency_seconds": round(elapsed, 4),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "status": status,
        "error_message": error_msg
    }


def call_groq_api(
    model_id: str,
    prompt: str,
    api_key: str,
    max_tokens: int = 2048,
    seed: int = 42
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Queries Groq API with 2,048 token budget and adaptive retry-after backoff."""
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

    for attempt in range(8):
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
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
                sleep_time = max(retry_after + 1.0, body_wait + 1.0, 3.0 * (attempt + 1), 6.0)
                print(f"[Rate Limit 429] Backing off for {sleep_time:.1f}s (attempt {attempt+1}/8)...")
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
        "error_message": "Exceeded 8 retries on rate limit"
    }, rate_headers


def score_item(item: Dict[str, Any], output_text: str) -> Dict[str, Any]:
    """Scores an item using the objective checkers."""
    if "checklist" in item:
        # Track B
        res = score_fact_checklist(output_text, item["checklist"], max_word_cap=item.get("word_cap", 75))
        return {
            "passed": res["binary_pass"],
            "recall": res["recall"],
            "checker": "fact_checklist_scorer",
            "details": f"Recall: {res['recall']:.2f}, Violations: {len(res.get('negative_violations', []))}"
        }
    else:
        # Track A
        passed, checker_name, details = evaluate_subtask(item, output_text)
        return {
            "passed": passed,
            "recall": 1.0 if passed else 0.0,
            "checker": checker_name,
            "details": details
        }


def bootstrap_ci(scores: List[float], n_boot: int = 10000, seed: int = 42) -> Tuple[float, float]:
    """Computes non-parametric 95% bootstrap confidence interval [2.5%, 97.5%]."""
    if not scores:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(scores)
    means = []
    for _ in range(n_boot):
        sample = [scores[rng.randint(0, n - 1)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lower = round(means[int(0.025 * n_boot)] * 100, 2)
    upper = round(means[int(0.975 * n_boot)] * 100, 2)
    return (lower, upper)


def compute_stratum_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes all required stratum metrics with two accuracy figures:
    - Valid-only (truncated & failed excluded)
    - Total accuracy (truncated & failed counted as failures)
    Takes latest record per item_id if retried rows exist.
    """
    # Deduplicate by item_id taking latest entry
    latest_by_id = {}
    for r in records:
        latest_by_id[r["item_id"]] = r
    dedup_records = list(latest_by_id.values())

    strata_definitions = {
        "all_dev": lambda r: True,
        "track_a_all": lambda r: r.get("track") == "A",
        "atomic_all": lambda r: r.get("stratum") == "atomic",
        "atomic_math": lambda r: r.get("stratum") == "atomic" and r.get("task_type") == "math",
        "atomic_code": lambda r: r.get("stratum") == "atomic" and r.get("task_type") == "code",
        "atomic_sql": lambda r: r.get("stratum") == "atomic" and r.get("task_type") == "sql",
        "atomic_qa": lambda r: r.get("stratum") == "atomic" and r.get("task_type") == "qa",
        "compound_all": lambda r: r.get("stratum") == "composed",
        "compound_solvable_without_tools": lambda r: r.get("stratum") == "composed" and r.get("solvability") == "solvable_without_tools",
        "compound_tool_required": lambda r: r.get("stratum") == "composed" and r.get("solvability") == "tool-required",
        "compound_2_stage": lambda r: r.get("stratum") == "composed" and r.get("num_stages") == 2,
        "compound_3_stage": lambda r: r.get("stratum") == "composed" and r.get("num_stages") == 3,
        "track_b_all": lambda r: r.get("track") == "B",
    }

    results = {}
    for stratum_name, filter_fn in strata_definitions.items():
        subset = [r for r in dedup_records if filter_fn(r)]
        n_total = len(subset)
        if n_total == 0:
            continue

        valid_subset = [r for r in subset if r["status"] == "COMPLETE" and not r["truncated"]]
        n_valid = len(valid_subset)
        n_failed = len([r for r in subset if r["status"] == "FAILED"])
        n_truncated = len([r for r in subset if r["truncated"]])

        # 1. Valid only (truncated & failed excluded)
        valid_scores = [1.0 if r["passed"] else 0.0 for r in valid_subset]
        acc_valid = round((sum(valid_scores) / n_valid * 100), 2) if n_valid > 0 else 0.0
        ci_valid = bootstrap_ci(valid_scores) if n_valid > 0 else (0.0, 0.0)

        # 2. Total (truncated & failed counted as failures)
        total_scores = [1.0 if (r["status"] == "COMPLETE" and not r["truncated"] and r["passed"]) else 0.0 for r in subset]
        acc_total = round((sum(total_scores) / n_total * 100), 2)
        ci_total = bootstrap_ci(total_scores)

        results[stratum_name] = {
            "n_total": n_total,
            "n_valid": n_valid,
            "n_failed": n_failed,
            "n_truncated": n_truncated,
            "acc_valid": acc_valid,
            "ci_valid_95": ci_valid,
            "acc_total": acc_total,
            "ci_total_95": ci_total,
            "passed_count": sum(1 for s in total_scores if s == 1.0)
        }

    return results


def run_c0_evaluation_2048(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Runs C0 (local base Phi-4-mini on llama-server) with 2,048 token budget (append-only resume)."""
    out_path = os.path.join(RESULTS_DIR, "c0_phi4_mini_dev_records.jsonl")

    # Read existing records to check for items already evaluated at max_tokens=2048
    existing_records = []
    completed_ids = set()
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        rec = json.loads(line)
                        existing_records.append(rec)
                        if rec.get("max_tokens_budget") == 2048 and (rec.get("status") == "COMPLETE" or rec.get("truncated")):
                            completed_ids.add(rec["item_id"])
                    except Exception:
                        pass

    items_to_run = [it for it in items if (it.get("subtask_id") or it.get("original_id") or it.get("question_id")) not in completed_ids]

    print(f"\n==========================================")
    print(f"C0 EVALUATION (Phi-4-mini, Budget=2048 tokens)")
    print(f"Total: {len(items)}, Already completed at 2048: {len(completed_ids)}, Remaining: {len(items_to_run)}")
    print(f"==========================================")

    if not items_to_run:
        print("All items already evaluated at 2048 tokens.")
        return existing_records

    # Append new records
    f_out = open(out_path, "a", encoding="utf-8")

    def process_item(item):
        prompt = format_prompt(item)
        resp = call_llama_server(prompt, port=8080, max_tokens=2048)
        truncated = (resp["finish_reason"] == "length")

        if resp["status"] == "COMPLETE" and not truncated:
            score = score_item(item, resp["content"])
        else:
            score = {"passed": False, "recall": 0.0, "checker": "none", "details": f"Status: {resp['status']}, Finish: {resp['finish_reason']}"}

        item_id = item.get("subtask_id") or item.get("original_id") or item.get("question_id")
        stratum = item.get("stratum", "track_b" if "checklist" in item else "unknown")
        track = "B" if "checklist" in item else "A"
        solvability = item.get("solvability")
        num_stages = len(item.get("component_parts", [])) if item.get("component_parts") else None

        rec = {
            "item_id": item_id,
            "track": track,
            "task_type": item.get("task_type", "track_b_qa" if "checklist" in item else "unknown"),
            "stratum": stratum,
            "solvability": solvability,
            "num_stages": num_stages,
            "model_id": "microsoft/Phi-4-mini-instruct",
            "condition": "C0",
            "max_tokens_budget": 2048,
            "prompt": prompt,
            "output": resp["content"],
            "finish_reason": resp["finish_reason"],
            "truncated": truncated,
            "latency_seconds": resp["latency_seconds"],
            "prompt_tokens": resp["prompt_tokens"],
            "completion_tokens": resp["completion_tokens"],
            "status": resp["status"],
            "passed": score["passed"],
            "recall": score["recall"],
            "checker": score["checker"],
            "checker_details": score["details"]
        }
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_item = {executor.submit(process_item, it): it for it in items_to_run}
        done_count = 0
        for future in concurrent.futures.as_completed(future_to_item):
            rec = future.result()
            existing_records.append(rec)
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            done_count += 1
            if done_count % 20 == 0 or done_count == len(items_to_run):
                trunc_count = sum(1 for r in existing_records if r.get("truncated"))
                pass_count = sum(1 for r in existing_records if r.get("passed"))
                print(f"[C0 Progress] {done_count}/{len(items_to_run)} completed. Passes: {pass_count}, Truncations: {trunc_count}")

    f_out.close()
    # Update hash journal
    audit_results_journal(REPO_ROOT)
    return existing_records


def run_b0_evaluation_2048(
    model_id: str,
    condition_name: str,
    items: List[Dict[str, Any]],
    api_key: str,
    raw_filename: str,
    inter_request_sleep: float = 2.0
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Runs B0 baseline model on Groq with 2,048 token budget (append-only resume)."""
    out_path = os.path.join(RESULTS_DIR, raw_filename)

    # Load existing records to check resolved items
    existing_records = []
    resolved_ids = set()
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        rec = json.loads(line)
                        existing_records.append(rec)
                        # An item is resolved if complete or truncated at 2048 tokens
                        if rec.get("max_tokens_budget") == 2048 and (rec.get("status") == "COMPLETE" or rec.get("truncated")):
                            resolved_ids.add(rec["item_id"])
                    except Exception:
                        pass

    items_to_run = [it for it in items if (it.get("subtask_id") or it.get("original_id") or it.get("question_id")) not in resolved_ids]

    print(f"\n==========================================")
    print(f"STARTING {condition_name} EVALUATION: {model_id} (Groq, Budget=2048)")
    print(f"Total: {len(items)}, Already resolved: {len(resolved_ids)}, Remaining: {len(items_to_run)}")
    print(f"==========================================")

    f_out = open(out_path, "a", encoding="utf-8")
    latest_ratelimits = {}
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for idx, item in enumerate(items_to_run, 1):
        prompt = format_prompt(item)
        resp, ratelimits = call_groq_api(model_id, prompt, api_key, max_tokens=2048)
        if ratelimits:
            latest_ratelimits = ratelimits

        truncated = (resp["finish_reason"] == "length")
        if resp["status"] == "COMPLETE" and not truncated:
            score = score_item(item, resp["content"])
        else:
            score = {"passed": False, "recall": 0.0, "checker": "none", "details": f"Status: {resp['status']}, Finish: {resp['finish_reason']}"}

        item_id = item.get("subtask_id") or item.get("original_id") or item.get("question_id")
        stratum = item.get("stratum", "track_b" if "checklist" in item else "unknown")
        track = "B" if "checklist" in item else "A"
        solvability = item.get("solvability")
        num_stages = len(item.get("component_parts", [])) if item.get("component_parts") else None

        rec = {
            "item_id": item_id,
            "track": track,
            "task_type": item.get("task_type", "track_b_qa" if "checklist" in item else "unknown"),
            "stratum": stratum,
            "solvability": solvability,
            "num_stages": num_stages,
            "model_id": model_id,
            "condition": condition_name,
            "max_tokens_budget": 2048,
            "prompt": prompt,
            "output": resp["content"],
            "finish_reason": resp["finish_reason"],
            "truncated": truncated,
            "latency_seconds": resp["latency_seconds"],
            "prompt_tokens": resp["prompt_tokens"],
            "completion_tokens": resp["completion_tokens"],
            "status": resp["status"],
            "passed": score["passed"],
            "recall": score["recall"],
            "checker": score["checker"],
            "checker_details": score["details"]
        }
        existing_records.append(rec)
        f_out.write(json.dumps(rec) + "\n")
        f_out.flush()

        total_prompt_tokens += resp["prompt_tokens"]
        total_completion_tokens += resp["completion_tokens"]

        if idx % 10 == 0 or idx == len(items_to_run):
            trunc_count = sum(1 for r in existing_records if r.get("truncated"))
            pass_count = sum(1 for r in existing_records if r.get("passed"))
            rem_req = latest_ratelimits.get("x-ratelimit-remaining-requests", "N/A")
            rem_tok = latest_ratelimits.get("x-ratelimit-remaining-tokens", "N/A")
            print(f"[{condition_name} Progress] {idx}/{len(items_to_run)} done | Total Passes: {pass_count}, Truncations: {trunc_count} | Rem Req: {rem_req}, Rem Tok: {rem_tok}")

        # Pacing sleep to strictly respect TPM refill
        time.sleep(inter_request_sleep)

    f_out.close()
    # Update hash journal
    audit_results_journal(REPO_ROOT)

    quota_report = {
        "model_id": model_id,
        "items_evaluated": len(items_to_run),
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "final_remaining_requests": latest_ratelimits.get("x-ratelimit-remaining-requests"),
        "final_remaining_tokens": latest_ratelimits.get("x-ratelimit-remaining-tokens"),
        "request_limit": latest_ratelimits.get("x-ratelimit-limit-requests"),
        "token_limit": latest_ratelimits.get("x-ratelimit-limit-tokens"),
    }
    return existing_records, quota_report


def main():
    print("Loading Dev Datasets...")
    with open(TRACK_A_DEV_PATH, "r", encoding="utf-8") as f:
        track_a_items = json.load(f)
    with open(TRACK_B_DEV_PATH, "r", encoding="utf-8") as f:
        track_b_items = json.load(f)

    all_dev_items = track_a_items + track_b_items
    print(f"Loaded Track A Dev: {len(track_a_items)} items.")
    print(f"Loaded Track B Dev: {len(track_b_items)} items.")
    print(f"Total Dev Items: {len(all_dev_items)} items.")

    groq_api_key = os.getenv("GROQ_API_KEY", "")
    if not groq_api_key:
        from dotenv import load_dotenv
        load_dotenv()
        groq_api_key = os.getenv("GROQ_API_KEY", "")

    if not groq_api_key:
        print("ERROR: GROQ_API_KEY is not set. Cannot run B0 baselines.")
        sys.exit(1)

    # 1. Run C0 with 2,048 token budget (Local Phi-4-mini)
    c0_records = run_c0_evaluation_2048(all_dev_items)
    c0_metrics = compute_stratum_metrics(c0_records)

    # 2. Run B0 Tier 1: Qwen-27B with 2,048 token budget (Groq)
    # 2.5s pacing for Qwen due to 1,000 OTPM limit
    b0_qwen_records, qwen_quota = run_b0_evaluation_2048(
        model_id="qwen/qwen3.8-27b",
        condition_name="B0_Qwen27B",
        items=all_dev_items,
        api_key=groq_api_key,
        raw_filename="b0_qwen27b_dev_records.jsonl",
        inter_request_sleep=2.5
    )
    b0_qwen_metrics = compute_stratum_metrics(b0_qwen_records)

    # 3. Run B0 Tier 3: GPT-OSS-120B with 2,048 token budget (Groq)
    # 1.5s pacing for GPT-120B (8,000 TPM limit)
    b0_gpt_records, gpt_quota = run_b0_evaluation_2048(
        model_id="openai/gpt-oss-120b",
        condition_name="B0_GPT120B",
        items=all_dev_items,
        api_key=groq_api_key,
        raw_filename="b0_gpt120b_dev_records.jsonl",
        inter_request_sleep=1.5
    )
    b0_gpt_metrics = compute_stratum_metrics(b0_gpt_records)

    # Difficulty Gate Verification — STRICTLY EVALUATED ON TOTAL ACCURACY
    # Gate 1: C0 compound TOTAL accuracy <= 60.0%
    c0_compound_total_acc = c0_metrics["compound_all"]["acc_total"]
    gate1_pass = (c0_compound_total_acc <= 60.0)

    # Gate 2: Baseline B0 compound solvable-without-tools TOTAL accuracy <= 90.0%
    qwen_solvable_total_acc = b0_qwen_metrics["compound_solvable_without_tools"]["acc_total"]
    gpt_solvable_total_acc = b0_gpt_metrics["compound_solvable_without_tools"]["acc_total"]
    gate2_qwen_pass = (qwen_solvable_total_acc <= 90.0)
    gate2_gpt_pass = (gpt_solvable_total_acc <= 90.0)
    gate2_pass = (gate2_qwen_pass and gate2_gpt_pass)

    summary_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "answer_budget_tokens": 2048,
        "total_items": len(all_dev_items),
        "difficulty_gate_evaluated_on_total_accuracy": {
            "c0_compound_total_accuracy": c0_compound_total_acc,
            "c0_compound_threshold": 60.0,
            "c0_gate_pass": gate1_pass,
            "b0_qwen_solvable_total_accuracy": qwen_solvable_total_acc,
            "b0_gpt_solvable_total_accuracy": gpt_solvable_total_acc,
            "b0_solvable_threshold": 90.0,
            "gate2_pass": gate2_pass,
            "overall_difficulty_gate_pass": (gate1_pass and gate2_pass)
        },
        "c0_phi4_mini": {
            "model": "microsoft/Phi-4-mini-instruct",
            "serving": "llama-server (Vulkan GPU, port 8080)",
            "truncations": c0_metrics["all_dev"]["n_truncated"],
            "metrics": c0_metrics
        },
        "b0_qwen27b": {
            "model": "qwen/qwen3.8-27b",
            "serving": "Groq API",
            "truncations": b0_qwen_metrics["all_dev"]["n_truncated"],
            "metrics": b0_qwen_metrics,
            "quota": qwen_quota
        },
        "b0_gpt120b": {
            "model": "openai/gpt-oss-120b",
            "serving": "Groq API",
            "truncations": b0_gpt_metrics["all_dev"]["n_truncated"],
            "metrics": b0_gpt_metrics,
            "quota": gpt_quota
        }
    }

    summary_path = os.path.join(RESULTS_DIR, "phase4_dev_c0_b0_report.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2)

    # Sync journal
    audit_results_journal(REPO_ROOT)

    print("\n=======================================================")
    print("PHASE 4 DEV EVALUATION COMPLETE: C0 & B0 (2048 TOKENS)")
    print("=======================================================")
    print(f"Summary Report saved to: {summary_path}")
    print(f"Truncations Reported:")
    print(f"  - C0 Phi-4-mini Truncations: {c0_metrics['all_dev']['n_truncated']} / 150")
    print(f"  - B0 Qwen-27B Truncations: {b0_qwen_metrics['all_dev']['n_truncated']} / 150")
    print(f"  - B0 GPT-OSS-120B Truncations: {b0_gpt_metrics['all_dev']['n_truncated']} / 150")
    print(f"Difficulty Gate Status (Total Accuracy):")
    print(f"  - C0 Compound Total Acc: {c0_compound_total_acc:.1f}% (Threshold <= 60.0%): {'PASS' if gate1_pass else 'FAIL'}")
    print(f"  - B0 Qwen Solvable-w/o-tools Total Acc: {qwen_solvable_total_acc:.1f}% (Threshold <= 90.0%): {'PASS' if gate2_qwen_pass else 'FAIL'}")
    print(f"  - B0 GPT-OSS-120B Solvable-w/o-tools Total Acc: {gpt_solvable_total_acc:.1f}% (Threshold <= 90.0%): {'PASS' if gate2_gpt_pass else 'FAIL'}")
    print(f"  - Overall Difficulty Gate: {'QUALIFIED' if (gate1_pass and gate2_pass) else 'BREACHED - REGENERATION REQUIRED'}")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
