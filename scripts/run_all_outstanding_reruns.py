"""
Master script to execute all outstanding Phase 4 reruns:
1. B0 Qwen-27B: 23 failed/truncated Track A items at 4,096 tokens.
2. B1 Qwen-27B: 6 failed/truncated compound Track A items at 4,096 tokens.
3. B1 Qwen-27B: 50 Track B items with exact top_k=5 retrieval and exact format instruction.
4. B1 GPT-120B: 50 Track B items with exact top_k=5 retrieval and exact format instruction.

Rules:
- Append-only: all records are appended as new rows to results files.
- Max tokens: strictly 4,096.
- Temperature: 0.0, Seed: 42.
- Scorer version: 1.1.0 with Unicode normalization.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
load_dotenv()

from src.eval.versioned_scorer import score_record
from src.eval.fact_checklist_scorer import score_fact_checklist
from src.pipeline.specialist_pipeline import get_bm25_retriever, get_table_schema
from src.tools.tolerant_harness import execute_sql_tolerant, KNOWN_DATABASES
from src.sandbox.runner import execute_python_code

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
os.makedirs(RESULTS_DIR, exist_ok=True)

TRACK_A_PATH = os.path.join(REPO_ROOT, "data", "track_a_heldout_split.json")
TRACK_B_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_heldout_split.json")

B0_QWEN_PATH = os.path.join(RESULTS_DIR, "b0_qwen27b_heldout_records.jsonl")
B1_QWEN_PATH = os.path.join(RESULTS_DIR, "b1_qwen27b_heldout_records.jsonl")
B1_GPT_PATH = os.path.join(RESULTS_DIR, "b1_gpt120b_heldout_records.jsonl")


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

    for attempt in range(12):
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
                sleep_time = max(retry_after + 1.5, body_wait + 1.5, 3.0 * (attempt + 1), 6.0)
                print(f"    [Rate Limit 429] Backing off for {sleep_time:.1f}s (attempt {attempt+1}/12)...")
                time.sleep(sleep_time)
            elif he.code in [500, 502, 503, 504]:
                sleep_time = 4.0 * (attempt + 1)
                print(f"    [Server Error {he.code}] Backing off for {sleep_time:.1f}s (attempt {attempt+1}/12)...")
                time.sleep(sleep_time)
            else:
                try:
                    err_msg = he.read().decode("utf-8")
                except Exception:
                    err_msg = str(he)
                return {
                    "content": "",
                    "finish_reason": "error",
                    "latency_seconds": round(elapsed, 4),
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "status": "FAILED",
                    "error_message": f"HTTP {he.code}: {err_msg[:200]}"
                }
        except Exception as e:
            time.sleep(3.0 * (attempt + 1))

    return {
        "content": "",
        "finish_reason": "error",
        "latency_seconds": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "status": "FAILED",
        "error_message": "All retries exhausted"
    }


def format_eval_prompt_b0(item: Dict[str, Any]) -> str:
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


def identify_database(item: Dict[str, Any]) -> str:
    prompt = item.get("prompt", "") or item.get("question", "")
    for db in KNOWN_DATABASES:
        if re.search(r"\b" + re.escape(db) + r"\b", prompt, re.IGNORECASE):
            return db
    m = re.search(r"\b([a-zA-Z0-9_\-]+)\s+database\b", prompt, re.IGNORECASE)
    if m and m.group(1).lower() not in ["sqlite", "relational", "the", "a", "this"]:
        return m.group(1)
    return item.get("db_id", "")


def extract_sql_query(text: str) -> str:
    m = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(";")
    lines = text.strip().split("\n")
    for line in lines:
        if line.strip().upper().startswith("SELECT"):
            return line.strip().rstrip(";")
    return text.strip().rstrip(";")


def run_item_b1_compound(model_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.time()
    total_prompt_tok = 0
    total_comp_tok = 0
    clean_exec = True
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
            "clean_execution": resp["status"] == "COMPLETE",
            "passed": sc["passed"],
            "details": sc["details"],
            "duration": round(dt, 2)
        }


def run_item_track_b_fair(model_name: str, item: Dict[str, Any], retriever: Any) -> Dict[str, Any]:
    t0 = time.time()
    word_cap = item.get("word_cap", 75)
    raw_prompt = item["prompt"]

    # Pipeline exact retrieval call (top_k=5)
    query_str = f"{raw_prompt}\n\nProvide a concise answer in key-value pairs (max {word_cap} words). Conclude with 'Final Answer: <key-value pairs>'."
    passages = retriever.retrieve(query_str, top_k=5)
    context_str = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in passages])

    # Pipeline exact format instruction
    augmented_prompt = (
        f"[Retrieved Reference Documents]:\n{context_str}\n\n"
        f"Question:\n{raw_prompt}\n\n"
        f"Provide a concise answer in key-value pairs (max {word_cap} words).\n"
        f"Conclude with 'Final Answer: <key-value pairs>'."
    )

    resp = call_groq_api(
        model_name,
        augmented_prompt,
        system_prompt="You are an expert technical assistant. Answer the question based on the provided reference documents.",
        max_tokens=4096
    )
    final_text = resp["content"]
    dt = time.time() - t0

    # Strict score (with word cap)
    sc_strict = score_fact_checklist(final_text, item["checklist"], max_word_cap=word_cap)
    # Facts alone score (word cap ignored)
    sc_facts = score_fact_checklist(final_text, item["checklist"], max_word_cap=999999)

    passed_strict = sc_strict["binary_pass"]
    passed_facts = sc_facts["binary_pass"]
    details = f"Recall: {sc_strict['recall']:.2f}, Precision: {sc_strict['precision']:.2f}"
    if sc_strict.get("failed_facts"):
        details += f" | Failed: {sc_strict['failed_facts'][0]}"

    return {
        "output": final_text[:300],
        "full_output": final_text,
        "finish_reason": resp["finish_reason"],
        "prompt_tokens": resp["prompt_tokens"],
        "completion_tokens": resp["completion_tokens"],
        "total_tokens": resp["total_tokens"],
        "status": resp["status"],
        "clean_execution": resp["status"] == "COMPLETE",
        "passed": passed_strict,
        "passed_facts_alone": passed_facts,
        "details": details,
        "duration": round(dt, 2)
    }


def main():
    print("=== STARTING MASTER RERUN SUITE ===")
    with open(TRACK_A_PATH, "r", encoding="utf-8") as f:
        track_a_items = json.load(f)
    with open(TRACK_B_PATH, "r", encoding="utf-8") as f:
        track_b_items = json.load(f)

    tra_by_id = {(it.get("item_id") or it.get("original_id") or it.get("subtask_id")): it for it in track_a_items}
    trb_by_id = {(it.get("question_id") or it.get("item_id")): it for it in track_b_items}
    retriever = get_bm25_retriever()

    # -------------------------------------------------------------
    # 1. B0 Qwen-27B: 23 Track A items
    # -------------------------------------------------------------
    b0_failed_ids = [
        'Mercury_7241115', 'Mercury_7006790', 'HumanEval/132',
        'compound_heldout_v2_0001', 'compound_heldout_v2_0002', 'compound_heldout_v2_0003',
        'compound_heldout_v2_0004', 'compound_heldout_v2_0005', 'compound_heldout_v2_0006',
        'compound_heldout_v2_0007', 'compound_heldout_v2_0008', 'compound_heldout_v2_0009',
        'compound_heldout_v2_0010', 'compound_heldout_v2_0014', 'compound_heldout_v2_0017',
        'compound_heldout_v2_0020', 'compound_heldout_v2_0021', 'compound_heldout_v2_0022',
        'compound_heldout_v2_0023', 'compound_heldout_v2_0024', 'compound_heldout_v2_0026',
        'compound_heldout_v2_0028', 'compound_heldout_v2_0030'
    ]
    print(f"\n--- [1/4] Running B0 Qwen-27B: {len(b0_failed_ids)} items unclamped at 4096 tokens ---")
    with open(B0_QWEN_PATH, "a", encoding="utf-8") as f_out:
        for idx, iid in enumerate(b0_failed_ids, 1):
            it = tra_by_id[iid]
            prompt = format_eval_prompt_b0(it)
            resp = call_groq_api(
                "qwen/qwen3.8-27b",
                prompt,
                system_prompt="You are a helpful, precise assistant. Reason step-by-step and provide your final answer in the requested format.",
                max_tokens=4096
            )
            sc = score_record(it, resp["content"])
            rec = {
                "item_id": iid,
                "model": "qwen/qwen3.8-27b",
                "condition": "B0",
                "track": "A",
                "stratum": it.get("stratum", ""),
                "task_type": it.get("task_type") or it.get("type", ""),
                "solvability": it.get("solvability", ""),
                "prompt": prompt,
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
                "duration": resp["latency_seconds"],
                "rerun_4096": True,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  [{idx:02d}/{len(b0_failed_ids)}] B0 Qwen {iid}: passed={sc['passed']}, status={resp['status']}, fr={resp['finish_reason']}")
            time.sleep(2.5)

    # -------------------------------------------------------------
    # 2. B1 Qwen-27B: 6 compound Track A items
    # -------------------------------------------------------------
    b1_failed_ids = [
        'compound_heldout_v2_0003', 'compound_heldout_v2_0005', 'compound_heldout_v2_0009',
        'compound_heldout_v2_0017', 'compound_heldout_v2_0026', 'compound_heldout_v2_0038'
    ]
    print(f"\n--- [2/4] Running B1 Qwen-27B: {len(b1_failed_ids)} compound items unclamped at 4096 tokens ---")
    with open(B1_QWEN_PATH, "a", encoding="utf-8") as f_out:
        for idx, iid in enumerate(b1_failed_ids, 1):
            it = tra_by_id[iid]
            res = run_item_b1_compound("qwen/qwen3.8-27b", it)
            rec = {
                "item_id": iid,
                "model": "qwen/qwen3.8-27b",
                "condition": "B1",
                "track": "A",
                "stratum": it.get("stratum", ""),
                "task_type": it.get("task_type") or it.get("type", ""),
                "solvability": it.get("solvability", ""),
                "prompt": it.get("prompt", ""),
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
                "rerun_4096": True,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  [{idx:02d}/{len(b1_failed_ids)}] B1 Qwen {iid}: passed={res['passed']}, status={res['status']}, fr={res['finish_reason']}")
            time.sleep(2.5)

    # -------------------------------------------------------------
    # 3. B1 Qwen-27B: 50 Track B items (fair top_k=5 retrieval)
    # -------------------------------------------------------------
    print(f"\n--- [3/4] Running B1 Qwen-27B: 50 Track B items with exact top_k=5 retrieval ---")
    with open(B1_QWEN_PATH, "a", encoding="utf-8") as f_out:
        for idx, it in enumerate(track_b_items, 1):
            iid = it.get("question_id") or it.get("item_id")
            res = run_item_track_b_fair("qwen/qwen3.8-27b", it, retriever)
            rec = {
                "item_id": iid,
                "model": "qwen/qwen3.8-27b",
                "condition": "B1",
                "track": "B",
                "stratum": "track_b_rag",
                "task_type": "rag",
                "solvability": "tool-required",
                "prompt": it.get("prompt", ""),
                "output": res["output"],
                "full_output": res["full_output"],
                "finish_reason": res["finish_reason"],
                "prompt_tokens": res["prompt_tokens"],
                "completion_tokens": res["completion_tokens"],
                "total_tokens": res["total_tokens"],
                "status": res["status"],
                "clean_execution": res["clean_execution"],
                "passed": res["passed"],
                "passed_facts_alone": res["passed_facts_alone"],
                "details": res["details"],
                "duration": res["duration"],
                "rerun_topk5_fair": True,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  [{idx:02d}/50] B1 Qwen Track B {iid}: strict={res['passed']}, facts={res['passed_facts_alone']}, status={res['status']}")
            time.sleep(2.5)

    # -------------------------------------------------------------
    # 4. B1 GPT-120B: 50 Track B items (fair top_k=5 retrieval)
    # -------------------------------------------------------------
    print(f"\n--- [4/4] Running B1 GPT-120B: 50 Track B items with exact top_k=5 retrieval ---")
    with open(B1_GPT_PATH, "a", encoding="utf-8") as f_out:
        for idx, it in enumerate(track_b_items, 1):
            iid = it.get("question_id") or it.get("item_id")
            res = run_item_track_b_fair("openai/gpt-oss-120b", it, retriever)
            rec = {
                "item_id": iid,
                "model": "openai/gpt-oss-120b",
                "condition": "B1",
                "track": "B",
                "stratum": "track_b_rag",
                "task_type": "rag",
                "solvability": "tool-required",
                "prompt": it.get("prompt", ""),
                "output": res["output"],
                "full_output": res["full_output"],
                "finish_reason": res["finish_reason"],
                "prompt_tokens": res["prompt_tokens"],
                "completion_tokens": res["completion_tokens"],
                "total_tokens": res["total_tokens"],
                "status": res["status"],
                "clean_execution": res["clean_execution"],
                "passed": res["passed"],
                "passed_facts_alone": res["passed_facts_alone"],
                "details": res["details"],
                "duration": res["duration"],
                "rerun_topk5_fair": True,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  [{idx:02d}/50] B1 GPT Track B {iid}: strict={res['passed']}, facts={res['passed_facts_alone']}, status={res['status']}")
            time.sleep(2.5)

    print("\n=== ALL RERUNS COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()
