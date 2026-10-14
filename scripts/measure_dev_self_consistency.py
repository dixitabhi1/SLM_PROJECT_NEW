"""
Trigger T6: Self-Consistency Evaluation on Dev Split (150 items).

Generates 3 extra samples from the Specialist Pipeline at temperature=0.7.
Extracts the final answer from each sample and checks for disagreement with greedy answer.
Strictly Dev split only. No held-out or reserve data.
"""

import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import time
import re
import concurrent.futures
from typing import Dict, Any, List, Optional, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import (
    call_phi,
    get_table_schema,
    get_bm25_retriever,
    extract_sql_from_text,
    task_asks_for_query
)
from src.tools.tolerant_harness import execute_sql_tolerant, KNOWN_DATABASES
from src.eval.versioned_scorer import extract_code_block, check_code_subtask

DEV_A_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
DEV_B_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_dev_split.json")
V11_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_v11_pipeline_records.jsonl")
OUT_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_self_consistency_eval.json")


def extract_math_int(text: str) -> Optional[int]:
    """Extracts integer answer for GSM8K / math."""
    m = re.search(r"####\s*(-?\d+)", text)
    if m:
        return int(m.group(1))
    m = re.findall(r"\\boxed\{(-?\d+)\}", text)
    if m:
        return int(m[-1])
    m = re.findall(r"(?:answer\s+is\s+|total\s+is\s+|equal\s+to\s+|=\s*)(-?\d+)", text, re.I)
    if m:
        return int(m[-1])
    m = re.findall(r"\b(-?\d+)\b", text)
    return int(m[-1]) if m else None


def extract_qa_letter(text: str) -> Optional[str]:
    """Extracts multiple choice letter (A-D) for ARC QA."""
    m = re.findall(
        r"(?:answer\s*(?:is|:)?\s*|final\s+answer\s*(?:is|:)?\s*)(?:\()?([A-D])(?:\))?",
        text,
        re.I,
    )
    if m:
        return m[-1].upper()
    m = re.findall(r"\\boxed\{[(\[]?([A-D])[)\]]?\}", text, re.I)
    if m:
        return m[-1].upper()
    m = re.findall(
        r"(?:correct\s+(?:choice|option)\s*(?:is|:)?\s*|option\s*(?:is|:)?\s*)(?:\()?([A-D])(?:\))?",
        text,
        re.I,
    )
    if m:
        return m[-1].upper()
    m = re.findall(r"[(]([A-D])[)]", text)
    if m:
        return m[-1].upper()
    return None


def extract_tb_numbers(text: str) -> List[str]:
    """Extracts numeric values and entities from Track B answer."""
    ans_m = re.search(r"(?:Final\s+Answer:|Answer:)\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    body = ans_m.group(0).strip() if ans_m else text
    nums = re.findall(r"[-+]?\d*\.?\d+", body)
    return nums


def sample_single_pass(item: Dict[str, Any], greedy_rec: Dict[str, Any], seed: int) -> Tuple[str, Any]:
    """
    Generates 1 sample from the pipeline at temperature=0.7.
    Returns (raw_response, extracted_answer).
    """
    p = greedy_rec.get("prompt") or item.get("prompt") or item.get("question", "")
    routed_to = greedy_rec.get("routed_to", "direct")
    task_type = greedy_rec.get("task_type") or item.get("task_type") or item.get("type", "")

    if routed_to == "direct_sql":
        # Direct SQL path
        db_to_use = greedy_rec.get("stages", [{}])[0].get("db_name", "")
        if not db_to_use:
            for db in KNOWN_DATABASES:
                if db.lower() in p.lower():
                    db_to_use = db
                    break
        schema_str = get_table_schema(db_to_use)
        if "[database schema:" not in p.lower() and schema_str:
            query_prompt = f"Database: {db_to_use}\nSchema:\n{schema_str}\n\n{p}"
        else:
            query_prompt = p

        direct_sql_sys = (
            "You are an expert SQL assistant. Given the database schema and question, write a single valid SQLite query that answers the question.\n"
            "Guidelines:\n"
            "- Return ONLY the exact column(s) requested by the question. Do not include auxiliary count or aggregate columns in the SELECT clause unless explicitly asked.\n"
            "- Ensure necessary table joins are included when attributes belong to relational tables.\n"
            "- Output strictly the SQL query enclosed in ```sql\n<query>\n```. Do not provide conversational explanations."
        )

        resp1 = call_phi([
            {"role": "system", "content": direct_sql_sys},
            {"role": "user", "content": query_prompt}
        ], temperature=0.7, max_tokens=256)

        q1 = extract_sql_from_text(resp1)
        clean1, out1 = execute_sql_tolerant(db_to_use, q1, prompt_context=p)
        final_q = q1
        final_clean = clean1
        final_out = out1

        if not clean1:
            retry_msg = (
                f"The query failed execution with error:\n{out1}\n"
                f"Please fix the query and provide a valid SQLite query in ```sql ... ```."
            )
            resp2 = call_phi([
                {"role": "system", "content": direct_sql_sys},
                {"role": "user", "content": query_prompt},
                {"role": "assistant", "content": f"```sql\n{q1}\n```"},
                {"role": "user", "content": retry_msg}
            ], temperature=0.7, max_tokens=256)
            q2 = extract_sql_from_text(resp2)
            clean2, out2 = execute_sql_tolerant(db_to_use, q2, prompt_context=p)
            final_q = q2
            final_clean = clean2
            final_out = out2

        # Extracted answer is (clean, row_output_string)
        return final_q, (final_clean, final_out)

    elif "checklist" in item:
        # Track B: retrieval context is deterministic top-3 BM25
        retriever = get_bm25_retriever()
        passages = retriever.retrieve(p, top_k=3)
        context_str = "\n\n".join([f"[{p_obj.doc_id}]:\n{p_obj.text}" for p_obj in passages])
        word_cap = item.get("word_cap", 75)
        user_msg = (
            f"Task:\n{p}\n\n"
            f"Retrieved Context:\n{context_str}\n\n"
            f"Step to Complete:\nProvide a concise answer in key-value pairs (max {word_cap} words).\n\n"
            f"Reason step-by-step and conclude with 'Final Answer: <answer>' or '#### <answer>'."
        )
        resp = call_phi([
            {"role": "system", "content": "You are an expert reasoning assistant. Use the provided retrieved data to solve the task step-by-step. Conclude with 'Final Answer: <answer>' or '#### <answer>'."},
            {"role": "user", "content": user_msg}
        ], temperature=0.7, max_tokens=768)

        nums = extract_tb_numbers(resp)
        return resp, nums

    elif routed_to == "outside_data":
        # Compound item: fetch DB column, downstream reasoning
        db_name = ""
        for db in KNOWN_DATABASES:
            if db.lower() in p.lower():
                db_name = db
                break
        schema_str = get_table_schema(db_name) if db_name else ""
        user_msg = (
            f"Task:\n{p}\n\n"
            f"Database Schema:\n{schema_str}\n\n"
            f"Solve the task step-by-step and conclude with 'Final Answer: <answer>' or '#### <answer>'."
        )
        resp = call_phi([
            {"role": "system", "content": "You are an expert reasoning assistant. Solve the task step-by-step. Conclude with 'Final Answer: <answer>' or '#### <answer>'."},
            {"role": "user", "content": user_msg}
        ], temperature=0.7, max_tokens=768)
        ans_int = extract_math_int(resp)
        return resp, ans_int

    else:
        # Direct reasoning path (ARC QA, GSM8K Math, HumanEval Code)
        resp = call_phi([
            {"role": "system", "content": "You are a helpful, precise assistant. Reason step-by-step and provide your final answer in the requested format."},
            {"role": "user", "content": p}
        ], temperature=0.7, max_tokens=1024)

        if task_type == "math":
            val = extract_math_int(resp)
        elif task_type == "qa":
            val = extract_qa_letter(resp)
        elif task_type == "code":
            # Test code via HumanEval assertions
            pass_status, _, _ = check_code_subtask(item.get("subtask_id", item.get("item_id")), resp, item)
            val = pass_status
        else:
            val = resp[:100]

        return resp, val


def extract_greedy_answer(item: Dict[str, Any], greedy_rec: Dict[str, Any]) -> Any:
    """Extracts answer from greedy v1.1 execution."""
    p = greedy_rec.get("prompt") or item.get("prompt") or item.get("question", "")
    routed_to = greedy_rec.get("routed_to", "direct")
    task_type = greedy_rec.get("task_type") or item.get("task_type") or item.get("type", "")
    final_ans = greedy_rec.get("final_answer") or greedy_rec.get("output", "")

    if routed_to == "direct_sql":
        db_to_use = ""
        for db in KNOWN_DATABASES:
            if db.lower() in p.lower():
                db_to_use = db
                break
        q = extract_sql_from_text(final_ans)
        clean, out = execute_sql_tolerant(db_to_use, q, prompt_context=p)
        return (clean, out)

    elif "checklist" in item:
        return extract_tb_numbers(final_ans)

    elif routed_to == "outside_data":
        return extract_math_int(final_ans)

    else:
        if task_type == "math":
            return extract_math_int(final_ans)
        elif task_type == "qa":
            return extract_qa_letter(final_ans)
        elif task_type == "code":
            pass_status, _, _ = check_code_subtask(item.get("subtask_id", item.get("item_id")), final_ans, item)
            return pass_status
        else:
            return final_ans[:100]


def check_disagreement(greedy_val: Any, sample_vals: List[Any], task_type: str) -> Tuple[bool, str]:
    """Checks whether any sample disagrees with greedy answer."""
    if greedy_val is None:
        # Greedy failed extraction
        return True, "Greedy answer unparseable/None"

    for idx, s_val in enumerate(sample_vals):
        if s_val is None:
            return True, f"Sample {idx} unparseable/None"
        if s_val != greedy_val:
            return True, f"Sample {idx} ({s_val}) != Greedy ({greedy_val})"

    return False, "All 3 samples agree with greedy"


def main():
    print("=" * 70)
    print("TRIGGER T6: SELF-CONSISTENCY MEASUREMENT ON DEV (N=150)")
    print("=" * 70)

    # 1. Load splits
    with open(DEV_A_PATH, "r", encoding="utf-8") as f:
        dev_a = json.load(f)
    with open(DEV_B_PATH, "r", encoding="utf-8") as f:
        dev_b = json.load(f)

    all_items = {it.get("original_id", it.get("item_id")): it for it in dev_a}
    for it in dev_b:
        all_items[it["question_id"]] = it

    # 2. Load greedy records
    with open(V11_RECORDS_PATH, "r", encoding="utf-8") as f:
        greedy_recs = {json.loads(l)["item_id"]: json.loads(l) for l in f if l.strip()}

    print(f"Loaded {len(all_items)} dev items ({len(dev_a)} Track A, {len(dev_b)} Track B).")
    print(f"Loaded {len(greedy_recs)} greedy v1.1 records.")

    # 3. Load existing cache if any
    results = {}
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, "r", encoding="utf-8") as f:
                results = json.load(f)
            print(f"Resuming with {len(results)} cached evaluations.")
        except Exception:
            results = {}

    item_ids = list(all_items.keys())
    t0_all = time.time()

    for idx, iid in enumerate(item_ids):
        if iid in results:
            continue

        item = all_items[iid]
        g_rec = greedy_recs[iid]
        greedy_val = extract_greedy_answer(item, g_rec)
        t_start = time.time()

        # Generate 3 samples concurrently across the 3 llama-server slots
        sample_vals = []
        sample_raws = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(sample_single_pass, item, g_rec, seed=s) for s in [101, 202, 303]]
            for fut in futures:
                try:
                    raw_resp, val = fut.result()
                    sample_raws.append(raw_resp)
                    sample_vals.append(val)
                except Exception as e:
                    sample_raws.append(f"EXCEPTION: {e}")
                    sample_vals.append(None)

        disagrees, reason = check_disagreement(greedy_val, sample_vals, g_rec.get("task_type", ""))
        dt = time.time() - t_start

        results[iid] = {
            "item_id": iid,
            "passed_v11": g_rec.get("passed", False),
            "task_type": g_rec.get("task_type") or item.get("task_type") or item.get("type", ""),
            "greedy_val": str(greedy_val),
            "sample_vals": [str(v) for v in sample_vals],
            "flagged": disagrees,
            "disagreement_reason": reason,
            "duration": round(dt, 2)
        }

        flag_str = "FLAGGED" if disagrees else "AGREED"
        pass_str = "PASS" if g_rec.get("passed") else "FAIL"
        safe_reason = reason.encode("ascii", errors="replace").decode("ascii")[:120]
        print(f"[{idx+1:03d}/{len(item_ids)}] {iid} ({pass_str}): {flag_str} ({dt:.2f}s) | {safe_reason}")

        # Save checkpoint immediately
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

    total_time = time.time() - t0_all
    print(f"\nDone in {total_time:.1f}s.")

    # 4. Summary statistics
    total = len(results)
    right = [k for k, v in results.items() if v["passed_v11"]]
    wrong = [k for k, v in results.items() if not v["passed_v11"]]

    flagged_total = [k for k, v in results.items() if v["flagged"]]
    flagged_wrong = [k for k in wrong if results[k]["flagged"]]
    flagged_right = [k for k in right if results[k]["flagged"]]

    print("\n" + "=" * 70)
    print("TRIGGER T6 (SELF-CONSISTENCY) SUMMARY STATISTICS:")
    print("=" * 70)
    print(f"Total dev items: {total}")
    print(f"v1.1 Correct: {len(right)}, v1.1 Wrong: {len(wrong)}")
    print(f"Total Flagged: {len(flagged_total)} / {total} ({len(flagged_total)/total*100:.1f}%)")
    print(f"True Positives (Wrong items flagged): {len(flagged_wrong)} / {len(wrong)} ({len(flagged_wrong)/len(wrong)*100:.1f}%)")
    print(f"False Positives (Right items flagged): {len(flagged_right)} / {len(right)} ({len(flagged_right)/len(right)*100:.1f}%)")
    print("=" * 70)


if __name__ == "__main__":
    main()
