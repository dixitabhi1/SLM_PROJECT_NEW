"""
scripts/rescore_and_append_track_b.py

Rescores all Track B records on disk with fact_checklist_scorer v1.2.0:
- Applies format-tolerant token matching bounded by non-alphanumerics.
- Applies normalized unit symbols (powers, micro, ohm, deg C, narrow spaces).
- Calculates strict accuracy under the 75-word cap.
- Calculates true fact check accuracy (correct value attached to correct component anywhere, length ignored).
- In accordance with Hard Rule 2 (append-only), appends updated records as new rows.
- Records all changed verdicts in results/phase4/corrections.jsonl.
"""

import os
import sys
import json
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.eval.fact_checklist_scorer import (
    CHECKLIST_SCORER_VERSION,
    score_fact_checklist,
    check_true_facts
)

RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
CORRECTIONS_PATH = os.path.join(RESULTS_DIR, "corrections.jsonl")
TRACK_B_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_heldout_split.json")

TARGET_FILES = [
    ("Specialist Pipeline", os.path.join(RESULTS_DIR, "heldout_pipeline_records.jsonl"), True),
    ("Baseline B1 (Qwen-27B)", os.path.join(RESULTS_DIR, "b1_qwen27b_heldout_records.jsonl"), False),
    ("Baseline B1 (GPT-120B)", os.path.join(RESULTS_DIR, "b1_gpt120b_heldout_records.jsonl"), False),
]


def main():
    print(f"=== RESCORING TRACK B WITH FACT CHECKLIST SCORER v{CHECKLIST_SCORER_VERSION} ===")
    with open(TRACK_B_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)
    items_map = {it["question_id"]: it for it in items}

    changed_verdicts = []

    for model_name, filepath, is_pipe in TARGET_FILES:
        print(f"\nProcessing {model_name} in {os.path.basename(filepath)}...")
        recs = []
        with open(filepath, "r", encoding="utf-8") as f:
            for l in f:
                r = json.loads(l)
                if r.get("track") == "B":
                    if is_pipe:
                        recs.append(r)
                    elif r.get("rerun_topk5_fair"):
                        recs.append(r)

        rec_map = {}
        for r in recs:
            iid = r.get("item_id") or r.get("question_id")
            rec_map[iid] = r

        new_rows = []
        for qid, it in sorted(items_map.items()):
            r = rec_map.get(qid)
            if not r:
                continue

            ans = r.get("final_answer") if is_pipe else (r.get("output") or r.get("full_output"))
            old_passed = r.get("passed", False)
            old_facts = r.get("passed_facts_alone", False)

            # Score v1.2.0 strict
            res_strict = score_fact_checklist(ans, it["checklist"], max_word_cap=it.get("word_cap", 75))
            new_passed = res_strict["binary_pass"]

            # Score v1.2.0 true facts
            res_facts = check_true_facts(ans, it["checklist"])
            new_facts = res_facts["passed"]

            details = f"Scorer v1.2.0 | Strict: {new_passed} (Recall: {res_strict['recall']:.2f}, Prec: {res_strict['precision']:.2f}) | TrueFacts: {new_facts} ({res_facts['reason']})"

            # Create updated record
            new_r = dict(r)
            new_r["passed"] = new_passed
            new_r["passed_facts_alone"] = new_facts
            new_r["scorer_version"] = CHECKLIST_SCORER_VERSION
            new_r["details"] = details
            new_r["rescore_v120"] = True
            new_r["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            new_rows.append(new_r)

            if old_passed != new_passed or old_facts != new_facts:
                changed_verdicts.append({
                    "model": model_name,
                    "target_file": os.path.normpath(os.path.relpath(filepath, REPO_ROOT)).replace("\\", "/"),
                    "item_id": qid,
                    "old_passed": old_passed,
                    "new_passed": new_passed,
                    "old_facts": old_facts,
                    "new_facts": new_facts,
                    "reason": f"v1.1.0 word boundary / unicode format limitation resolved under v1.2.0 format tolerance"
                })

        # Append new rows to file (Hard Rule 2)
        with open(filepath, "a", encoding="utf-8") as f_out:
            for nr in new_rows:
                f_out.write(json.dumps(nr) + "\n")

        print(f"  Appended {len(new_rows)} rescored rows to {os.path.basename(filepath)}.")

    # Record corrections
    if changed_verdicts:
        with open(CORRECTIONS_PATH, "a", encoding="utf-8") as f_corr:
            for cv in changed_verdicts:
                corr_rec = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "target_file": cv["target_file"],
                    "item_id": cv["item_id"],
                    "field": "passed",
                    "old_value": f"strict={cv['old_passed']}, facts={cv['old_facts']}",
                    "new_value": f"strict={cv['new_passed']}, facts={cv['new_facts']}",
                    "reason": cv["reason"],
                    "component": "fact_checklist_scorer",
                    "action": f"Rescored {cv['item_id']} ({cv['model']}) from v1.1.0 to v1.2.0"
                }
                f_corr.write(json.dumps(corr_rec) + "\n")

    print(f"\n=== SUMMARY: {len(changed_verdicts)} changed verdicts logged to corrections.jsonl ===")


if __name__ == "__main__":
    main()

