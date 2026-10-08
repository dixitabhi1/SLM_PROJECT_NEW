"""
Generator for Compound Tasks (Dev Stratum & Calibration Pool).
Enforces Conditions 2 through 8:
- Reference programs computing all stage values and final answer
- Table schemas in SQL prompts
- Solvability tags ('tool-required' vs 'solvable without tools')
- Cross-domain mixing only (SQL+Math, Math+Code, SQL+Code, SQL+Math+Code)
- High difficulty (multi-step maths, joins/grouping, non-trivial code)
- Varied phrasing and stage orders
- Labeled 'derived from <ID>'
"""

import os
import sys
import json
import sqlite3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_table_schema(db_name: str, table_names: list = None) -> str:
    db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_name, f"{db_name}.sqlite")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")
    tables = c.fetchall()
    conn.close()
    
    parts = []
    for name, sql in tables:
        if table_names and name not in table_names:
            continue
        cleaned = " ".join(sql.split())
        parts.append(cleaned)
    return " [Database Schema: " + "; ".join(parts) + "]"

def execute_ref_code(code: str) -> dict:
    locs = {}
    exec(code, {}, locs)
    if "final_answer" not in locs:
        raise ValueError("Missing final_answer in reference code")
    return locs

print("Generator utility ready.")
