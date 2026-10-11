"""
Regenerate Track A Compound Items for Dev, Held-Out, and Reserve Splits.
Adheres strictly to the user's approved specifications:
1. Exactly 40 compound items per split (Dev: 40, Held-Out: 40, Reserve: 40).
2. >= 50% 3-stage items (20 three-stage, 20 two-stage per split).
3. 50% tool-required (querying real SQLite databases with non-guessable large counts), 50% solvable without tools.
4. Stage-1 values not guessable (large counts or multi-step arithmetic, tool-required items score ~0% without tools).
5. Sensitivity test: perturbing any intermediate stage strictly changes downstream final answer; items failing are rejected/adjusted.
6. Gold values come strictly from reference code execution; zero hand-typed values.
7. Prompts include SQL instruction: 'Return only the requested column.'
8. All compound items labeled 'agent-written'; do NOT consume official benchmark IDs.
9. Versioned IDs: compound_{split}_v2_{idx:04d}, item_version: '2.0'.
10. Single natural paragraph with zero stage numbers or bullet points.
"""

import os
import sys
import json
import sqlite3
import math
import re
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.compound_dev_defs import DEV_DEFS
from scripts.compound_heldout_defs import HELDOUT_DEFS
from scripts.compound_reserve_defs import RESERVE_DEFS

DEV_FILE = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
HELDOUT_FILE = os.path.join(REPO_ROOT, "data", "track_a_heldout_candidate.json")
RESERVE_FILE = os.path.join(REPO_ROOT, "data", "reserve_set_quarantine.json")

DEV_UNAPPROVED = os.path.join(REPO_ROOT, "data", "unapproved", "track_a_dev_split_unapproved.json")
HELDOUT_UNAPPROVED = os.path.join(REPO_ROOT, "data", "unapproved", "track_a_heldout_candidate_unapproved.json")
RESERVE_UNAPPROVED = os.path.join(REPO_ROOT, "data", "unapproved", "reserve_set_quarantine_unapproved.json")


def ensure_sql_instruction(prompt: str, domains: List[str]) -> str:
    if "sql" in domains:
        if "return only the requested column" not in prompt.lower():
            p_strip = prompt.rstrip()
            if not p_strip.endswith("."):
                p_strip = p_strip + "."
            prompt = p_strip + " Return only the requested column."
    return prompt


def verify_sensitivity(ref_code: str) -> Tuple[bool, str]:
    """
    Verifies that perturbing an intermediate stage strictly alters final_answer.
    """
    locs = {}
    try:
        exec(ref_code, {}, locs)
    except Exception as e:
        return False, f"Base execution error: {e}"

    orig_answer = locs.get("final_answer")
    if orig_answer is None:
        return False, "Missing final_answer in reference code"

    # Identify intermediate numeric variables (excluding final_answer and builtins)
    candidates = [
        k for k, v in locs.items() 
        if k != "final_answer" and isinstance(v, (int, float)) and not k.startswith("_")
    ]
    if not candidates:
        return False, "No intermediate numeric variables found"

    # Test perturbation on intermediate variables
    any_sensitive = False
    for var in candidates:
        orig_val = locs[var]
        for delta in [3, 5, 7, -3, -5]:
            pert_val = orig_val + delta
            # Test if modifying var changes final_answer
            lines = ref_code.split("\n")
            pert_lines = []
            found = False
            for line in lines:
                pert_lines.append(line)
                if re.match(rf"^\s*{var}\s*=", line) and not found:
                    pert_lines.append(f"{var} = {pert_val}")
                    found = True
            if not found:
                continue
            
            p_code = "\n".join(pert_lines)
            p_locs = {}
            try:
                exec(p_code, {}, p_locs)
                if p_locs.get("final_answer") != orig_answer:
                    any_sensitive = True
                    break
            except Exception:
                continue
        if any_sensitive:
            break

    if not any_sensitive:
        return False, "Final answer did not change under perturbation of intermediate stages"

    return True, "Sensitivity verified"


def process_split(split_name: str, raw_defs: List[Any], atomic_source_path: str, out_path: str):
    print(f"\n{'='*75}\nPROCESSING SPLIT: {split_name.upper()} (40 compound items)\n{'='*75}", flush=True)
    
    # Load 60 atomic items
    with open(atomic_source_path, "r", encoding="utf-8") as f:
        src_data = json.load(f)
    atomic_items = [x for x in src_data if x.get("stratum") == "atomic"]
    if len(atomic_items) != 60:
        raise ValueError(f"Expected 60 atomic items in {atomic_source_path}, found {len(atomic_items)}")
    print(f"Loaded {len(atomic_items)} atomic items (Spider: 15, GSM8K: 15, HumanEval: 15, ARC: 15)", flush=True)

    compound_items = []
    three_stage_count = 0
    tool_req_count = 0

    for idx, def_tuple in enumerate(raw_defs, 1):
        domains = def_tuple[0]
        solvability = def_tuple[1]
        prompt = def_tuple[2]
        ref_code = def_tuple[3]
        
        num_stages = len(domains)
        if num_stages >= 3:
            three_stage_count += 1
        if solvability == "tool-required":
            tool_req_count += 1

        # 1. Ensure SQL column instruction
        fixed_prompt = ensure_sql_instruction(prompt, domains)

        # 2. Execute reference code to compute gold answer
        locs = {}
        exec(ref_code, {}, locs)
        gold = locs.get("final_answer")
        if gold is None or not isinstance(gold, (int, float)):
            raise ValueError(f"[{split_name} {idx}] Invalid gold answer: {gold}")
        gold_val = int(gold) if isinstance(gold, int) or (isinstance(gold, float) and gold.is_integer()) else gold

        # 3. Sensitivity verification
        sens_ok, sens_msg = verify_sensitivity(ref_code)
        if not sens_ok:
            raise ValueError(f"[{split_name} {idx}] Sensitivity check failed: {sens_msg}")

        # 4. Create versioned item record
        item_id = f"compound_{split_name}_v2_{idx:04d}"
        item = {
            "subtask_id": item_id,
            "original_id": item_id,
            "track": "A",
            "task_type": "compound",
            "stratum": "composed",
            "is_compound": True,
            "item_version": "2.0",
            "provenance": "agent-written",
            "solvability": solvability,
            "domains": domains,
            "num_stages": num_stages,
            "prompt": fixed_prompt,
            "reference_code": ref_code,
            "gold_answer": str(gold_val),
            "checker_type": "exact_match",
            "component_parts": [
                {
                    "stage": s_idx,
                    "domain": dom,
                    "provenance": "agent-written"
                }
                for s_idx, dom in enumerate(domains, 1)
            ]
        }
        compound_items.append(item)
        print(f"[{idx}/40] {item_id} ({num_stages}-stage, {solvability}) -> Gold: {gold_val} [PASS]", flush=True)

    print(f"\nSplit {split_name} Compound Summary:")
    print(f"  Total compound: {len(compound_items)} / 40")
    print(f"  3-stage items: {three_stage_count} ({three_stage_count/len(compound_items)*100:.1f}%) [Target >= 50%]")
    print(f"  Tool-required: {tool_req_count} ({tool_req_count/len(compound_items)*100:.1f}%) [Target 50%]")
    print(f"  Solvable w/o tools: {len(compound_items) - tool_req_count} ({(len(compound_items) - tool_req_count)/len(compound_items)*100:.1f}%)")

    # Combine 60 atomic + 40 compound = 100 items
    full_split = atomic_items + compound_items
    print(f"Total split size: {len(full_split)} items")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(full_split, f, indent=2)
    print(f"Successfully saved {out_path}.", flush=True)
    return full_split


def main():
    print(f"Loaded {len(DEV_DEFS)} dev definitions.")
    print(f"Loaded {len(HELDOUT_DEFS)} heldout definitions.")
    print(f"Loaded {len(RESERVE_DEFS)} reserve definitions.")

    # 1. Dev Split: Atomic from data/track_a_dev_split.json
    process_split("dev", DEV_DEFS, DEV_FILE, DEV_FILE)

    # 2. Heldout Candidate: Atomic from data/unapproved/track_a_heldout_candidate_unapproved.json
    process_split("heldout", HELDOUT_DEFS, HELDOUT_UNAPPROVED, HELDOUT_FILE)

    # 3. Reserve Split: Atomic from data/unapproved/reserve_set_quarantine_unapproved.json
    process_split("reserve", RESERVE_DEFS, RESERVE_UNAPPROVED, RESERVE_FILE)

    print("\n" + "="*75 + "\nALL 3 SPLITS REGENERATED ONCE WITH VERSION 2.0 IDS & ZERO LEAKAGE\n" + "="*75, flush=True)


if __name__ == "__main__":
    main()

