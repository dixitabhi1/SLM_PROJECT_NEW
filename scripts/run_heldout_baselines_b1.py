"""
Phase 4 Frozen Held-Out Evaluation Script: B1 Baselines with Fair Tools & Retrieved Passages.

Provides fair resources (Hard Rule 9) matching the Specialist Pipeline:
1. Track B items: Top-3 retrieved passages from HyperGrid corpus via BM25.
2. SQL items: SQLite database access via tolerant harness with 1 retry on syntax error.
3. Compound items: If database named, writes 1 SQL query, harness executes (1 retry),
   and query result is injected into direct reasoning prompt.
4. Code items: Python sandbox execution with 1 retry on error.

Models:
1. qwen/qwen3.8-27b (Tier 1 Baseline, 27B)
2. openai/gpt-oss-120b (Tier 3 Ceiling Baseline, 120B)

Configuration:
- Condition: B1 (Tools + Retrieved Passages, unclamped max_tokens=2048, greedy temp=0.0)
- Pacing: 2.0s between requests + adaptive HTTP 429 backoff
- Append-only records to results/phase4/b1_qwen27b_heldout_records.jsonl and b1_gpt120b_heldout_records.jsonl
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
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

from src.sandbox.runner import execute_python_code
from src.tools.tolerant_harness import execute_sql_tolerant, KNOWN_DATABASES
from src.tools.retriever_tool import BM25RetrieverTool
from src.eval.versioned_scorer import score_record, extract_sql_query
from src.eval.fact_checklist_scorer import score_fact_checklist
from src.pipeline.specialist_pipeline import get_table_schema, get_bm25_retriever

TRACK_A_HELDOUT_PATH = os.path.join(REPO_ROOT, "data", "track_a_heldout_split.json")
TRACK_B_HELDOUT_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_heldout_split.json")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
os.makedirs(RESULTS_DIR, exist_ok=True)

EXPECTED_TRACK_A_HASH = "2314fca186a064ffcface62f42dc346bda9fdc73c5221852e8ecf5b19aafd629"
EXPECTED_TRACK_B_HASH = "075bf20d1daafdb89e3eef1e35271113766b9845cfb9d52e88301faa2919c0e1"


def verify_split_hashes():
    h_a = hashlib.sha256(open(TRACK_A_HELDOUT_PATH, "rb").read()).hexdigest()
    h_b = hashlib.sha256(open(TRACK_B_HELDOUT_PATH, "rb").read()).hexdigest()
    assert h_a == EXPECTED_TRACK_A_HASH, f"Track A hash mismatch: got {h_a}, expected {EXPECTED_TRACK_A_HASH}"
    assert h_b == EXPECTED_TRACK_B_HASH, f"Track B hash mismatch: got {h_b}, expected {EXPECTED_TRACK_B_HASH}"
    print("Cryptographic Lock Verified:")
    print(f"  Track A Held-out SHA-256: {h_a} [LOCKED]")
    print(f"  Track B Held-out SHA-256: {h_b} [LOCKED]")


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
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

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
                sleep_time = max(retry_after + 1.0, body_wait + 1.0, 3.0 * (attempt + 1), 5.0)
                print(f"    [Rate Limit 429] Backing off for {sleep_time:.1f}s (attempt {attempt+1}/10)...")
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
        "error_message": "All 10 retries exhausted"
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


def run_item_with_b1_tools(model_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Executes item under B1 condition with tools / retrieved passages."""
    t0 = time.time()
    total_prompt_tok = 0
    total_comp_tok = 0
    clean_exec = True

    # 1. Track B: Retrieval-then-Answer
    if "checklist" in item:
        word_cap = item.get("word_cap", 75)
        raw_prompt = item["prompt"]
        retriever = get_bm25_retriever()
        passages = retriever.retrieve(raw_prompt, top_k=3)
        context_str = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in passages])

        augmented_prompt = (
            f"[Retrieved Reference Documents]:\n{context_str}\n\n"
            f"Question:\n{raw_prompt}\n\n"
            f"Based on the retrieved documents above, provide a concise answer in key-value pairs (max {word_cap} words).\n"
            f"Conclude with 'Final Answer: <key-value pairs>'."
        )

        resp = call_groq_api(
            model_name,
            augmented_prompt,
            system_prompt="You are an expert technical assistant. Answer the question based on the provided reference documents.",
            max_tokens=4096
        )
        total_prompt_tok += resp["prompt_tokens"]
        total_comp_tok += resp["completion_tokens"]
        final_text = resp["content"]
        dt = time.time() - t0

        sc = score_fact_checklist(final_text, item["checklist"], max_word_cap=word_cap)
        passed = sc["binary_pass"]
        details = f"Recall: {sc['recall']:.2f}, Precision: {sc['precision']:.2f}"
        if sc.get("failed_facts"):
            details += f" | Failed: {sc['failed_facts'][0]}"

        return {
            "output": final_text[:300],
            "full_output": final_text,
            "finish_reason": resp["finish_reason"],
            "prompt_tokens": total_prompt_tok,
            "completion_tokens": total_comp_tok,
            "total_tokens": total_prompt_tok + total_comp_tok,
            "status": resp["status"],
            "clean_execution": clean_exec and resp["status"] == "COMPLETE",
            "passed": passed,
            "details": details,
            "duration": round(dt, 2)
        }

    task_type = item.get("task_type") or item.get("type") or ""

    # 2. Pure SQL (Spider)
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
            model_name,
            sql_prompt,
            system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
            max_tokens=4096
        )
        total_prompt_tok += resp1["prompt_tokens"]
        total_comp_tok += resp1["completion_tokens"]
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
                model_name,
                retry_prompt,
                system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
                max_tokens=4096
            )
            total_prompt_tok += resp2["prompt_tokens"]
            total_comp_tok += resp2["completion_tokens"]
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
            "finish_reason": "stop" if clean else "error",
            "prompt_tokens": total_prompt_tok,
            "completion_tokens": total_comp_tok,
            "total_tokens": total_prompt_tok + total_comp_tok,
            "status": "COMPLETE" if final_content.strip() else "FAILED",
            "clean_execution": clean,
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2)
        }

    # 3. Pure Code (HumanEval)
    if task_type == "code":
        code_prompt = f"{item['prompt']}\nComplete the implementation of the above Python function inside ```python ... ```."
        resp1 = call_groq_api(
            model_name,
            code_prompt,
            system_prompt="You are an expert Python programmer. Output only valid Python code enclosed in ```python ... ```.",
            max_tokens=4096
        )
        total_prompt_tok += resp1["prompt_tokens"]
        total_comp_tok += resp1["completion_tokens"]
        sc1 = score_record(item, resp1["content"])
        if sc1["passed"]:
            dt = time.time() - t0
            return {
                "output": resp1["content"][:300],
                "full_output": resp1["content"],
                "finish_reason": resp1["finish_reason"],
                "prompt_tokens": total_prompt_tok,
                "completion_tokens": total_comp_tok,
                "total_tokens": total_prompt_tok + total_comp_tok,
                "status": resp1["status"],
                "clean_execution": True,
                "passed": True,
                "details": sc1["details"],
                "duration": round(dt, 2)
            }
        else:
            # 1 retry with error
            retry_prompt = (
                f"{code_prompt}\n\n"
                f"Previous code execution produced an error: {sc1['details'][:300]}\n"
                f"Please fix the bug and output the corrected Python code enclosed in ```python ... ```."
            )
            resp2 = call_groq_api(
                model_name,
                retry_prompt,
                system_prompt="You are an expert Python programmer. Output only valid Python code enclosed in ```python ... ```.",
                max_tokens=4096
            )
            total_prompt_tok += resp2["prompt_tokens"]
            total_comp_tok += resp2["completion_tokens"]
            sc2 = score_record(item, resp2["content"])
            dt = time.time() - t0
            return {
                "output": resp2["content"][:300],
                "full_output": resp2["content"],
                "finish_reason": resp2["finish_reason"],
                "prompt_tokens": total_prompt_tok,
                "completion_tokens": total_comp_tok,
                "total_tokens": total_prompt_tok + total_comp_tok,
                "status": resp2["status"],
                "clean_execution": sc2["passed"],
                "passed": sc2["passed"],
                "details": sc2["details"],
                "duration": round(dt, 2)
            }

    # 4. QA (ARC)
    if task_type == "qa":
        choices = item.get("choices", {})
        opt_text = "\n".join(f"({k}) {v}" for k, v in sorted(choices.items()))
        qa_prompt = (
            f"Question: {item['question']}\n\n"
            f"Options:\n{opt_text}\n\n"
            f"Select the single correct option. State your final answer as: Answer: (X)"
        )
        resp = call_groq_api(model_name, qa_prompt, max_tokens=4096)
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
            "clean_execution": True,
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2)
        }

    # 5. Compound items (SQL + Reason, Math + Code, etc.)
    if task_type == "compound" or item.get("stratum") == "composed":
        raw_prompt = item["prompt"]
        db_name = identify_database(item)

        if db_name:
            # Data-then-reason: fetch database data first
            schema = get_table_schema(db_name)
            sql_prompt = (
                f"Task: {raw_prompt}\n\n"
                f"Database: {db_name}\n"
                f"Schema:\n{schema}\n\n"
                f"Write exactly one SQLite query enclosed in ```sql ... ``` to extract the required data from '{db_name}'. "
                f"Select ONLY the single requested column."
            )
            resp_sql = call_groq_api(
                model_name,
                sql_prompt,
                system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
                max_tokens=4096
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
                resp_sql2 = call_groq_api(
                    model_name,
                    retry_sql,
                    system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
                    max_tokens=4096
                )
                total_prompt_tok += resp_sql2["prompt_tokens"]
                total_comp_tok += resp_sql2["completion_tokens"]
                q2 = extract_sql_query(resp_sql2["content"])
                clean, out_text = execute_sql_tolerant(db_name, q2, prompt_context=raw_prompt)

            # Insert fetched data into downstream reasoning prompt
            downstream_prompt = (
                f"Task: {raw_prompt}\n\n"
                f"Database Query Executed: {q}\n"
                f"Retrieved Query Data: {out_text}\n\n"
                f"Based on the retrieved data, solve the problem step by step.\n"
                f"Conclude your final answer with: 'Final Answer: <answer>' or '#### <answer>'."
            )
            resp_reason = call_groq_api(
                model_name,
                downstream_prompt,
                system_prompt="You are an expert mathematical and logical reasoning assistant.",
                max_tokens=4096
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
            # Solvable without tools: direct step-by-step reasoning
            direct_prompt = (
                f"{raw_prompt}\n\n"
                f"Solve the problem step by step. Conclude your final answer with 'Final Answer: <answer>' or '#### <answer>'."
            )
            resp = call_groq_api(model_name, direct_prompt, max_tokens=4096)
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
                "clean_execution": True,
                "passed": sc["passed"],
                "details": sc["details"],
                "duration": round(dt, 2)
            }

    # Default fallback: math / general
    direct_prompt = (
        f"{item.get('prompt') or item.get('question')}\n\n"
        f"Solve the problem step by step. Conclude your final answer with: #### <number>"
    )
    resp = call_groq_api(model_name, direct_prompt, max_tokens=4096)
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
        "clean_execution": True,
        "passed": sc["passed"],
        "details": sc["details"],
        "duration": round(dt, 2)
    }


def bootstrap_ci(scores: List[float], n_boot: int = 2000, alpha: float = 0.05) -> Tuple[float, float]:
    if not scores:
        return (0.0, 0.0)
    rng = random.Random(42)
    n = len(scores)
    means = []
    for _ in range(n_boot):
        sample = [rng.choice(scores) for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lower_idx = int(n_boot * (alpha / 2))
    upper_idx = int(n_boot * (1 - alpha / 2))
    return (round(means[lower_idx] * 100, 2), round(means[upper_idx] * 100, 2))


def evaluate_baseline_b1_model(
    model_name: str,
    output_path: str,
    all_items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    print(f"\nEvaluating Baseline Condition B1 (Fair Tools): {model_name} -> {output_path}")
    existing = load_existing_records(output_path)
    print(f"Existing records: {len(existing)} / {len(all_items)}")

    records = []
    total_tokens_used = 0

    with open(output_path, "a", encoding="utf-8") as f_out:
        for idx, item in enumerate(all_items, 1):
            iid = item.get("subtask_id") or item.get("original_id") or item.get("question_id") or item.get("item_id")
            if iid in existing:
                rec_ex = existing[iid]
                # If completed cleanly without length truncation, keep it
                if rec_ex.get("status") == "COMPLETE" and rec_ex.get("finish_reason") != "length":
                    records.append(rec_ex)
                    continue
                else:
                    print(f"  [RERUN TRUNCATED/FAILED] {iid} had finish_reason={rec_ex.get('finish_reason')}, status={rec_ex.get('status')}. Rerunning unclamped (4096 tokens)...")

            res = run_item_with_b1_tools(model_name, item)
            total_tokens_used += res["total_tokens"]

            rec = {
                "item_id": iid,
                "split": "heldout",
                "track": "B" if "checklist" in item else "A",
                "task_type": item.get("task_type", "track_b" if "checklist" in item else ""),
                "stratum": item.get("stratum", "atomic" if "checklist" in item else ""),
                "solvability": item.get("solvability", ""),
                "model_id": model_name,
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
                "duration": res["duration"]
            }
            records.append(rec)
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()

            status_str = "PASS" if res["passed"] else "FAIL"
            print(f"  [B1 {idx:03d}/{len(all_items)}] {model_name} {iid}: {status_str} ({res['duration']:.2f}s, tok={res['completion_tokens']})")

            # Respect rate limits
            time.sleep(2.0)

    # Ensure latest record per item_id is returned
    latest_map = {}
    for r in records:
        latest_map[r["item_id"]] = r
    for r in existing.values():
        if r["item_id"] not in latest_map:
            latest_map[r["item_id"]] = r
    final_records = [latest_map[it.get("subtask_id") or it.get("original_id") or it.get("question_id") or it.get("item_id")] for it in all_items if (it.get("subtask_id") or it.get("original_id") or it.get("question_id") or it.get("item_id")) in latest_map]

    print(f"Finished B1 for {model_name}. New tokens used: {total_tokens_used}. Final unique records: {len(final_records)}")
    return final_records


def analyze_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    def compute_stratum_metrics(subset: List[Dict[str, Any]]) -> Dict[str, Any]:
        count = len(subset)
        if count == 0:
            return {"count": 0, "passes": 0, "acc": 0.0, "ci_95": [0.0, 0.0], "clean_share": 0.0, "mean_duration": 0.0, "failed_or_trunc": 0, "failed_trunc_pct": 0.0}
        passes = sum(1 for r in subset if r.get("passed"))
        acc = round(passes / count * 100, 2)
        ci = bootstrap_ci([1.0 if r.get("passed") else 0.0 for r in subset])
        clean_share = round(sum(1 for r in subset if r.get("clean_execution")) / count * 100, 2)
        durations = [r.get("duration", 0.0) for r in subset]
        mean_dur = round(sum(durations) / count, 2) if durations else 0.0
        failed_trunc = sum(1 for r in subset if r.get("finish_reason") == "length" or r.get("status") == "FAILED")
        failed_trunc_pct = round(failed_trunc / count * 100, 2)
        return {
            "count": count,
            "passes": passes,
            "acc": acc,
            "ci_95": list(ci),
            "clean_share": clean_share,
            "mean_duration": mean_dur,
            "failed_or_trunc": failed_trunc,
            "failed_trunc_pct": failed_trunc_pct
        }

    tra_items = [r for r in records if r.get("track") == "A"]
    trb_items = [r for r in records if r.get("track") == "B"]
    atomic = [r for r in tra_items if r.get("stratum") == "atomic"]
    comp = [r for r in tra_items if r.get("stratum") == "composed"]
    comp_solv = [r for r in comp if r.get("solvability") == "solvable_without_tools"]
    comp_treq = [r for r in comp if r.get("solvability") == "tool-required"]

    return {
        "track_a_total": compute_stratum_metrics(tra_items),
        "track_b_total": compute_stratum_metrics(trb_items),
        "tra_atomic": compute_stratum_metrics(atomic),
        "tra_compound": compute_stratum_metrics(comp),
        "tra_comp_solv": compute_stratum_metrics(comp_solv),
        "tra_comp_treq": compute_stratum_metrics(comp_treq)
    }


def main():
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY environment variable is missing.")
        sys.exit(1)

    verify_split_hashes()

    track_a = json.load(open(TRACK_A_HELDOUT_PATH, "r", encoding="utf-8"))
    track_b = json.load(open(TRACK_B_HELDOUT_PATH, "r", encoding="utf-8"))
    all_heldout_items = track_a + track_b
    print(f"Loaded {len(track_a)} Track A heldout items + {len(track_b)} Track B heldout items. Total: {len(all_heldout_items)} items.")

    # 1. Qwen-27B B1
    qwen_out = os.path.join(RESULTS_DIR, "b1_qwen27b_heldout_records.jsonl")
    qwen_recs = evaluate_baseline_b1_model("qwen/qwen3.8-27b", qwen_out, all_heldout_items)

    # 2. GPT-OSS-120B B1
    gpt_out = os.path.join(RESULTS_DIR, "b1_gpt120b_heldout_records.jsonl")
    gpt_recs = evaluate_baseline_b1_model("openai/gpt-oss-120b", gpt_out, all_heldout_items)

    # Compile report
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "split": "heldout",
        "condition": "B1",
        "hashes": {
            "track_a_heldout_sha256": EXPECTED_TRACK_A_HASH,
            "track_b_heldout_sha256": EXPECTED_TRACK_B_HASH
        },
        "results": {
            "qwen27b": analyze_records(qwen_recs),
            "gpt120b": analyze_records(gpt_recs)
        }
    }

    report_path = os.path.join(RESULTS_DIR, "phase4_b1_heldout_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()

