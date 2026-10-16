# Experiment 4 (E4: Learned Adaptive Router) Dev Evaluation Report

- **Date:** 2026-10-16 20:00:42 UTC
- **Pipeline Version:** `v1.4-e4`
- **Base Pipeline:** Frozen Pipeline v1.3 (`v1.3-slm-frozen`, commit `acef7a5`)
- **Model:** `phi-4-mini` (3.82B active parameters, 100% local Vulkan GPU on port 8080)
- **Groq API Calls:** Strictly **0**
- **Raw Records:** [`results/phase4/dev_e4_pipeline_records.jsonl`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/results/phase4/dev_e4_pipeline_records.jsonl)
- **Summary JSON:** [`results/phase4/dev_e4_evaluation_summary.json`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/results/phase4/dev_e4_evaluation_summary.json)

---

## 1. Executive Summary & Pre-Registered Criteria Results

| Criterion | Target Requirement | Empirical Result | Status |
|---|---|---|:---:|
| **Criterion 1 (Track A Paired Bootstrap)** | 95% Bootstrap CI Lower Bound > 0.0 pp | **-1.00 pp [-6.00 pp, +4.00 pp]** | **FAIL** |
| **Criterion 2 (Track A Category Safety)** | No category drops > 1 item vs v1.3 | **Worst category delta: -2 items** | **FAIL** |
| **Criterion 3 (Track B Non-Regression)** | Dev Track B drop <= 1 item vs v1.3 | **48/50 vs 48/50 (Delta: +0)** | **PASS** |

**Overall Verdict:** **CRITERIA NOT MET**

---

## 2. Category Performance Breakdown (Dev Track A & Track B)

| Category | Sample Size ($n$) | Pipeline v1.3 | Pipeline v1.4 (E4) | Delta ($v1.3 \to E4$) |
|---|:---:|:---:|:---:|:---:|
| `atomic_code` | 15 | 13/15 (86.7%) | 13/15 (86.7%) | **+0 (+0.0 pp)** |
| `atomic_math` | 15 | 13/15 (86.7%) | 14/15 (93.3%) | **+1 (+6.7 pp)** |
| `atomic_qa` | 15 | 11/15 (73.3%) | 12/15 (80.0%) | **+1 (+6.7 pp)** |
| `atomic_sql` | 15 | 7/15 (46.7%) | 7/15 (46.7%) | **+0 (+0.0 pp)** |
| `compound_solvable` | 20 | 17/20 (85.0%) | 16/20 (80.0%) | **-1 (-5.0 pp)** |
| `compound_tool_required` | 20 | 16/20 (80.0%) | 14/20 (70.0%) | **-2 (-10.0 pp)** |
| **Dev Track A Total** | **100** | **77/100 (77.0%)** | **76/100 (76.0%)** | **-1.00 pp [-6.00 pp, +4.00 pp]** |
| `track_b_hypergrid` | 50 | 48/50 (96.0%) | 48/50 (96.0%) | **+0 (+0.0 pp)** |
| **Total Dev Evaluation** | **150** | **125/150 (83.3%)** | **124/150 (82.7%)** | **-1 items** |

---

## 3. Head-to-Head Comparison vs Pipeline v1.3

Across all 100 Dev Track A items:
- **E4 Unique Wins (Fixed by Learned Router):** **3 items**
- **Both Right:** **73 items**
- **Both Wrong:** **20 items**
- **v1.3 Unique Wins (Regressions):** **4 items**
- **Net Gain:** **-1 items**

---

## 4. Latency, Cost, and Fallback Rate

- **Mean Latency:**
  - Pipeline v1.3: **8.06s**
  - Pipeline v1.4 (E4): **9.17s** (Delta: +1.11s)
- **Monetary Cost:** **$0.00** (100% local Vulkan GPU serving; 0 Groq calls)
- **Router Fallback Rate:** **27 / 150 (18.0%)**

### Route Selection Distribution on Dev (N=150)
- `direct_reasoner`: 78 / 150 (52.0%)
- `direct_sql`: 15 / 150 (10.0%)
- `code_execution`: 29 / 150 (19.3%)
- `decompose_reasoner`: 12 / 150 (8.0%)
- `decompose_code`: 16 / 150 (10.7%)

---

## 5. Feature Importances: What Decides the Route?

From the trained Logistic Regression models ($L_2$ regularized with latency penalization), the top driving features per route are:
- **`direct_sql`**: Driven by `task_type_sql` (+1.2009), `task_asks_for_query` (+1.2009), and `solvability_atomic` (+0.2969).
- **`code_execution`**: Driven by `solvability_tool_req` (+1.7807), `has_math_ops` (+1.3138), `task_type_math` (+1.0099), `has_hash_box` (+0.9669), and `has_code_syntax` (+0.8972).
- **`direct_reasoner`**: Driven by `has_multiple_choice` (+1.1503), `task_type_math` (+0.9859), and `source_none` (+0.7375).
- **`decompose_code`**: Driven by `solvability_tool_req` (+1.6258), `has_hash_box` (+1.1654), and `task_type_math` (+1.0338).
- **`decompose_reasoner`**: Driven by `source_none` (+0.9634) and `task_type_math` (+0.8240).

---

## 6. Cryptographic Reserve Quarantine Verification

- Quarantine File: `data/reserve_set_quarantine.json`
- Verified SHA-256 Hash: `bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db`
- Status: **100% UNTOUCHED AND UNINSPECTED**.
