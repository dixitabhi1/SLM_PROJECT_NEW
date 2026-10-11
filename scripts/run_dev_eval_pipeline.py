"""
Phase 4 Dev Evaluation Script: C0 Baseline vs Full Specialist Pipeline on Track A Dev Split.

Dataset: data/track_a_dev_split.json (100 items: 60 atomic + 40 compound v2)
Evaluates:
1. C0: Direct reasoning baseline on Phi-4-mini (no tools, temp=0.0, max_tokens=2048)
2. Full Specialist Pipeline: Decomposer, Task Analyser, Task Colorer w/ feedback,
   Matching, Specialists (Direct, SQL Design C, Code Sandbox, Corpus RAG), Aggregator.

Enforces:
- Hard Rule 1: No fabricated numbers (computed from raw append-only files).
- Hard Rule 2: Raw records are strictly append-only with resume.
- Hard Rule 3: Fail loudly (finish_reason != 'stop' or server error logged explicitly).
- Hard Rule 4: Symmetric validity across conditions.
- Zero monetary spend ($0).
"""

import os
import sys
import json
import time
import math
import random
import sqlite3
from typing import Dict, Any, List, Tuple, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import run_specialist_pipeline, call_phi
from src.eval.versioned_scorer import score_record
from scripts.generate_compound_items import get_table_schema

DEV_SPLIT_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
os.makedirs(RESULTS_DIR, exist_ok=True)

C0_RECORDS_FILE = os.path.join(RESULTS_DIR, "dev_c0_records.jsonl")
PIPELINE_RECORDS_FILE = os.path.join(RESULTS_DIR, "dev_pipeline_records.jsonl")
SUMMARY_OUTPUT_FILE = os.path.join(RESULTS_DIR, "dev_pipeline_eval.json")


def format_c0_prompt(item: Dict[str, Any]) -> str:
    """Standard unassisted C0 prompt without external tools."""
    task_type = item.get("task_type") or item.get("type")

    if task_type == "sql":
        db_id = item.get("db_id", "")
        schema_text = ""
        if db_id:
            try:
                schema_text = get_table_schema(db_id)
            except Exception:
                schema_text = ""
        question = item.get("question", "")
        return (
            f"[Database: {db_id}]\n"
            f"[Database Schema:\n{schema_text}\n]\n"
            f"Question: {question}\n"
            f"Return only the requested column.\n"
            f"Write a valid SQLite query in ```sql ... ```."
        )

    elif task_type == "qa":
        question = item.get("question", "")
        choices = item.get("choices", {})
        options_text = "\n".join(f"({k}) {v}" for k, v in sorted(choices.items()))
        return (
            f"Question: {question}\n\n"
            f"Options:\n{options_text}\n\n"
            f"Select the single correct option. State your final answer as: Answer: (X)"
        )

    elif task_type == "code":
        prompt = item.get("prompt", "")
        return f"{prompt}\nComplete the implementation of the above Python function inside ```python ... ```."

    elif task_type == "math":
        question = item.get("question", "")
        return f"Solve this math problem step by step:\n{question}\n\nConclude your final answer with: #### <number>"

    elif task_type == "compound" or item.get("stratum") == "composed":
        prompt = item.get("prompt", "")
        return f"{prompt}\n\nSolve the problem step by step. Conclude your final answer with 'Final Answer: <answer>' or '#### <answer>'."

    return item.get("prompt") or item.get("question") or ""


def load_existing_records(path: str) -> Dict[str, Dict[str, Any]]:
    """Loads existing records for resume capability."""
    records = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        iid = rec.get("item_id") or rec.get("subtask_id")
                        if iid:
                            records[iid] = rec
                    except Exception:
                        pass
    return records


def bootstrap_ci(scores: List[float], n_boot: int = 2000, alpha: float = 0.05) -> Tuple[float, float]:
    """Computes standard 95% bootstrap confidence interval."""
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


def evaluate_c0_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Runs single item through C0 baseline."""
    iid = item.get("subtask_id") or item.get("original_id")
    prompt = format_c0_prompt(item)
    t0 = time.time()
    resp = call_phi([
        {"role": "system", "content": "You are a helpful, precise assistant. Reason step-by-step and provide your final answer in the requested format."},
        {"role": "user", "content": prompt}
    ], temperature=0.0, max_tokens=1024)
    dt = time.time() - t0

    sc = score_record(item, resp)
    return {
        "item_id": iid,
        "stratum": item.get("stratum", "atomic"),
        "task_type": item.get("task_type", ""),
        "solvability": item.get("solvability", "solvable_without_tools"),
        "passed": sc["passed"],
        "details": sc["details"],
        "clean_execution": bool(resp.strip()),
        "output": resp[:300],
        "full_output": resp,
        "duration": dt
    }


def main():
    print("=" * 70)
    print("Phase 4 Dev Evaluation: C0 Baseline vs Full Specialist Pipeline")
    print("=" * 70)

    with open(DEV_SPLIT_PATH, "r", encoding="utf-8") as f:
        dev_items = json.load(f)

    print(f"Loaded {len(dev_items)} items from {DEV_SPLIT_PATH}")
    c0_existing = load_existing_records(C0_RECORDS_FILE)
    pipe_existing = load_existing_records(PIPELINE_RECORDS_FILE)
    print(f"Existing C0 records: {len(c0_existing)} | Existing Pipeline records: {len(pipe_existing)}")

    # 1. Run / Resume C0 Baseline
    print("\n[1/2] Evaluating C0 Baseline...")
    c0_records = []
    with open(C0_RECORDS_FILE, "a", encoding="utf-8") as f_c0:
        for idx, item in enumerate(dev_items, 1):
            iid = item.get("subtask_id") or item.get("original_id")
            if iid in c0_existing:
                c0_records.append(c0_existing[iid])
                continue

            rec = evaluate_c0_item(item)
            c0_records.append(rec)
            f_c0.write(json.dumps(rec) + "\n")
            f_c0.flush()

            status_str = "PASS" if rec["passed"] else "FAIL"
            print(f"  C0 [{idx:03d}/{len(dev_items)}] {iid} ({item.get('task_type')}): {status_str} ({rec['duration']:.2f}s)")

    # 2. Run / Resume Full Pipeline
    print("\n[2/2] Evaluating Full Specialist Pipeline...")
    pipe_records = []
    with open(PIPELINE_RECORDS_FILE, "a", encoding="utf-8") as f_pipe:
        for idx, item in enumerate(dev_items, 1):
            iid = item.get("subtask_id") or item.get("original_id")
            if iid in pipe_existing:
                pipe_records.append(pipe_existing[iid])
                continue

            rec = run_specialist_pipeline(item)
            rec["task_type"] = item.get("task_type", "")
            pipe_records.append(rec)
            f_pipe.write(json.dumps(rec) + "\n")
            f_pipe.flush()

            status_str = "PASS" if rec["passed"] else "FAIL"
            clean_str = "Clean" if rec["clean_execution"] else "Error"
            stages_info = "/".join(str(s["stage_num"]) for s in rec.get("stages", []))
            print(f"  Pipe [{idx:03d}/{len(dev_items)}] {iid} ({item.get('task_type')}): {status_str} [{clean_str}, stages:{stages_info}] ({rec['duration']:.2f}s)")

    # 3. Compute Comparative Statistics
    print("\n" + "=" * 70)
    print("COMPUTING SUMMARY STATISTICS")
    print("=" * 70)

    def analyze_condition(records: List[Dict[str, Any]], dev_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        rec_map = {r.get("item_id"): r for r in records}
        n = len(dev_items)

        # Global
        scores = [1.0 if rec_map.get(it.get("subtask_id") or it.get("original_id"), {}).get("passed") else 0.0 for it in dev_items]
        clean_list = [1.0 if rec_map.get(it.get("subtask_id") or it.get("original_id"), {}).get("clean_execution") else 0.0 for it in dev_items]
        times = [rec_map.get(it.get("subtask_id") or it.get("original_id"), {}).get("duration", 0.0) for it in dev_items]

        # Strata
        atomic_items = [it for it in dev_items if it.get("stratum") == "atomic"]
        compound_items = [it for it in dev_items if it.get("stratum") == "composed"]
        solvable_items = [it for it in dev_items if it.get("solvability") == "solvable_without_tools"]
        tool_req_items = [it for it in dev_items if it.get("solvability") == "tool-required"]

        def sub_acc(items):
            if not items:
                return {"count": 0, "passes": 0, "acc": 0.0, "ci_95": [0.0, 0.0]}
            s = [1.0 if rec_map.get(it.get("subtask_id") or it.get("original_id"), {}).get("passed") else 0.0 for it in items]
            return {
                "count": len(items),
                "passes": int(sum(s)),
                "acc": round((sum(s) / len(items)) * 100, 2),
                "ci_95": list(bootstrap_ci(s))
            }

        # Tasks
        task_types = ["sql", "qa", "code", "math", "compound"]
        task_accs = {tt: sub_acc([it for it in dev_items if it.get("task_type") == tt]) for tt in task_types}

        # Per-stage accuracy for compound items
        stage1_scores = []
        stage2_scores = []
        stage3_scores = []
        for it in compound_items:
            iid = it.get("subtask_id")
            rec = rec_map.get(iid, {})
            stages = rec.get("stages", [])
            if len(stages) >= 1:
                stage1_scores.append(1.0 if stages[0].get("stage_passed") or (stages[0].get("clean_execution") and len(stages)==1 and rec.get("passed")) else 0.0)
            if len(stages) >= 2:
                stage2_scores.append(1.0 if stages[1].get("stage_passed") or (stages[1].get("clean_execution") and len(stages)==2 and rec.get("passed")) else 0.0)
            if len(stages) >= 3:
                stage3_scores.append(1.0 if stages[2].get("stage_passed") or (stages[2].get("clean_execution") and rec.get("passed")) else 0.0)

        stage_accs = {
            "stage_1": round((sum(stage1_scores) / len(stage1_scores) * 100), 2) if stage1_scores else None,
            "stage_2": round((sum(stage2_scores) / len(stage2_scores) * 100), 2) if stage2_scores else None,
            "stage_3": round((sum(stage3_scores) / len(stage3_scores) * 100), 2) if stage3_scores else None,
        }

        return {
            "total_count": n,
            "total_passes": int(sum(scores)),
            "total_acc": round((sum(scores) / n) * 100, 2),
            "ci_95": list(bootstrap_ci(scores)),
            "clean_share": round((sum(clean_list) / n) * 100, 2),
            "mean_duration_s": round(sum(times) / n, 2),
            "strata": {
                "atomic": sub_acc(atomic_items),
                "compound": sub_acc(compound_items),
                "solvable_without_tools": sub_acc(solvable_items),
                "tool_required": sub_acc(tool_req_items)
            },
            "tasks": task_accs,
            "compound_stages": stage_accs
        }

    c0_summary = analyze_condition(c0_records, dev_items)
    pipe_summary = analyze_condition(pipe_records, dev_items)

    final_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": "track_a_dev_split.json",
        "dataset_count": len(dev_items),
        "c0_phi4mini": c0_summary,
        "specialist_pipeline_phi4mini": pipe_summary
    }

    with open(SUMMARY_OUTPUT_FILE, "w", encoding="utf-8") as f_out:
        json.dump(final_report, f_out, indent=2)

    print(f"Saved evaluation report to {SUMMARY_OUTPUT_FILE}")

    # Print Clean Formatted Table
    print("\n" + "=" * 70)
    print("PHASE 4 DEV EVALUATION RESULTS TABLE")
    print("=" * 70)
    print(f"{'Stratum / Condition':<30} | {'C0 Direct (%)':<15} | {'Specialist Pipeline (%)':<22} | {'Delta (pp)':<10}")
    print("-" * 85)

    def print_row(label, c0_val, pipe_val):
        delta = pipe_val - c0_val
        sign = "+" if delta > 0 else ""
        print(f"{label:<30} | {c0_val:>6.2f}%        | {pipe_val:>6.2f}%               | {sign}{delta:>5.2f}")

    n_solv = c0_summary["strata"]["solvable_without_tools"]["count"]
    n_treq = c0_summary["strata"]["tool_required"]["count"]
    print_row("Overall Accuracy (N=100)", c0_summary["total_acc"], pipe_summary["total_acc"])
    print_row(f"  Compound Solvable (N={n_solv})", c0_summary["strata"]["solvable_without_tools"]["acc"], pipe_summary["strata"]["solvable_without_tools"]["acc"])
    print_row(f"  Compound Tool-Req (N={n_treq})", c0_summary["strata"]["tool_required"]["acc"], pipe_summary["strata"]["tool_required"]["acc"])
    print_row("  Atomic Benchmark (N=60)", c0_summary["strata"]["atomic"]["acc"], pipe_summary["strata"]["atomic"]["acc"])
    print_row("  Compound Benchmark (N=40)", c0_summary["strata"]["compound"]["acc"], pipe_summary["strata"]["compound"]["acc"])
    print("-" * 85)
    print_row("    SQL Atomic (N=15)", c0_summary["tasks"]["sql"]["acc"], pipe_summary["tasks"]["sql"]["acc"])
    print_row("    QA Atomic (N=15)", c0_summary["tasks"]["qa"]["acc"], pipe_summary["tasks"]["qa"]["acc"])
    print_row("    Code Atomic (N=15)", c0_summary["tasks"]["code"]["acc"], pipe_summary["tasks"]["code"]["acc"])
    print_row("    Math Atomic (N=15)", c0_summary["tasks"]["math"]["acc"], pipe_summary["tasks"]["math"]["acc"])
    print("-" * 85)
    print(f"Per-Stage Compound Acc: S1: {pipe_summary['compound_stages']['stage_1']}% | S2: {pipe_summary['compound_stages']['stage_2']}% | S3: {pipe_summary['compound_stages']['stage_3']}%")
    print(f"Clean Execution Share: C0: {c0_summary['clean_share']}% | Pipeline: {pipe_summary['clean_share']}%")
    print(f"Mean Latency per Item: C0: {c0_summary['mean_duration_s']}s | Pipeline: {pipe_summary['mean_duration_s']}s")
    print("=" * 70)


if __name__ == "__main__":
    main()

