import json

with open("results/phase4/versioned_rescore_report.json", "r", encoding="utf-8") as f:
    report = json.load(f)

hca = report["hand_check_audit"]
for chk, d in hca.items():
    print(f"=== CHECKER: {chk} ===")
    print(f"  Passes sampled: {d['sampled_passes_count']} / {d['total_passes_available']}")
    print(f"  Fails sampled:  {d['sampled_fails_count']} / {d['total_fails_available']}")
    for p in d["sampled_passes"][:2]:
        print(f"    PASS sample: {p['item_id']} ({p['model_id']}) -> {p['checker_details'][:60]}")
    for fl in d["sampled_fails"][:2]:
        print(f"    FAIL sample: {fl['item_id']} ({fl['model_id']}) -> {fl['checker_details'][:60]}")

