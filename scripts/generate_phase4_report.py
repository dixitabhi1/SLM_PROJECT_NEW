"""
Phase 4 Dev Evaluation Report Generator.

Extracts objective, unmanipulated results directly from append-only JSONL files on disk:
- results/phase4/c0_phi4_mini_dev_records.jsonl
- results/phase4/b0_qwen27b_dev_records.jsonl
- results/phase4/b0_gpt120b_dev_records.jsonl
- results/phase4/corrections.jsonl (if present)

Computes:
1. Stratum Accuracy Table (Atomic, Compound Solvable-without-tools, Compound Tool-required, 2-stage, 3-stage, Track B, Overall Dev)
   - Sample size n
   - Truncations count
   - Valid Accuracy (%) + 95% Bootstrap CI
   - Total Accuracy (%) + 95% Bootstrap CI (where truncated / failed count as 0)
2. Difficulty Gate Verdicts (strictly evaluated on Total Accuracy):
   - Gate 1: C0 Compound Total Acc <= 60.0%
   - Gate 2: Baseline B0 Compound Solvable-without-tools Total Acc <= 90.0%
3. Empirical Groq Quota Plan for B1 based on measured tokens and rate-limit headers.
"""

import os
import sys
import json
import random
import time
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.eval.subtask_checkers import evaluate_subtask
from src.eval.fact_checklist_scorer import score_fact_checklist
from src.audit.audit_rules import audit_results_journal

RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")


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


def load_and_dedup_records(file_path: str, max_budget: int = 2048) -> List[Dict[str, Any]]:
    """Loads records, keeping latest record per item_id matching max_budget."""
    if not os.path.exists(file_path):
        return []
    records_by_id = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("max_tokens_budget") == max_budget:
                    records_by_id[rec["item_id"]] = rec
            except Exception:
                pass
    return list(records_by_id.values())


def load_corrections(corr_path: str) -> Dict[Tuple[str, str], Any]:
    """Loads corrections from corrections.jsonl keyed by (target_file_basename, item_id)."""
    corrections = {}
    if not os.path.exists(corr_path):
        return corrections
    with open(corr_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    c = json.loads(line.strip())
                    key = (os.path.basename(c.get("target_file", "")), c.get("item_id"))
                    corrections[key] = c
                except Exception:
                    pass
    return corrections


def compute_stratum_metrics(records: List[Dict[str, Any]], corrections: Dict[Tuple[str, str], Any] = None, filename: str = "") -> Dict[str, Any]:
    """Computes stratum metrics with both valid-only and total accuracy."""
    corrections = corrections or {}
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
        subset = [r for r in records if filter_fn(r)]
        n_total = len(subset)
        if n_total == 0:
            continue

        valid_subset = [r for r in subset if r["status"] == "COMPLETE" and not r["truncated"]]
        n_valid = len(valid_subset)
        n_failed = len([r for r in subset if r["status"] == "FAILED"])
        n_truncated = len([r for r in subset if r["truncated"]])

        # Check effective pass status considering corrections
        def is_passed(r):
            key = (filename, r.get("item_id"))
            if key in corrections and corrections[key].get("field") == "passed":
                return corrections[key]["new_value"]
            return r.get("passed", False)

        valid_scores = [1.0 if is_passed(r) else 0.0 for r in valid_subset]
        acc_valid = round((sum(valid_scores) / n_valid * 100), 2) if n_valid > 0 else 0.0
        ci_valid = bootstrap_ci(valid_scores) if n_valid > 0 else (0.0, 0.0)

        total_scores = [1.0 if (r["status"] == "COMPLETE" and not r["truncated"] and is_passed(r)) else 0.0 for r in subset]
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


def main():
    c0_file = "c0_phi4_mini_dev_records.jsonl"
    qwen_file = "b0_qwen27b_dev_records.jsonl"
    gpt_file = "b0_gpt120b_dev_records.jsonl"
    corr_file = os.path.join(RESULTS_DIR, "corrections.jsonl")

    corrections = load_corrections(corr_file)

    c0_records = load_and_dedup_records(os.path.join(RESULTS_DIR, c0_file), 2048)
    qwen_records = load_and_dedup_records(os.path.join(RESULTS_DIR, qwen_file), 2048)
    gpt_records = load_and_dedup_records(os.path.join(RESULTS_DIR, gpt_file), 2048)

    print(f"Loaded C0 records (2048 tokens): {len(c0_records)}")
    print(f"Loaded Qwen-27B records (2048 tokens): {len(qwen_records)}")
    print(f"Loaded GPT-120B records (2048 tokens): {len(gpt_records)}")

    if len(c0_records) < 150 or len(qwen_records) < 150 or len(gpt_records) < 150:
        print(f"WAITING: Runs not yet fully completed. C0: {len(c0_records)}/150, Qwen: {len(qwen_records)}/150, GPT: {len(gpt_records)}/150.")
        return

    c0_metrics = compute_stratum_metrics(c0_records, corrections, c0_file)
    qwen_metrics = compute_stratum_metrics(qwen_records, corrections, qwen_file)
    gpt_metrics = compute_stratum_metrics(gpt_records, corrections, gpt_file)

    # Difficulty Gates (evaluated strictly on TOTAL accuracy)
    c0_comp_total = c0_metrics["compound_all"]["acc_total"]
    gate1_pass = (c0_comp_total <= 60.0)

    qwen_solv_total = qwen_metrics["compound_solvable_without_tools"]["acc_total"]
    gpt_solv_total = gpt_metrics["compound_solvable_without_tools"]["acc_total"]
    gate2_qwen_pass = (qwen_solv_total <= 90.0)
    gate2_gpt_pass = (gpt_solv_total <= 90.0)
    gate2_pass = (gate2_qwen_pass and gate2_gpt_pass)
    overall_gate_pass = (gate1_pass and gate2_pass)

    print("\n=======================================================")
    print("DIFFICULTY GATE VERDICT (EVALUATED ON TOTAL ACCURACY)")
    print("=======================================================")
    print(f"Gate 1: C0 Compound Total Accuracy <= 60.0% -> {c0_comp_total}% [{'PASS' if gate1_pass else 'FAIL'}]")
    print(f"Gate 2: B0 Qwen Solvable-without-tools <= 90.0% -> {qwen_solv_total}% [{'PASS' if gate2_qwen_pass else 'FAIL'}]")
    print(f"Gate 2: B0 GPT Solvable-without-tools <= 90.0% -> {gpt_solv_total}% [{'PASS' if gate2_gpt_pass else 'FAIL'}]")
    print(f"Overall Difficulty Gate: [{'PASS' if overall_gate_pass else 'FAIL'}]")

    # Generate JSON summary
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "budget_tokens": 2048,
        "gates": {
            "gate1_c0_compound_acc": c0_comp_total,
            "gate1_threshold": 60.0,
            "gate1_pass": gate1_pass,
            "gate2_qwen_solvable_acc": qwen_solv_total,
            "gate2_gpt_solvable_acc": gpt_solv_total,
            "gate2_threshold": 90.0,
            "gate2_pass": gate2_pass,
            "overall_pass": overall_gate_pass
        },
        "c0_phi4_mini": c0_metrics,
        "b0_qwen27b": qwen_metrics,
        "b0_gpt120b": gpt_metrics
    }

    out_json = os.path.join(RESULTS_DIR, "phase4_dev_complete_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote full report to {out_json}")


if __name__ == "__main__":
    main()

