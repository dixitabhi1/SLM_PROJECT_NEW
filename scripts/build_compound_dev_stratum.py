"""
Builds the Compound Stratum for Track A Dev Split (40 items) and 10 Calibration Items.
Adheres strictly to Owner Conditions 2 through 8:
2. Every item carries a reference program that computes all stage values and the final answer; gold values come only from running it.
3. SQL tasks include the table schema in the prompt. Tag each item 'tool-required' or 'solvable without tools' (at least 50% solvable without tools).
4. Every compound item mixes at least two domains. Same-domain chains are strictly prohibited.
5. High difficulty: multi-step maths, SQL with joins/grouping, non-trivial code logic.
6. Varied phrasing and stage order across items (no fixed sentence patterns).
7. Final check evaluates final value however obtained; records whether code was executed.
8. Component parts labeled 'derived from <ID>'.
"""

import os
import sys
import json
import sqlite3
import subprocess

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

def get_db_schema(db_name: str) -> str:
    db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_name, f"{db_name}.sqlite")
    if not os.path.exists(db_path):
        return ""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")
    tables = [r[0] for r in c.fetchall()]
    conn.close()
    # Clean and format schema string
    clean_lines = []
    for t in tables:
        clean = " ".join(t.split())
        clean_lines.append(clean)
    return "; ".join(clean_lines)

# Run a reference python program in memory to verify it produces the gold values
def execute_reference_program(code_str: str) -> str:
    locs = {}
    exec(code_str, {}, locs)
    if "final_answer" not in locs:
        raise ValueError("Reference program must define 'final_answer'")
    return str(locs["final_answer"]).strip()

print("Compound stratum builder module loaded.")
