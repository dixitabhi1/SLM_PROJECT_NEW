"""
scripts/build_sql_dev_extended.py

Constructs data/sql_dev_extended.json:
- 100 items selected deterministically from data/raw_official/spider_val.json.
- Strictly disjoint from dev, held-out, and reserve splits.
- Verified executable against real local SQLite databases on disk.
- Fixed random seed: 42.
- Computes and prints cryptographic SHA-256 hash.
"""

import os
import sys
import json
import random
import hashlib
import sqlite3
from typing import Dict, Any, List, Set, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SPIDER_VAL_PATH = os.path.join(REPO_ROOT, "data", "raw_official", "spider_val.json")
DEV_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
HELDOUT_PATH = os.path.join(REPO_ROOT, "data", "track_a_heldout_split.json")
RESERVE_PATH = os.path.join(REPO_ROOT, "data", "reserve_set_quarantine.json")
DB_ROOT = os.path.join(REPO_ROOT, "data", "spider", "database")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "sql_dev_extended.json")

SEED = 42
TARGET_COUNT = 100


def get_used_queries_and_ids() -> Tuple[Set[str], Set[str]]:
    used_questions = set()
    used_ids = set()

    for split_path in [DEV_PATH, HELDOUT_PATH, RESERVE_PATH]:
        if not os.path.exists(split_path):
            continue
        with open(split_path, "r", encoding="utf-8") as f:
            items = json.load(f)
        for it in items:
            if it.get("task_type") == "sql" or it.get("db_id"):
                used_questions.add(it.get("question", "").strip().lower())
                used_ids.add(it.get("original_id") or it.get("item_id"))
            for part in it.get("component_parts", []):
                if part.get("task_type") == "sql":
                    used_questions.add(part.get("question", "").strip().lower())
                    if part.get("original_id"):
                        used_ids.add(part.get("original_id"))

    return used_questions, used_ids


def main():
    print("=" * 80)
    print(f"BUILDING EXTENDED SQL DEV SET (N={TARGET_COUNT}, SEED={SEED})")
    print("=" * 80)

    with open(SPIDER_VAL_PATH, "r", encoding="utf-8") as f:
        spider_val = json.load(f)
    print(f"Loaded {len(spider_val)} raw Spider validation items.")

    used_questions, used_ids = get_used_queries_and_ids()
    print(f"Loaded {len(used_questions)} used questions and {len(used_ids)} used IDs from dev, held-out, reserve.")

    available_dbs = set(os.listdir(DB_ROOT)) if os.path.exists(DB_ROOT) else set()
    print(f"Available local SQLite databases on disk: {len(available_dbs)}")

    # Filter candidates
    candidates = []
    for idx, it in enumerate(spider_val):
        q = it.get("question", "").strip().lower()
        raw_id = it.get("original_id", f"spider_val_{idx:04d}")
        db_id = it.get("db_id", "")

        if q in used_questions or raw_id in used_ids:
            continue
        if db_id not in available_dbs:
            continue

        db_path = os.path.join(DB_ROOT, db_id, f"{db_id}.sqlite")
        if not os.path.exists(db_path):
            continue

        # Test execute gold query
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(it["gold_query"])
            rows = cur.fetchall()
            conn.close()
            candidates.append((it, rows))
        except Exception:
            continue

    print(f"Filtered {len(candidates)} valid, executable, non-overlapping candidate items.")
    assert len(candidates) >= TARGET_COUNT, f"Not enough candidates! Found {len(candidates)} < {TARGET_COUNT}"

    # Deterministic sampling
    # Sort deterministically by original_id first
    candidates.sort(key=lambda x: x[0].get("original_id", ""))
    rng = random.Random(SEED)
    selected = rng.sample(candidates, TARGET_COUNT)
    # Sort selected items by original_id for clean presentation
    selected.sort(key=lambda x: x[0].get("original_id", ""))

    extended_items = []
    for idx, (it, rows) in enumerate(selected, 1):
        item_dict = {
            "item_id": f"spider_dev_ext_{idx:04d}",
            "original_id": it["original_id"],
            "task_type": "sql",
            "stratum": "atomic",
            "source_benchmark": "Spider",
            "source_split": "validation",
            "db_id": it["db_id"],
            "question": it["question"],
            "gold_query": it["gold_query"],
            "gold_rows_sample": [str(r) for r in rows[:5]],
            "row_count": len(rows),
            "download_source": it.get("download_source", "datasets.load_dataset('xlangai/spider', split='validation')")
        }
        extended_items.append(item_dict)

    # Write output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(extended_items, f, indent=2)

    # Cryptographic hash
    with open(OUTPUT_PATH, "rb") as f:
        sha256_hash = hashlib.sha256(f.read()).hexdigest()

    print(f"\nSuccessfully generated: {OUTPUT_PATH}")
    print(f"Total items: {len(extended_items)}")
    print(f"Random seed used: {SEED}")
    print(f"Cryptographic SHA-256 Hash: {sha256_hash}")

    # Database distribution
    from collections import Counter
    db_counts = Counter(it["db_id"] for it in extended_items)
    print("\nDatabase distribution across 100 extended SQL dev items:")
    for db, count in sorted(db_counts.items(), key=lambda x: -x[1]):
        print(f"  - {db:<30}: {count:>2} items")


if __name__ == "__main__":
    main()
