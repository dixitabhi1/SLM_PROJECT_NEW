import json

with open('results/phase4/c1_diagnosis_detailed.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

it = [x for x in data if x['item_id'] == 'calib_hard_0011'][0]
print(f"ITEM: {it['item_id']} | Solvability: {it['solvability']} | Outcome: {it['outcome']} | Passed: {it['passed']}")
print(f"Gold: {it['gold_answer']}")
print(f"Turns: {len(it['turns'])}")
for t in it['turns']:
    print(f"\n--- Turn {t['turn']} ---")
    print("ASSISTANT:")
    print(t['assistant_content'])
    if t.get('tool_name'):
        print(f"TOOL: {t['tool_name']}")
        print(f"ARGS: {t.get('tool_args')}")
        print(f"OUT: {t.get('tool_output')}")
print("\nFINAL OUTPUT:")
print(it['final_output'])

