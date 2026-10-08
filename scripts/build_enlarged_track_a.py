"""
Build Enlarged Track A Splits (Dev, Held-Out Candidate, Reserve) with Compound Stratum.

Specifications:
- Dev Split: 100 items (60 atomic + 40 compound = 40% compound).
- Held-Out Candidate Split: 100 items (60 atomic + 40 compound = 40% compound).
- Reserve Set: 100 items (60 atomic + 40 compound = 40% compound) quarantined.
- Deterministic sampling seed: 42.
- 100% official downloads, original part IDs preserved.
- Zero agent-written items in atomic stratum.
- All Spider items verified via SQLite execution on real databases on disk.
- Excludes all 50 spent benchmark items.
- Computes cryptographic SHA-256 hashes for all three splits.
"""

import os
import sys
import json
import gzip
import random
import sqlite3
import hashlib
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(REPO_ROOT, "data")
SPIDER_DB_DIR = os.path.join(DATA_DIR, "spider", "database")

# Load spent ledger
with open(os.path.join(DATA_DIR, "spent_benchmark_items.json"), "r", encoding="utf-8") as f:
    spent_ledger = json.load(f)

SPENT_HUMANEVAL = set(spent_ledger.get("new_50_hard_subtasks_spent", []))
SPENT_GSM8K = set(range(25, 40)) # gsm8k_test_0025 to 0039

def load_verified_spider() -> List[Dict[str, Any]]:
    with open(os.path.join(DATA_DIR, "raw_official", "spider_val.json"), "r", encoding="utf-8") as f:
        spider_raw = json.load(f)
    
    verified = []
    for item in spider_raw:
        db_id = item["db_id"]
        db_path = os.path.join(SPIDER_DB_DIR, db_id, f"{db_id}.sqlite")
        if not os.path.exists(db_path):
            continue
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(item["gold_query"])
            rows = cur.fetchall()
            conn.close()
            # Successfully executed on real DB
            verified.append({
                "task_type": "sql",
                "stratum": "atomic",
                "source_benchmark": "Spider",
                "source_split": "validation",
                "original_id": item["original_id"],
                "db_id": db_id,
                "question": item["question"],
                "gold_query": item["gold_query"],
                "gold_rows_sample": [str(r) for r in rows[:5]],
                "row_count": len(rows),
                "download_source": item["download_source"]
            })
        except Exception:
            continue
    print(f"Loaded {len(verified)} verified Spider items with working SQLite DBs.")
    return verified

def load_arc() -> List[Dict[str, Any]]:
    with open(os.path.join(DATA_DIR, "raw_official", "arc_challenge_val.json"), "r", encoding="utf-8") as f:
        arc_raw = json.load(f)
    items = []
    for x in arc_raw:
        items.append({
            "task_type": "qa",
            "stratum": "atomic",
            "source_benchmark": "ARC-Challenge",
            "source_split": "validation",
            "original_id": x["original_id"],
            "question": x["question"],
            "choices": x["choices"],
            "gold_answer": x["gold_answer"],
            "download_source": x["download_source"]
        })
    print(f"Loaded {len(items)} ARC-Challenge validation items.")
    return items

def load_humaneval() -> List[Dict[str, Any]]:
    gz_path = os.path.join(DATA_DIR, "HumanEval.jsonl.gz")
    items = []
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if d["task_id"] in SPENT_HUMANEVAL:
                continue
            items.append({
                "task_type": "code",
                "stratum": "atomic",
                "source_benchmark": "HumanEval",
                "source_split": "test",
                "original_id": d["task_id"],
                "entry_point": d["entry_point"],
                "prompt": d["prompt"],
                "test": d["test"],
                "download_source": "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz"
            })
    print(f"Loaded {len(items)} fresh HumanEval items.")
    return items

def load_gsm8k() -> List[Dict[str, Any]]:
    jsonl_path = os.path.join(DATA_DIR, "gsm8k_test.jsonl")
    items = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if not line.strip() or idx in SPENT_GSM8K:
                continue
            d = json.loads(line)
            ans = d["answer"].split("####")[-1].strip().replace(",", "")
            items.append({
                "task_type": "math",
                "stratum": "atomic",
                "source_benchmark": "GSM8K",
                "source_split": "test",
                "original_id": f"gsm8k_test_{idx:04d}",
                "question": d["question"],
                "gold_solution": d["answer"],
                "gold_number": ans,
                "download_source": "https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl"
            })
    print(f"Loaded {len(items)} fresh GSM8K items.")
    return items

def generate_composed_item(composed_id: str, stage_type: str, item_pool: Dict[str, List[Dict[str, Any]]], rng: random.Random) -> Dict[str, Any]:
    """Generates a deterministic 2-stage or 3-stage compound task chaining atomic items."""
    if stage_type == "2-stage":
        chain_pattern = rng.choice(["sql->math", "math->code", "qa->sql"])
        if chain_pattern == "sql->math":
            sql_item = rng.choice(item_pool["spider"])
            db_id = sql_item["db_id"]
            db_path = os.path.join(SPIDER_DB_DIR, db_id, f"{db_id}.sqlite")
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(sql_item["gold_query"])
            rows = cur.fetchall()
            conn.close()
            # Derive integer result or row count
            if rows and isinstance(rows[0][0], (int, float)):
                k_val = int(rows[0][0])
            else:
                k_val = len(rows)
            if k_val <= 0: k_val = 5

            mult = rng.choice([2, 3, 4, 5])
            add_c = rng.choice([10, 20, 50, 100])
            gold_math = (k_val * mult) + add_c
            
            prompt = (
                f"[Stage 1 - SQL Query]\n"
                f"Database: {db_id}\n"
                f"Question: {sql_item['question']}\n"
                f"Write an SQLite query in ```sql ... ``` to retrieve the result.\n\n"
                f"[Stage 2 - Derived Calculation]\n"
                f"Let K be the resulting integer value from Stage 1.\n"
                f"A logistics facility processes K batches per day. Each batch contains {mult} packages, and an additional {add_c} emergency packages are dispatched daily.\n"
                f"What is the total number of packages processed per day?\n"
                f"Conclude your answer with:\n#### <total_packages>"
            )
            
            return {
                "task_type": "composed",
                "stratum": "composed",
                "stages": 2,
                "chain_type": "sql->math",
                "original_id": composed_id,
                "composed_part_ids": [sql_item["original_id"]],
                "prompt": prompt,
                "stage_1": {
                    "type": "sql",
                    "db_id": db_id,
                    "gold_query": sql_item["gold_query"],
                    "gold_result": k_val,
                    "checker": "check_sqlite_execution"
                },
                "stage_2": {
                    "type": "math",
                    "gold_number": str(gold_math),
                    "checker": "check_exact_numeric"
                }
            }
            
        elif chain_pattern == "math->code":
            math_item = rng.choice(item_pool["gsm8k"])
            try:
                gold_num = int(math_item["gold_number"])
                if gold_num <= 0: gold_num = 18
            except Exception:
                gold_num = 18
                
            compatible_code = [c for c in item_pool["humaneval"] if any(k in c["prompt"] for k in ["int", "number", "string", "List"])]
            if not compatible_code:
                compatible_code = item_pool["humaneval"]
            code_item = rng.choice(compatible_code)
            ep = code_item["entry_point"]
            prompt_snippet = code_item["prompt"].strip()
            
            prompt = (
                f"[Stage 1 - Math Problem]\n"
                f"{math_item['question']}\n"
                f"Conclude your reasoning with:\n#### <number>\n\n"
                f"[Stage 2 - Python Implementation]\n"
                f"Using the integer result N from Stage 1 as context, implement `{ep}`:\n"
                f"```python\n{prompt_snippet}\n```\n"
                f"Wrap your complete implementation in a ```python ... ``` block."
            )
            
            return {
                "task_type": "composed",
                "stratum": "composed",
                "stages": 2,
                "chain_type": "math->code",
                "original_id": composed_id,
                "composed_part_ids": [math_item["original_id"], code_item["original_id"]],
                "prompt": prompt,
                "stage_1": {
                    "type": "math",
                    "gold_number": str(gold_num),
                    "checker": "check_exact_numeric"
                },
                "stage_2": {
                    "type": "code",
                    "entry_point": ep,
                    "full_test": code_item["test"],
                    "checker": "check_python_sandbox"
                }
            }
            
        else: # qa->sql
            qa_item = rng.choice(item_pool["arc"])
            sql_item = rng.choice(item_pool["spider"])
            db_id = sql_item["db_id"]
            gold_ans = qa_item["gold_answer"]
            
            prompt = (
                f"[Stage 1 - Science QA]\n"
                f"{qa_item['question']}\n"
                f"Choices:\n" + "\n".join([f"{k}: {v}" for k, v in qa_item["choices"].items()]) + "\n"
                f"State your choice: Option: <Letter>\n\n"
                f"[Stage 2 - Conditioned SQL]\n"
                f"Database: {db_id}\n"
                f"If the chosen option in Stage 1 is '{gold_ans}', write an SQLite query in ```sql ... ``` for: {sql_item['question']}."
            )
            
            return {
                "task_type": "composed",
                "stratum": "composed",
                "stages": 2,
                "chain_type": "qa->sql",
                "original_id": composed_id,
                "composed_part_ids": [qa_item["original_id"], sql_item["original_id"]],
                "prompt": prompt,
                "stage_1": {
                    "type": "qa",
                    "gold_answer": gold_ans,
                    "checker": "check_multiple_choice"
                },
                "stage_2": {
                    "type": "sql",
                    "db_id": db_id,
                    "gold_query": sql_item["gold_query"],
                    "checker": "check_sqlite_execution"
                }
            }
    else: # 3-stage
        qa_item = rng.choice(item_pool["arc"])
        math_item = rng.choice(item_pool["gsm8k"])
        code_item = rng.choice(item_pool["humaneval"])
        ep = code_item["entry_point"]
        prompt_code = code_item["prompt"].strip()
        gold_opt = qa_item["gold_answer"]
        opt_idx = ord(gold_opt.upper()) - ord('A') + 1 # A=1, B=2, C=3, D=4
        if opt_idx < 1 or opt_idx > 4: opt_idx = 2
        
        scale_val = opt_idx * 15
        gold_math = scale_val * 4 + 20
        
        prompt = (
            f"[Stage 1 - Science Reasoning]\n"
            f"{qa_item['question']}\n"
            f"Choices:\n" + "\n".join([f"{k}: {v}" for k, v in qa_item["choices"].items()]) + "\n"
            f"State your choice: Option: <Letter>\n\n"
            f"[Stage 2 - Parametric Arithmetic]\n"
            f"Map Option A=1, B=2, C=3, D=4 to integer M. A turbine operates at M * 15 RPM.\n"
            f"Over 4 minutes of runtime plus 20 startup rotations, what is the total rotation count?\n"
            f"Conclude with:\n#### <rotations>\n\n"
            f"[Stage 3 - Code Verification]\n"
            f"Write a Python function `sum_to_n(n: int) -> int` in ```python ... ``` that sums integers from 1 to n.\n"
            f"Ensure sum_to_n(M) passes verification."
        )
        
        return {
            "task_type": "composed",
            "stratum": "composed",
            "stages": 3,
            "chain_type": "qa->math->code",
            "original_id": composed_id,
            "composed_part_ids": [qa_item["original_id"], math_item["original_id"], code_item["original_id"]],
            "prompt": prompt,
            "stage_1": {
                "type": "qa",
                "gold_answer": gold_opt,
                "checker": "check_multiple_choice"
            },
            "stage_2": {
                "type": "math",
                "gold_number": str(gold_math),
                "checker": "check_exact_numeric"
            },
            "stage_3": {
                "type": "code",
                "entry_point": "sum_to_n",
                "test_assertion": f"assert sum_to_n({opt_idx}) == {opt_idx * (opt_idx + 1) // 2}",
                "full_test": code_item["test"],
                "checker": "check_python_sandbox"
            }
        }

def build_all_splits():
    rng = random.Random(42)
    spider_all = load_verified_spider()
    arc_all = load_arc()
    humaneval_all = load_humaneval()
    gsm8k_all = load_gsm8k()
    
    # Shuffle pools deterministically with seed 42
    rng.shuffle(spider_all)
    rng.shuffle(arc_all)
    rng.shuffle(humaneval_all)
    rng.shuffle(gsm8k_all)
    
    # Stratum requirements per 100-item split:
    # Atomic: 60 items (15 Spider, 15 ARC, 15 HumanEval, 15 GSM8K)
    # Compound: 40 items (25 2-stage, 15 3-stage)
    
    splits_data = {}
    split_names = ["dev", "heldout_candidate", "reserve"]
    
    # Track used items to guarantee ZERO overlap across Dev, Held-Out, and Reserve
    used_ids = set()
    
    for s_idx, s_name in enumerate(split_names):
        print(f"\n--- Building Split: {s_name.upper()} (100 items) ---")
        
        # 1. Atomic items (60)
        atomics = []
        spider_slice = spider_all[s_idx * 15 : (s_idx + 1) * 15]
        arc_slice = arc_all[s_idx * 15 : (s_idx + 1) * 15]
        code_slice = humaneval_all[s_idx * 15 : (s_idx + 1) * 15]
        math_slice = gsm8k_all[s_idx * 15 : (s_idx + 1) * 15]
        
        for item_list in [spider_slice, arc_slice, code_slice, math_slice]:
            for it in item_list:
                assert it["original_id"] not in used_ids, f"Leakage detected: {it['original_id']}"
                used_ids.add(it["original_id"])
                atomics.append(it)
                
        assert len(atomics) == 60, f"Expected 60 atomic items, got {len(atomics)}"
        
        # 2. Compound items (40: 25 2-stage, 15 3-stage)
        pool = {
            "spider": spider_all[100 + s_idx * 30 : 100 + (s_idx + 1) * 30],
            "arc": arc_all[100 + s_idx * 30 : 100 + (s_idx + 1) * 30],
            "humaneval": humaneval_all[50 + s_idx * 20 : 50 + (s_idx + 1) * 20],
            "gsm8k": gsm8k_all[100 + s_idx * 30 : 100 + (s_idx + 1) * 30],
        }
        
        compounds = []
        for c_i in range(25):
            cid = f"composed_{s_name}_{c_i+1:03d}_2stage"
            compounds.append(generate_composed_item(cid, "2-stage", pool, rng))
        for c_i in range(15):
            cid = f"composed_{s_name}_{c_i+26:03d}_3stage"
            compounds.append(generate_composed_item(cid, "3-stage", pool, rng))
            
        assert len(compounds) == 40, f"Expected 40 compound items, got {len(compounds)}"
        
        full_split = atomics + compounds
        assert len(full_split) == 100, f"Expected 100 items total, got {len(full_split)}"
        splits_data[s_name] = full_split
        print(f"Split {s_name} assembled: 60 atomic + 40 composed = 100 items (40.0% compound).")

    # Save files
    dev_path = os.path.join(DATA_DIR, "track_a_dev_split.json")
    held_path = os.path.join(DATA_DIR, "track_a_heldout_candidate.json")
    res_path = os.path.join(DATA_DIR, "reserve_set_quarantine.json")
    
    with open(dev_path, "w", encoding="utf-8") as f:
        json.dump(splits_data["dev"], f, indent=2)
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump(splits_data["heldout_candidate"], f, indent=2)
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(splits_data["reserve"], f, indent=2)
        
    dev_hash = hashlib.sha256(open(dev_path, "rb").read()).hexdigest()
    held_hash = hashlib.sha256(open(held_path, "rb").read()).hexdigest()
    res_hash = hashlib.sha256(open(res_path, "rb").read()).hexdigest()
    
    print("\n--- CRYPTOGRAPHIC HASHES (SHA-256) ---")
    print(f"Dev Split (100 items): {dev_hash}")
    print(f"Held-Out Candidate (100 items): {held_hash}")
    print(f"Reserve Quarantine (100 items): {res_hash}")
    
    manifest = {
        "metadata": {
            "sampling_seed": 42,
            "method": "deterministic stratified random sampling without replacement from official downloads",
            "pretraining_contamination_note": "Spider, ARC, HumanEval, and GSM8K are public benchmarks with probable presence in training corpora of evaluated models. Track B provides uncontaminated private knowledge test.",
            "total_items_per_split": 100,
            "compound_ratio": "40.0% (40 composed, 60 atomic)",
        },
        "dev_split": {
            "file": dev_path,
            "sha256": dev_hash,
            "count": 100,
            "breakdown": {"Spider_SQL": 15, "ARC_QA": 15, "HumanEval_Code": 15, "GSM8K_Math": 15, "Composed_2Stage": 25, "Composed_3Stage": 15}
        },
        "heldout_candidate": {
            "file": held_path,
            "sha256": held_hash,
            "count": 100,
            "breakdown": {"Spider_SQL": 15, "ARC_QA": 15, "HumanEval_Code": 15, "GSM8K_Math": 15, "Composed_2Stage": 25, "Composed_3Stage": 15}
        },
        "reserve_quarantine": {
            "file": res_path,
            "sha256": res_hash,
            "count": 100,
            "breakdown": {"Spider_SQL": 15, "ARC_QA": 15, "HumanEval_Code": 15, "GSM8K_Math": 15, "Composed_2Stage": 25, "Composed_3Stage": 15}
        }
    }
    
    manifest_path = os.path.join(DATA_DIR, "track_a_splits_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Updated manifest: {manifest_path}")

if __name__ == "__main__":
    build_all_splits()
