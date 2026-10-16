"""
scripts/eval_e4b_pool_routes.py

Evaluates the 100 rebuilt compound items (50 solvable, 50 tool-required) in
data/router_e4b_train_pool.json across all 5 canonical routes:
1. direct_reasoner
2. direct_sql
3. code_execution
4. decompose_reasoner
5. decompose_code

Appends records to results/phase4/router_e4b_pool_route_records.jsonl.
Combines with the 300 existing non-SQL records (Math, QA, Code) from
results/phase4/router_train_pool_route_records.jsonl to form the complete 400-item evaluation set.
"""

import os
import sys
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import (
    call_phi,
    get_table_schema,
    execute_sql_tolerant,
    extract_sql_from_text,
    decompose_task_model_call,
    execute_data_fetch,
    execute_downstream_reasoning,
    KNOWN_DATABASES
)
from src.pipeline.specialist_pipeline_e3 import (
    is_function_completion,
    execute_computation_code
)
from src.eval.versioned_scorer import check_math_subtask

POOL_PATH = os.path.join(REPO_ROOT, "data", "router_e4b_train_pool.json")
EXISTING_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "router_train_pool_route_records.jsonl")
OUT_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "router_e4b_pool_route_records.jsonl")
COMBINED_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "router_e4b_complete_route_records.jsonl")


def format_compound_prompt(item: Dict[str, Any]) -> str:
    """Formats prompt according to task category."""
    q = item.get("question", "").strip()
    return f"Task: {q}\nReason step by step and provide the final numeric answer inside \\boxed{{...}} or as 'Final Answer: <number>'."


def route_direct_reasoner(prompt: str) -> str:
    """Route 1: Direct Reasoner."""
    resp = call_phi([
        {"role": "system", "content": "You are a helpful, precise assistant. Reason step-by-step and provide your final answer in the requested format."},
        {"role": "user", "content": prompt}
    ], temperature=0.0, max_tokens=1024)
    return resp


def route_direct_sql(prompt: str) -> str:
    """Route 2: Direct SQL with Schema lookup."""
    db_m = re.search(r"Database:\s*([a-zA-Z0-9_\-]+)", prompt)
    db_to_use = db_m.group(1).strip() if db_m else ""
    schema = get_table_schema(db_to_use) if db_to_use else ""

    direct_sql_sys = (
        "You are an expert SQLite text-to-SQL assistant. Given a database schema and a natural language question, "
        "write a syntactically correct SQLite query. Return strictly the SQL query inside ```sql\n<query>\n```."
    )
    query_prompt = f"Database Schema:\n{schema}\n\nQuestion: {prompt}\n\nWrite the SQLite query inside ```sql ... ```."
    resp_1 = call_phi([
        {"role": "system", "content": direct_sql_sys},
        {"role": "user", "content": query_prompt}
    ], temperature=0.0, max_tokens=256)
    query_1 = extract_sql_from_text(resp_1)
    return f"```sql\n{query_1}\n```"


def route_code_execution(prompt: str) -> str:
    """Route 3: Python Code Execution in Sandbox."""
    comp_prompt = (
        f"Problem:\n{prompt}\n\n"
        "Write a short, self-contained Python program to compute the exact answer to the problem.\n"
        "Guidelines:\n"
        "- Implement the arithmetic, counting, modular math, simulation, or search directly in Python.\n"
        "- When converting floats to integers or using functions requiring int, use int(round(x)).\n"
        "- Print only the final numeric result to stdout using print().\n"
        "- Output strictly the Python code block enclosed in ```python\n<code>\n```."
    )
    resp = call_phi([
        {"role": "system", "content": "You are an expert computational assistant. Write a short Python program to compute the exact answer."},
        {"role": "user", "content": comp_prompt}
    ], temperature=0.0, max_tokens=512)

    code_m = re.search(r"```python\s*(.*?)\s*```", resp, re.DOTALL | re.IGNORECASE)
    v = ""
    if code_m:
        code = code_m.group(1).strip()
        clean_exec, out_v, v = execute_computation_code(code, retry_prompt_base=comp_prompt, timeout=6.0)

    if v:
        return f"Final Answer: {v}"
    return resp


def route_decompose_reasoner(prompt: str) -> str:
    """Route 4: Decompose + Direct Reasoner."""
    subtasks, _ = decompose_task_model_call(prompt)

    # Solve Subtask 1
    db_present = any(db.lower() in prompt.lower() for db in KNOWN_DATABASES)
    if db_present:
        clean_fetch, fetch_summary, fetched_val = execute_data_fetch(
            subtask_1=subtasks[0],
            color_1="SQL_DATA",
            db_name="",
            prompt=prompt
        )
    else:
        # Solve initial subtask via reasoner
        s1_resp = call_phi([
            {"role": "system", "content": "Solve this initial step cleanly and state the numeric answer after Result:"},
            {"role": "user", "content": f"Task context: {prompt}\n\nStep 1 to solve:\n{subtasks[0]}"}
        ], temperature=0.0, max_tokens=256)
        fetch_summary = s1_resp
        fetched_val = s1_resp

    # Downstream reasoning on Subtask 2
    clean_down, full_down, clean_ans = execute_downstream_reasoning(
        subtasks[1], fetched_val, fetch_summary, "DIRECT_REASON", prompt
    )
    return clean_ans


def route_decompose_code(prompt: str) -> str:
    """Route 5: Decompose + Code Sandbox Execution."""
    subtasks, _ = decompose_task_model_call(prompt)

    # Solve Subtask 1
    db_present = any(db.lower() in prompt.lower() for db in KNOWN_DATABASES)
    if db_present:
        clean_fetch, fetch_summary, fetched_val = execute_data_fetch(
            subtask_1=subtasks[0],
            color_1="SQL_DATA",
            db_name="",
            prompt=prompt
        )
    else:
        # Solve initial subtask via reasoner
        s1_resp = call_phi([
            {"role": "system", "content": "Solve this initial step cleanly and state the numeric answer after Result:"},
            {"role": "user", "content": f"Task context: {prompt}\n\nStep 1 to solve:\n{subtasks[0]}"}
        ], temperature=0.0, max_tokens=256)
        fetch_summary = s1_resp
        fetched_val = s1_resp

    down_prompt = (
        f"Task: {prompt}\n\n"
        f"Retrieved Step 1 Context:\n{fetch_summary}\n\n"
        f"Step 2 to Complete:\n{subtasks[1]}\n\n"
        "Write a short, self-contained Python program to compute the exact answer to this step using the retrieved data.\n"
        "Guidelines:\n"
        "- Implement the arithmetic or logic directly in Python.\n"
        "- When converting floats to integers or using functions requiring int, use int(round(x)).\n"
        "- Print only the final numeric result to stdout using print().\n"
        "- Output strictly the Python code block enclosed in ```python\n<code>\n```."
    )
    resp = call_phi([
        {"role": "system", "content": "You are an expert computational assistant. Write a short Python program to compute the exact answer."},
        {"role": "user", "content": down_prompt}
    ], temperature=0.0, max_tokens=512)

    code_m = re.search(r"```python\s*(.*?)\s*```", resp, re.DOTALL | re.IGNORECASE)
    v = ""
    if code_m:
        code = code_m.group(1).strip()
        clean_exec, out_v, v = execute_computation_code(code, retry_prompt_base=down_prompt, timeout=6.0)

    if v:
        return f"Final Answer: {v}"
    return resp


ROUTES = [
    ("direct_reasoner", route_direct_reasoner),
    ("direct_sql", route_direct_sql),
    ("code_execution", route_code_execution),
    ("decompose_reasoner", route_decompose_reasoner),
    ("decompose_code", route_decompose_code),
]


def score_compound_item(item: Dict[str, Any], ans: str) -> bool:
    """Evaluates whether the answer string matches the gold answer."""
    gold_val = str(item.get("gold_answer", "")).strip()
    passed, _, _ = check_math_subtask("pool_compound", ans, gold_val)
    return bool(passed)


def evaluate_compound_route(item: Dict[str, Any], route_name: str, route_fn) -> Dict[str, Any]:
    """Runs single item through route with duration measurement and scoring."""
    t0 = time.time()
    prompt = format_compound_prompt(item)
    try:
        ans = route_fn(prompt)
        dt = time.time() - t0
        passed = score_compound_item(item, ans)
    except Exception as e:
        dt = time.time() - t0
        ans = f"ERROR: {e}"
        passed = False

    return {
        "pool_id": item["pool_id"],
        "original_id": item.get("original_id", ""),
        "category": item["category"],
        "route": route_name,
        "passed": passed,
        "duration": round(dt, 2),
        "output": ans[:200],
        "full_output": ans,
        "gold_answer": item.get("gold_answer", "")
    }


def main():
    print("=" * 80)
    print("EVALUATING REBUILT COMPOUND POOL (100 ITEMS x 5 ROUTES = 500 PAIRS)")
    print("=" * 80)

    with open(POOL_PATH, "r", encoding="utf-8") as f:
        pool_items = json.load(f)

    compound_items = [it for it in pool_items if "compound" in it.get("category", "")]
    print(f"Loaded {len(compound_items)} compound items from {POOL_PATH}.")

    # Load existing records for resume capability
    existing = {}
    if os.path.exists(OUT_RECORDS_PATH):
        with open(OUT_RECORDS_PATH, "r", encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    r = json.loads(l)
                    existing[(r["pool_id"], r["route"])] = r
    print(f"Loaded {len(existing)} existing compound route evaluations.")

    pending = []
    for it in compound_items:
        for r_name, r_fn in ROUTES:
            if (it["pool_id"], r_name) not in existing:
                pending.append((it, r_name, r_fn))

    print(f"Pending evaluations: {len(pending)} / {len(compound_items) * len(ROUTES)}")

    if pending:
        # Run in parallel across 3 Vulkan slots
        records = []
        with open(OUT_RECORDS_PATH, "a", encoding="utf-8") as f_out:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(evaluate_compound_route, it, r_name, r_fn) for (it, r_name, r_fn) in pending]
                for idx, fut in enumerate(futures, 1):
                    rec = fut.result()
                    f_out.write(json.dumps(rec) + "\n")
                    f_out.flush()
                    existing[(rec["pool_id"], rec["route"])] = rec
                    if idx % 25 == 0 or idx == len(futures):
                        print(f"  Completed {idx}/{len(futures)} evaluations ({rec['category']} [{rec['route']}] -> {'PASS' if rec['passed'] else 'FAIL'}, {rec['duration']}s)")

    print("\nAll 500 compound route evaluations completed.")

    # Combine with existing non-SQL pool records (Math, QA, Code: 300 items x 5 routes = 1,500 records)
    combined = []
    # 1. Existing atomic records (Math, QA, Code)
    with open(EXISTING_RECORDS_PATH, "r", encoding="utf-8") as f:
        for l in f:
            if l.strip():
                r = json.loads(l)
                if r.get("category") in ("atomic_math", "atomic_qa", "atomic_code"):
                    combined.append(r)

    # 2. Rebuilt compound records
    with open(OUT_RECORDS_PATH, "r", encoding="utf-8") as f:
        for l in f:
            if l.strip():
                r = json.loads(l)
                combined.append(r)

    print(f"Total combined records for E4b training: {len(combined)} (400 items x 5 routes = 2,000 evaluations).")
    with open(COMBINED_RECORDS_PATH, "w", encoding="utf-8") as f:
        for r in combined:
            f.write(json.dumps(r) + "\n")

    print(f"Wrote combined records to: {COMBINED_RECORDS_PATH}")


if __name__ == "__main__":
    main()

