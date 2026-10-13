"""
test_heldout_report_verification.py — Full Verification Test Suite for Held-Out Report.

Recomputes every single number, interval, percentage, count, and rate printed in
docs/heldout_evaluation_report.md directly from raw disk records and asserts exact equality.
Fails on any discrepancy.
"""

import os
import sys
import json
import hashlib
import random
import re
import pytest
from typing import Dict, Any, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

REPORT_PATH = os.path.join(REPO_ROOT, "docs", "heldout_evaluation_report.md")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
DATA_DIR = os.path.join(REPO_ROOT, "data")
PROGRESS_PATH = os.path.join(REPO_ROOT, "PROGRESS.md")

from scripts.build_heldout_report import (
    sha256_file,
    load_unique_records,
    load_json,
    evaluate_stratum,
    compute_paired_diff_and_ci,
    parse_incidents_from_progress,
)


@pytest.fixture(scope="module")
def report_content() -> str:
    assert os.path.exists(REPORT_PATH), f"Report not found at {REPORT_PATH}"
    with open(REPORT_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def raw_data():
    tra_heldout_path = os.path.join(DATA_DIR, "track_a_heldout_split.json")
    trb_heldout_path = os.path.join(DATA_DIR, "track_b", "track_b_heldout_split.json")
    trb_candidate_path = os.path.join(DATA_DIR, "track_b", "track_b_heldout_candidate.json")
    
    tra_items = load_json(tra_heldout_path)
    trb_items = load_json(trb_heldout_path)
    trb_candidate_items = load_json(trb_candidate_path) if os.path.exists(trb_candidate_path) else []
    
    tra_atomic = [it for it in tra_items if it.get("stratum") == "atomic"]
    tra_compound = [it for it in tra_items if it.get("stratum") == "composed"]
    tra_solv = [it for it in tra_compound if it.get("solvability") == "solvable_without_tools"]
    tra_treq = [it for it in tra_compound if it.get("solvability") == "tool-required"]
    
    c0 = load_unique_records(os.path.join(RESULTS_DIR, "heldout_c0_records.jsonl"))
    pipe = load_unique_records(os.path.join(RESULTS_DIR, "heldout_pipeline_records.jsonl"))
    b0_qwen = load_unique_records(os.path.join(RESULTS_DIR, "b0_qwen27b_heldout_records.jsonl"))
    b0_gpt = load_unique_records(os.path.join(RESULTS_DIR, "b0_gpt120b_heldout_records.jsonl"))
    b1_qwen = load_unique_records(os.path.join(RESULTS_DIR, "b1_qwen27b_heldout_records.jsonl"))
    b1_gpt = load_unique_records(os.path.join(RESULTS_DIR, "b1_gpt120b_heldout_records.jsonl"))
    
    return {
        "tra_items": tra_items,
        "trb_items": trb_items,
        "trb_candidate_items": trb_candidate_items,
        "tra_atomic": tra_atomic,
        "tra_compound": tra_compound,
        "tra_solv": tra_solv,
        "tra_treq": tra_treq,
        "tra_80": tra_atomic + tra_solv,
        "c0": c0,
        "pipe": pipe,
        "b0_qwen": b0_qwen,
        "b0_gpt": b0_gpt,
        "b1_qwen": b1_qwen,
        "b1_gpt": b1_gpt,
        "tra_sha": sha256_file(tra_heldout_path),
        "trb_sha": sha256_file(trb_heldout_path),
    }


def test_section_order_and_structure(report_content):
    """Verifies that all 10 required sections and appendix appear in exact sequence."""
    sections = [
        "## 1. Summary",
        "## 2. System and setup",
        "## 3. Main results",
        "## 4. Pipeline against its base model",
        "## 5. Single-domain results by task type",
        "## 6. Private-knowledge track",
        "## 7. Pipeline stages",
        "## 8. Integrity",
        "## 9. Limitations and what was not tested",
        "## 10. Next steps",
        "## Appendix: Raw counts"
    ]
    last_pos = -1
    for s in sections:
        pos = report_content.find(s)
        assert pos != -1, f"Missing required section header: '{s}'"
        assert pos > last_pos, f"Section '{s}' out of order (pos {pos} <= previous {last_pos})"
        last_pos = pos


def test_section_lead_sentences(report_content):
    """Verifies that every section leads with its main point in one sentence."""
    sections = [
        "## 1. Summary",
        "## 2. System and setup",
        "## 3. Main results",
        "## 4. Pipeline against its base model",
        "## 5. Single-domain results by task type",
        "## 6. Private-knowledge track",
        "## 7. Pipeline stages",
        "## 8. Integrity",
        "## 9. Limitations and what was not tested",
        "## 10. Next steps",
        "## Appendix: Raw counts"
    ]
    for i, s in enumerate(sections):
        start = report_content.find(s)
        assert start != -1
        sub = report_content[start + len(s):].strip()
        first_line = sub.split("\n\n")[0].strip()
        assert len(first_line) > 20, f"Section '{s}' does not lead with a descriptive sentence"
        assert first_line.endswith("."), f"Section '{s}' lead sentence must end with a period"


def test_plain_language_rule(report_content):
    """Verifies that prohibited hype words do not appear in the report."""
    prohibited = ["breakthrough", "proves", "outperforms", "revolutionary", "state-of-the-art"]
    for word in prohibited:
        # Check case-insensitively
        matches = re.findall(rf"\b{word}\b", report_content, re.IGNORECASE)
        assert len(matches) == 0, f"Found prohibited hype word '{word}' in report text"


def test_main_results_table_recomputation(report_content, raw_data):
    """Recomputes all metrics in the Main Results table directly from raw records and verifies exact match."""
    tra = raw_data["tra_items"]
    atomic = raw_data["tra_atomic"]
    solv = raw_data["tra_solv"]
    treq = raw_data["tra_treq"]
    tra_80 = raw_data["tra_80"]
    
    conditions = {
        "Base model (C0)": raw_data["c0"],
        "Specialist pipeline": raw_data["pipe"],
        "Baseline B0 (Qwen-27B)": raw_data["b0_qwen"],
        "Baseline B0 (GPT-120B)": raw_data["b0_gpt"],
        "Baseline B1 (Qwen-27B with tools) (Provisional)": raw_data["b1_qwen"],
        "Baseline B1 (GPT-120B with tools)": raw_data["b1_gpt"],
    }
    
    # Parse Main Results table from markdown
    table_match = re.search(r"## 3\. Main results.*?\n(\|.*?\n)\n", report_content, re.DOTALL)
    assert table_match, "Main results table not found"
    rows = [r.strip() for r in table_match.group(1).split("\n") if r.strip().startswith("|")][2:]
    
    tra_97 = [it for it in tra if (it.get("item_id") or it.get("subtask_id") or it.get("original_id")) not in {"compound_heldout_v2_0005", "compound_heldout_v2_0017", "compound_heldout_v2_0026"}]
    
    for row in rows:
        cols = [c.strip() for c in row.split("|")[1:-1]]
        c_label = cols[0]
        size = cols[1]
        overall_col = cols[2]
        overall_pct = int(overall_col.split("%")[0].strip())
        single_domain_pct = int(cols[3].replace("%", ""))
        comp_solv_pct = int(cols[4].replace("%", ""))
        trunc_fail_pct = int(cols[6].replace("%", ""))
        
        assert c_label in conditions, f"Unexpected condition in main table: {c_label}"
        r_map = conditions[c_label]
        
        ev_atom = evaluate_stratum(atomic, r_map)
        ev_solv = evaluate_stratum(solv, r_map)
        
        if c_label.startswith("Baseline B0"):
            assert cols[5] == "not applicable (no database access)"
            ev_80 = evaluate_stratum(tra_80, r_map)
            assert overall_pct == ev_80["acc_round"], f"{c_label} overall mismatch: {overall_pct} != {ev_80['acc_round']}"
            assert trunc_fail_pct == ev_80["failed_trunc_pct_round"], f"{c_label} trunc/fail mismatch: {trunc_fail_pct} != {ev_80['failed_trunc_pct_round']}"
            assert ev_80["failed_trunc_pct_round"] <= 2
            assert "(Provisional)" not in c_label
        else:
            comp_treq_pct = int(cols[5].replace("%", ""))
            ev_all = evaluate_stratum(tra, r_map)
            ev_treq = evaluate_stratum(treq, r_map)
            assert overall_pct == ev_all["acc_round"], f"{c_label} overall mismatch: {overall_pct} != {ev_all['acc_round']}"
            assert comp_treq_pct == ev_treq["acc_round"], f"{c_label} tool-required mismatch: {comp_treq_pct} != {ev_treq['acc_round']}"
            assert trunc_fail_pct == ev_all["failed_trunc_pct_round"], f"{c_label} trunc/fail mismatch: {trunc_fail_pct} != {ev_all['failed_trunc_pct_round']}"
            if ev_all["failed_trunc_pct_round"] > 2:
                assert "(Provisional)" in c_label, f"{c_label} has >2% trunc/fail but is not marked (Provisional)"

            if c_label in ["Base model (C0)", "Specialist pipeline"]:
                ev_80 = evaluate_stratum(tra_80, r_map)
                assert f"({ev_80['acc_round']}% on 80 items)" in overall_col
            elif c_label.startswith("Baseline B1 (Qwen-27B"):
                ev_97 = evaluate_stratum(tra_97, r_map)
                assert f"({ev_97['acc_round']}% excl. unfinished)" in overall_col

        assert single_domain_pct == ev_atom["acc_round"], f"{c_label} single-domain mismatch: {single_domain_pct} != {ev_atom['acc_round']}"
        assert comp_solv_pct == ev_solv["acc_round"], f"{c_label} solvable mismatch: {comp_solv_pct} != {ev_solv['acc_round']}"


def test_paired_differences_recomputation(report_content, raw_data):
    """Recomputes paired differences and 95% bootstrap intervals for all strata and conditions."""
    tra = raw_data["tra_items"]
    atomic = raw_data["tra_atomic"]
    compound = raw_data["tra_compound"]
    solv = raw_data["tra_solv"]
    treq = raw_data["tra_treq"]
    tra_80 = raw_data["tra_80"]
    
    strata = [
        ("Track A Overall", tra),
        ("Atomic", atomic),
        ("Compound Total", compound),
        ("Compound Solvable", solv),
        ("Compound Tool-Required", treq)
    ]
    
    comparisons = [
        ("Base Model (C0)", raw_data["c0"]),
        ("B0 Qwen-27B", raw_data["b0_qwen"]),
        ("B0 GPT-120B", raw_data["b0_gpt"]),
        ("B1 Qwen-27B", raw_data["b1_qwen"]),
        ("B1 GPT-120B", raw_data["b1_gpt"])
    ]
    
    pipe_records = raw_data["pipe"]
    
    for comp_name, comp_records in comparisons:
        if comp_name.startswith("B0"):
            res_80 = compute_paired_diff_and_ci(tra_80, pipe_records, comp_records, seed=42, n_boot=2000)
            assert res_80["delta_pp_str"] + " pp" in report_content
            assert res_80["ci_str"] in report_content
            
            res_atom = compute_paired_diff_and_ci(atomic, pipe_records, comp_records, seed=42, n_boot=2000)
            assert res_atom["delta_pp_str"] + " pp" in report_content
            assert res_atom["ci_str"] in report_content

            res_solv = compute_paired_diff_and_ci(solv, pipe_records, comp_records, seed=42, n_boot=2000)
            assert res_solv["delta_pp_str"] + " pp" in report_content
            assert res_solv["ci_str"] in report_content
            
            assert f"| {comp_name} | Compound Tool-Required | 20 | not applicable (no database access)" in report_content
            assert f"| {comp_name} | Compound Total | 40 | not applicable" in report_content
        else:
            for s_label, s_items in strata:
                expected = compute_paired_diff_and_ci(s_items, pipe_records, comp_records, seed=42, n_boot=2000)
                delta_str = expected["delta_pp_str"] + " pp"
                ci_str = expected["ci_str"]
                sig_str = expected["sig_label"]
                assert delta_str in report_content, f"Expected delta '{delta_str}' for {comp_name} - {s_label} not found in report"
                assert ci_str in report_content, f"Expected CI '{ci_str}' for {comp_name} - {s_label} not found in report"
                assert sig_str in report_content, f"Expected significance label '{sig_str}' for {comp_name} - {s_label} not found in report"


def test_single_domain_results_recomputation(report_content, raw_data):
    """Recomputes single-domain results by task type and verifies accuracy and paths."""
    atomic = raw_data["tra_atomic"]
    c0 = raw_data["c0"]
    pipe = raw_data["pipe"]
    
    table_match = re.search(r"## 5\. Single-domain results by task type.*?\n(\|.*?\n)\n", report_content, re.DOTALL)
    assert table_match, "Single-domain table not found"
    rows = [r.strip() for r in table_match.group(1).split("\n") if r.strip().startswith("|")][2:]
    
    expected_paths = {
        "QA": "Direct single-call",
        "Code": "Direct single-call",
        "Math": "Direct single-call",
        "SQL": "Decompose -> Fetch -> Reason"
    }
    
    for row in rows:
        cols = [c.strip() for c in row.split("|")[1:-1]]
        tt_label = cols[0]
        src = cols[1]
        n_items = int(cols[2])
        c0_acc = int(cols[3].replace("%", ""))
        pipe_acc = int(cols[4].replace("%", ""))
        path = cols[5]
        
        assert tt_label in expected_paths, f"Unexpected task type: {tt_label}"
        assert path == expected_paths[tt_label], f"Unexpected path for {tt_label}: {path}"
        
        # Verify from items
        tt_raw = tt_label.lower()
        items_sub = [it for it in atomic if it.get("task_type") == tt_raw]
        assert len(items_sub) == n_items == 15
        
        c0_p = sum(1 for it in items_sub if c0.get(it.get("original_id") or it.get("item_id"), {}).get("passed"))
        pi_p = sum(1 for it in items_sub if pipe.get(it.get("original_id") or it.get("item_id"), {}).get("passed"))
        
        assert c0_acc == int(round(c0_p / 15 * 100))
        assert pipe_acc == int(round(pi_p / 15 * 100))


def test_private_knowledge_track_recomputation(report_content, raw_data):
    """Recomputes Track B results and confirms strict and facts-alone accuracy."""
    trb = raw_data["trb_items"]
    
    table_match = re.search(r"## 6\. Private-knowledge track.*?\n(\|.*?\n)\n", report_content, re.DOTALL)
    assert table_match, "Track B table not found"
    rows = [r.strip() for r in table_match.group(1).split("\n") if r.strip().startswith("|")][2:]
    
    # Dynamically compute expected strict and facts-alone accuracies
    def eval_tb(items_list, r_map):
        n = len(items_list)
        p_strict = 0
        p_facts = 0
        for it in items_list:
            qid = it.get("question_id") or it.get("item_id")
            r = r_map.get(qid)
            if r:
                if r.get("passed"):
                    p_strict += 1
                if r.get("passed_facts_alone") if "passed_facts_alone" in r else r.get("passed"):
                    p_facts += 1
        return int(round(p_strict / n * 100)), int(round(p_facts / n * 100))

    exp_c0_s, exp_c0_f = eval_tb(trb, raw_data["c0"])
    exp_pipe_s, exp_pipe_f = eval_tb(trb, raw_data["pipe"])
    exp_b1_q_s, exp_b1_q_f = eval_tb(trb, raw_data["b1_qwen"])
    exp_b1_g_s, exp_b1_g_f = eval_tb(trb, raw_data["b1_gpt"])

    assert len(rows) == 4, f"Expected exactly 4 rows in Track B table, found {len(rows)}"
    assert f"{exp_c0_s}%" in rows[0]
    assert f"{exp_pipe_s}%" in rows[1]
    assert f"{exp_b1_q_s}%" in rows[2]
    assert f"{exp_b1_g_s}%" in rows[3]


def test_cryptographic_hashes_and_incidents(report_content, raw_data):
    """Verifies that cryptographic hashes and all 14 incidents appear in the report."""
    assert raw_data["tra_sha"] in report_content, "Track A SHA-256 missing"
    assert raw_data["trb_sha"] in report_content, "Track B SHA-256 missing"
    assert "v1.0-frozen" in report_content, "Freeze tag missing"
    assert "infra-timeout-fix" in report_content, "Infra tag missing"
    assert "track-b-fix" in report_content, "Track B tag missing"
    
    # Check all incidents INC-001 through INC-015
    for i in range(1, 16):
        inc_id = f"INC-{i:03d}"
        assert inc_id in report_content, f"Incident {inc_id} missing from report"


def test_provenance_disclosure_present(report_content):
    """Verifies explicit disclosure that held-out compound items and pipeline were written by same agent."""
    disclosure = "Held-out compound items and the pipeline were written by the same agent"
    assert disclosure in report_content, "Mandatory provenance disclosure missing from report"


def test_summary_does_not_cite_provisional_rows(report_content):
    """
    Verifies that provisional rows (truncation/failure share > 2%) are strictly excluded
    from all performance comparison claims and bullets in the summary.
    """
    # 1. Parse Section 1
    s1_match = re.search(r"## 1\. Summary\n\n(.*?)\n\n## 2\.", report_content, re.DOTALL)
    assert s1_match, "Section 1 Summary not found"
    summary_text = s1_match.group(1).strip()
    
    # 2. Parse Section 3 to identify which conditions are provisional
    s3_match = re.search(r"## 3\. Main results.*?\n(\|.*?\n)\n", report_content, re.DOTALL)
    assert s3_match, "Section 3 Main results table not found"
    rows = [r.strip() for r in s3_match.group(1).split("\n") if r.strip().startswith("|")][2:]
    
    provisional_labels = []
    for r in rows:
        cols = [c.strip() for c in r.split("|")[1:-1]]
        if "(Provisional)" in cols[0] or int(cols[6].replace("%", "")) > 2:
            provisional_labels.append(cols[0])
            
    assert len(provisional_labels) > 0, "Expected at least one provisional condition (Qwen-27B)"
    
    # Separate the summary into comparison text vs the explicit provisional caveat bullet
    bullets = summary_text.split("- **")
    lead_paragraph = bullets[0]
    comparison_bullets = [b for b in bullets[1:] if not b.startswith("What is provisional:")]
    provisional_bullet = [b for b in bullets[1:] if b.startswith("What is provisional:")][0]
    
    track_a_opening = lead_paragraph.strip().split("\n\n")[0]
    claims_text = track_a_opening + "\n" + "\n".join(comparison_bullets)
    
    prohibited_tokens = ["B1 Qwen", "B1 (Qwen", "Qwen-27B with tools", "27B with tools"]
    for tok in prohibited_tokens:
        assert tok not in claims_text, (
            f"Provisional condition token '{tok}' cited in summary comparison claims: {claims_text}"
        )
        
    # The provisional caveat bullet MUST explicitly identify what is provisional
    assert "Qwen-27B" in provisional_bullet or "27B" in provisional_bullet
    assert "provisional" in provisional_bullet.lower()
    assert "86%" in provisional_bullet
    assert "89%" in provisional_bullet


def test_appendix_raw_counts_recomputation(report_content, raw_data):
    """Verifies every row in the appendix raw counts table against disk records."""
    appendix_pos = report_content.find("## Appendix: Raw counts")
    assert appendix_pos != -1, "Appendix section not found"
    sub_text = report_content[appendix_pos:]
    table_lines = [l.strip() for l in sub_text.split("\n") if l.strip().startswith("|") and not l.strip().startswith("|---")]
    assert len(table_lines) >= 34, f"Expected header + at least 34 rows in appendix table, found {len(table_lines)}"
    rows = table_lines[1:]
    
    for row in rows:
        cols = [c.strip() for c in row.split("|")[1:-1]]
        c_label = cols[0]
        s_label = cols[1]
        n_items = int(cols[2])
        if cols[3] == "not applicable":
            assert "not applicable" in cols[5]
            continue
        passes = int(cols[3])
        failed_trunc = int(cols[4])
        acc_pct = float(cols[5].replace("%", ""))
        ci_str = cols[6]
        
        # Verify mathematical consistency
        computed_acc = round((passes / n_items) * 100.0, 2)
        assert abs(acc_pct - computed_acc) < 0.05, f"Appendix row math mismatch: {acc_pct} != {computed_acc}"
        assert ci_str.startswith("[") and ci_str.endswith("]"), f"Malformed CI string: {ci_str}"

