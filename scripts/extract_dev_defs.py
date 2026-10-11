"""
Extract DEV_DEFS cleanly into scripts/compound_dev_defs.py.
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_FILE = os.path.join(REPO_ROOT, "scripts", "build_hard_compound_dev_40.py")
DEST_FILE = os.path.join(REPO_ROOT, "scripts", "compound_dev_defs.py")

with open(SRC_FILE, "r", encoding="utf-8") as f:
    lines = f.readlines()

start_idx = None
end_idx = None
for i, l in enumerate(lines):
    if l.strip().startswith("defs = ["):
        start_idx = i
    if "Total definitions planned" in l:
        end_idx = i
        break

print(f"Found defs from line {start_idx} to line {end_idx}")

header = '''"""
Dev Split: 40 Hard Compound Definitions.
20 three-stage (10 tool-req, 10 solv w/o tools)
20 two-stage (10 tool-req, 10 solv w/o tools)
"""

from scripts.generate_compound_items import get_table_schema

sch_world = get_table_schema("world_1", ["country", "city"])
sch_flight = get_table_schema("flight_2", ["flights", "airlines"])
sch_orchestra = get_table_schema("orchestra", ["conductor", "orchestra"])
sch_battle = get_table_schema("battle_death", ["death"])
sch_poker = get_table_schema("poker_player", ["poker_player", "people"])
sch_tv = get_table_schema("tvshow", ["TV_series", "TV_Channel"])
sch_dogs = get_table_schema("dog_kennels", ["dogs", "treatments"])
sch_concert = get_table_schema("concert_singer", ["concert", "singer"])
sch_emp = get_table_schema("employee_hire_evaluation", ["employee", "evaluation"])
sch_wta = get_table_schema("wta_1", ["players", "matches"])

'''

defs_body = "".join(lines[start_idx:end_idx]).strip()
# Rename defs = [ to DEV_DEFS = [
if defs_body.startswith("defs = ["):
    defs_body = "DEV_DEFS = [" + defs_body[len("defs = ["):]

# Remove trailing commas or extra brackets if any, ensuring it ends with ]
if not defs_body.endswith("]"):
    # Find last ]
    last_bracket = defs_body.rfind("]")
    if last_bracket != -1:
        defs_body = defs_body[:last_bracket + 1]

with open(DEST_FILE, "w", encoding="utf-8") as f:
    f.write(header + defs_body + "\n")

print(f"Successfully generated {DEST_FILE}")

