"""
scripts/diagnose_e3_dev_track_b.py

Diagnoses E3 candidate on Dev Track B only (N=50).
Compares accuracy against v1.2 baseline (results/phase4/dev_v11_pipeline_records.jsonl).
Reports for each broken item: item_id, route, and reason.
Strictly Dev Track B only; zero inspection of held-out Track B items.
"""

import os
import sys
import json
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline_e3 import run_specialist_pipeline_e3
from src.eval.fact_checklist_scorer import score_fact_checklist
from scripts.rerun_dev_phase4_fix import format_eval_prompt

DEV_TRACK_B_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_dev_split.json")
V12_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_v11_pipeline_records.jsonl")
OUT_DIAGNOSTIC_PATH = os.path.join(REPO_ROOT, "results", "phase4", "e3_dev_track_b_diagnosis.json")


def main():
    print("=" * 80)
    print("DIAGNOSING E3 CANDIDATE ON DEV TRACK B (N=50)")
    print("=" * 80)

    with open(DEV_TRACK_B_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)
    print(f"Loaded {len(items)} Dev Track B items.")

    # Load v1.2 baseline records
    v12_map = {}
    with open(V12_RECORDS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                v12_map[r["item_id"]] = r

    e3_records = []
    broken_items = []
    fixed_items = []

    for idx, it in enumerate(items, 1):
        iid = it.get("question_id") or it.get("item_id")
        v12_rec = v12_map.get(iid)
        v12_pass = v12_rec["passed"] if v12_rec else None

        prompt = format_eval_prompt(it)
        t0 = time.time()
        res = run_specialist_pipeline_e3(prompt)
        dt = time.time() - t0

        text_to_score = res.get("final_answer") or res.get("output")
        score_res = score_fact_checklist(text_to_score, it["checklist"], max_word_cap=it.get("word_cap", 75))
        passed = score_res["binary_pass"]

        rec = {
            "item_id": iid,
            "v12_passed": v12_pass,
            "e3_passed": passed,
            "routed_to": res.get("routed_to"),
            "colors": res.get("colors"),
            "source": res.get("source"),
            "subtasks": res.get("subtasks"),
            "duration": dt,
            "failed_facts": score_res.get("failed_facts", []),
            "word_count": score_res.get("word_count", 0),
            "final_answer": res.get("final_answer", "")
        }
        e3_records.append(rec)

        if v12_pass and not passed:
            broken_items.append(rec)
            status_str = "BROKEN"
        elif not v12_pass and passed:
            fixed_items.append(rec)
            status_str = "FIXED"
        elif passed:
            status_str = "PASS"
        else:
            status_str = "FAIL"

        print(f"[{idx:02d}/50] {iid} -> v1.2: {v12_pass} | E3: {passed} ({status_str}) | routed: {res.get('routed_to')} | dt: {dt:.2f}s", flush=True)

    v12_passed_cnt = sum(1 for r in e3_records if r["v12_passed"])
    e3_passed_cnt = sum(1 for r in e3_records if r["e3_passed"])

    print("\n" + "=" * 80)
    print("DIAGNOSTIC SUMMARY:")
    print(f"v1.2 Dev Track B Accuracy: {v12_passed_cnt}/50 ({v12_passed_cnt/50*100:.2f}%)")
    print(f"E3   Dev Track B Accuracy: {e3_passed_cnt}/50 ({e3_passed_cnt/50*100:.2f}%)")
    print(f"Broken items count:        {len(broken_items)}")
    print(f"Fixed items count:         {len(fixed_items)}")
    print("=" * 80)

    print("\nBROKEN ITEMS DETAIL:")
    for b in broken_items:
        print(f"\nItem: {b['item_id']}")
        print(f"  Route: {b['routed_to']}")
        print(f"  Source from Analyser: {b['source']}")
        print(f"  Colors: {b['colors']}")
        print(f"  Word count: {b['word_count']}")
        print(f"  Failed facts: {b['failed_facts']}")
        print(f"  Output snippet: {b['final_answer'][:200]}...")

    with open(OUT_DIAGNOSTIC_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "v12_passed": v12_passed_cnt,
            "e3_passed": e3_passed_cnt,
            "broken_count": len(broken_items),
            "broken_items": broken_items,
            "all_records": e3_records
        }, f, indent=2)

    print(f"\nDiagnostic JSON saved to {OUT_DIAGNOSTIC_PATH}")


if __name__ == "__main__":
    main()
