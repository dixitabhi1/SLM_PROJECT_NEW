"""
Evaluation of Cascade Tiers and Reference Points on Dev Split (N=150).

Combines:
1. Specialist Pipeline v1.1 records (results/phase4/dev_v11_pipeline_records.jsonl)
2. Trigger T5: Self-Check Disagreement (results/phase4/dev_self_check_eval.json)
3. Trigger T6: Self-Consistency Disagreement (results/phase4/dev_self_consistency_eval.json)
4. 120B B1 with Tools records (results/phase4/dev_b1_gpt120b_records.jsonl)

Generates:
- Comprehensive Cascade Performance Table:
  - System / Tier
  - Track A Acc (N=100)
  - Track B Acc (N=50)
  - Overall Acc (N=150)
  - Escalation Share (%)
  - 120B Calls
  - 120B Total Tokens (Prompt + Completion)
  - Fixed Count
  - Broke Count
  - Net Gain (Fixed - Broke)
- Summary JSON saved to results/phase4/cascade_dev_evaluation.json
"""

import os
import sys
import json
import re
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

V11_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_v11_pipeline_records.jsonl")
T5_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_self_check_eval.json")
T6_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_self_consistency_eval.json")
B1_120B_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_b1_gpt120b_records.jsonl")
ANALYSER_SOURCES_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_analyser_sources.json")
OUT_JSON_PATH = os.path.join(REPO_ROOT, "results", "phase4", "cascade_dev_evaluation.json")


def load_data():
    with open(V11_PATH, "r", encoding="utf-8") as f:
        v11_recs = {json.loads(l)["item_id"]: json.loads(l) for l in f if l.strip()}

    with open(T5_PATH, "r", encoding="utf-8") as f:
        t5_data = json.load(f)

    with open(T6_PATH, "r", encoding="utf-8") as f:
        t6_data = json.load(f)

    with open(B1_120B_PATH, "r", encoding="utf-8") as f:
        b1_recs = {json.loads(l)["item_id"]: json.loads(l) for l in f if l.strip()}

    analyser_sources = {}
    if os.path.exists(ANALYSER_SOURCES_PATH):
        with open(ANALYSER_SOURCES_PATH, "r", encoding="utf-8") as f:
            analyser_sources = json.load(f)

    return v11_recs, t5_data, t6_data, b1_recs, analyser_sources


def get_triggers(iid: str, v11_rec: Dict[str, Any], t5_data: Dict[str, Any], t6_data: Dict[str, Any]) -> Dict[str, bool]:
    # T1: Unclean execution
    clean = v11_rec.get("clean_execution", True)
    t1 = not clean

    # T2: Analyser fallback
    fallbacks = v11_rec.get("fallbacks", {})
    t2 = bool(fallbacks.get("analyser", False))

    # T3: Database identifier fallback
    t3 = bool(fallbacks.get("database_identifier", False))

    # T4: Missing final answer
    final_ans = v11_rec.get("final_answer") or v11_rec.get("output", "")
    t4 = not bool(str(final_ans).strip())

    # T5: Self-check disagreement
    t5 = bool(t5_data.get(iid, {}).get("flagged", False))

    # T6: Self-consistency disagreement
    t6 = bool(t6_data.get(iid, {}).get("flagged", False))

    return {
        "T1": t1,
        "T2": t2,
        "T3": t3,
        "T4": t4,
        "T5": t5,
        "T6": t6,
        "Tier1": t1 or t4,
        "Tier2": t1 or t2 or t3 or t4,
        "Tier3": t1 or t2 or t3 or t4 or t5,
        "Tier4": t1 or t2 or t3 or t4 or t5 or t6,
    }


def evaluate_condition(
    name: str,
    v11_recs: Dict[str, Any],
    b1_recs: Dict[str, Any],
    escalate_fn
) -> Dict[str, Any]:
    total_items = len(v11_recs)
    track_a_items = [iid for iid, r in v11_recs.items() if not iid.startswith("track_b")]
    track_b_items = [iid for iid, r in v11_recs.items() if iid.startswith("track_b")]

    escalated_items = []
    fixed_items = []
    broke_items = []
    unchanged_wrong = []
    unchanged_right = []

    calls_120b = 0
    prompt_tokens_120b = 0
    completion_tokens_120b = 0
    total_tokens_120b = 0

    harnesses_used = {}
    verdicts = {}

    for iid, r_v11 in v11_recs.items():
        r_120b = b1_recs.get(iid, {})
        v11_pass = r_v11.get("passed", False)
        b1_pass = r_120b.get("passed", False)

        should_escalate = escalate_fn(iid, r_v11)

        if should_escalate:
            escalated_items.append(iid)
            calls_120b += r_120b.get("num_calls", 1)
            prompt_tokens_120b += r_120b.get("prompt_tokens", 0)
            completion_tokens_120b += r_120b.get("completion_tokens", 0)
            total_tokens_120b += r_120b.get("total_tokens", 0)

            harness = r_120b.get("harness_used", "unknown")
            harnesses_used[harness] = harnesses_used.get(harness, 0) + 1

            final_pass = b1_pass
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

        verdicts[iid] = final_pass

    track_a_correct = sum(1 for iid in track_a_items if verdicts[iid])
    track_b_correct = sum(1 for iid in track_b_items if verdicts[iid])
    overall_correct = sum(1 for iid, p in verdicts.items() if p)

    return {
        "condition": name,
        "overall_correct": overall_correct,
        "overall_total": total_items,
        "overall_acc": round(overall_correct / total_items * 100, 2),
        "track_a_correct": track_a_correct,
        "track_a_total": len(track_a_items),
        "track_a_acc": round(track_a_correct / len(track_a_items) * 100, 2),
        "track_b_correct": track_b_correct,
        "track_b_total": len(track_b_items),
        "track_b_acc": round(track_b_correct / len(track_b_items) * 100, 2),
        "escalated_count": len(escalated_items),
        "escalation_share": round(len(escalated_items) / total_items * 100, 2),
        "calls_120b": calls_120b,
        "prompt_tokens_120b": prompt_tokens_120b,
        "completion_tokens_120b": completion_tokens_120b,
        "total_tokens_120b": total_tokens_120b,
        "fixed_count": len(fixed_items),
        "broke_count": len(broke_items),
        "net_gain": len(fixed_items) - len(broke_items),
        "harnesses_used": harnesses_used,
        "fixed_items": fixed_items,
        "broke_items": broke_items
    }


def main():
    print("=" * 80)
    print("CASCADE EVALUATION SUITE ON DEV SPLIT (N=150)")
    print("=" * 80)

    v11_recs, t5_data, t6_data, b1_recs, analyser_sources = load_data()
    print(f"Loaded {len(v11_recs)} v1.1 records, {len(t5_data)} T5 records, {len(t6_data)} T6 records, {len(b1_recs)} 120B B1 records, {len(analyser_sources)} analyser records.")

    # Precompute trigger flags
    item_triggers = {
        iid: get_triggers(iid, r, t5_data, t6_data)
        for iid, r in v11_recs.items()
    }

    conditions = [
        ("Pipeline v1.1 Alone", lambda iid, r: False),
        ("Tier 1: T1|T4 (Unclean/No Ans)", lambda iid, r: item_triggers[iid]["Tier1"]),
        ("Tier 2: Tier 1 + Analyser/DB Fallback", lambda iid, r: item_triggers[iid]["Tier2"]),
        ("Tier 3: Tier 2 + T5 (Self-Check, All)", lambda iid, r: item_triggers[iid]["Tier3"]),
        ("Chosen Trigger: Tier 3 (No Corpus Escalation)", lambda iid, r: item_triggers[iid]["Tier3"] and analyser_sources.get(iid, {}).get("source") != "CORPUS"),
        ("Sensitivity: T5 (Self-Check Alone)", lambda iid, r: item_triggers[iid]["T5"]),
        ("Reference: Oracle (Escalate Wrong v1.1)", lambda iid, r: not r.get("passed", False)),
        ("Reference: Escalate Everything (120B Alone)", lambda iid, r: True),
    ]

    results = []
    for name, fn in conditions:
        eval_res = evaluate_condition(name, v11_recs, b1_recs, fn)
        results.append(eval_res)

    # Save to JSON
    with open(OUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Print markdown table
    print("\n" + "=" * 110)
    print(f"{'Condition / Tier':<35} | {'Overall':<10} | {'Track A':<10} | {'Track B':<10} | {'Esc Share':<10} | {'120B Calls':<10} | {'120B Tokens':<12} | {'Fixed':<6} | {'Broke':<6} | {'Net'}")
    print("-" * 110)
    for r in results:
        print(
            f"{r['condition']:<35} | "
            f"{r['overall_acc']:>5.1f}% ({r['overall_correct']:>3}/{r['overall_total']}) | "
            f"{r['track_a_acc']:>5.1f}%   | "
            f"{r['track_b_acc']:>5.1f}%   | "
            f"{r['escalation_share']:>5.1f}% ({r['escalated_count']:>3}) | "
            f"{r['calls_120b']:>6}     | "
            f"{r['total_tokens_120b']:>8}     | "
            f"{r['fixed_count']:>5}  | "
            f"{r['broke_count']:>5}  | "
            f"{r['net_gain']:>+3}"
        )
    print("=" * 110)


if __name__ == "__main__":
    main()

