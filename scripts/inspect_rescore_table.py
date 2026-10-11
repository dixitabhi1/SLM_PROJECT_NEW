import json

with open("results/phase4/versioned_rescore_report.json", "r", encoding="utf-8") as f:
    report = json.load(f)

print("=== SCORER METADATA ===")
print("Version:", report["scorer_version"])
print("SHA-256:", report["scorer_sha256"])

models = [
    ("C0 (Phi-4-mini)", report["c0_phi4_mini"]),
    ("B0 (Qwen-27B)", report["b0_qwen27b"]),
    ("B0 (GPT-OSS-120B)", report["b0_gpt120b"])
]

strata_order = [
    "all_dev",
    "track_a_all",
    "atomic_all",
    "atomic_math",
    "atomic_code",
    "atomic_sql",
    "atomic_qa",
    "compound_all",
    "compound_solvable_without_tools",
    "compound_tool_required",
    "compound_2_stage",
    "compound_3_stage",
    "track_b_all"
]

for name, mdata in models:
    print(f"\n==========================================================================================================")
    print(f"MODEL: {name}")
    print(f"==========================================================================================================")
    print(f"{'Stratum':<32} | {'Total':<5} | {'Valid':<5} | {'Fail':<5} | {'Trunc':<5} | {'Total Acc [95% CI]':<26} | {'Valid Acc [95% CI]'}")
    print("-" * 106)
    for s in strata_order:
        sd = mdata.get(s)
        if not sd: continue
        tot = sd["n_total"]
        val = sd["n_valid"]
        fail = sd["n_failed"]
        trunc = sd["n_truncated"]
        tot_acc = f"{sd['acc_total']:.1f}% [{sd['ci_total_95'][0]:.1f}, {sd['ci_total_95'][1]:.1f}]"
        val_acc = f"{sd['acc_valid']:.1f}% [{sd['ci_valid_95'][0]:.1f}, {sd['ci_valid_95'][1]:.1f}]"
        print(f"{s:<32} | {tot:>5} | {val:>5} | {fail:>5} | {trunc:>5} | {tot_acc:<26} | {val_acc}")

