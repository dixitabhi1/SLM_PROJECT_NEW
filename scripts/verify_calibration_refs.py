import json

with open('data/calibration_hard_20_items.json', 'r', encoding='utf-8') as f:
    items = json.load(f)

print("=== CALIBRATION ITEMS REFERENCE PROGRAM OUTPUTS ===")
for it in items:
    loc = {}
    exec(it['reference_code'], {}, loc)
    ans = loc.get('final_answer')
    assert ans == it['gold_answer'], f"Mismatch in {it['subtask_id']}: ref={ans} vs gold={it['gold_answer']}"
    print(f"{it['subtask_id']} ({it['solvability']}): reference_program_output = {ans}")
print("ALL 20 REFERENCE PROGRAMS MATCH GOLD EXACTLY!")

