"""
B1 Tool Harness Execution for openai/gpt-oss-120b on Dev Split (N=150).

Provides exact B1 tools and retrieved passages matching Phase 5 heldout baseline:
1. Track B: BM25 top-3 passages from HyperGrid corpus (track_b_retrieval_harness)
2. SQL: SQLite database access with schema and 1 execution retry (sql_harness_with_retry)
3. Code: Python sandbox execution with 1 assertion retry (code_harness_with_retry)
4. QA: Multiple choice option prompt (qa_harness)
5. Compound: SQLite fetch + downstream reasoning (compound_multistep_harness)
6. Math: Direct step-by-step reasoning (math_harness)

Append-only records saved to results/phase4/dev_b1_gpt120b_records.jsonl.
Strictly Dev split only. Reserve and held-out remain untouched.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
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

DEV_A_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
DEV_B_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_dev_split.json")
OUT_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_b1_gpt120b_records.jsonl")

MODEL_ID = "openai/gpt-oss-120b"


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
    num_calls = 0

    # 1. Track B: Retrieval-then-Answer
    if "checklist" in item:
        harness_used = "track_b_retrieval_harness"
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
        num_calls += 1
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
            "harness_used": harness_used,
            "output": final_text[:300],
            "full_output": final_text,
            "finish_reason": resp["finish_reason"],
            "prompt_tokens": total_prompt_tok,
            "completion_tokens": total_comp_tok,
            "total_tokens": total_prompt_tok + total_comp_tok,
            "num_calls": num_calls,
            "status": resp["status"],
            "clean_execution": clean_exec and resp["status"] == "COMPLETE",
            "passed": passed,
            "details": details,
            "duration": round(dt, 2)
        }

    task_type = item.get("task_type") or item.get("type") or ""

    # 2. Pure SQL (Spider)
    if task_type == "sql":
        harness_used = "sql_harness_with_retry"
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
        num_calls += 1
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
            num_calls += 1
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
            "harness_used": harness_used,
            "output": final_content[:300],
            "full_output": final_content,
            "finish_reason": "stop" if clean else "error",
            "prompt_tokens": total_prompt_tok,
            "completion_tokens": total_comp_tok,
            "total_tokens": total_prompt_tok + total_comp_tok,
            "num_calls": num_calls,
            "status": "COMPLETE" if final_content.strip() else "FAILED",
            "clean_execution": clean,
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2)
        }

    # 3. Pure Code (HumanEval)
    if task_type == "code":
        harness_used = "code_harness_with_retry"
        code_prompt = f"{item['prompt']}\nComplete the implementation of the above Python function inside ```python ... ```."
        resp1 = call_groq_api(
            model_name,
            code_prompt,
            system_prompt="You are an expert Python programmer. Output only valid Python code enclosed in ```python ... ```.",
            max_tokens=4096
        )
        num_calls += 1
        total_prompt_tok += resp1["prompt_tokens"]
        total_comp_tok += resp1["completion_tokens"]
        sc1 = score_record(item, resp1["content"])
        if sc1["passed"]:
            dt = time.time() - t0
            return {
                "harness_used": harness_used,
                "output": resp1["content"][:300],
                "full_output": resp1["content"],
                "finish_reason": resp1["finish_reason"],
                "prompt_tokens": total_prompt_tok,
                "completion_tokens": total_comp_tok,
                "total_tokens": total_prompt_tok + total_comp_tok,
                "num_calls": num_calls,
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
            num_calls += 1
            total_prompt_tok += resp2["prompt_tokens"]
            total_comp_tok += resp2["completion_tokens"]
            sc2 = score_record(item, resp2["content"])
            dt = time.time() - t0
            return {
                "harness_used": harness_used,
                "output": resp2["content"][:300],
                "full_output": resp2["content"],
                "finish_reason": resp2["finish_reason"],
                "prompt_tokens": total_prompt_tok,
                "completion_tokens": total_comp_tok,
                "total_tokens": total_prompt_tok + total_comp_tok,
                "num_calls": num_calls,
                "status": resp2["status"],
                "clean_execution": sc2["passed"],
                "passed": sc2["passed"],
                "details": sc2["details"],
                "duration": round(dt, 2)
            }

    # 4. QA (ARC)
    if task_type == "qa":
        harness_used = "qa_harness"
        choices = item.get("choices", {})
        opt_text = "\n".join(f"({k}) {v}" for k, v in sorted(choices.items()))
        qa_prompt = (
            f"Question: {item['question']}\n\n"
            f"Options:\n{opt_text}\n\n"
            f"Select the single correct option. State your final answer as: Answer: (X)"
        )
        resp = call_groq_api(model_name, qa_prompt, max_tokens=4096)
        num_calls += 1
        dt = time.time() - t0
        sc = score_record(item, resp["content"])
        return {
            "harness_used": harness_used,
            "output": resp["content"][:300],
            "full_output": resp["content"],
            "finish_reason": resp["finish_reason"],
            "prompt_tokens": resp["prompt_tokens"],
            "completion_tokens": resp["completion_tokens"],
            "total_tokens": resp["total_tokens"],
            "num_calls": num_calls,
            "status": resp["status"],
            "clean_execution": True,
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2)
        }

    # 5. Compound items (SQL + Reason, Math + Code, etc.)
    if task_type == "compound" or item.get("stratum") == "composed":
        harness_used = "compound_multistep_harness"
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
            resp_sql = call_groq_api(
                model_name,
                sql_prompt,
                system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
                max_tokens=4096
            )
            num_calls += 1
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
                num_calls += 1
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
            resp_reason = call_groq_api(
                model_name,
                downstream_prompt,
                system_prompt="You are an expert mathematical and logical reasoning assistant.",
                max_tokens=4096
            )
            num_calls += 1
            total_prompt_tok += resp_reason["prompt_tokens"]
            total_comp_tok += resp_reason["completion_tokens"]
            dt = time.time() - t0

            sc = score_record(item, resp_reason["content"])
            return {
                "harness_used": harness_used,
                "output": resp_reason["content"][:300],
                "full_output": resp_reason["content"],
                "finish_reason": resp_reason["finish_reason"],
                "prompt_tokens": total_prompt_tok,
                "completion_tokens": total_comp_tok,
                "total_tokens": total_prompt_tok + total_comp_tok,
                "num_calls": num_calls,
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
            resp = call_groq_api(model_name, direct_prompt, max_tokens=4096)
            num_calls += 1
            dt = time.time() - t0
            sc = score_record(item, resp["content"])
            return {
                "harness_used": harness_used,
                "output": resp["content"][:300],
                "full_output": resp["content"],
                "finish_reason": resp["finish_reason"],
                "prompt_tokens": resp["prompt_tokens"],
                "completion_tokens": resp["completion_tokens"],
                "total_tokens": resp["total_tokens"],
                "num_calls": num_calls,
                "status": resp["status"],
                "clean_execution": True,
                "passed": sc["passed"],
                "details": sc["details"],
                "duration": round(dt, 2)
            }

    # 6. Math (GSM8K)
    harness_used = "math_harness"
    direct_prompt = (
        f"{item.get('prompt') or item.get('question')}\n\n"
        f"Solve the problem step by step. Conclude your final answer with: #### <number>"
    )
    resp = call_groq_api(model_name, direct_prompt, max_tokens=4096)
    num_calls += 1
    dt = time.time() - t0
    sc = score_record(item, resp["content"])
    return {
        "harness_used": harness_used,
        "output": resp["content"][:300],
        "full_output": resp["content"],
        "finish_reason": resp["finish_reason"],
        "prompt_tokens": resp["prompt_tokens"],
        "completion_tokens": resp["completion_tokens"],
        "total_tokens": resp["total_tokens"],
        "num_calls": num_calls,
        "status": resp["status"],
        "clean_execution": True,
        "passed": sc["passed"],
        "details": sc["details"],
        "duration": round(dt, 2)
    }


def main():
    print("=" * 70)
    print("DEV B1 BASELINE EXECUTION: openai/gpt-oss-120b (WITH TOOLS)")
    print("=" * 70)

    # Load dev items
    with open(DEV_A_PATH, "r", encoding="utf-8") as f:
        dev_a = json.load(f)
    with open(DEV_B_PATH, "r", encoding="utf-8") as f:
        dev_b = json.load(f)

    # Load existing records for resume capability
    existing_recs = {}
    if os.path.exists(OUT_RECORDS_PATH):
        with open(OUT_RECORDS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        iid = rec.get("item_id")
                        if iid:
                            existing_recs[iid] = rec
                    except Exception:
                        pass
        print(f"Resuming with {len(existing_recs)} existing records.")

    all_items = []
    for it in dev_a:
        it_copy = dict(it)
        it_copy["item_id"] = it.get("original_id") or it.get("item_id")
        all_items.append(it_copy)
    for it in dev_b:
        it_copy = dict(it)
        it_copy["item_id"] = it["question_id"]
        all_items.append(it_copy)

    print(f"Total items to evaluate: {len(all_items)} (100 Track A, 50 Track B)")

    completed = len(existing_recs)
    passed_cnt = sum(1 for r in existing_recs.values() if r.get("passed"))
    total_tokens_spent = sum(r.get("total_tokens", 0) for r in existing_recs.values())

    out_file = open(OUT_RECORDS_PATH, "a", encoding="utf-8")

    for idx, item in enumerate(all_items, 1):
        iid = item["item_id"]
        if iid in existing_recs:
            continue

        print(f"[{idx:03d}/{len(all_items)}] Running {iid} ({item.get('task_type', 'track_b')})...")
        res = run_item_with_b1_tools(MODEL_ID, item)

        rec = {
            "item_id": iid,
            "task_type": item.get("task_type", "track_b"),
            "stratum": item.get("stratum", "track_b"),
            "condition": "B1",
            "model_id": MODEL_ID,
            "harness_used": res["harness_used"],
            "output": res["output"],
            "full_output": res["full_output"],
            "finish_reason": res["finish_reason"],
            "prompt_tokens": res["prompt_tokens"],
            "completion_tokens": res["completion_tokens"],
            "total_tokens": res["total_tokens"],
            "num_calls": res["num_calls"],
            "status": res["status"],
            "clean_execution": res["clean_execution"],
            "passed": res["passed"],
            "details": res["details"],
            "duration": res["duration"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        out_file.write(json.dumps(rec) + "\n")
        out_file.flush()
        existing_recs[iid] = rec

        completed += 1
        if rec["passed"]:
            passed_cnt += 1
        total_tokens_spent += rec["total_tokens"]

        pass_str = "PASS" if rec["passed"] else "FAIL"
        print(f"    -> {pass_str} | Harness: {rec['harness_used']} | Calls: {rec['num_calls']} | Tok: {rec['total_tokens']} | {rec['details']}")

        # Respect Groq rate pacing (2.5s)
        time.sleep(2.5)

    out_file.close()

    print("\n" + "=" * 70)
    print("DEV B1 BASELINE EXECUTION COMPLETE")
    print(f"Total evaluated: {len(existing_recs)} / {len(all_items)}")
    print(f"Passed: {passed_cnt} / {len(existing_recs)} ({passed_cnt/len(existing_recs)*100:.1f}%)")
    print(f"Total tokens spent: {total_tokens_spent}")
    print("=" * 70)


if __name__ == "__main__":
    main()

