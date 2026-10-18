# Final Reserve Evaluation Report (Track A, N=100)

- **Date:** 2026-10-18 15:10:17 UTC
- **Reserve Split File:** `data/reserve_set_quarantine.json`
- **Reserve SHA-256 (Pre-Run):** `bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db` [VERIFIED]
- **Reserve SHA-256 (Post-Run):** `bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db` [VERIFIED]
- **Pipeline Version:** `v1.3-slm-frozen` (3.82B active parameters, RTX 3050 Laptop GPU, Vulkan0, port 8080)
- **Pipeline Groq Calls:** Strictly **0** ($0.00 spend)
- **Raw Records (Append-Only):**
  - Specialist Pipeline Run 1 (Primary): [`results/phase4/reserve_final_pipeline_records.jsonl`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/results/phase4/reserve_final_pipeline_records.jsonl)
  - Specialist Pipeline Run 2 (Confirmation): [`results/phase4/reserve_final_pipeline_run2_records.jsonl`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/results/phase4/reserve_final_pipeline_run2_records.jsonl)
  - Baseline B1 (GPT-OSS-120B): [`results/phase4/reserve_final_b1_gpt120b_records.jsonl`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/results/phase4/reserve_final_b1_gpt120b_records.jsonl)
  - Baseline B1 (Qwen-3.8-27B): [`results/phase4/reserve_final_b1_qwen27b_records.jsonl`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/results/phase4/reserve_final_b1_qwen27b_records.jsonl)
  - Baseline B1+code (GPT-OSS-120B): [`results/phase4/reserve_final_b1_plus_code_gpt120b_records.jsonl`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/results/phase4/reserve_final_b1_plus_code_gpt120b_records.jsonl)
  - Baseline B1+code (Qwen-3.8-27B): [`results/phase4/reserve_final_b1_plus_code_qwen27b_records.jsonl`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/results/phase4/reserve_final_b1_plus_code_qwen27b_records.jsonl)

---

## 1. Executive Head-to-Head Summary

| Comparison | Specialist SLM v1.3 (3.82B) | Baseline LLM | Paired Difference (SLM - LLM) | 95% Bootstrap CI ($B=10,000$) |
|---|:---:|:---:|:---:|:---:|
| **SLM (Run 1) vs GPT-OSS-120B (B1 Fair Tools)** | **87/100 (87.0%)** | 80/100 (80.0%) | **+6.12 pp** | [-4.08 pp, +16.33 pp] |
| **SLM (Run 1) vs GPT-OSS-120B (B1+code)** | **87/100 (87.0%)** | 73/100 (73.0%) | **+1.16 pp** | [-9.30 pp, +11.63 pp] |
| **SLM (Run 1) vs Qwen-3.8-27B (B1 Fair Tools)** | **87/100 (87.0%)** | 82/100 (82.0%) | **+3.09 pp** | [-7.22 pp, +13.40 pp] |
| **SLM (Run 1) vs Qwen-3.8-27B (B1+code)** | **87/100 (87.0%)** | 82/100 (82.0%) | **+0.00 pp** | [-9.57 pp, +9.57 pp] |
| **SLM Run 2 (Confirmation Run)** | **87/100 (87.0%)** | — | — | — |

---

## 2. Non-Tool-Required Subset (80 Items)

On the 80 reserve items without compound tool-required tasks (15 SQL, 15 QA, 15 Code, 15 Math, 20 Compound Solvable):
- **Specialist SLM v1.3 (Run 1):** 68/80 (85.0%)
- **Specialist SLM v1.3 (Run 2):** 68/80 (85.0%)
- **GPT-OSS-120B (B1):** 76/80 (95.0%)
- **Qwen-3.8-27B (B1):** 75/80 (93.8%)

> [!NOTE]
> The SLM underperformed the larger baselines on atomic reasoning and tool-free compound tasks (-10.0 pp vs 120B, -8.8 pp vs 27B). The SLM's overall accuracy lead across all 100 items stems from the compound tool-required category.

---

## 3. SLM Reproducibility & Concurrency Stability (Run 1 vs Run 2)

- **Total Reserve Items:** 100
- **Exact Final Answer Match:** **97/100 (97.0%)**
- **Score Verdict Match:** **100/100 (100.0%)**
  - Both Passed: 87 items
  - Both Failed: 13 items
  - Run 1 Pass / Run 2 Fail: 0 items
  - Run 1 Fail / Run 2 Pass: 0 items
- **Multi-Slot Token Variance Note:** Vulkan0 GPU execution with `--np 3` concurrent slots introduces minor non-deterministic floating-point reduction order variations at `temperature = 0.0`. Across 100 reserve items, the pipeline achieves 100.0% verdict stability.

---

## 4. Head-to-Head Contingency Tables (Symmetric Validity, Run 1)

### Specialist SLM (3.82B) vs GPT-OSS-120B (B1 with Fair Tools)
- **SLM Win:** 17 items
- **Both Right:** 69 items
- **Both Wrong:** 1 items
- **120B Win:** 11 items
- **Missing / Excluded:** 2 items

### Specialist SLM (3.82B) vs GPT-OSS-120B (B1+code)
- **SLM Win:** 12 items
- **Both Right:** 62 items
- **Both Wrong:** 1 items
- **120B Win:** 11 items
- **Missing / Excluded:** 14 items

### Specialist SLM (3.82B) vs Qwen-3.8-27B (B1 with Fair Tools)
- **SLM Win:** 14 items
- **Both Right:** 71 items
- **Both Wrong:** 1 items
- **27B Win:** 11 items
- **Missing / Excluded:** 3 items

### Specialist SLM (3.82B) vs Qwen-3.8-27B (B1+code)
- **SLM Win:** 11 items
- **Both Right:** 71 items
- **Both Wrong:** 1 items
- **27B Win:** 11 items
- **Missing / Excluded:** 6 items

---

## 5. Stratified Per-Category Breakdown

| Category / Stratum | Sample Size ($n$) | SLM Run 1 (3.82B) | SLM Run 2 (3.82B) | GPT-120B (B1) | GPT-120B (B1+code) | Qwen-27B (B1) | Qwen-27B (B1+code) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `atomic_sql` | 15 | 11/15 (73.3%) | 11/15 (73.3%) | 14/15 (93.3%) | 14/15 (93.3%) | 14/15 (93.3%) | 14/15 (93.3%) |
| `atomic_qa` | 15 | 14/15 (93.3%) | 14/15 (93.3%) | 15/15 (100.0%) | 15/15 (100.0%) | 15/15 (100.0%) | 15/15 (100.0%) |
| `atomic_code` | 15 | 11/15 (73.3%) | 11/15 (73.3%) | 15/15 (100.0%) | 15/15 (100.0%) | 14/15 (93.3%) | 14/15 (93.3%) |
| `atomic_math` | 15 | 14/15 (93.3%) | 14/15 (93.3%) | 15/15 (100.0%) | 15/15 (100.0%) | 15/15 (100.0%) | 15/15 (100.0%) |
| `compound_solvable` | 20 | 18/20 (90.0%) | 18/20 (90.0%) | 17/20 (85.0%) | 9/20 (45.0%) | 17/20 (85.0%) | 18/20 (90.0%) |
| `compound_tool_required` | 20 | 19/20 (95.0%) | 19/20 (95.0%) | 4/20 (20.0%) | 5/20 (25.0%) | 7/20 (35.0%) | 6/20 (30.0%) |
| **Non-Tool-Required (80)** | **80** | **68/80 (85.0%)** | **68/80 (85.0%)** | **76/80 (95.0%)** | **68/80 (85.0%)** | **75/80 (93.8%)** | **76/80 (95.0%)** |
| **Track A Total** | **100** | **87/100 (87.0%)** | **87/100 (87.0%)** | **80/100 (80.0%)** | **73/100 (73.0%)** | **82/100 (82.0%)** | **82/100 (82.0%)** |

---

## 6. Truncations & Exclusions

| System | Truncations (`finish_reason == "length"`) | Excluded Items |
|---|:---:|:---:|
| Specialist SLM Run 1 | 0 | 0 |
| Specialist SLM Run 2 | 0 | 0 |
| GPT-OSS-120B (B1) | 0 | 0 |
| Qwen-3.8-27B (B1) | 0 | 0 |
| GPT-OSS-120B (B1+code) | 1 | 0 |
| Qwen-3.8-27B (B1+code) | 4 | 0 |

---

## 7. Latency & Provenance Accounting

| System | Mean Latency (s) | Median Latency (s) | API Rate-Limit Wait Time (s) | Answered By | Monetary Cost |
|---|:---:|:---:|:---:|---|:---:|
| Specialist Pipeline (Run 1) | 7.27s | 5.53s | 0.00s (Local Vulkan GPU) | `phi-4-mini` (local) | $0.00 |
| Specialist Pipeline (Run 2) | 7.46s | 5.69s | 0.00s (Local Vulkan GPU) | `phi-4-mini` (local) | $0.00 |
| GPT-OSS-120B (B1) | 4.82s | 1.52s | 2.90s (Groq backoff) | `gpt-oss-120b` (Groq API) | $0.00 |
| Qwen-3.8-27B (B1) | 42.49s | 22.19s | 39.10s (Groq backoff) | `qwen3.8-27b` (Groq API) | $0.00 |

---

## 8. Cryptographic Reserve Immutability Proof

- Reserve Quarantine File: `data/reserve_set_quarantine.json`
- Pre-Evaluation SHA-256: `bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db`
- Post-Evaluation SHA-256: `bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db`
- Cryptographic Proof: **100% BYTE-FOR-BYTE IDENTICAL AND UNTOUCHED**.

