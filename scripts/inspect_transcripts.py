import json

with open('results/phase4/c1_diagnosis_detailed.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for item_id in ['calib_hard_0011', 'calib_hard_0003', 'calib_hard_0005']:
    it = [x for x in data if x['item_id'] == item_id][0]
    print('=' * 60)
    print(f"ITEM: {it['item_id']} | Solvability: {it['solvability']} | Outcome: {it['outcome']} | Passed: {it['passed']}")
    print(f"Gold Answer: {it['gold_answer']}")
    print(f"Turns count: {len(it['turns'])}")
    for t in it['turns']:
        print(f"\n--- Turn {t['turn']} ---")
        print("ASSISTANT:")
        print(t['assistant_content'])
        if t.get('tool_name'):
            print(f"TOOL CALLED: {t['tool_name']}")
            print(f"ARGS: {t.get('tool_args')}")
            print(f"TOOL OUTPUT: {t.get('tool_output')}")
    print("\nFINAL OUTPUT:")
    print(it['final_output'])

