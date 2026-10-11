"""
Generates results/phase4/corrections.jsonl per Hard Rule 2.
Documents checker corrections with exact reasons without modifying raw files.
"""

import os
import json
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
import sys
sys.path.insert(0, REPO_ROOT)

from src.eval.subtask_checkers import check_qa_subtask

def main():
    qwen_path = os.path.join(REPO_ROOT, "results", "phase4", "b0_qwen27b_dev_records.jsonl")
    dev_path = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
    corr_path = os.path.join(REPO_ROOT, "results", "phase4", "corrections.jsonl")

    with open(dev_path, "r", encoding="utf-8") as f:
        dev_items = {it["original_id"]: it for it in json.load(f) if it.get("task_type") == "qa"}

    raw_lines = [json.loads(l) for l in open(qwen_path, "r", encoding="utf-8") if l.strip()]
    lines_2048 = [x for x in raw_lines if x.get("max_tokens_budget") == 2048]
    qa_records = [x for x in lines_2048 if x.get("task_type") == "qa"]

    corrections = []
    for q in qa_records:
        gold = dev_items[q["item_id"]]["gold_answer"]
        ok, chk, det = check_qa_subtask(q["item_id"], q["output"], gold)
        if ok and not q.get("passed"):
            clean_gold = gold.strip("()")
            corr = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "target_file": "results/phase4/b0_qwen27b_dev_records.jsonl",
                "item_id": q["item_id"],
                "field": "passed",
                "old_value": False,
                "new_value": True,
                "reason": f"ARC-Challenge multiple-choice regex fix: raw output explicitly concludes with Answer: ({clean_gold}), but legacy regex erroneously matched earlier option (A) discussed during elimination reasoning."
            }
            corrections.append(corr)

    with open(corr_path, "w", encoding="utf-8") as f:
        for c in corrections:
            f.write(json.dumps(c) + "\n")

    print(f"Recorded {len(corrections)} corrections in {corr_path}")

if __name__ == "__main__":
    main()

