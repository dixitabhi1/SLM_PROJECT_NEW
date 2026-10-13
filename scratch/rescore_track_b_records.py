import os
import sys
import json
import re

sys.path.insert(0, ".")
from scratch.develop_v120_scorer import normalize_format_tolerant, match_component_token, match_phrase_tolerant, score_strict, check_true_facts
from src.eval.fact_checklist_scorer import score_fact_checklist as score_v110

def rescore_all():
    items = json.load(open("data/track_b/track_b_heldout_split.json", encoding="utf-8"))
    items_map = {it["question_id"]: it for it in items}

    targets = [
        ("Pipeline", "results/phase4/heldout_pipeline_records.jsonl", True),
        ("Qwen-27B", "results/phase4/b1_qwen27b_heldout_records.jsonl", False),
        ("GPT-120B", "results/phase4/b1_gpt120b_heldout_records.jsonl", False),
    ]

    changed_verdicts = []

    for name, path, is_pipe in targets:
        recs = []
        with open(path, "r", encoding="utf-8") as f:
            for l in f:
                r = json.loads(l)
                if r.get("track") == "B":
                    if is_pipe:
                        recs.append(r)
                    elif r.get("rerun_topk5_fair"):
                        recs.append(r)

        # Map by item_id (latest wins)
        rec_map = {}
        for r in recs:
            iid = r.get("item_id") or r.get("question_id")
            rec_map[iid] = r

        print(f"\n=== Rescoring {name} ({len(rec_map)} items) ===")
        v110_passes = 0
        v120_strict_passes = 0
        v120_true_fact_passes = 0

        for qid, it in sorted(items_map.items()):
            r = rec_map.get(qid)
            if not r:
                continue
            ans = r.get("final_answer") if is_pipe else (r.get("output") or r.get("full_output"))
            
            # v1.1.0 score
            res_v110 = score_v110(ans, it["checklist"], max_word_cap=it.get("word_cap", 75))
            pass_v110 = res_v110["binary_pass"]
            
            # v1.2.0 strict score
            res_v120_s = score_strict(ans, it, max_word_cap=it.get("word_cap", 75))
            pass_v120_s = res_v120_s["passed"]
            
            # v1.2.0 true fact check
            res_v120_f = check_true_facts(ans, it)
            pass_v120_f = res_v120_f["passed"]

            if pass_v110:
                v110_passes += 1
            if pass_v120_s:
                v120_strict_passes += 1
            if pass_v120_f:
                v120_true_fact_passes += 1

            if pass_v110 != pass_v120_s:
                changed_verdicts.append({
                    "model": name,
                    "item_id": qid,
                    "v110": "PASS" if pass_v110 else "FAIL",
                    "v120_strict": "PASS" if pass_v120_s else "FAIL",
                    "v120_facts": "PASS" if pass_v120_f else "FAIL",
                    "v110_failure": res_v110.get("failed_facts", ["none"])[0] if not pass_v110 else "",
                    "answer_snippet": ans[:120].replace("\n", " ")
                })

        print(f"  v1.1.0 Strict Pass: {v110_passes}/50 ({v110_passes*2}%)")
        print(f"  v1.2.0 Strict Pass: {v120_strict_passes}/50 ({v120_strict_passes*2}%)")
        print(f"  v1.2.0 True Facts Pass: {v120_true_fact_passes}/50 ({v120_true_fact_passes*2}%)")

    print(f"\n=== Total Changed Verdicts: {len(changed_verdicts)} ===")
    for cv in changed_verdicts:
        print(f"[{cv['model']}] {cv['item_id']}: v1.1.0={cv['v110']} -> v1.2.0_strict={cv['v120_strict']} (facts={cv['v120_facts']})")
        print(f"  v1.1.0 reason: {cv['v110_failure']}")
        print(f"  snippet: {cv['answer_snippet'].encode('ascii', errors='replace').decode('ascii')}")

if __name__ == "__main__":
    rescore_all()
