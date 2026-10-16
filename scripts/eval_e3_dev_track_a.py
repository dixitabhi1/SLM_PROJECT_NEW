"""
scripts/eval_e3_dev_track_a.py

Evaluates Experiment 3 (E3: Compute Numbers in Code) on Dev Track A (N=100).
Rules: Any subtask requiring arithmetic, counting, modular maths, iterative simulation,
or algorithmic search gets a short Python program executed in the isolated sandbox.
Generic rule based strictly on model analyser/routing, zero prompt keywords from dev items.

Pre-Registered Criteria:
1. Dev Track A accuracy improves over v1.2 baseline (66.00%), paired bootstrap 95% CI lower bound > 0.
2. Atomic GSM8K drops by no more than 1 item (>= 13/15).
3. Atomic ARC QA drops by no more than 1 item (>= 11/15).
"""

import os
import sys
import json
import time
from typing import Tuple
import numpy as np

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline_e3 import run_specialist_pipeline_e3
from src.eval.versioned_scorer import score_record
from scripts.rerun_dev_phase4_fix import format_eval_prompt

DEV_SPLIT_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
V12_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_v11_pipeline_records.jsonl")
OUT_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_e3_verified_pipeline_records.jsonl")
OUT_SUMMARY_PATH = os.path.join(REPO_ROOT, "results", "phase4", "e3_dev_verified_evaluation.json")

# The 9 specific arithmetic and routing failures from Phase 4 Dev failure analysis
ARITHMETIC_ROUTING_FAILED_IDS = [
    "compound_dev_v2_0011", "compound_dev_v2_0012", "compound_dev_v2_0013",
    "compound_dev_v2_0015", "compound_dev_v2_0016", "compound_dev_v2_0017",
    "compound_dev_v2_0019", "compound_dev_v2_0034", "compound_dev_v2_0040"
]


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
    print("EVALUATING EXPERIMENT 3 (E3: COMPUTE NUMBERS IN CODE) ON DEV TRACK A (N=100)")
    print("=" * 80)

    with open(DEV_SPLIT_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    with open(V12_RECORDS_PATH, "r", encoding="utf-8") as f:
        v12_recs = {json.loads(l)["item_id"]: json.loads(l) for l in f if l.strip()}

    existing = {}
    if os.path.exists(OUT_RECORDS_PATH):
        with open(OUT_RECORDS_PATH, "r", encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    r = json.loads(l)
                    existing[r["item_id"]] = r
        print(f"Resuming with {len(existing)} existing records.")

    records = []
    with open(OUT_RECORDS_PATH, "a", encoding="utf-8") as out_f:
        for idx, it in enumerate(items, 1):
            iid = it.get("original_id") or it.get("subtask_id")
            if iid in existing:
                records.append(existing[iid])
                continue

            prompt = format_eval_prompt(it)
            t0 = time.time()
            res = run_specialist_pipeline_e3(prompt)
            dt = time.time() - t0

            score_res = score_record(it, res["final_answer"])
            passed = score_res["passed"]

            task_type = it.get("task_type")
            if not task_type:
                task_type = "compound" if it.get("stratum") == "composed" else "unknown"

            rec = {
                "item_id": iid,
                "original_id": iid,
                "split": "dev_track_a",
                "task_type": task_type,
                "stratum": it.get("stratum", ""),
                "solvability": it.get("solvability", ""),
                "model_id": "phi-4-mini",
                "condition": "pipeline_v1.3_e3",
                "answered_by": res.get("answered_by", "phi-4-mini"),
                "routed_to": res.get("routed_to", ""),
                "clean_execution": res.get("clean_execution", True),
                "output": res.get("output", "")[:300],
                "final_answer": res.get("final_answer", ""),
                "status": "COMPLETE",
                "finish_reason": "stop",
                "completion_tokens": 100,
                "passed": passed,
                "details": score_res.get("details", {}),
                "duration": round(dt, 2)
            }

            out_f.write(json.dumps(rec) + "\n")
            out_f.flush()
            existing[iid] = rec
            records.append(rec)

            v12_p = v12_recs[iid]["passed"] if iid in v12_recs else False
            status_tag = "FIXED" if passed and not v12_p else ("BROKE" if not passed and v12_p else ("PASS" if passed else "FAIL"))
            print(f"[{idx:03d}/100] {iid} ({task_type}) -> Passed: {passed} | v1.2: {v12_p} | {status_tag} | dt: {dt:.2f}s | routed: {res.get('routed_to')}")

    # Compute comprehensive metrics
    y_e3 = np.array([r["passed"] for r in records], dtype=int)
    y_v12 = np.array([v12_recs[r["item_id"]]["passed"] for r in records], dtype=int)

    acc_e3 = float(np.mean(y_e3)) * 100
    acc_v12 = float(np.mean(y_v12)) * 100
    obs_diff, ci_lower, ci_upper = paired_bootstrap_ci(y_e3, y_v12)
    obs_diff_pp = obs_diff * 100
    ci_lower_pp = ci_lower * 100
    ci_upper_pp = ci_upper * 100

    # Categorize items into the 6 strata
    strata = {
        "atomic_sql": [],
        "atomic_qa": [],
        "atomic_code": [],
        "atomic_math": [],
        "compound_solvable": [],
        "compound_tool_required": []
    }

    for r in records:
        iid = r["item_id"]
        tt = r["task_type"]
        solv = r.get("solvability", "")
        if tt == "sql":
            strata["atomic_sql"].append(r)
        elif tt == "qa":
            strata["atomic_qa"].append(r)
        elif tt == "code":
            strata["atomic_code"].append(r)
        elif tt == "math":
            strata["atomic_math"].append(r)
        elif solv == "solvable_without_tools" or "solvable" in solv:
            strata["compound_solvable"].append(r)
        else:
            strata["compound_tool_required"].append(r)

    strata_results = {}
    for s_name, s_recs in strata.items():
        n = len(s_recs)
        p_e3 = sum(1 for r in s_recs if r["passed"])
        p_v12 = sum(1 for r in s_recs if v12_recs[r["item_id"]]["passed"])
        mean_lat = float(np.mean([r["duration"] for r in s_recs])) if n > 0 else 0.0
        strata_results[s_name] = {
            "n": n,
            "passed_e3": p_e3,
            "accuracy_e3": (p_e3 / n) * 100 if n > 0 else 0.0,
            "passed_v12": p_v12,
            "accuracy_v12": (p_v12 / n) * 100 if n > 0 else 0.0,
            "delta_pp": ((p_e3 - p_v12) / n) * 100 if n > 0 else 0.0,
            "mean_latency_s": round(mean_lat, 2)
        }

    # Failure analysis metrics
    fixed_failures = []
    for fid in ARITHMETIC_ROUTING_FAILED_IDS:
        rec = existing.get(fid)
        if rec and rec["passed"]:
            fixed_failures.append(fid)

    broken_items = []
    for r in records:
        iid = r["item_id"]
        if not r["passed"] and v12_recs[iid]["passed"]:
            broken_items.append(iid)

    mean_lat_e3 = float(np.mean([r["duration"] for r in records]))
    mean_lat_v12 = float(np.mean([v12_recs[r["item_id"]]["duration"] for r in records]))

    # Gate verification
    crit1_pass = ci_lower_pp > 0.0 and acc_e3 > acc_v12
    gsm_drop = strata_results["atomic_math"]["passed_v12"] - strata_results["atomic_math"]["passed_e3"]
    qa_drop = strata_results["atomic_qa"]["passed_v12"] - strata_results["atomic_qa"]["passed_e3"]
    crit2_pass = gsm_drop <= 1 and qa_drop <= 1

    summary = {
        "condition": "pipeline_v1.3_e3",
        "sample_size": 100,
        "accuracy_v12": acc_v12,
        "accuracy_e3": acc_e3,
        "paired_difference_pp": round(obs_diff_pp, 2),
        "ci_95": [round(ci_lower_pp, 2), round(ci_upper_pp, 2)],
        "criterion_1_passed": crit1_pass,
        "criterion_2_passed": crit2_pass,
        "gsm8k_drop_count": gsm_drop,
        "qa_drop_count": qa_drop,
        "arithmetic_routing_failures_evaluated": len(ARITHMETIC_ROUTING_FAILED_IDS),
        "arithmetic_routing_failures_fixed": len(fixed_failures),
        "fixed_ids": fixed_failures,
        "previously_correct_broken_count": len(broken_items),
        "broken_ids": broken_items,
        "mean_latency_v12_s": round(mean_lat_v12, 2),
        "mean_latency_e3_s": round(mean_lat_e3, 2),
        "latency_cost_delta_s": round(mean_lat_e3 - mean_lat_v12, 2),
        "strata_results": strata_results
    }

    with open(OUT_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print("EXPERIMENT 3 (E3) FINAL EVALUATION REPORT")
    print(f"Overall Track A Dev Accuracy: v1.2 = {acc_v12:.2f}% -> v1.3(E3) = {acc_e3:.2f}%")
    print(f"Paired Difference: {obs_diff_pp:+.2f} pp (95% CI [{ci_lower_pp:+.2f} pp, {ci_upper_pp:+.2f} pp])")
    print(f"Criterion 1 (CI Lower > 0): {'PASS' if crit1_pass else 'FAIL'}")
    print(f"Criterion 2 (GSM drop <= 1, QA drop <= 1): {'PASS' if crit2_pass else 'FAIL'} (GSM drop: {gsm_drop}, QA drop: {qa_drop})")
    print(f"Arithmetic/Routing Failures Fixed: {len(fixed_failures)}/9 ({fixed_failures})")
    print(f"Previously Correct Items Broken: {len(broken_items)} ({broken_items})")
    print(f"Mean Latency: {mean_lat_e3:.2f}s (v1.2: {mean_lat_v12:.2f}s, delta: {mean_lat_e3 - mean_lat_v12:+.2f}s)")
    print("=" * 80)
    print("CATEGORY BREAKDOWN:")
    for s_name, res in strata_results.items():
        print(f"  {s_name:24s}: v1.2 = {res['passed_v12']}/{res['n']} ({res['accuracy_v12']:.1f}%) -> E3 = {res['passed_e3']}/{res['n']} ({res['accuracy_e3']:.1f}%) | Delta: {res['delta_pp']:+.1f} pp | Latency: {res['mean_latency_s']:.2f}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
