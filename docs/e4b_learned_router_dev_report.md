# Experiment 4b (E4b: Retrained Learned Router) Dev Evaluation Report

- **Date:** 2026-10-16 22:57:19 UTC
- **Pipeline Version:** `v1.4b-e4b`
- **Base Pipeline:** Frozen Pipeline v1.3 (`v1.3-slm-frozen`, commit `acef7a5`)
- **Model:** `phi-4-mini` (3.82B active parameters, 100% local Vulkan GPU on port 8080)
- **Groq API Calls:** Strictly **0**
- **Raw Records:** [`results/phase4/dev_e4b_pipeline_records.jsonl`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/results/phase4/dev_e4b_pipeline_records.jsonl)
- **Summary JSON:** [`results/phase4/dev_e4b_evaluation_summary.json`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/results/phase4/dev_e4b_evaluation_summary.json)

---

## 1. Executive Summary & Pre-Registered Criteria Results

| Criterion | Target Requirement | Empirical Result | Status |
|---|---|---|:---:|
| **Criterion 1 (Track A Paired Bootstrap)** | 95% Bootstrap CI Lower Bound > 0.0 pp | **-11.00 pp [-19.00 pp, -3.00 pp]** | **FAIL** |
| **Criterion 2 (Track A Category Safety)** | No category drops > 1 item vs v1.3 | **Worst category delta: -11 items** | **FAIL** |
| **Criterion 3 (Track B Non-Regression)** | Dev Track B drop <= 1 item vs v1.3 | **48/50 vs 48/50 (Delta: +0)** | **PASS** |

**Overall Verdict:** **CRITERIA NOT MET**

---

## 2. Category Performance Breakdown (Dev Track A & Track B)

| Category | Sample Size ($n$) | Pipeline v1.3 | Pipeline v1.4b (E4b) | Delta ($v1.3 \to E4b$) |
|---|:---:|:---:|:---:|:---:|
| `atomic_sql` | 15 | 7/15 (46.7%) | 7/15 (46.7%) | **+0 (+0.0 pp)** |
| `atomic_qa` | 15 | 11/15 (73.3%) | 12/15 (80.0%) | **+1 (+6.7 pp)** |
| `atomic_code` | 15 | 13/15 (86.7%) | 13/15 (86.7%) | **+0 (+0.0 pp)** |
| `atomic_math` | 15 | 13/15 (86.7%) | 14/15 (93.3%) | **+1 (+6.7 pp)** |
| `compound_tool_required` | 20 | 16/20 (80.0%) | 5/20 (25.0%) | **-11 (-55.0 pp)** |
| `compound_solvable` | 20 | 17/20 (85.0%) | 15/20 (75.0%) | **-2 (-10.0 pp)** |
| `track_b_hypergrid` | 50 | 48/50 (96.0%) | 48/50 (96.0%) | **+0 (+0.0 pp)** |
| **Dev Track A Total** | **100** | **77/100 (77.0%)** | **66/100 (66.0%)** | **-11.00 pp [-19.00 pp, -3.00 pp]** |
| `track_b_hypergrid` | 50 | 48/50 (96.0%) | 48/50 (96.0%) | **+0 (+0.0 pp)** |
| **Total Dev Evaluation** | **150** | **125/150 (83.3%)** | **114/150 (76.0%)** | **-11 items** |

---

## 3. Head-to-Head Comparison vs Pipeline v1.3

Across all 100 Dev Track A items:
- **E4b Unique Wins (Fixed by Learned Router):** **3 items**
  - `Mercury_7183733` (`atomic_qa`) -> routed to `direct_reasoner`
  - `gsm8k_test_0530` (`atomic_math`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0009` (`compound_tool_required`) -> routed to `direct_reasoner`

- **v1.3 Unique Wins (Regressions):** **14 items**
  - `compound_dev_v2_0002` (`compound_tool_required`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0004` (`compound_tool_required`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0005` (`compound_tool_required`) -> routed to `decompose_reasoner`
  - `compound_dev_v2_0007` (`compound_tool_required`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0008` (`compound_tool_required`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0017` (`compound_solvable`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0021` (`compound_tool_required`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0023` (`compound_tool_required`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0024` (`compound_tool_required`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0026` (`compound_tool_required`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0028` (`compound_tool_required`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0029` (`compound_tool_required`) -> routed to `direct_reasoner`
  - `compound_dev_v2_0030` (`compound_tool_required`) -> routed to `decompose_reasoner`
  - `compound_dev_v2_0034` (`compound_solvable`) -> routed to `direct_reasoner`

- **Both Right:** **63 items**
- **Both Wrong:** **20 items**
- **Net Gain:** **-11 items**

---

## 4. Latency, Cost, and Fallback Rate

- **Mean Latency:**
  - Pipeline v1.3: **8.06s**
  - Pipeline v1.4b (E4b): **8.75s** (Delta: +0.69s)
- **Monetary Cost:** **$0.00** (100% local Vulkan GPU serving; 0 Groq calls)
- **Router Fallback Rate:** **26 / 150 (17.3%)**

### Route Selection Distribution on Dev (N=150)
- `direct_reasoner`: 96 / 150 (64.0%)
- `direct_sql`: 16 / 150 (10.7%)
- `code_execution`: 30 / 150 (20.0%)
- `decompose_reasoner`: 8 / 150 (5.3%)
- `decompose_code`: 0 / 150 (0.0%)

---

## 5. Cryptographic Reserve Quarantine Verification

- Quarantine File: `data/reserve_set_quarantine.json`
- Verified SHA-256 Hash: `bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db`
- Status: **100% UNTOUCHED AND UNINSPECTED**.
