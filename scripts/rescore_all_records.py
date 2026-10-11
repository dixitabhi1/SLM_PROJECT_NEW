"""
Phase 4 Rescoring & Hand-Check Audit Script.

Uses Versioned Scorer (src/eval/versioned_scorer.py, Version 1.0.0):
1. Rescores all raw records for C0, B0-Qwen, and B0-GPT directly from immutable output strings.
2. Replaces per-item overrides with objective, unified versioned scoring.
3. Produces stratum metrics (Total, Valid, Truncated, Failed, 95% Bootstrap CIs).
4. Executes deterministic hand-check audit sampling: 10 passes and 10 fails per checker.
"""

import os
import sys
import json
import random
import hashlib
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.eval.versioned_scorer import score_record, SCORER_VERSION
from scripts.generate_phase4_report import bootstrap_ci

RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
TRACK_A_DEV_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
TRACK_B_DEV_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_dev_split.json")


def load_dev_items() -> Dict[str, Dict[str, Any]]:
    with open(TRACK_A_DEV_PATH, "r", encoding="utf-8") as f:
        track_a = json.load(f)
    with open(TRACK_B_DEV_PATH, "r", encoding="utf-8") as f:
        track_b = json.load(f)
    items_by_id = {}
    for it in track_a:
        key = it.get("subtask_id") or it.get("original_id")
        items_by_id[key] = it
    for it in track_b:
        key = it.get("question_id")
        items_by_id[key] = it
    return items_by_id


def load_latest_records(file_path: str) -> List[Dict[str, Any]]:
    """Loads latest record per item_id (so 4096-budget reruns supersede earlier rows)."""
    if not os.path.exists(file_path):
        return []
    records_by_id = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    rec = json.loads(line.strip())
                    records_by_id[rec["item_id"]] = rec
                except Exception:
                    pass
    return list(records_by_id.values())


def rescore_records(records: List[Dict[str, Any]], dev_items: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rescores every record using the versioned scorer."""
    rescored = []
    for r in records:
        it_id = r["item_id"]
        item = dev_items.get(it_id)
        if not item:
            rescored.append(r)
            continue

        output_text = r.get("output", "")
        # If model failed or was truncated, scoring depends on whether output was valid
        truncated = r.get("truncated", False)
        status = r.get("status", "")

        if status == "COMPLETE" and not truncated and output_text:
            score = score_record(item, output_text)
            passed = score["passed"]
            recall = score["recall"]
            checker = score["checker"]
            details = score["details"]
        else:
            passed = False
            recall = 0.0
            checker = "none"
            details = f"Status: {status}, Finish: {r.get('finish_reason')}, Truncated: {truncated}"

        rec = dict(r)
        rec["rescored_passed"] = passed
        rec["rescored_recall"] = recall
        rec["rescored_checker"] = checker
        rec["rescored_details"] = details
        rescored.append(rec)
    return rescored


def compute_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes all stratum metrics including total, valid, failed, truncated."""
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
        n_failed = len([r for r in subset if r["status"] == "FAILED" or r.get("truncated")])
        n_truncated = len([r for r in subset if r.get("truncated")])

        # Valid-only
        valid_scores = [1.0 if r["rescored_passed"] else 0.0 for r in valid_subset]
        acc_valid = round((sum(valid_scores) / n_valid * 100), 2) if n_valid > 0 else 0.0
        ci_valid = bootstrap_ci(valid_scores) if n_valid > 0 else (0.0, 0.0)

        # Total
        total_scores = [1.0 if (r["status"] == "COMPLETE" and not r.get("truncated") and r["rescored_passed"]) else 0.0 for r in subset]
        acc_total = round((sum(total_scores) / n_total * 100), 2)
        ci_total = bootstrap_ci(total_scores)

        # Truncation / failure rate check
        failure_rate = (n_failed / n_total * 100) if n_total > 0 else 0.0
        truncation_rate = (n_truncated / n_total * 100) if n_total > 0 else 0.0
        comparable = (failure_rate <= 2.0 and truncation_rate <= 2.0)

        results[stratum_name] = {
            "n_total": n_total,
            "n_valid": n_valid,
            "n_failed": n_failed,
            "n_truncated": n_truncated,
            "failure_rate_pct": round(failure_rate, 2),
            "truncation_rate_pct": round(truncation_rate, 2),
            "comparable_under_2pct_rule": comparable,
            "acc_valid": acc_valid,
            "ci_valid_95": ci_valid,
            "acc_total": acc_total,
            "ci_total_95": ci_total,
            "passed_count": sum(1 for s in total_scores if s == 1.0)
        }

    return results


def run_hand_check_audit(rescored_all: List[Dict[str, Any]], dev_items: Dict[str, Dict[str, Any]], seed: int = 42) -> Dict[str, Any]:
    """Samples 10 passes and 10 fails per checker for manual verification."""
    rng = random.Random(seed)
    checkers = [
        "python_sandbox_test",
        "exact_numeric_test",
        "sqlite_execution_test",
        "multiple_choice_exact_match",
        "fact_checklist_scorer"
    ]

    audit_sample = {}
    for chk in checkers:
        passes = [r for r in rescored_all if r.get("rescored_checker") == chk and r.get("rescored_passed")]
        fails = [r for r in rescored_all if (r.get("rescored_checker") == chk or (chk == "fact_checklist_scorer" and "checklist" in dev_items.get(r["item_id"], {}))) and not r.get("rescored_passed")]

        sampled_passes = rng.sample(passes, min(10, len(passes)))
        sampled_fails = rng.sample(fails, min(10, len(fails)))

        def pack_item(r):
            it = dev_items.get(r["item_id"], {})
            return {
                "item_id": r["item_id"],
                "model_id": r["model_id"],
                "checker": r.get("rescored_checker"),
                "passed": r.get("rescored_passed"),
                "checker_details": r.get("rescored_details"),
                "output_preview": r.get("output", "")[:200],
                "gold_preview": str(it.get("gold") or it.get("gold_answer") or it.get("gold_query") or it.get("checklist", []))[:100]
            }

        audit_sample[chk] = {
            "total_passes_available": len(passes),
            "sampled_passes_count": len(sampled_passes),
            "sampled_passes": [pack_item(x) for x in sampled_passes],
            "total_fails_available": len(fails),
            "sampled_fails_count": len(sampled_fails),
            "sampled_fails": [pack_item(x) for x in sampled_fails]
        }

    return audit_sample


def main():
    dev_items = load_dev_items()
    c0_records = load_latest_records(os.path.join(RESULTS_DIR, "c0_phi4_mini_dev_records.jsonl"))
    qwen_records = load_latest_records(os.path.join(RESULTS_DIR, "b0_qwen27b_dev_records.jsonl"))
    gpt_records = load_latest_records(os.path.join(RESULTS_DIR, "b0_gpt120b_dev_records.jsonl"))

    print(f"Loaded Latest Records: C0={len(c0_records)}, Qwen={len(qwen_records)}, GPT={len(gpt_records)}")

    c0_rescored = rescore_records(c0_records, dev_items)
    qwen_rescored = rescore_records(qwen_records, dev_items)
    gpt_rescored = rescore_records(gpt_records, dev_items)

    c0_metrics = compute_metrics(c0_rescored)
    qwen_metrics = compute_metrics(qwen_rescored)
    gpt_metrics = compute_metrics(gpt_rescored)

    # Scorer SHA-256
    scorer_path = os.path.join(REPO_ROOT, "src", "eval", "versioned_scorer.py")
    scorer_hash = hashlib.sha256(open(scorer_path, "rb").read()).hexdigest()

    all_rescored = c0_rescored + qwen_rescored + gpt_rescored
    hand_check_data = run_hand_check_audit(all_rescored, dev_items)

    full_rescored_report = {
        "timestamp": "2026-10-08",
        "scorer_version": SCORER_VERSION,
        "scorer_sha256": scorer_hash,
        "c0_phi4_mini": c0_metrics,
        "b0_qwen27b": qwen_metrics,
        "b0_gpt120b": gpt_metrics,
        "hand_check_audit": hand_check_data
    }

    out_file = os.path.join(RESULTS_DIR, "versioned_rescore_report.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(full_rescored_report, f, indent=2)
    print(f"Saved versioned rescore report to {out_file}")


if __name__ == "__main__":
    main()

