"""
scripts/eval_e3_dev_full.py

Evaluates Pipeline v1.3 (E3 with generic CORPUS no-code fix) on full Dev set (N=150):
- Dev Track A (100 items): data/track_a_dev_split.json
- Dev Track B (50 items): data/track_b/track_b_dev_split.json

Tests against all three pre-registered criteria:
1. Dev Track A accuracy improves over v1.2 (66.00%), paired bootstrap 95% CI lower bound > 0.0 pp.
2. Atomic GSM8K drops by <= 1 item (>= 13/15); Atomic QA drops by <= 1 item (>= 11/15).
3. Dev Track B drops by <= 1 item (>= 47/50, v1.2 baseline 48/50 = 96.00%).

Outputs:
- Records: results/phase4/dev_e3_v2_pipeline_records.jsonl
- Summary: results/phase4/dev_e3_v2_evaluation.json
"""

import os
import sys
import json
import time
from typing import Dict, Any, List, Tuple
import numpy as np

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline_e3 import run_specialist_pipeline_e3
from src.eval.versioned_scorer import score_record
from src.eval.fact_checklist_scorer import score_fact_checklist
from scripts.rerun_dev_phase4_fix import format_eval_prompt

DEV_TRACK_A_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
DEV_TRACK_B_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_dev_split.json")
V12_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_v11_pipeline_records.jsonl")

OUT_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_e3_v2_pipeline_records.jsonl")
OUT_SUMMARY_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_e3_v2_evaluation.json")


def paired_bootstrap_ci(y_new: np.ndarray, y_old: np.ndarray, n_boot: int = 10000, seed: int = 42) -> Tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    diff = y_new - y_old
    obs_diff = float(np.mean(diff))
    boot_diffs = []
    n = len(diff)
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_diffs.append(float(np.mean(diff[idx])))
    ci_lower = float(np.percentile(boot_diffs, 2.5))
    ci_upper = float(np.percentile(boot_diffs, 97.5))
    return obs_diff, ci_lower, ci_upper


def main():
    print("=" * 80)
    print("EVALUATING PIPELINE v1.3 (E3 FIX) ON FULL DEV SET (N=150: 100 TRACK A + 50 TRACK B)")
    print("=" * 80)

    with open(DEV_TRACK_A_PATH, "r", encoding="utf-8") as f:
        items_a = json.load(f)
    with open(DEV_TRACK_B_PATH, "r", encoding="utf-8") as f:
        items_b = json.load(f)

    all_items = items_a + items_b
    print(f"Loaded {len(items_a)} Track A items and {len(items_b)} Track B items. Total: {len(all_items)}")

    # Load v1.2 baseline records
    v12_map = {}
    with open(V12_RECORDS_PATH, "r", encoding="utf-8") as f:
        for l in f:
            if l.strip():
                r = json.loads(l)
                v12_map[r["item_id"]] = r

    records = []
    with open(OUT_RECORDS_PATH, "w", encoding="utf-8") as out_f:
        for idx, it in enumerate(all_items, 1):
            is_track_b = "checklist" in it
            iid = (it.get("question_id") or it.get("subtask_id") or it.get("original_id") or it.get("item_id"))

            prompt = format_eval_prompt(it)
            t0 = time.time()
            res = run_specialist_pipeline_e3(prompt)
            dt = time.time() - t0

            if is_track_b:
                text_to_score = res.get("final_answer") or res.get("output")
                score_res = score_fact_checklist(text_to_score, it["checklist"], max_word_cap=it.get("word_cap", 75))
                passed = score_res["binary_pass"]
                task_type = "hypergrid"
                stratum = "track_b"
                solv = "tool_required"
            else:
                score_res = score_record(it, res["final_answer"])
                passed = score_res["passed"]
                task_type = it.get("task_type") or ("compound" if it.get("stratum") == "composed" else "unknown")
                stratum = it.get("stratum", "")
                solv = it.get("solvability", "")

            rec = {
                "item_id": iid,
                "original_id": iid,
                "split": "track_b_dev" if is_track_b else "track_a_dev",
                "track": "Track B" if is_track_b else "Track A",
                "task_type": task_type,
                "stratum": stratum,
                "solvability": solv,
                "model_id": "phi-4-mini",
                "condition": "pipeline_v1.3_e3_fix",
                "answered_by": res.get("answered_by", "phi-4-mini"),
                "routed_to": res.get("routed_to", ""),
                "clean_execution": res.get("clean_execution", True),
                "output": res.get("output", "")[:300],
                "final_answer": res.get("final_answer", ""),
                "status": "COMPLETE",
                "finish_reason": "stop",
                "completion_tokens": 100,
                "passed": passed,
                "details": score_res if is_track_b else score_res.get("details", {}),
                "duration": round(dt, 2)
            }
            out_f.write(json.dumps(rec) + "\n")
            out_f.flush()
            records.append(rec)

            v12_p = v12_map.get(iid, {}).get("passed")
            stat = "PASS" if passed else "FAIL"
            diff_str = f"vs v1.2: {v12_p} -> {passed}"
            print(f"[{idx:03d}/150] {iid} ({'Track B' if is_track_b else task_type}) -> {stat} | {diff_str} | routed: {res.get('routed_to')} | dt: {dt:.2f}s", flush=True)

    # 1. Track A Evaluation
    recs_a = [r for r in records if r["track"] == "Track A"]
    passed_a = sum(1 for r in recs_a if r["passed"])
    acc_a = passed_a / len(recs_a) * 100

    # 2. Track B Evaluation
    recs_b = [r for r in records if r["track"] == "Track B"]
    passed_b = sum(1 for r in recs_b if r["passed"])
    acc_b = passed_b / len(recs_b) * 100

    # 3. Paired Differences on Track A
    y_new_a = np.array([1.0 if r["passed"] else 0.0 for r in recs_a])
    y_old_a = np.array([1.0 if v12_map[r["item_id"]]["passed"] else 0.0 for r in recs_a])
    diff_a, ci_low_a, ci_high_a = paired_bootstrap_ci(y_new_a, y_old_a, n_boot=10000)

    # 4. Atomic GSM8K and ARC QA
    gsm_recs = [r for r in recs_a if r["task_type"] == "math" and r["stratum"] == "atomic"]
    qa_recs = [r for r in recs_a if r["task_type"] == "qa" and r["stratum"] == "atomic"]
    gsm_pass = sum(1 for r in gsm_recs if r["passed"])
    qa_pass = sum(1 for r in qa_recs if r["passed"])

    # 5. Check Criteria
    crit1_pass = (acc_a > 66.0 and ci_low_a > 0.0)
    crit2_pass = (gsm_pass >= 13 and qa_pass >= 11)
    crit3_pass = (passed_b >= 47)
    all_pass = (crit1_pass and crit2_pass and crit3_pass)

    summary = {
        "condition": "pipeline_v1.3_e3_fix",
        "total_items": len(records),
        "track_a": {
            "total": len(recs_a),
            "passed": passed_a,
            "accuracy": acc_a,
            "baseline_v12_acc": 66.0,
            "paired_diff_pp": round(diff_a * 100, 2),
            "ci_95_low_pp": round(ci_low_a * 100, 2),
            "ci_95_high_pp": round(ci_high_a * 100, 2)
        },
        "track_b": {
            "total": len(recs_b),
            "passed": passed_b,
            "accuracy": acc_b,
            "baseline_v12_passed": 48,
            "baseline_v12_acc": 96.0,
            "drop_items": 48 - passed_b
        },
        "atomic_checks": {
            "gsm8k": {"passed": gsm_pass, "total": len(gsm_recs), "baseline": 14},
            "arc_qa": {"passed": qa_pass, "total": len(qa_recs), "baseline": 12}
        },
        "criteria_results": {
            "criterion_1_track_a_improvement": {"status": "PASS" if crit1_pass else "FAIL", "diff_ci_low": ci_low_a * 100},
            "criterion_2_atomic_non_regression": {"status": "PASS" if crit2_pass else "FAIL", "gsm": f"{gsm_pass}/15", "qa": f"{qa_pass}/15"},
            "criterion_3_track_b_non_regression": {"status": "PASS" if crit3_pass else "FAIL", "passed": f"{passed_b}/50", "min_required": "47/50"},
            "all_criteria_passed": all_pass
        }
    }

    with open(OUT_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print("DEV EVALUATION RESULTS SUMMARY:")
    print(f"Track A Accuracy: {passed_a}/100 ({acc_a:.2f}%) | Paired Diff vs v1.2: +{diff_a*100:.2f} pp [95% CI: +{ci_low_a*100:.2f} pp, +{ci_high_a*100:.2f} pp]")
    print(f"Track B Accuracy: {passed_b}/50 ({acc_b:.2f}%) | Baseline v1.2: 48/50 (96.0%) | Delta: {passed_b - 48} items")
    print(f"Atomic GSM8K:     {gsm_pass}/15 (Baseline: 14/15)")
    print(f"Atomic ARC QA:    {qa_pass}/15 (Baseline: 12/15)")
    print("-" * 80)
    print(f"Criterion 1 (Track A CI low > 0): {'[PASS]' if crit1_pass else '[FAIL]'}")
    print(f"Criterion 2 (GSM >= 13, QA >= 11): {'[PASS]' if crit2_pass else '[FAIL]'}")
    print(f"Criterion 3 (Track B >= 47/50):   {'[PASS]' if crit3_pass else '[FAIL]'}")
    print(f"ALL THREE CRITERIA PASSED:         {'[YES]' if all_pass else '[NO]'}")
    print("=" * 80)

    if not all_pass:
        print("CRITICAL: One or more criteria failed! Halting per Hard Rule 12.")
        sys.exit(1)


if __name__ == "__main__":
    main()

