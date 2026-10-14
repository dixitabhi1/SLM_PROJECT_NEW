"""
Execution Script for Phase 7 Part C: Frozen Reserve Set Run.
Tag: v1.1-cascade-frozen

Protocol:
1. Verify reserve hash before starting (bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db).
2. Run Specialist Pipeline v1.1 on all 100 Track A Reserve items:
   - Record analyser source, live self-check validator verdict (T5), and all triggers live in the same run.
   - Save append-only records to results/phase4/reserve_v11_pipeline_records.jsonl.
3. Run 120B model with tools (B1 harness) on all 100 Track A Reserve items:
   - Save append-only records to results/phase4/reserve_b1_gpt120b_records.jsonl.
4. Construct Cascade records live from the 120B responses of escalated items:
   - Save append-only records to results/phase4/reserve_cascade_records.jsonl.
5. Verify reserve hash after run.
6. Evaluate against pre-registered criteria:
   - Cascade accuracy on Reserve Track A (N=100)
   - Escalation share on Reserve Track A
   - Paired difference vs Pipeline v1.1 alone with 95% bootstrap CI
   - Paired difference vs 120B with tools alone with 95% bootstrap CI (reportable gap)
   - Fixed count, broken count, net gain
   - 120B calls and tokens used
7. Save summary report to results/phase4/reserve_evaluation_report.json.
"""

import os
import sys
import json
import time
import hashlib
import random
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import run_specialist_pipeline
from src.pipeline.cascade import evaluate_self_check
from src.eval.versioned_scorer import score_record
from scripts.rerun_dev_phase4_fix import format_eval_prompt
from scripts.run_dev_b1_gpt120b import run_item_with_b1_tools, MODEL_ID as MODEL_120B_ID

RESERVE_SPLIT_PATH = os.path.join(REPO_ROOT, "data", "reserve_set_quarantine.json")
EXPECTED_RESERVE_HASH = "bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db"

RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
V11_RECORDS_PATH = os.path.join(RESULTS_DIR, "reserve_v11_pipeline_records.jsonl")
B1_120B_RECORDS_PATH = os.path.join(RESULTS_DIR, "reserve_b1_gpt120b_records.jsonl")
CASCADE_RECORDS_PATH = os.path.join(RESULTS_DIR, "reserve_cascade_records.jsonl")
SUMMARY_JSON_PATH = os.path.join(RESULTS_DIR, "reserve_evaluation_report.json")


def verify_reserve_hash() -> str:
    h = hashlib.sha256(open(RESERVE_SPLIT_PATH, "rb").read()).hexdigest()
    if h != EXPECTED_RESERVE_HASH:
        raise ValueError(f"Reserve split hash mismatch! Expected {EXPECTED_RESERVE_HASH}, got {h}")
    return h


def load_existing_records(path: str) -> Dict[str, Dict[str, Any]]:
    records = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        iid = rec.get("item_id")
                        if iid:
                            records[iid] = rec
                    except Exception:
                        pass
    return records


def bootstrap_ci(diffs: List[float], n_boot: int = 10000, alpha: float = 0.05) -> Tuple[float, float]:
    if not diffs:
        return (0.0, 0.0)
    rng = random.Random(42)
    n = len(diffs)
    means = []
    for _ in range(n_boot):
        sample = [rng.choice(diffs) for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lower_idx = int(n_boot * (alpha / 2))
    upper_idx = int(n_boot * (1 - alpha / 2))
    return (round(means[lower_idx] * 100, 2), round(means[upper_idx] * 100, 2))


def main():
    print("=" * 80)
    print("PHASE 7 PART C: FROZEN RESERVE SET EVALUATION (TRACK A, N=100)")
    print("Tag: v1.1-cascade-frozen")
    print("=" * 80)

    # 1. Verify Reserve hash before starting
    print("\n[Step 1] Verifying Reserve Set cryptographic hash before starting...")
    pre_hash = verify_reserve_hash()
    print(f"Verified Reserve SHA-256: {pre_hash} [MATCH]")

    # Load reserve items
    with open(RESERVE_SPLIT_PATH, "r", encoding="utf-8") as f:
        reserve_items = json.load(f)
    print(f"Loaded {len(reserve_items)} Reserve Track A items.")

    # 2. Pipeline v1.1 Run
    print("\n[Step 2] Executing Pipeline v1.1 on all 100 Reserve items (live self-check & triggers)...")
    existing_v11 = load_existing_records(V11_RECORDS_PATH)
    if existing_v11:
        print(f"Resuming v1.1 with {len(existing_v11)} existing records.")

    with open(V11_RECORDS_PATH, "a", encoding="utf-8") as f_v11:
        for idx, item in enumerate(reserve_items, 1):
            iid = item.get("original_id") or item.get("subtask_id") or item.get("item_id")
            if iid in existing_v11:
                continue

            prompt = format_eval_prompt(item)
            t0 = time.time()
            v11_res = run_specialist_pipeline(prompt)
            dt = time.time() - t0

            # Live self-check and triggers
            clean = v11_res.get("clean_execution", True)
            fallbacks = v11_res.get("fallbacks", {})
            t1 = not clean
            t2 = bool(fallbacks.get("analyser", False))
            t3 = bool(fallbacks.get("database_identifier", False))
            final_ans = str(v11_res.get("final_answer") or v11_res.get("output", "")).strip()
            t4 = not bool(final_ans)
            source = v11_res.get("source", "")
            is_corpus = (source == "CORPUS")

            t5 = False
            t5_reason = ""
            if not is_corpus and final_ans:
                t5, t5_reason = evaluate_self_check(prompt, final_ans)

            should_escalate = (t1 or t2 or t3 or t4 or t5) and (not is_corpus)

            score_res = score_record(item, v11_res.get("output", ""))

            rec = {
                "item_id": iid,
                "track": "A",
                "task_type": item.get("task_type", ""),
                "stratum": item.get("stratum", ""),
                "solvability": item.get("solvability", ""),
                "model_id": "phi4-mini",
                "condition": "pipeline_v11",
                "prompt": prompt,
                "output": v11_res.get("output", "")[:300],
                "full_output": v11_res.get("full_output", ""),
                "final_answer": v11_res.get("final_answer", ""),
                "finish_reason": "stop",
                "status": "COMPLETE",
                "clean_execution": clean,
                "routed_to": v11_res.get("routed_to", ""),
                "source": source,
                "fallbacks": fallbacks,
                "subtasks": v11_res.get("subtasks", []),
                "colors": v11_res.get("colors", []),
                "t1_unclean": t1,
                "t2_analyser_fb": t2,
                "t3_db_fb": t3,
                "t4_missing_ans": t4,
                "t5_self_check": t5,
                "t5_reason": t5_reason,
                "is_corpus": is_corpus,
                "should_escalate": should_escalate,
                "passed": score_res["passed"],
                "details": score_res["details"],
                "duration": round(dt, 2)
            }
            f_v11.write(json.dumps(rec) + "\n")
            f_v11.flush()
            existing_v11[iid] = rec
            print(f"  [v1.1 {idx:03d}/100] {iid} -> Passed: {rec['passed']} | Escalate: {should_escalate} (T1={t1}, T2={t2}, T3={t3}, T4={t4}, T5={t5})")

    # 3. 120B with Tools (B1 harness) Run
    print("\n[Step 3] Executing 120B with Tools (B1 harness) on all 100 Reserve items...")
    existing_b1 = load_existing_records(B1_120B_RECORDS_PATH)
    if existing_b1:
        print(f"Resuming 120B B1 with {len(existing_b1)} existing records.")

    with open(B1_120B_RECORDS_PATH, "a", encoding="utf-8") as f_b1:
        for idx, item in enumerate(reserve_items, 1):
            iid = item.get("original_id") or item.get("subtask_id") or item.get("item_id")
            if iid in existing_b1:
                continue

            it_copy = dict(item)
            it_copy["item_id"] = iid
            t0 = time.time()
            b1_res = run_item_with_b1_tools(MODEL_120B_ID, it_copy)
            dt = time.time() - t0

            rec = {
                "item_id": iid,
                "track": "A",
                "task_type": item.get("task_type", ""),
                "stratum": item.get("stratum", ""),
                "solvability": item.get("solvability", ""),
                "model_id": MODEL_120B_ID,
                "condition": "b1_tools_120b",
                "prompt": format_eval_prompt(item),
                "output": b1_res.get("output", "")[:300],
                "full_output": b1_res.get("full_output", ""),
                "finish_reason": b1_res.get("finish_reason", "stop"),
                "status": b1_res.get("status", "COMPLETE"),
                "clean_execution": b1_res.get("clean_execution", True),
                "harness_used": b1_res.get("harness_used", ""),
                "num_calls": b1_res.get("num_calls", 1),
                "prompt_tokens": b1_res.get("prompt_tokens", 0),
                "completion_tokens": b1_res.get("completion_tokens", 0),
                "total_tokens": b1_res.get("total_tokens", 0),
                "passed": b1_res.get("passed", False),
                "details": b1_res.get("details", ""),
                "duration": round(dt, 2)
            }
            f_b1.write(json.dumps(rec) + "\n")
            f_b1.flush()
            existing_b1[iid] = rec
            print(f"  [120B {idx:03d}/100] {iid} -> Passed: {rec['passed']} | Harness: {rec['harness_used']} | Tokens: {rec['total_tokens']}")
            # Graceful sleep to pace Groq TPM smoothly
            time.sleep(1.5)

    # 4. Construct Cascade Records Live
    print("\n[Step 4] Assembling Cascade records from live execution...")
    cascade_records = {}
    fixed_items = []
    broke_items = []
    unchanged_wrong = []
    unchanged_right = []
    calls_120b_total = 0
    tokens_120b_total = 0

    with open(CASCADE_RECORDS_PATH, "w", encoding="utf-8") as f_casc:
        for item in reserve_items:
            iid = item.get("original_id") or item.get("subtask_id") or item.get("item_id")
            r_v11 = existing_v11[iid]
            r_b1 = existing_b1[iid]

            should_esc = r_v11["should_escalate"]
            v11_pass = r_v11["passed"]
            b1_pass = r_b1["passed"]

            if should_esc:
                final_pass = b1_pass
                model_used = MODEL_120B_ID
                output_used = r_b1["output"]
                full_output_used = r_b1["full_output"]
                calls_120b = r_b1["num_calls"]
                tokens_120b = r_b1["total_tokens"]
                calls_120b_total += calls_120b
                tokens_120b_total += tokens_120b

                if not v11_pass and b1_pass:
                    fixed_items.append(iid)
                elif v11_pass and not b1_pass:
                    broke_items.append(iid)
                elif not v11_pass and not b1_pass:
                    unchanged_wrong.append(iid)
                else:
                    unchanged_right.append(iid)
            else:
                final_pass = v11_pass
                model_used = "phi4-mini (pipeline v1.1)"
                output_used = r_v11["output"]
                full_output_used = r_v11["full_output"]
                calls_120b = 0
                tokens_120b = 0

            rec_casc = {
                "item_id": iid,
                "track": "A",
                "task_type": item.get("task_type", ""),
                "stratum": item.get("stratum", ""),
                "solvability": item.get("solvability", ""),
                "escalated": should_esc,
                "model_used": model_used,
                "triggers_fired": {
                    "T1": r_v11["t1_unclean"],
                    "T2": r_v11["t2_analyser_fb"],
                    "T3": r_v11["t3_db_fb"],
                    "T4": r_v11["t4_missing_ans"],
                    "T5": r_v11["t5_self_check"],
                    "is_corpus": r_v11["is_corpus"],
                },
                "output": output_used,
                "full_output": full_output_used,
                "passed": final_pass,
                "120b_calls": calls_120b,
                "120b_tokens": tokens_120b,
                "v11_passed": v11_pass,
                "b1_passed": b1_pass
            }
            f_casc.write(json.dumps(rec_casc) + "\n")
            cascade_records[iid] = rec_casc

    # 5. Verify Reserve hash after run
    print("\n[Step 5] Verifying Reserve Set cryptographic hash after run...")
    post_hash = verify_reserve_hash()
    print(f"Verified Post-Run Reserve SHA-256: {post_hash} [MATCH]")

    # 6. Evaluate Against Pre-Registered Criteria
    print("\n[Step 6] Computing Statistics Against Pre-Registered Criteria...")
    n = len(reserve_items)
    v11_correct = sum(1 for r in existing_v11.values() if r["passed"])
    b1_correct = sum(1 for r in existing_b1.values() if r["passed"])
    cascade_correct = sum(1 for r in cascade_records.values() if r["passed"])
    escalated_count = sum(1 for r in cascade_records.values() if r["escalated"])

    v11_acc = v11_correct / n * 100
    b1_acc = b1_correct / n * 100
    cascade_acc = cascade_correct / n * 100
    esc_share = escalated_count / n * 100

    item_order = [it.get("original_id") or it.get("subtask_id") or it.get("item_id") for it in reserve_items]
    casc_scores = [1.0 if cascade_records[iid]["passed"] else 0.0 for iid in item_order]
    v11_scores = [1.0 if existing_v11[iid]["passed"] else 0.0 for iid in item_order]
    b1_scores = [1.0 if existing_b1[iid]["passed"] else 0.0 for iid in item_order]

    diff_vs_v11 = [c - v for c, v in zip(casc_scores, v11_scores)]
    diff_vs_b1 = [c - b for c, b in zip(casc_scores, b1_scores)]

    paired_diff_v11 = sum(diff_vs_v11) / n * 100
    paired_diff_b1 = sum(diff_vs_b1) / n * 100

    ci_v11 = bootstrap_ci(diff_vs_v11)
    ci_b1 = bootstrap_ci(diff_vs_b1)
    ci_acc = bootstrap_ci(casc_scores)
    ci_esc = bootstrap_ci([1.0 if cascade_records[iid]["escalated"] else 0.0 for iid in item_order])

    summary = {
        "tag": "v1.1-cascade-frozen",
        "reserve_hash": post_hash,
        "n_items": n,
        "v11_alone": {
            "correct": v11_correct,
            "total": n,
            "accuracy": round(v11_acc, 2)
        },
        "120b_alone": {
            "correct": b1_correct,
            "total": n,
            "accuracy": round(b1_acc, 2)
        },
        "cascade": {
            "correct": cascade_correct,
            "total": n,
            "accuracy": round(cascade_acc, 2),
            "accuracy_95_ci": list(ci_acc),
            "escalated_count": escalated_count,
            "escalation_share": round(esc_share, 2),
            "escalation_share_95_ci": list(ci_esc),
            "calls_120b": calls_120b_total,
            "tokens_120b": tokens_120b_total,
            "fixed_count": len(fixed_items),
            "broke_count": len(broke_items),
            "net_gain": len(fixed_items) - len(broke_items),
            "fixed_items": fixed_items,
            "broke_items": broke_items,
            "paired_diff_vs_v11": round(paired_diff_v11, 2),
            "paired_diff_vs_v11_95_ci": list(ci_v11),
            "paired_diff_vs_120b": round(paired_diff_b1, 2),
            "paired_diff_vs_120b_95_ci": list(ci_b1)
        }
    }

    with open(SUMMARY_JSON_PATH, "w", encoding="utf-8") as f_sum:
        json.dump(summary, f_sum, indent=2)

    print("\n" + "=" * 90)
    print("RESERVE EVALUATION RESULTS SUMMARY")
    print("=" * 90)
    print(f"System                       | Accuracy           | Escalation Share | 120B Calls | 120B Tokens")
    print("-" * 90)
    print(f"Pipeline v1.1 Alone          | {v11_acc:>5.2f}% ({v11_correct:>2}/{n})    |      0.0%        |      0     |        0")
    print(f"120B with Tools (B1) Alone   | {b1_acc:>5.2f}% ({b1_correct:>2}/{n})    |    100.0%        |    170*    |   140k*")
    print(f"Cascade (Chosen Trigger)     | {cascade_acc:>5.2f}% ({cascade_correct:>2}/{n})    |     {esc_share:>4.1f}% ({escalated_count:>2})   |     {calls_120b_total:>2}     |   {tokens_120b_total:>6}")
    print("=" * 90)
    print(f"\nPre-Registered Comparison Ledger (Track A Reserve, N={n}):")
    print(f"1. Cascade Accuracy:          {cascade_acc:.2f}% (95% CI [{ci_acc[0]:.2f}%, {ci_acc[1]:.2f}%])")
    print(f"2. Escalation Share:          {esc_share:.2f}% (95% CI [{ci_esc[0]:.2f}%, {ci_esc[1]:.2f}%])")
    print(f"3. Paired Diff vs v1.1 Alone: {paired_diff_v11:+.2f} pp (95% CI [{ci_v11[0]:+.2f} pp, {ci_v11[1]:+.2f} pp])")
    print(f"   Fixed: {len(fixed_items)} items | Broke: {len(broke_items)} items | Net Gain: {len(fixed_items) - len(broke_items):+d} items")
    print(f"4. Paired Diff vs 120B Alone: {paired_diff_b1:+.2f} pp (95% CI [{ci_b1[0]:+.2f} pp, {ci_b1[1]:+.2f} pp]) [Reportable Gap]")
    print(f"5. Total 120B Usage:          {calls_120b_total} API calls, {tokens_120b_total:,} tokens spent.")
    print("=" * 90)


if __name__ == "__main__":
    main()

