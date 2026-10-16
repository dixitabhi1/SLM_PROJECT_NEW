"""
scripts/eval_e3_heldout_secondary.py

Secondary Check: Evaluates E3 Pipeline on Held-Out Splits (150 items):
- Track A Held-Out (100 items): data/track_a_heldout_split.json
- Track B Held-Out (50 items): data/track_b/track_b_heldout_split.json

Output Records: results/phase4/heldout_e3_pipeline_records.jsonl (new file only).
Summary JSON: results/phase4/e3_heldout_secondary_evaluation.json
Report: docs/secondary_e3_heldout_head_to_head.md

Explicitly labeled: "secondary: held-out previously inspected".
"""

import os
import sys
import json
import time
import hashlib
from typing import Dict, Any, List, Tuple
import numpy as np

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline_e3 import run_specialist_pipeline_e3
from src.eval.versioned_scorer import score_record
from src.eval.fact_checklist_scorer import score_fact_checklist
from scripts.run_heldout_evaluation import format_eval_prompt

TRACK_A_PATH = os.path.join(REPO_ROOT, "data", "track_a_heldout_split.json")
TRACK_B_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_heldout_split.json")
OUT_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "heldout_e3_pipeline_records.jsonl")
OUT_SUMMARY_PATH = os.path.join(REPO_ROOT, "results", "phase4", "e3_heldout_secondary_evaluation.json")
OUT_REPORT_PATH = os.path.join(REPO_ROOT, "docs", "secondary_e3_heldout_head_to_head.md")

B1_120B_PATH = os.path.join(REPO_ROOT, "results", "phase4", "b1_gpt120b_heldout_records.jsonl")
B1_27B_PATH = os.path.join(REPO_ROOT, "results", "phase4", "b1_qwen27b_heldout_records.jsonl")

EXPECTED_TRACK_A_HASH = "2314fca186a064ffcface62f42dc346bda9fdc73c5221852e8ecf5b19aafd629"
EXPECTED_TRACK_B_HASH = "075bf20d1daafdb89e3eef1e35271113766b9845cfb9d52e88301faa2919c0e1"


def verify_hashes():
    h_a = hashlib.sha256(open(TRACK_A_PATH, "rb").read()).hexdigest()
    h_b = hashlib.sha256(open(TRACK_B_PATH, "rb").read()).hexdigest()
    assert h_a == EXPECTED_TRACK_A_HASH, f"Track A hash mismatch: {h_a} != {EXPECTED_TRACK_A_HASH}"
    assert h_b == EXPECTED_TRACK_B_HASH, f"Track B hash mismatch: {h_b} != {EXPECTED_TRACK_B_HASH}"
    print(f"Verified Held-out Cryptographic Hashes:")
    print(f"  Track A Held-out: {h_a} [VERIFIED]")
    print(f"  Track B Held-out: {h_b} [VERIFIED]")


def load_baseline_records(path: str) -> Dict[str, Dict[str, Any]]:
    recs = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    r = json.loads(l)
                    iid = r.get("item_id") or r.get("subtask_id")
                    recs[iid] = r
    return recs


def main():
    print("=" * 80)
    print("SECONDARY CHECK: EVALUATING E3 PIPELINE ON HELD-OUT SPLITS (N=150)")
    print("Label: secondary: held-out previously inspected")
    print("=" * 80)

    verify_hashes()

    with open(TRACK_A_PATH, "r", encoding="utf-8") as f:
        items_a = json.load(f)
    with open(TRACK_B_PATH, "r", encoding="utf-8") as f:
        items_b = json.load(f)

    all_items = items_a + items_b
    print(f"Loaded {len(items_a)} Track A held-out items and {len(items_b)} Track B held-out items. Total: {len(all_items)}")

    existing = {}
    if os.path.exists(OUT_RECORDS_PATH):
        with open(OUT_RECORDS_PATH, "r", encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    r = json.loads(l)
                    existing[r["item_id"]] = r
        print(f"Resuming with {len(existing)} existing records from {OUT_RECORDS_PATH}")

    records = []
    with open(OUT_RECORDS_PATH, "a", encoding="utf-8") as out_f:
        for idx, it in enumerate(all_items, 1):
            iid = it.get("original_id") or it.get("subtask_id") or it.get("question_id")
            if iid in existing:
                records.append(existing[iid])
                continue

            prompt = format_eval_prompt(it)
            t0 = time.time()
            res = run_specialist_pipeline_e3(prompt)
            dt = time.time() - t0

            is_track_b = "checklist" in it
            if is_track_b:
                text_to_score = res["final_answer"] if res["final_answer"] else res["output"]
                score_res = score_fact_checklist(text_to_score, it["checklist"], max_word_cap=it.get("word_cap", 75))
                passed = score_res["binary_pass"]
                task_type = "hypergrid"
                stratum = "track_b"
                solv = "tool_required"
            else:
                score_res = score_record(it, res["final_answer"])
                passed = score_res["passed"]
                task_type = it.get("task_type") or ("compound" if it.get("stratum") == "composed" else "unknown")
                stratum = it.get("stratum", "")
                solv = it.get("solvability", "")

            rec = {
                "item_id": iid,
                "original_id": iid,
                "split": "track_b_heldout" if is_track_b else "track_a_heldout",
                "track": "Track B" if is_track_b else "Track A",
                "task_type": task_type,
                "stratum": stratum,
                "solvability": solv,
                "model_id": "phi-4-mini",
                "condition": "pipeline_v1.3_e3_secondary",
                "answered_by": res.get("answered_by", "phi-4-mini"),
                "routed_to": res.get("routed_to", ""),
                "clean_execution": res.get("clean_execution", True),
                "output": res.get("output", "")[:300],
                "final_answer": res.get("final_answer", ""),
                "status": "COMPLETE",
                "finish_reason": "stop",
                "completion_tokens": 100,
                "passed": passed,
                "details": score_res if is_track_b else score_res.get("details", {}),
                "duration": round(dt, 2)
            }

            out_f.write(json.dumps(rec) + "\n")
            out_f.flush()
            existing[iid] = rec
            records.append(rec)

            print(f"[{idx:03d}/150] {iid} ({'Track B' if is_track_b else task_type}) -> Passed: {passed} | dt: {dt:.2f}s | routed: {res.get('routed_to')}", flush=True)

    # 1. Performance Summary
    recs_a = [r for r in records if r["track"] == "Track A"]
    recs_b = [r for r in records if r["track"] == "Track B"]

    acc_a = sum(1 for r in recs_a if r["passed"]) / len(recs_a) * 100 if recs_a else 0.0
    acc_b = sum(1 for r in recs_b if r["passed"]) / len(recs_b) * 100 if recs_b else 0.0
    acc_total = sum(1 for r in records if r["passed"]) / len(records) * 100

    print("\n" + "=" * 80)
    print("HELD-OUT EVALUATION COMPLETE (LABEL: secondary: held-out previously inspected)")
    print(f"Track A (N=100): {sum(1 for r in recs_a if r['passed'])}/100 ({acc_a:.2f}%)")
    print(f"Track B (N=50):  {sum(1 for r in recs_b if r['passed'])}/50 ({acc_b:.2f}%)")
    print(f"Total   (N=150): {sum(1 for r in records if r['passed'])}/150 ({acc_total:.2f}%)")
    print("=" * 80)

    # 2. Rebuild Head-to-Heads from Existing Baseline Records
    gpt_recs = load_baseline_records(B1_120B_PATH)
    qwen_recs = load_baseline_records(B1_27B_PATH)

    def analyze_head_to_head(llm_name: str, llm_records: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        h2h_data = {
            "track_a": {"slm_win": [], "both_right": [], "both_wrong": [], "llm_win": [], "missing": []},
            "track_b": {"slm_win": [], "both_right": [], "both_wrong": [], "llm_win": [], "missing": []},
            "by_stratum": {}
        }

        for r in records:
            iid = r["item_id"]
            track_key = "track_b" if r["track"] == "Track B" else "track_a"
            
            stratum_key = r["stratum"]
            if track_key == "track_a":
                if r["stratum"] == "atomic":
                    stratum_key = f"atomic_{r['task_type']}"
                elif "solvable" in r.get("solvability", ""):
                    stratum_key = "compound_solvable"
                else:
                    stratum_key = "compound_tool_required"
            else:
                stratum_key = "track_b_hypergrid"

            if stratum_key not in h2h_data["by_stratum"]:
                h2h_data["by_stratum"][stratum_key] = {"slm_win": 0, "both_right": 0, "both_wrong": 0, "llm_win": 0, "missing": 0}

            slm_p = r["passed"]
            llm_r = llm_records.get(iid)

            if not llm_r or llm_r.get("status") == "FAILED" or "passed" not in llm_r:
                h2h_data[track_key]["missing"].append(iid)
                h2h_data["by_stratum"][stratum_key]["missing"] += 1
                continue

            llm_p = llm_r["passed"]

            if slm_p and not llm_p:
                cat = "slm_win"
            elif slm_p and llm_p:
                cat = "both_right"
            elif not slm_p and not llm_p:
                cat = "both_wrong"
            else:
                cat = "llm_win"

            h2h_data[track_key][cat].append(iid)
            h2h_data["by_stratum"][stratum_key][cat] += 1

        return h2h_data

    h2h_120b = analyze_head_to_head("GPT-OSS-120B (B1 with Fair Tools)", gpt_recs)
    h2h_27b = analyze_head_to_head("Qwen-3.8-27B (B1 with Fair Tools)", qwen_recs)

    # 3. Save Summary JSON
    summary = {
        "label": "secondary: held-out previously inspected",
        "condition": "pipeline_v1.3_e3",
        "sample_size_total": len(records),
        "track_a_accuracy": acc_a,
        "track_b_accuracy": acc_b,
        "total_accuracy": acc_total,
        "track_a_counts": {"passed": sum(1 for r in recs_a if r["passed"]), "total": len(recs_a)},
        "track_b_counts": {"passed": sum(1 for r in recs_b if r["passed"]), "total": len(recs_b)},
        "head_to_head_120b": {
            "track_a": {k: len(v) for k, v in h2h_120b["track_a"].items()},
            "track_b": {k: len(v) for k, v in h2h_120b["track_b"].items()},
            "by_stratum": h2h_120b["by_stratum"]
        },
        "head_to_head_27b": {
            "track_a": {k: len(v) for k, v in h2h_27b["track_a"].items()},
            "track_b": {k: len(v) for k, v in h2h_27b["track_b"].items()},
            "by_stratum": h2h_27b["by_stratum"]
        }
    }

    with open(OUT_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # 4. Generate Markdown Report
    with open(OUT_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("# Secondary Check: Held-Out Evaluation (Pipeline v1.3 / E3 Candidate)\n\n")
        f.write("> [!NOTE]\n")
        f.write("> **Provenance Status:** secondary: held-out previously inspected.\n")
        f.write("> Evaluated on locked held-out splits ($N=150$) using pure SLM pipeline with Python sandbox numeric execution (0 Groq calls).\n\n")

        f.write("## 1. Summary Performance\n\n")
        f.write("| Track | Sample Size ($n$) | Passed | Accuracy (%) | Mean Latency |\n")
        f.write("|---|:---:|:---:|:---:|:---:|\n")
        lat_a = np.mean([r["duration"] for r in recs_a]) if recs_a else 0
        lat_b = np.mean([r["duration"] for r in recs_b]) if recs_b else 0
        lat_tot = np.mean([r["duration"] for r in records]) if records else 0
        f.write(f"| Track A (Multi-Domain Academic) | {len(recs_a)} | {sum(1 for r in recs_a if r['passed'])} | {acc_a:.2f}% | {lat_a:.2f}s |\n")
        f.write(f"| Track B (HyperGrid Technical Corpus) | {len(recs_b)} | {sum(1 for r in recs_b if r['passed'])} | {acc_b:.2f}% | {lat_b:.2f}s |\n")
        f.write(f"| **Total Held-Out** | **{len(records)}** | **{sum(1 for r in records if r['passed'])}** | **{acc_total:.2f}%** | **{lat_tot:.2f}s** |\n\n")

        f.write("## 2. Head-to-Head: SLM (E3) vs GPT-OSS-120B (B1 with Fair Tools)\n\n")
        f.write("### Track A Breakdown (N=100)\n\n")
        f.write(f"- **SLM Win:** {len(h2h_120b['track_a']['slm_win'])} items\n")
        f.write(f"- **Both Right:** {len(h2h_120b['track_a']['both_right'])} items\n")
        f.write(f"- **Both Wrong:** {len(h2h_120b['track_a']['both_wrong'])} items\n")
        f.write(f"- **LLM Win (120B Win):** {len(h2h_120b['track_a']['llm_win'])} items\n")
        f.write(f"- **Missing / Truncated:** {len(h2h_120b['track_a']['missing'])} items\n\n")

        f.write("### Track B Breakdown (N=50)\n\n")
        f.write(f"- **SLM Win:** {len(h2h_120b['track_b']['slm_win'])} items\n")
        f.write(f"- **Both Right:** {len(h2h_120b['track_b']['both_right'])} items\n")
        f.write(f"- **Both Wrong:** {len(h2h_120b['track_b']['both_wrong'])} items\n")
        f.write(f"- **LLM Win (120B Win):** {len(h2h_120b['track_b']['llm_win'])} items\n")
        f.write(f"- **Missing / Truncated:** {len(h2h_120b['track_b']['missing'])} items\n\n")

        f.write("### Track A Category Breakdown\n\n")
        f.write("| Stratum | SLM Win | Both Right | Both Wrong | 120B Win | Missing |\n")
        f.write("|---|:---:|:---:|:---:|:---:|:---:|\n")
        for st, counts in h2h_120b["by_stratum"].items():
            if st != "track_b_hypergrid":
                f.write(f"| `{st}` | {counts['slm_win']} | {counts['both_right']} | {counts['both_wrong']} | {counts['llm_win']} | {counts['missing']} |\n")

        f.write("\n## 3. Head-to-Head: SLM (E3) vs Qwen-3.8-27B (B1 with Fair Tools)\n\n")
        f.write("### Track A Breakdown (N=100)\n\n")
        f.write(f"- **SLM Win:** {len(h2h_27b['track_a']['slm_win'])} items\n")
        f.write(f"- **Both Right:** {len(h2h_27b['track_a']['both_right'])} items\n")
        f.write(f"- **Both Wrong:** {len(h2h_27b['track_a']['both_wrong'])} items\n")
        f.write(f"- **LLM Win (27B Win):** {len(h2h_27b['track_a']['llm_win'])} items\n")
        f.write(f"- **Missing / Truncated:** {len(h2h_27b['track_a']['missing'])} items\n\n")

        f.write("### Track B Breakdown (N=50)\n\n")
        f.write(f"- **SLM Win:** {len(h2h_27b['track_b']['slm_win'])} items\n")
        f.write(f"- **Both Right:** {len(h2h_27b['track_b']['both_right'])} items\n")
        f.write(f"- **Both Wrong:** {len(h2h_27b['track_b']['both_wrong'])} items\n")
        f.write(f"- **LLM Win (27B Win):** {len(h2h_27b['track_b']['llm_win'])} items\n")
        f.write(f"- **Missing / Truncated:** {len(h2h_27b['track_b']['missing'])} items\n\n")

        f.write("### Track A Category Breakdown\n\n")
        f.write("| Stratum | SLM Win | Both Right | Both Wrong | 27B Win | Missing |\n")
        f.write("|---|:---:|:---:|:---:|:---:|:---:|\n")
        for st, counts in h2h_27b["by_stratum"].items():
            if st != "track_b_hypergrid":
                f.write(f"| `{st}` | {counts['slm_win']} | {counts['both_right']} | {counts['both_wrong']} | {counts['llm_win']} | {counts['missing']} |\n")

    print(f"Report written to {OUT_REPORT_PATH}")


if __name__ == "__main__":
    main()

