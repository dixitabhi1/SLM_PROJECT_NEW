"""
Detailed SQL Failure Audit Script.

Inspects all 11 failed single-domain SQL items (Spider, Dev Split) across:
- C0 (Phi-4-mini)
- B0 (Qwen-27B)
- B0 (GPT-OSS-120B)

Outputs structured analysis:
1. Item ID & Database
2. Question
3. Schema in prompt?
4. Exact prompt sent
5. Gold query & Gold result set
6. Predicted query & Result set per model
7. Root cause & fault assignment (prompt vs checker vs model)
"""

import os
import sys
import json
import sqlite3
import itertools
from typing import Dict, Any, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.eval.versioned_scorer import extract_sql_query, _normalize_row, check_sql_subtask

RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
DEV_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")


def main():
    with open(DEV_PATH, "r", encoding="utf-8") as f:
        dev_items = [it for it in json.load(f) if it.get("task_type") == "sql"]
    dev_by_id = {it["original_id"]: it for it in dev_items}

    # Load 2048 records
    c0 = {x["item_id"]: x for x in [json.loads(l) for l in open(os.path.join(RESULTS_DIR, "c0_phi4_mini_dev_records.jsonl"), encoding="utf-8") if l.strip()] if x.get("max_tokens_budget") == 2048 and x.get("task_type") == "sql"}
    qwen = {x["item_id"]: x for x in [json.loads(l) for l in open(os.path.join(RESULTS_DIR, "b0_qwen27b_dev_records.jsonl"), encoding="utf-8") if l.strip()] if x.get("max_tokens_budget") == 2048 and x.get("task_type") == "sql"}
    gpt = {x["item_id"]: x for x in [json.loads(l) for l in open(os.path.join(RESULTS_DIR, "b0_gpt120b_dev_records.jsonl"), encoding="utf-8") if l.strip()] if x.get("max_tokens_budget") == 2048 and x.get("task_type") == "sql"}

    failed_ids = ['spider_val_0180', 'spider_val_0242', 'spider_val_0263', 'spider_val_0475', 'spider_val_0646', 'spider_val_0676', 'spider_val_0705', 'spider_val_0776', 'spider_val_0797', 'spider_val_0816', 'spider_val_0936']

    audit_records = []

    for it_id in failed_ids:
        it = dev_by_id[it_id]
        db_id = it["db_id"]
        q = it["question"]
        gold_sql = it["gold_query"]
        prompt = c0[it_id]["prompt"]

        db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_id, f"{db_id}.sqlite")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        try:
            cur.execute(gold_sql)
            gold_rows = [_normalize_row(r) for r in cur.fetchall()]
        except Exception as e:
            gold_rows = f"ERROR: {e}"

        schema_in_prompt = "[Database Schema:" in prompt and len(prompt.split("[Database Schema:")[1].split("]")[0].strip()) > 0

        model_evals = {}
        for m_name, rec_dict in [("C0 (Phi-4-mini)", c0), ("B0 (Qwen-27B)", qwen), ("B0 (GPT-OSS-120B)", gpt)]:
            r = rec_dict.get(it_id, {})
            pred_sql = extract_sql_query(r.get("output", ""))
            try:
                cur.execute(pred_sql)
                pred_rows = [_normalize_row(x) for x in cur.fetchall()]
            except Exception as e:
                pred_rows = f"SQL_ERROR: {e}"

            # Check with versioned scorer
            passed_versioned, _, reason = check_sql_subtask(it_id, r.get("output", ""), gold_sql, it)

            model_evals[m_name] = {
                "pred_sql": pred_sql,
                "pred_rows": pred_rows,
                "passed_legacy": r.get("passed", False),
                "passed_versioned": passed_versioned,
                "checker_reason": reason
            }

        conn.close()

        # Diagnose fault
        fault = "Model error"
        if it_id in ["spider_val_0263", "spider_val_0797"]:
            fault = "Checker fault (column order permutation mismatch; semantically correct query, fixed in versioned checker)"
        elif it_id == "spider_val_0646":
            fault = "Spider gold query ambiguity (models used DISTINCT on package options; gold omitted DISTINCT)"
        elif it_id == "spider_val_0242":
            fault = "Spider gold query ambiguity ('at least 10' interpreted as > 10 in gold rather than >= 10; model also projected extra columns)"

        audit_records.append({
            "item_id": it_id,
            "db_id": db_id,
            "question": q,
            "schema_in_prompt": schema_in_prompt,
            "prompt": prompt,
            "gold_sql": gold_sql,
            "gold_rows": gold_rows,
            "model_evals": model_evals,
            "fault_diagnosis": fault
        })

    out_json = os.path.join(RESULTS_DIR, "sql_failure_audit.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(audit_records, f, indent=2)

    print(f"Audited {len(audit_records)} SQL items. Saved to {out_json}")


if __name__ == "__main__":
    main()

