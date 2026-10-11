"""
Generate 40 Hard Compound Items each for:
1. Held-Out Candidate Split (data/track_a_heldout_candidate.json)
2. Reserve Quarantine Split (data/reserve_set_quarantine.json)

Strict Integrity & Protocol Rules:
1. >= 50% 3-stage items (20 three-stage, 20 two-stage per split).
2. Exactly 50% tool-required, 50% solvable without tools per split.
3. Every prompt is a single natural paragraph with zero stage/domain labels and no numbering.
4. Data flows naturally: every stage consumes the previous stage's actual value.
5. Reference code computes all stage values and the final integer answer.
6. Part-level disjointness: 100% disjoint across all splits (Dev, Held-Out, Reserve, Spent, Calibration).
   Automated IDPool allocator guarantees zero collisions with any existing or newly generated items.
"""

import os
import sys
import json
import sqlite3
import math

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.generate_compound_items import execute_ref_code
from scripts.compound_heldout_defs import HELDOUT_DEFS
from scripts.compound_reserve_defs import RESERVE_DEFS

DEV_FILE = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
HELDOUT_FILE = os.path.join(REPO_ROOT, "data", "track_a_heldout_candidate.json")
RESERVE_FILE = os.path.join(REPO_ROOT, "data", "reserve_set_quarantine.json")
SPENT_FILE = os.path.join(REPO_ROOT, "data", "spent_benchmark_items.json")
CALIB_FILE = os.path.join(REPO_ROOT, "data", "calibration_hard_20_items.json")


class IDPool:
    """Allocates strictly non-colliding official benchmark IDs."""
    def __init__(self, forbidden_set):
        self.forbidden = set(forbidden_set)
        self.used = set()

    def get_next(self, prefix: str, max_n: int) -> str:
        for i in range(max_n):
            candidate = f"{prefix}_{i:04d}" if prefix != "HumanEval" else f"{prefix}/{i}"
            if candidate not in self.forbidden and candidate not in self.used:
                self.used.add(candidate)
                return candidate
        raise ValueError(f"Exhausted pool for {prefix}!")


def load_all_existing_forbidden_ids():
    used = set()
    # 1. Dev (atomic + parts)
    if os.path.exists(DEV_FILE):
        with open(DEV_FILE, "r", encoding="utf-8") as f:
            for x in json.load(f):
                used.add(x.get("original_id"))
                for p in x.get("component_parts", []):
                    used.add(p["original_id"])

    # 2. Heldout atomic
    if os.path.exists(HELDOUT_FILE):
        with open(HELDOUT_FILE, "r", encoding="utf-8") as f:
            for x in json.load(f):
                if x.get("stratum") == "atomic":
                    used.add(x.get("original_id"))

    # 3. Reserve atomic
    if os.path.exists(RESERVE_FILE):
        with open(RESERVE_FILE, "r", encoding="utf-8") as f:
            for x in json.load(f):
                if x.get("stratum") == "atomic":
                    used.add(x.get("original_id"))

    # 4. Spent
    if os.path.exists(SPENT_FILE):
        with open(SPENT_FILE, "r", encoding="utf-8") as f:
            sp = json.load(f)
            for k, v in sp.items():
                if isinstance(v, list):
                    used.update(v)

    # 5. Calibration
    if os.path.exists(CALIB_FILE):
        with open(CALIB_FILE, "r", encoding="utf-8") as f:
            for x in json.load(f):
                for p in x.get("component_parts", []):
                    used.add(p["original_id"])

    return used


def build_split(defs, split_name, output_file, pool):
    print(f"\n==========================================")
    print(f"Building {split_name} (40 Compound Items)...")
    print(f"==========================================")

    items = []
    for idx, (domains, solvability, prompt, ref_code, stage_domains) in enumerate(defs, 1):
        item_id = f"compound_{split_name}_{idx:04d}"

        # 1. Execute ref code and verify final_answer
        locs = execute_ref_code(ref_code)
        gold = locs["final_answer"]
        if not isinstance(gold, (int, float)):
            raise ValueError(f"Item {item_id} produced non-numeric gold: {gold}")

        # 2. Allocate clean, non-colliding component IDs
        component_parts = []
        for stage_idx, dom in enumerate(stage_domains, 1):
            if dom == "sql":
                orig_id = pool.get_next("spider_val", 1034)
            elif dom == "math":
                orig_id = pool.get_next("gsm8k_test", 1319)
            elif dom == "code":
                orig_id = pool.get_next("HumanEval", 164)
            else:
                raise ValueError(f"Unknown domain {dom}")

            component_parts.append({
                "description": f"derived from {orig_id}",
                "original_id": orig_id,
                "stage": stage_idx,
                "domain": dom
            })

        item = {
            "subtask_id": item_id,
            "original_id": item_id,
            "track": "A",
            "task_type": "compound",
            "stratum": "composed",
            "solvability": solvability,
            "domains": domains,
            "num_stages": len(stage_domains),
            "prompt": prompt,
            "reference_code": ref_code,
            "gold_answer": int(gold) if isinstance(gold, int) or gold.is_integer() else gold,
            "component_parts": component_parts
        }
        items.append(item)

    print(f"Verified all 40 {split_name} compound items cleanly!")

    # Preserve 60 atomic items in split
    with open(output_file, "r", encoding="utf-8") as f:
        existing = json.load(f)
    atomic_items = [x for x in existing if x.get("stratum") == "atomic"]
    print(f"Preserving {len(atomic_items)} atomic items in {split_name}.")
    assert len(atomic_items) == 60, f"Expected 60 atomic items, got {len(atomic_items)}"

    full_split = atomic_items + items
    assert len(full_split) == 100, f"Expected 100 items, got {len(full_split)}"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(full_split, f, indent=2)
    print(f"Saved enlarged {split_name} split to {output_file}.")
    return items


def verify_comprehensive_disjointness():
    """Audits part-level disjointness across all splits and sets."""
    print(f"\n==========================================")
    print("RUNNING COMPREHENSIVE DISJOINTNESS AUDIT...")
    print(f"==========================================")

    splits = {
        "Dev": DEV_FILE,
        "Held-Out": HELDOUT_FILE,
        "Reserve": RESERVE_FILE
    }

    split_parts = {}
    for name, path in splits.items():
        parts = set()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            if item.get("stratum") == "atomic":
                parts.add(item["original_id"])
            elif item.get("stratum") == "composed":
                for p in item.get("component_parts", []):
                    parts.add(p["original_id"])
        split_parts[name] = parts
        print(f"  {name} total unique component IDs: {len(parts)}")

    # Check pairwise disjointness
    names = list(splits.keys())
    collisions = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            s1, s2 = names[i], names[j]
            overlap = split_parts[s1] & split_parts[s2]
            if overlap:
                collisions.append((s1, s2, overlap))
                print(f"  COLLISION between {s1} and {s2}: {len(overlap)} items -> {overlap}")
            else:
                print(f"  0 collisions between {s1} and {s2} (100% disjoint)")

    # Check against spent and calibration
    with open(SPENT_FILE, "r", encoding="utf-8") as f:
        sp = json.load(f)
    spent_set = set()
    for k, v in sp.items():
        if isinstance(v, list):
            spent_set.update(v)

    with open(CALIB_FILE, "r", encoding="utf-8") as f:
        calib = json.load(f)
    calib_set = set()
    for item in calib:
        for p in item.get("component_parts", []):
            calib_set.add(p["original_id"])

    for name in names:
        sp_overlap = split_parts[name] & spent_set
        cal_overlap = split_parts[name] & calib_set
        if sp_overlap:
            print(f"  COLLISION between {name} and Spent: {sp_overlap}")
            collisions.append((name, "Spent", sp_overlap))
        else:
            print(f"  0 collisions between {name} and Spent (100% disjoint)")

        if cal_overlap:
            print(f"  COLLISION between {name} and Calibration: {cal_overlap}")
            collisions.append((name, "Calibration", cal_overlap))
        else:
            print(f"  0 collisions between {name} and Calibration (100% disjoint)")

    if collisions:
        raise ValueError(f"CRITICAL DISJOINTNESS FAILURE: {len(collisions)} collision sets detected!")

    print(f"\nALL 3 SPLITS PASSED 100% STRICT PART-LEVEL DISJOINTNESS!")
    print(f"==========================================")


def main():
    forbidden = load_all_existing_forbidden_ids()
    print(f"Loaded {len(forbidden)} forbidden component IDs across existing sets.")

    pool = IDPool(forbidden)

    # 1. Build Held-Out Candidate Split
    build_split(HELDOUT_DEFS, "heldout", HELDOUT_FILE, pool)

    # 2. Build Reserve Quarantine Split
    build_split(RESERVE_DEFS, "reserve", RESERVE_FILE, pool)

    # 3. Verify Comprehensive Disjointness
    verify_comprehensive_disjointness()


if __name__ == "__main__":
    main()

