"""
Run C0 and C1 on the 20 Hard Calibration Items.
"""

import os
import sys
import json
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.eval_calibration_hard_20 import run_model_no_tools, run_model_with_tools, CALIB_FILE
from src.eval.versioned_scorer import score_record

OUTPUT_C0_C1 = os.path.join(REPO_ROOT, "results", "phase4", "calibration_c0_c1_eval.json")


def main():
    with open(CALIB_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)

    print(f"Loaded {len(items)} calibration items.")

    c0_records = []
    print("\n--- Running C0 (Phi-4-mini w/o tools) ---")
    for idx, item in enumerate(items, 1):
        it_id = item["subtask_id"]
        solv = item["solvability"]
        print(f"[C0 {idx}/20] {it_id} ({solv})...", end=" ", flush=True)
        try:
            out = run_model_no_tools(item, is_local=True)
            sc = score_record(item, out)
            passed = sc["passed"]
            print(f"-> {'PASS' if passed else 'FAIL'} (gold={item['gold_answer']})")
            c0_records.append({
                "item_id": it_id,
                "solvability": solv,
                "num_stages": item["num_stages"],
                "passed": passed,
                "gold": item["gold_answer"],
                "output": out,
                "details": sc["details"]
            })
        except Exception as e:
            print(f"-> ERROR: {e}")
            c0_records.append({"item_id": it_id, "passed": False, "error": str(e)})

    c1_records = []
    print("\n--- Running C1 (Phi-4-mini with tools) ---")
    for idx, item in enumerate(items, 1):
        it_id = item["subtask_id"]
        solv = item["solvability"]
        print(f"[C1 {idx}/20] {it_id} ({solv})...", end=" ", flush=True)
        try:
            out = run_model_with_tools(item, is_local=True)
            sc = score_record(item, out)
            passed = sc["passed"]
            print(f"-> {'PASS' if passed else 'FAIL'} (gold={item['gold_answer']})")
            c1_records.append({
                "item_id": it_id,
                "solvability": solv,
                "num_stages": item["num_stages"],
                "passed": passed,
                "gold": item["gold_answer"],
                "output": out,
                "details": sc["details"]
            })
        except Exception as e:
            print(f"-> ERROR: {e}")
            c1_records.append({"item_id": it_id, "passed": False, "error": str(e)})

    c0_acc = (sum(1 for r in c0_records if r["passed"]) / len(c0_records)) * 100
    c1_acc = (sum(1 for r in c1_records if r["passed"]) / len(c1_records)) * 100

    c0_tool_req = [r for r in c0_records if r.get("solvability") == "tool-required"]
    c0_tool_acc = (sum(1 for r in c0_tool_req if r["passed"]) / len(c0_tool_req)) * 100 if c0_tool_req else 0.0

    c0_solv = [r for r in c0_records if r.get("solvability") == "solvable_without_tools"]
    c0_solv_acc = (sum(1 for r in c0_solv if r["passed"]) / len(c0_solv)) * 100 if c0_solv else 0.0

    c1_tool_req = [r for r in c1_records if r.get("solvability") == "tool-required"]
    c1_tool_acc = (sum(1 for r in c1_tool_req if r["passed"]) / len(c1_tool_req)) * 100 if c1_tool_req else 0.0

    c1_solv = [r for r in c1_records if r.get("solvability") == "solvable_without_tools"]
    c1_solv_acc = (sum(1 for r in c1_solv if r["passed"]) / len(c1_solv)) * 100 if c1_solv else 0.0

    summary = {
        "c0_total_acc": c0_acc,
        "c0_tool_required_acc": c0_tool_acc,
        "c0_solvable_w_o_tools_acc": c0_solv_acc,
        "c1_total_acc": c1_acc,
        "c1_tool_required_acc": c1_tool_acc,
        "c1_solvable_w_o_tools_acc": c1_solv_acc,
        "c0_records": c0_records,
        "c1_records": c1_records
    }

    with open(OUTPUT_C0_C1, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("C0 vs C1 CALIBRATION RESULTS:")
    print(f"C0 (w/o tools) Total Acc: {c0_acc:.1f}% (Tool-req: {c0_tool_acc:.1f}%, Solv: {c0_solv_acc:.1f}%) [Target: 30-60%]")
    print(f"C1 (with tools) Total Acc: {c1_acc:.1f}% (Tool-req: {c1_tool_acc:.1f}%, Solv: {c1_solv_acc:.1f}%) [Target: 40-75%]")
    print("=" * 60)


if __name__ == "__main__":
    main()

