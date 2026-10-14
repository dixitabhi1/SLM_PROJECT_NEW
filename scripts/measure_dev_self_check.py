"""
Measures Trigger T5 (Self-Check Disagreement) across all 150 dev items.
Uses local llama-server on port 8080 (Phi-4-mini).
Computes True Positive Flag Rate (on wrong items) and False Alarm Rate (on right items).
Saves results to results/phase4/dev_self_check_eval.json.
"""

import os
import sys
import json
import re
import time
from typing import Dict, Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import call_phi

V11_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_v11_pipeline_records.jsonl")
OUT_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_self_check_eval.json")

CHECK_SYS = """You are an expert solution validator. Check whether the candidate answer directly and correctly answers the given task.
Respond in exactly this format:
VERIFIED: <YES or NO>
REASON: <brief explanation>"""


def main():
    with open(V11_RECORDS_PATH, "r", encoding="utf-8") as f:
        recs = [json.loads(l) for l in f if l.strip()]

    print(f"Loaded {len(recs)} v1.1 dev records.")

    results = {}
    if os.path.exists(OUT_PATH):
        try:
            results = json.load(open(OUT_PATH, "r", encoding="utf-8"))
        except Exception:
            results = {}

    total_items = len(recs)
    right_items = [r for r in recs if r.get("passed")]
    wrong_items = [r for r in recs if not r.get("passed")]

    print(f"Total: {total_items} | Correct under v1.1: {len(right_items)} | Wrong under v1.1: {len(wrong_items)}")

    flagged_records = {}

    for idx, r in enumerate(recs, 1):
        iid = r["item_id"]
        if iid in results:
            flagged_records[iid] = results[iid]
            continue

        prompt = r["prompt"]
        ans = r.get("final_answer") or r.get("output", "")

        t0 = time.time()
        resp = call_phi([
            {"role": "system", "content": CHECK_SYS},
            {"role": "user", "content": f"Task Prompt:\n{prompt}\n\nCandidate Answer:\n{ans}\n\nValidation:"}
        ], temperature=0.0, max_tokens=100)
        dt = time.time() - t0

        m = re.search(r"VERIFIED:\s*(YES|NO)", resp, re.I)
        verdict = m.group(1).upper() if m else "NO"  # unparseable defaults to flagged (NO)
        flagged = (verdict == "NO")

        res_item = {
            "item_id": iid,
            "passed": r.get("passed", False),
            "verdict": verdict,
            "flagged": flagged,
            "raw_response": resp,
            "duration": round(dt, 2)
        }
        results[iid] = res_item
        flagged_records[iid] = res_item

        status_str = "FLAGGED" if flagged else "OK"
        print(f"[{idx:03d}/{total_items}] {iid}: {status_str} (verdict={verdict}, true_pass={r.get('passed')})")

        if idx % 10 == 0:
            with open(OUT_PATH, "w", encoding="utf-8") as f_out:
                json.dump(results, f_out, indent=2)

    with open(OUT_PATH, "w", encoding="utf-8") as f_out:
        json.dump(results, f_out, indent=2)

    # Compute Statistics
    tp = sum(1 for r in wrong_items if results[r["item_id"]]["flagged"])
    fn = len(wrong_items) - tp
    fp = sum(1 for r in right_items if results[r["item_id"]]["flagged"])
    tn = len(right_items) - fp

    tp_rate = tp / len(wrong_items) * 100 if wrong_items else 0.0
    fp_rate = fp / len(right_items) * 100 if right_items else 0.0
    total_flagged = tp + fp

    print("\n" + "=" * 70)
    print("SELF-CHECK (T5) EVALUATION REPORT ON DEV (N=150)")
    print("=" * 70)
    print(f"Total items evaluated: {total_items}")
    print(f"Total flagged: {total_flagged}/{total_items} ({total_flagged/total_items*100:.1f}%)")
    print(f"True Positives (Wrong items flagged): {tp}/{len(wrong_items)} ({tp_rate:.1f}% detection rate)")
    print(f"False Positives (Right items flagged): {fp}/{len(right_items)} ({fp_rate:.1f}% false alarm rate)")
    print(f"True Negatives (Right items not flagged): {tn}/{len(right_items)}")
    print(f"False Negatives (Wrong items missed): {fn}/{len(wrong_items)}")


if __name__ == "__main__":
    main()

