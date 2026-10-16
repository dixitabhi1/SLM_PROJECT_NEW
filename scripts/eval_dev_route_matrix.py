"""
scripts/eval_dev_route_matrix.py

Headroom evaluation for Experiment 4 (Learned Router):
Evaluates all 100 Dev Track A items across the 5 canonical pipeline routes:
1. direct_reasoner
2. direct_sql
3. code_execution
4. decompose_reasoner
5. decompose_code

Preloads verified records from frozen baseline/dev runs where identical,
then executes all remaining (item_id, route) pairs live via llama-server (port 8080).
Calculates individual route accuracies, v1.3 accuracy, and Oracle accuracy
(best route chosen per item). If Oracle - v1.3 < 5.0 pp, E4 is not viable.

Outputs:
- Raw records (append-only): results/phase4/dev_route_headroom_records.jsonl
- Summary report JSON: results/phase4/dev_route_headroom_summary.json
"""

import os
import sys
import re
import json
import time
from typing import Dict, Any, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import (
    call_phi,
    get_table_schema,
    execute_sql_tolerant,
    extract_sql_from_text,
    decompose_task_model_call,
    color_subtasks_with_feedback,
    execute_data_fetch,
    execute_downstream_reasoning,
    KNOWN_DATABASES
)
from src.pipeline.specialist_pipeline_e3 import (
    is_function_completion,
    execute_computation_code
)
from src.eval.versioned_scorer import score_record
from scripts.rerun_dev_phase4_fix import format_eval_prompt

DEV_TRACK_A_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
OUT_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_route_headroom_records.jsonl")
OUT_SUMMARY_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_route_headroom_summary.json")

# Verified historical run paths
C0_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_rerun_clean_c0_records.jsonl")
V13_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_e3_v2_pipeline_records.jsonl")
V11_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_v11_pipeline_records.jsonl")


def get_item_id(it: Dict[str, Any]) -> str:
    return (
        it.get("original_id")
        or it.get("compound_id")
        or it.get("question_id")
        or it.get("subtask_id")
        or it.get("item_id")
    )


def get_category(it: Dict[str, Any]) -> str:
    stratum = it.get("stratum", "")
    task_type = it.get("task_type", "")
    solvability = it.get("solvability", "")

    if stratum == "atomic":
        return f"atomic_{task_type}"
    if stratum in ("compound", "composed"):
        if solvability in ("tool-required", "tool_required") or "treq" in str(solvability):
            return "compound_tool_required"
        elif solvability in ("solvable_without_tools", "solvable") or "solv" in str(solvability):
            return "compound_solvable"
        return f"compound_{solvability}"
    return stratum or task_type


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
    db_to_use = ""
    for db in KNOWN_DATABASES:
        if db.lower() in prompt.lower():
            db_to_use = db
            break
    if not db_to_use:
        query_prompt = prompt
    else:
        schema_str = get_table_schema(db_to_use)
        if "[database schema:" not in prompt.lower() and schema_str:
            query_prompt = f"Database: {db_to_use}\nSchema:\n{schema_str}\n\n{prompt}"
        else:
            query_prompt = prompt

    direct_sql_sys = (
        "You are an expert SQL assistant. Given the database schema and question, write a single valid SQLite query that answers the question.\n"
        "Guidelines:\n"
        "- Return ONLY the exact column(s) requested by the question. Do not include auxiliary count or aggregate columns in the SELECT clause unless explicitly asked.\n"
        "- Ensure necessary table joins are included when attributes belong to relational tables.\n"
        "- Output strictly the SQL query enclosed in ```sql\n<query>\n```. Do not provide conversational explanations."
    )
    resp_1 = call_phi([
        {"role": "system", "content": direct_sql_sys},
        {"role": "user", "content": query_prompt}
    ], temperature=0.0, max_tokens=256)
    query_1 = extract_sql_from_text(resp_1)

    if db_to_use:
        clean_1, out_1 = execute_sql_tolerant(db_to_use, query_1, prompt_context=prompt)
        if not clean_1:
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


def preload_historical_records(dev_ids: set, id_to_cat: Dict[str, str]) -> Dict[tuple, Dict[str, Any]]:
    """Loads pre-existing verified records from C0, v1.3, and v1.1 dev runs."""
    preloaded = {}

    # 1. C0: Direct reasoner across all 100 dev items
    if os.path.exists(C0_RECORDS_PATH):
        with open(C0_RECORDS_PATH, "r", encoding="utf-8") as f:
            for l in f:
                if not l.strip(): continue
                r = json.loads(l)
                iid = r["item_id"]
                if iid in dev_ids:
                    preloaded[(iid, "direct_reasoner")] = {
                        "item_id": iid,
                        "category": id_to_cat.get(iid, ""),
                        "route": "direct_reasoner",
                        "final_answer": r.get("output", "")[:500],
                        "passed": r["passed"],
                        "duration": r.get("duration", 0.0),
                        "source": "preloaded_c0"
                    }

    # 2. v1.3: Specific routes executed by v1.3 pipeline
    if os.path.exists(V13_RECORDS_PATH):
        with open(V13_RECORDS_PATH, "r", encoding="utf-8") as f:
            for l in f:
                if not l.strip(): continue
                r = json.loads(l)
                iid = r["item_id"]
                if iid in dev_ids:
                    rt = r.get("routed_to")
                    mapped = None
                    if rt == "direct_sql": mapped = "direct_sql"
                    elif rt in ("code_compute", "code_implementation"): mapped = "code_execution"
                    elif rt == "outside_data_code": mapped = "decompose_code"
                    elif rt == "outside_data": mapped = "decompose_reasoner"
                    elif rt == "direct": mapped = "direct_reasoner"

                    if mapped:
                        preloaded[(iid, mapped)] = {
                            "item_id": iid,
                            "category": id_to_cat.get(iid, ""),
                            "route": mapped,
                            "final_answer": r.get("final_answer", "")[:500],
                            "passed": r["passed"],
                            "duration": r.get("duration", 0.0),
                            "source": "preloaded_v13"
                        }

    # 3. v1.1: Decompose reasoner for compound items
    if os.path.exists(V11_RECORDS_PATH):
        with open(V11_RECORDS_PATH, "r", encoding="utf-8") as f:
            for l in f:
                if not l.strip(): continue
                r = json.loads(l)
                iid = r["item_id"]
                if iid in dev_ids and r.get("routed_to") == "outside_data":
                    preloaded[(iid, "decompose_reasoner")] = {
                        "item_id": iid,
                        "category": id_to_cat.get(iid, ""),
                        "route": "decompose_reasoner",
                        "final_answer": r.get("final_answer", "")[:500],
                        "passed": r["passed"],
                        "duration": r.get("duration", 0.0),
                        "source": "preloaded_v11"
                    }

    return preloaded


def main():
    print("=" * 80)
    print("EXPERIMENT 4 (LEARNED ROUTER): STEP 0 HEADROOM CHECK")
    print("Evaluating 100 Dev Track A Items across 5 Routes")
    print("=" * 80)

    with open(DEV_TRACK_A_PATH, "r", encoding="utf-8") as f:
        dev_items = json.load(f)

    id_to_cat = {get_item_id(it): get_category(it) for it in dev_items}
    dev_ids = set(id_to_cat.keys())

    # Preload records from disk if existing records file doesn't exist
    existing_records = {}
    if os.path.exists(OUT_RECORDS_PATH):
        with open(OUT_RECORDS_PATH, "r", encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    r = json.loads(l)
                    existing_records[(r["item_id"], r["route"])] = r
        print(f"Loaded {len(existing_records)} existing records from {OUT_RECORDS_PATH}.")
    else:
        # Preload historical verified runs
        preloaded = preload_historical_records(dev_ids, id_to_cat)
        print(f"Preloaded {len(preloaded)} verified records from historical runs.")
        with open(OUT_RECORDS_PATH, "w", encoding="utf-8") as f:
            for rec in preloaded.values():
                f.write(json.dumps(rec) + "\n")
        existing_records = preloaded

    total_pairs = len(dev_items) * len(ROUTES)
    done_count = len(existing_records)
    print(f"Total pairs: {total_pairs}. Completed so far: {done_count}. Remaining to run: {total_pairs - done_count}.")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    pending_tasks = []
    for it in dev_items:
        iid = get_item_id(it)
        for route_name, route_fn in ROUTES:
            if (iid, route_name) not in existing_records:
                pending_tasks.append((it, route_name, route_fn))

    print(f"Total pending tasks to run: {len(pending_tasks)} with max_workers=3")

    def process_task(task_info):
        it, route_name, route_fn = task_info
        iid = get_item_id(it)
        cat = id_to_cat[iid]
        prompt = format_eval_prompt(it)

        t0 = time.time()
        try:
            ans = route_fn(prompt)
        except Exception as ex:
            ans = f"ERROR: {ex}"
        dt = time.time() - t0

        score = score_record(it, ans)
        passed = score["passed"]

        rec = {
            "item_id": iid,
            "category": cat,
            "route": route_name,
            "final_answer": ans[:500],
            "passed": passed,
            "duration": round(dt, 2),
            "source": "live_run"
        }
        return rec

    with open(OUT_RECORDS_PATH, "a", encoding="utf-8") as out_f:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(process_task, t) for t in pending_tasks]
            for f in as_completed(futures):
                rec = f.result()
                out_f.write(json.dumps(rec) + "\n")
                out_f.flush()
                existing_records[(rec["item_id"], rec["route"])] = rec
                done_count += 1
                print(f"[{done_count}/{total_pairs}] {rec['item_id']} [{rec['category']}] -> {rec['route']}: passed={rec['passed']} ({rec['duration']}s)")

    # Analyze full matrix across 100 items
    print("\n" + "=" * 80)
    print("HEADROOM ANALYSIS")
    print("=" * 80)

    route_passes = {r[0]: 0 for r in ROUTES}
    route_durations = {r[0]: [] for r in ROUTES}
    item_oracle = {}
    item_best_route = {}

    for it in dev_items:
        iid = get_item_id(it)
        cat = id_to_cat[iid]
        any_pass = False
        best_rt = "none"

        for route_name, _ in ROUTES:
            rec = existing_records.get((iid, route_name))
            if rec and rec["passed"]:
                route_passes[route_name] += 1
                any_pass = True
                if best_rt == "none":
                    best_rt = route_name
            if rec:
                route_durations[route_name].append(rec["duration"])

        item_oracle[iid] = any_pass
        item_best_route[iid] = best_rt

    # Load v1.3 dev records to compare exactly
    v13_path = os.path.join(REPO_ROOT, "results", "phase4", "dev_e3_v2_pipeline_records.jsonl")
    v13_passes = 0
    v13_map = {}
    with open(v13_path, "r", encoding="utf-8") as f:
        for l in f:
            if l.strip():
                r = json.loads(l)
                if r["item_id"] in item_oracle:
                    v13_map[r["item_id"]] = r["passed"]
                    if r["passed"]:
                        v13_passes += 1

    oracle_count = sum(1 for v in item_oracle.values() if v)
    v13_acc = v13_passes / len(dev_items) * 100.0
    oracle_acc = oracle_count / len(dev_items) * 100.0
    headroom_pp = oracle_acc - v13_acc

    print(f"\nPipeline v1.3 Accuracy : {v13_passes}/{len(dev_items)} ({v13_acc:.2f}%)")
    print(f"Oracle Route Accuracy  : {oracle_count}/{len(dev_items)} ({oracle_acc:.2f}%)")
    print(f"Headroom (Oracle - v1.3): {headroom_pp:+.2f} percentage points")

    print("\nPer-Route Accuracy (Single Static Route across all 100 Dev Items):")
    for route_name, _ in ROUTES:
        acc = route_passes[route_name] / len(dev_items) * 100.0
        mean_dur = sum(route_durations[route_name]) / max(1, len(route_durations[route_name]))
        print(f"  - {route_name:22s}: {route_passes[route_name]}/100 ({acc:.1f}%), mean latency: {mean_dur:.2f}s")

    # Category breakdown for oracle vs v1.3
    cats = sorted(list(set(id_to_cat.values())))
    print("\nPer-Category Oracle vs v1.3:")
    print("| Category | Sample Size (n) | Pipeline v1.3 | Oracle | Delta |")
    print("|---|:---:|:---:|:---:|:---:|")

    cat_stats = {}
    for c in cats:
        c_iids = [i for i, cat in id_to_cat.items() if cat == c]
        c_v13 = sum(1 for i in c_iids if v13_map.get(i))
        c_orc = sum(1 for i in c_iids if item_oracle.get(i))
        tot = len(c_iids)
        cat_stats[c] = {
            "total": tot,
            "v13": c_v13,
            "oracle": c_orc,
            "delta": c_orc - c_v13
        }
        print(f"| `{c}` | {tot} | {c_v13}/{tot} ({c_v13/tot*100:.1f}%) | {c_orc}/{tot} ({c_orc/tot*100:.1f}%) | {c_orc - c_v13:+d} ({(c_orc - c_v13)/tot*100:+.1f} pp) |")

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "v13_accuracy_pct": v13_acc,
        "oracle_accuracy_pct": oracle_acc,
        "headroom_pp": headroom_pp,
        "viable_for_e4": bool(headroom_pp >= 5.0),
        "per_route_accuracy": {r[0]: route_passes[r[0]] for r in ROUTES},
        "category_breakdown": cat_stats,
        "item_best_route": item_best_route
    }

    with open(OUT_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSummary written to: {OUT_SUMMARY_PATH}")
    if headroom_pp >= 5.0:
        print(f"RESULT: PASS (Headroom {headroom_pp:+.2f} pp >= 5.0 pp). Viable for E4.")
    else:
        print(f"RESULT: STOP (Headroom {headroom_pp:+.2f} pp < 5.0 pp). E4 is NOT viable.")


if __name__ == "__main__":
    main()
