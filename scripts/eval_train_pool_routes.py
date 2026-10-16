"""
scripts/eval_train_pool_routes.py

Evaluates all 500 items in data/router_train_pool.json across the 5 canonical routes:
1. direct_reasoner
2. direct_sql
3. code_execution
4. decompose_reasoner
5. decompose_code

Records are append-only in: results/phase4/router_train_pool_route_records.jsonl
Summary is saved in: results/phase4/router_train_pool_route_summary.json
Resumable: skips already completed (pool_id, route) pairs.
Uses ThreadPoolExecutor(max_workers=3) across 3 parallel Vulkan slots on llama-server.
"""

import os
import sys
import re
import json
import time
import sqlite3
from typing import Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

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
from src.sandbox.runner import execute_python_code
from src.eval.versioned_scorer import score_record, check_math_subtask, check_qa_subtask

POOL_PATH = os.path.join(REPO_ROOT, "data", "router_train_pool.json")
TABLES_PATH = os.path.join(REPO_ROOT, "data", "spider", "tables.json")
OUT_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "router_train_pool_route_records.jsonl")
OUT_SUMMARY_PATH = os.path.join(REPO_ROOT, "results", "phase4", "router_train_pool_route_summary.json")

# Load tables.json for Spider train schema lookup
SPIDER_TABLES_MAP = {}
if os.path.exists(TABLES_PATH):
    with open(TABLES_PATH, "r", encoding="utf-8") as f:
        tables_data = json.load(f)
        for entry in tables_data:
            SPIDER_TABLES_MAP[entry["db_id"]] = entry


def get_schema_for_db(db_name: str) -> str:
    """Gets DDL schema for a database name (from local sqlite or tables.json)."""
    # Try existing sqlite db first
    s = get_table_schema(db_name)
    if s:
        return s
    entry = SPIDER_TABLES_MAP.get(db_name)
    if not entry:
        return ""
    tables_orig = entry["table_names_original"]
    cols_orig = entry["column_names_original"]
    col_types = entry["column_types"]
    ddl_statements = []
    for t_idx, t_name in enumerate(tables_orig):
        t_cols = []
        for (col_t_idx, col_name), col_type in zip(cols_orig, col_types):
            if col_t_idx == t_idx:
                t_cols.append(f'"{col_name}" {col_type.upper()}')
        ddl = f'CREATE TABLE "{t_name}" ({", ".join(t_cols)});'
        ddl_statements.append(ddl)
    return "\n".join(ddl_statements)


def format_pool_prompt(item: Dict[str, Any]) -> str:
    """Formats prompt according to task category."""
    cat = item.get("category", "")
    q = item.get("question", "").strip()

    if cat == "atomic_sql":
        db_id = item.get("db_id", "")
        return f"Database: {db_id}\nQuestion: {q}\nProvide the SQL query in ```sql ... ```."
    elif cat == "atomic_math":
        return f"Task: {q}\nReason step by step and give your final answer as a number after '#### '."
    elif cat == "atomic_qa":
        return f"{q}\nAnswer with the letter of the correct choice (A, B, C, or D)."
    elif cat == "atomic_code":
        return q
    elif cat in ("compound_solvable", "compound_tool_required"):
        return f"Task: {q}\nReason step by step and provide the final numeric answer inside \\boxed{{...}} or as 'Final Answer: <number>'."
    return q


# =========================================================================
# ROUTE DEFINITIONS
# =========================================================================

def route_direct_reasoner(prompt: str) -> str:
    """Route 1: Direct Reasoner."""
    resp = call_phi([
        {"role": "system", "content": "You are a helpful, precise assistant. Reason step-by-step and provide your final answer in the requested format."},
        {"role": "user", "content": prompt}
    ], temperature=0.0, max_tokens=1024)
    return resp


def route_direct_sql(prompt: str) -> str:
    """Route 2: Direct SQL with Schema and tolerant execution."""
    db_m = re.search(r"Database:\s*([a-zA-Z0-9_\-]+)", prompt)
    db_to_use = db_m.group(1).strip() if db_m else ""
    schema = get_schema_for_db(db_to_use) if db_to_use else ""

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

    if db_to_use:
        clean_1, out_1 = execute_sql_tolerant(db_to_use, query_1, prompt_context=prompt)
        if not clean_1 and "no such table" not in str(out_1).lower():
            retry_msg = (
                f"The query failed execution with error:\n{out_1}\n"
                f"Please fix the query and provide a valid SQLite query in ```sql ... ```."
            )
            resp_2 = call_phi([
                {"role": "system", "content": direct_sql_sys},
                {"role": "user", "content": query_prompt},
                {"role": "assistant", "content": f"```sql\n{query_1}\n```"},
                {"role": "user", "content": retry_msg}
            ], temperature=0.0, max_tokens=256)
            query_2 = extract_sql_from_text(resp_2)
            return f"```sql\n{query_2}\n```"

    return f"```sql\n{query_1}\n```"


def route_code_execution(prompt: str) -> str:
    """Route 3: Python Code Execution in Sandbox."""
    if is_function_completion(prompt):
        resp = call_phi([
            {"role": "system", "content": "You are an expert Python programmer. Complete the function implementation cleanly inside ```python\n<code>\n```."},
            {"role": "user", "content": prompt}
        ], temperature=0.0, max_tokens=512)
        return resp

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
        clean_exec, out_v, v = execute_computation_code(code, retry_prompt_base=comp_prompt, timeout=5.0)

    if v:
        return f"#### {v}" if "####" in prompt else f"Final Answer: {v}"
    return resp


def route_decompose_reasoner(prompt: str) -> str:
    """Route 4: Decompose + Direct Reasoner."""
    subtasks, _ = decompose_task_model_call(prompt)
    clean_fetch, fetch_summary, fetched_val = execute_data_fetch(
        subtask_1=subtasks[0],
        color_1="SQL_DATA",
        db_name="",
        prompt=prompt
    )
    clean_down, full_down, clean_ans = execute_downstream_reasoning(
        subtasks[1], fetched_val, fetch_summary, "DIRECT_REASON", prompt
    )
    return clean_ans


def route_decompose_code(prompt: str) -> str:
    """Route 5: Decompose + Code Sandbox Execution."""
    subtasks, _ = decompose_task_model_call(prompt)
    clean_fetch, fetch_summary, fetched_val = execute_data_fetch(
        subtask_1=subtasks[0],
        color_1="SQL_DATA",
        db_name="",
        prompt=prompt
    )
    down_prompt = (
        f"Task: {prompt}\n\n"
        f"Retrieved Context:\n{fetch_summary}\n\n"
        f"Step to Complete:\n{subtasks[1]}\n\n"
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
        clean_exec, out_v, v = execute_computation_code(code, retry_prompt_base=down_prompt, timeout=5.0)

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


# =========================================================================
# POOL SCORER
# =========================================================================

def score_pool_item(item: Dict[str, Any], ans: str) -> bool:
    """Determines binary pass/fail for a pool item given its answer string."""
    cat = item.get("category", "")
    chk = item.get("checker_type", "")

    if chk == "sql_query":
        # Extract query from ans
        q_m = re.search(r"```sql\s*(.*?)\s*```", ans, re.DOTALL | re.IGNORECASE)
        q_str = q_m.group(1).strip() if q_m else ans.strip()
        gold_q = item.get("gold_query", "").strip()

        # Check normalization match
        def norm_sql(s):
            s = re.sub(r"\s+", " ", s.lower().replace(";", "").strip())
            return s
        if norm_sql(q_str) == norm_sql(gold_q):
            return True

        # Test execution on in-memory schema
        db_id = item.get("db_id", "")
        schema = get_schema_for_db(db_id)
        if schema:
            try:
                conn = sqlite3.connect(":memory:")
                for stmt in schema.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        conn.execute(stmt)
                # Test syntax execution
                cur = conn.cursor()
                cur.execute(q_str)
                # Valid syntax that executes on schema
                conn.close()
                # Check for major keyword match
                gold_selects = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", norm_sql(gold_q)))
                pred_selects = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", norm_sql(q_str)))
                jaccard = len(gold_selects & pred_selects) / max(1, len(gold_selects | pred_selects))
                return jaccard >= 0.5
            except Exception:
                return False
        return False

    elif chk == "numeric" or cat == "atomic_math":
        gold_val = str(item.get("gold_answer", "")).strip()
        passed, _, _ = check_math_subtask("pool_math", ans, gold_val)
        return bool(passed)

    elif chk == "multiple_choice" or cat == "atomic_qa":
        key = str(item.get("answer_key", "")).strip().upper()
        passed, _, _ = check_qa_subtask("pool_qa", ans, key)
        return bool(passed)

    elif chk == "code_execution" or cat == "atomic_code":
        # Extract code
        code_m = re.search(r"```python\s*(.*?)\s*```", ans, re.DOTALL | re.IGNORECASE)
        code = code_m.group(1).strip() if code_m else ans.strip()
        tests = "\n".join(item.get("test_list", []))
        full_script = f"{code}\n{tests}\nprint('PASS')"
        res = execute_python_code(full_script, timeout_seconds=6.0)
        return bool(res.exit_code == 0 and "PASS" in res.stdout)

    elif chk == "exact_match" or "compound" in cat:
        gold_val = str(item.get("gold_answer", "")).strip()
        passed, _, _ = check_math_subtask("pool_compound", ans, gold_val)
        return bool(passed)

    return False


def main():
    print("=" * 80)
    print("EVALUATING ROUTER TRAINING POOL ACROSS 5 CANONICAL ROUTES")
    print(f"Target Pool: {POOL_PATH} (500 items x 5 routes = 2,500 pairs)")
    print("=" * 80)

    if not os.path.exists(POOL_PATH):
        raise FileNotFoundError(f"Training pool not found at: {POOL_PATH}")

    with open(POOL_PATH, "r", encoding="utf-8") as f:
        pool_items = json.load(f)

    # Load existing records for resume capability
    existing_records = {}
    if os.path.exists(OUT_RECORDS_PATH):
        with open(OUT_RECORDS_PATH, "r", encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    r = json.loads(l)
                    existing_records[(r["pool_id"], r["route"])] = r
    print(f"Loaded {len(existing_records)} existing records from {OUT_RECORDS_PATH}")

    pending_tasks = []
    for it in pool_items:
        pid = it["pool_id"]
        for route_name, route_fn in ROUTES:
            if (pid, route_name) not in existing_records:
                pending_tasks.append((it, route_name, route_fn))

    # Interleave pending tasks across categories for rapid balanced cross-category coverage
    tasks_by_cat = {}
    for t in pending_tasks:
        cat = t[0]["category"]
        if cat not in tasks_by_cat:
            tasks_by_cat[cat] = []
        tasks_by_cat[cat].append(t)

    interleaved = []
    max_len = max(len(v) for v in tasks_by_cat.values()) if tasks_by_cat else 0
    for idx in range(max_len):
        for cat in sorted(tasks_by_cat.keys()):
            if idx < len(tasks_by_cat[cat]):
                interleaved.append(tasks_by_cat[cat][idx])
    pending_tasks = interleaved

    print(f"Total pending tasks to run: {len(pending_tasks)} with max_workers=3 (interleaved across {len(tasks_by_cat)} categories)")

    def process_task(task_info):
        it, route_name, route_fn = task_info
        pid = it["pool_id"]
        cat = it["category"]
        prompt = format_pool_prompt(it)

        t0 = time.time()
        try:
            ans = route_fn(prompt)
        except Exception as ex:
            ans = f"ERROR: {ex}"
        dt = time.time() - t0

        passed = score_pool_item(it, ans)

        rec = {
            "pool_id": pid,
            "original_id": it.get("original_id", pid),
            "category": cat,
            "route": route_name,
            "final_answer": ans[:500],
            "passed": passed,
            "duration": round(dt, 2),
            "source": "pool_run"
        }
        return rec

    done_count = len(existing_records)
    total_pairs = len(pool_items) * len(ROUTES)

    os.makedirs(os.path.dirname(OUT_RECORDS_PATH), exist_ok=True)
    with open(OUT_RECORDS_PATH, "a", encoding="utf-8") as out_f:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(process_task, t) for t in pending_tasks]
            for f in as_completed(futures):
                rec = f.result()
                out_f.write(json.dumps(rec) + "\n")
                out_f.flush()
                existing_records[(rec["pool_id"], rec["route"])] = rec
                done_count += 1
                if done_count % 10 == 0 or done_count == total_pairs:
                    print(f"[{done_count}/{total_pairs}] {rec['pool_id']} [{rec['category']}] -> {rec['route']}: passed={rec['passed']} ({rec['duration']}s)")

    # Analyze pool matrix
    route_passes = {r[0]: 0 for r in ROUTES}
    route_durations = {r[0]: [] for r in ROUTES}
    item_oracle = {}

    for it in pool_items:
        pid = it["pool_id"]
        any_pass = False
        for route_name, _ in ROUTES:
            rec = existing_records.get((pid, route_name))
            if rec and rec["passed"]:
                route_passes[route_name] += 1
                any_pass = True
            if rec:
                route_durations[route_name].append(rec["duration"])
        item_oracle[pid] = any_pass

    oracle_count = sum(1 for v in item_oracle.values() if v)
    oracle_acc = oracle_count / len(pool_items) * 100.0

    print("\n" + "=" * 80)
    print("POOL ROUTE MATRIX SUMMARY")
    print("=" * 80)
    print(f"Oracle Accuracy across 500 pool items: {oracle_count}/500 ({oracle_acc:.2f}%)")
    for route_name, _ in ROUTES:
        acc = route_passes[route_name] / len(pool_items) * 100.0
        mean_dur = sum(route_durations[route_name]) / max(1, len(route_durations[route_name]))
        print(f"  - {route_name:22s}: {route_passes[route_name]}/500 ({acc:.1f}%), mean latency: {mean_dur:.2f}s")

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_items": len(pool_items),
        "oracle_accuracy_pct": oracle_acc,
        "per_route_accuracy": {r[0]: route_passes[r[0]] for r in ROUTES},
        "per_route_mean_duration": {r[0]: round(sum(route_durations[r[0]]) / max(1, len(route_durations[r[0]])), 2) for r in ROUTES}
    }
    with open(OUT_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written to: {OUT_SUMMARY_PATH}")


if __name__ == "__main__":
    main()

