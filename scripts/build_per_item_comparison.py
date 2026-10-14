"""
build_per_item_comparison.py — Per-Item Model Comparison Table Generator

Generates a comprehensive per-item comparison table across all 150 held-out evaluation items
comparing:
- SLM: Specialist Pipeline (phi-4-mini, 3.82B, local Vulkan GPU)
- 120B: GPT-OSS-120B with Tools (B1 harness, Groq API)
- 27B: Qwen-3.8-27B with Tools (B1 harness, Groq API)

Table Columns:
- Item ID
- Category
- SLM Answer
- 120B Answer
- 27B Answer
- SLM Mark (PASS/FAIL)
- 120B Mark (PASS/FAIL)
- 27B Mark (PASS/FAIL)
- Outcome (SLM-only win / Tie / LLM-only win)
- Latencies (SLM, 120B, 27B)

Also computes and prints:
- Category Summary Table: Counts of outcomes per category and mean latencies
- Overall Totals
"""

import os
import sys
import json
from collections import defaultdict
from typing import Dict, Any, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
DATA_DIR = os.path.join(REPO_ROOT, "data")
OUTPUT_MD_PATH = os.path.join(REPO_ROOT, "docs", "per_item_model_comparison.md")

from scripts.build_heldout_report import load_unique_records


def clean_snippet(text: str, max_chars: int = 60) -> str:
    """Cleans up text into a compact single-line markdown-friendly snippet."""
    if not text:
        return "*(empty)*"
    s = " ".join(str(text).split())
    # replace markdown pipes to avoid breaking tables
    s = s.replace("|", "/")
    if len(s) > max_chars:
        return s[:max_chars - 3] + "..."
    return s


def get_category_name(item: Dict[str, Any]) -> str:
    if "checklist" in item:
        return "Track B HyperGrid"
    tt = item.get("task_type") or item.get("type") or ""
    if tt == "sql":
        return "Atomic SQL (Spider)"
    elif tt == "qa":
        return "Atomic QA (ARC)"
    elif tt == "code":
        return "Atomic Code (HumanEval)"
    elif tt == "math":
        return "Atomic Math (GSM8K)"
    elif item.get("stratum") == "composed":
        solv = item.get("solvability")
        if solv == "tool-required":
            return "Compound Tool-Required"
        else:
            return "Compound Solvable"
    return "Other"


def main():
    print("=" * 80)
    print("GENERATING PER-ITEM COMPARISON TABLE ACROSS HELD-OUT SPLIT (N=150)")
    print("=" * 80)

    tra_items = json.load(open(os.path.join(DATA_DIR, "track_a_heldout_split.json"), "r", encoding="utf-8"))
    trb_items = json.load(open(os.path.join(DATA_DIR, "track_b", "track_b_heldout_split.json"), "r", encoding="utf-8"))
    all_items = tra_items + trb_items

    pipe_records = load_unique_records(os.path.join(RESULTS_DIR, "heldout_pipeline_records.jsonl"))
    b1_120b_records = load_unique_records(os.path.join(RESULTS_DIR, "b1_gpt120b_heldout_records.jsonl"))
    b1_27b_records = load_unique_records(os.path.join(RESULTS_DIR, "b1_qwen27b_heldout_records.jsonl"))

    category_stats = defaultdict(lambda: {"total": 0, "slm_win": 0, "tie": 0, "llm_win": 0, "lat_slm": [], "lat_120b": [], "lat_27b": []})
    rows = []

    for item in all_items:
        iid = item.get("item_id") or item.get("subtask_id") or item.get("original_id") or item.get("question_id")
        cat = get_category_name(item)

        r_slm = pipe_records.get(iid, {})
        r_120b = b1_120b_records.get(iid, {})
        r_27b = b1_27b_records.get(iid, {})

        slm_pass = bool(r_slm.get("passed", False))
        b120_pass = bool(r_120b.get("passed", False))
        b27_pass = bool(r_27b.get("passed", False))

        # Outcome classification:
        # SLM-only win: SLM passed, BOTH 120B and 27B failed
        # LLM-only win: SLM failed, AT LEAST ONE LLM passed
        # Tie: Either all passed, all failed, or SLM passed and at least one LLM also passed
        if slm_pass and not (b120_pass or b27_pass):
            outcome = "SLM-only win"
            category_stats[cat]["slm_win"] += 1
        elif not slm_pass and (b120_pass or b27_pass):
            outcome = "LLM-only win"
            category_stats[cat]["llm_win"] += 1
        else:
            outcome = "Tie"
            category_stats[cat]["tie"] += 1

        category_stats[cat]["total"] += 1

        # Answers
        slm_ans = clean_snippet(r_slm.get("final_answer") or r_slm.get("output", ""))
        b120_ans = clean_snippet(r_120b.get("output", ""))
        b27_ans = clean_snippet(r_27b.get("output", ""))

        # Latencies
        slm_lat = float(r_slm.get("duration", 0.0) or 0.0)
        b120_lat = float(r_120b.get("duration", 0.0) or r_120b.get("latency_seconds", 0.0) or 0.0)
        b27_lat = float(r_27b.get("duration", 0.0) or r_27b.get("latency_seconds", 0.0) or 0.0)

        category_stats[cat]["lat_slm"].append(slm_lat)
        category_stats[cat]["lat_120b"].append(b120_lat)
        category_stats[cat]["lat_27b"].append(b27_lat)

        slm_mark = "PASS" if slm_pass else "FAIL"
        b120_mark = "PASS" if b120_pass else "FAIL"
        b27_mark = "PASS" if b27_pass else "FAIL"

        rows.append({
            "item_id": iid,
            "category": cat,
            "slm_ans": slm_ans,
            "b120_ans": b120_ans,
            "b27_ans": b27_ans,
            "slm_mark": slm_mark,
            "b120_mark": b120_mark,
            "b27_mark": b27_mark,
            "outcome": outcome,
            "slm_lat": slm_lat,
            "b120_lat": b120_lat,
            "b27_lat": b27_lat,
        })

    # Build Markdown document
    lines = [
        "# Per-Item Model Comparison: SLM Pipeline vs Baselines (B1)",
        "",
        "This document provides the exhaustive per-item comparison and categorical outcome analysis across all 150 items on the held-out split.",
        "",
        "- **SLM Pipeline:** Specialist Pipeline (phi-4-mini, 3.82B, local Vulkan GPU, answered_by: phi-4-mini, 0 Groq calls)",
        "- **120B Baseline:** openai/gpt-oss-120b with Fair Tools (B1 harness, Groq API)",
        "- **27B Baseline:** qwen/qwen3.8-27b with Fair Tools (B1 harness, Groq API)",
        "",
        "---",
        "",
        "## 1. Outcome Summary by Category",
        "",
        "| Category | Total Items | SLM-only Win | Tie | LLM-only Win | SLM Mean Latency | 120B Mean Latency | 27B Mean Latency |",
        "|---|---|---|---|---|---|---|---|",
    ]

    tot_items = 0
    tot_slm_win = 0
    tot_tie = 0
    tot_llm_win = 0
    all_lat_slm = []
    all_lat_120b = []
    all_lat_27b = []

    cat_order = [
        "Atomic SQL (Spider)",
        "Atomic QA (ARC)",
        "Atomic Code (HumanEval)",
        "Atomic Math (GSM8K)",
        "Compound Solvable",
        "Compound Tool-Required",
        "Track B HyperGrid"
    ]

    for cat in cat_order:
        stats = category_stats[cat]
        tot_items += stats["total"]
        tot_slm_win += stats["slm_win"]
        tot_tie += stats["tie"]
        tot_llm_win += stats["llm_win"]
        all_lat_slm.extend(stats["lat_slm"])
        all_lat_120b.extend(stats["lat_120b"])
        all_lat_27b.extend(stats["lat_27b"])

        m_slm = sum(stats["lat_slm"]) / len(stats["lat_slm"]) if stats["lat_slm"] else 0.0
        m_120b = sum(stats["lat_120b"]) / len(stats["lat_120b"]) if stats["lat_120b"] else 0.0
        m_27b = sum(stats["lat_27b"]) / len(stats["lat_27b"]) if stats["lat_27b"] else 0.0

        lines.append(
            f"| **{cat}** | {stats['total']} | {stats['slm_win']} | {stats['tie']} | {stats['llm_win']} | {m_slm:.2f}s | {m_120b:.2f}s | {m_27b:.2f}s |"
        )

    mean_all_slm = sum(all_lat_slm) / len(all_lat_slm) if all_lat_slm else 0.0
    mean_all_120b = sum(all_lat_120b) / len(all_lat_120b) if all_lat_120b else 0.0
    mean_all_27b = sum(all_lat_27b) / len(all_lat_27b) if all_lat_27b else 0.0

    lines.append(
        f"| **Overall Total** | **{tot_items}** | **{tot_slm_win}** | **{tot_tie}** | **{tot_llm_win}** | **{mean_all_slm:.2f}s** | **{mean_all_120b:.2f}s** | **{mean_all_27b:.2f}s** |"
    )
    lines.extend([
        "",
        "---",
        "",
        "## 2. Exhaustive Per-Item Comparison Table",
        "",
        "| Item ID | Category | SLM Answer | 120B Answer | 27B Answer | SLM | 120B | 27B | Outcome | SLM Lat | 120B Lat | 27B Lat |",
        "|---|---|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])

    for r in rows:
        lines.append(
            f"| `{r['item_id']}` | {r['category']} | {r['slm_ans']} | {r['b120_ans']} | {r['b27_ans']} | {r['slm_mark']} | {r['b120_mark']} | {r['b27_mark']} | **{r['outcome']}** | {r['slm_lat']:.2f}s | {r['b120_lat']:.2f}s | {r['b27_lat']:.2f}s |"
        )

    with open(OUTPUT_MD_PATH, "w", encoding="utf-8") as f_out:
        f_out.write("\n".join(lines) + "\n")

    print(f"Written per-item comparison to: {OUTPUT_MD_PATH}")
    print("\nOutcome Summary by Category:")
    for cat in cat_order:
        s = category_stats[cat]
        print(f"  {cat:<25}: Total {s['total']:>2} | SLM Win: {s['slm_win']:>2} | Tie: {s['tie']:>2} | LLM Win: {s['llm_win']:>2}")
    print(f"  {'Total':<25}: Total {tot_items:>2} | SLM Win: {tot_slm_win:>2} | Tie: {tot_tie:>2} | LLM Win: {tot_llm_win:>2}")


if __name__ == "__main__":
    main()
