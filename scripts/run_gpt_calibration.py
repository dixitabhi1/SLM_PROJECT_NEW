"""
Run B0 and B1 (GPT-OSS-120B w/o and with tools) on the 20 Hard Calibration Items.
"""

import os
import sys
import json
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.eval_calibration_hard_20 import run_model_no_tools, run_model_with_tools, CALIB_FILE
from src.eval.versioned_scorer import score_record

OUTPUT_B0_B1 = os.path.join(REPO_ROOT, "results", "phase4", "calibration_gpt_b0_b1_eval.json")


def main():
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        print("ERROR: GROQ_API_KEY not found.")
        sys.exit(1)

    with open(CALIB_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)

    print(f"Loaded {len(items)} calibration items.")

    # 1. B0 (GPT-OSS-120B without tools)
    b0_records = []
    print("\n--- Running B0 (GPT-OSS-120B w/o tools) ---")
    for idx, item in enumerate(items, 1):
        it_id = item["subtask_id"]
        solv = item["solvability"]
        print(f"[B0 {idx}/20] {it_id} ({solv})...", end=" ", flush=True)
        try:
            out = run_model_no_tools(item, is_local=False, groq_key=api_key)
            sc = score_record(item, out)
            passed = sc["passed"]
            print(f"-> {'PASS' if passed else 'FAIL'} (gold={item['gold_answer']})")
            b0_records.append({
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
            b0_records.append({"item_id": it_id, "passed": False, "error": str(e)})
        time.sleep(1.0)

    # 2. B1 (GPT-OSS-120B with tools)
    b1_records = []
    print("\n--- Running B1 (GPT-OSS-120B with tools) ---")
    for idx, item in enumerate(items, 1):
        it_id = item["subtask_id"]
        solv = item["solvability"]
        print(f"[B1 {idx}/20] {it_id} ({solv})...", end=" ", flush=True)
        try:
            out = run_model_with_tools(item, is_local=False, groq_key=api_key)
            sc = score_record(item, out)
            passed = sc["passed"]
            print(f"-> {'PASS' if passed else 'FAIL'} (gold={item['gold_answer']})")
            b1_records.append({
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
            b1_records.append({"item_id": it_id, "passed": False, "error": str(e)})
        time.sleep(1.5)

    b0_acc = (sum(1 for r in b0_records if r["passed"]) / len(b0_records)) * 100
    b1_acc = (sum(1 for r in b1_records if r["passed"]) / len(b1_records)) * 100

    b0_tool_req = [r for r in b0_records if r.get("solvability") == "tool-required"]
    b0_tool_acc = (sum(1 for r in b0_tool_req if r["passed"]) / len(b0_tool_req)) * 100 if b0_tool_req else 0.0

    b0_solv = [r for r in b0_records if r.get("solvability") == "solvable_without_tools"]
    b0_solv_acc = (sum(1 for r in b0_solv if r["passed"]) / len(b0_solv)) * 100 if b0_solv else 0.0

    b1_tool_req = [r for r in b1_records if r.get("solvability") == "tool-required"]
    b1_tool_acc = (sum(1 for r in b1_tool_req if r["passed"]) / len(b1_tool_req)) * 100 if b1_tool_req else 0.0

    b1_solv = [r for r in b1_records if r.get("solvability") == "solvable_without_tools"]
    b1_solv_acc = (sum(1 for r in b1_solv if r["passed"]) / len(b1_solv)) * 100 if b1_solv else 0.0

    summary = {
        "b0_total_acc": b0_acc,
        "b0_tool_required_acc": b0_tool_acc,
        "b0_solvable_w_o_tools_acc": b0_solv_acc,
        "b1_total_acc": b1_acc,
        "b1_tool_required_acc": b1_tool_acc,
        "b1_solvable_w_o_tools_acc": b1_solv_acc,
        "b0_records": b0_records,
        "b1_records": b1_records
    }

    with open(OUTPUT_B0_B1, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("B0 vs B1 CALIBRATION RESULTS:")
    print(f"B0 (120B w/o tools) Total Acc: {b0_acc:.1f}% (Tool-req: {b0_tool_acc:.1f}%, Solv: {b0_solv_acc:.1f}%) [Target: <= 80%]")
    print(f"B1 (120B with tools) Total Acc: {b1_acc:.1f}% (Tool-req: {b1_tool_acc:.1f}%, Solv: {b1_solv_acc:.1f}%) [Target: < 100%]")
    print("=" * 60)


if __name__ == "__main__":
    main()

