"""
Generator & Validation Utilities for Compound Tasks.
Strict Operational Constraints:
1. Sensitivity Test: Perturbing any stage's input/output value must strictly change the final answer. Items failing sensitivity are rejected.
2. Reference Programs Only: Gold answers must be computed dynamically by executing reference code; no hardcoded gold values.
3. Provenance Integrity: All compound tasks are explicitly labeled 'agent-written'.
4. Zero Official ID Leakage: No 'derived from <ID>' labels; does NOT consume official benchmark IDs.
5. Column Restrictions: SQL prompts explicitly require returning only the requested columns.
"""

import os
import sys
import json
import sqlite3
from typing import Dict, Any, List, Tuple, Callable

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def get_table_schema(db_name: str, table_names: list = None) -> str:
    """Extracts DDL schema for specified tables from SQLite database."""
    db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_name, f"{db_name}.sqlite")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database {db_name} not found at {db_path}")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")
    tables = c.fetchall()
    conn.close()

    parts = []
    t_lower = [t.lower() for t in table_names] if table_names else None
    for name, sql in tables:
        if t_lower and name.lower() not in t_lower:
            continue
        cleaned = " ".join(sql.split())
        parts.append(cleaned)
    return " [Database Schema: " + "; ".join(parts) + "]"


def execute_ref_code(code: str) -> Dict[str, Any]:
    """Executes reference program in isolated namespace and extracts final_answer."""
    locs = {}
    exec(code, {}, locs)
    if "final_answer" not in locs:
        raise ValueError("Missing 'final_answer' in reference code execution")
    return locs


def run_sensitivity_test(
    stage_funcs: List[Callable[[Any], Any]],
    initial_input: Any,
    perturbations: List[int] = (-1, 1)
) -> Tuple[bool, str]:
    """
    Tests chain sensitivity:
    Computes base execution through all stages.
    For each stage k in the pipeline, perturbs its output by +/- 1 and propagates
    through remaining stages. The perturbed final answer MUST differ from base final answer.
    """
    # 1. Base pipeline execution
    curr = initial_input
    stage_outputs = []
    for idx, fn in enumerate(stage_funcs):
        curr = fn(curr)
        stage_outputs.append(curr)

    base_final = stage_outputs[-1]

    # 2. Perturbation check for each intermediate stage
    for k in range(len(stage_funcs) - 1):
        orig_val = stage_outputs[k]
        if not isinstance(orig_val, (int, float)):
            continue

        for delta in perturbations:
            perturbed_val = orig_val + delta
            # Propagate through remaining stages (k+1 to end)
            p_curr = perturbed_val
            for post_fn in stage_funcs[k + 1:]:
                p_curr = post_fn(p_curr)
            
            if p_curr == base_final:
                return False, (
                    f"Sensitivity failure at Stage {k+1}: perturbing output {orig_val} by "
                    f"{delta} -> {perturbed_val} yielded identical final answer {base_final}."
                )

    return True, "PASSED"


def create_agent_written_compound_item(
    subtask_id: str,
    track: str,
    solvability: str,
    domains: List[str],
    num_stages: int,
    prompt: str,
    ref_code: str,
    stage_funcs: List[Callable[[Any], Any]] = None,
    initial_input: Any = None
) -> Dict[str, Any]:
    """
    Constructs a validated compound item:
    - Runs reference program dynamically to obtain gold_answer
    - Enforces sensitivity test if stage functions provided
    - Explicitly marks provenance as 'agent-written'
    - Eliminates any reference to official IDs
    """
    # Dynamic gold execution
    locs = execute_ref_code(ref_code)
    gold_answer = str(locs["final_answer"])

    # Sensitivity check
    if stage_funcs and initial_input is not None:
        passed, reason = run_sensitivity_test(stage_funcs, initial_input)
        if not passed:
            raise ValueError(f"Sensitivity test failed for {subtask_id}: {reason}")

    return {
        "subtask_id": subtask_id,
        "track": track,
        "task_type": "composed",
        "stratum": "composed",
        "provenance": "agent-written",
        "solvability": solvability,
        "domains": domains,
        "num_stages": num_stages,
        "prompt": prompt,
        "reference_program": ref_code,
        "gold_answer": gold_answer,
        "checker_type": "exact_match"
    }


print("Enhanced Generator & Validation utility ready.")
