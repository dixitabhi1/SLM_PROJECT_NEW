# Secondary Check: Held-Out Comparison (v1.0 → v1.3)

> [!NOTE]
> **Provenance Status:** secondary: held-out previously inspected.
> Evaluated on locked held-out splits ($N=150$) using pure SLM pipeline with Python sandbox numeric execution and generic CORPUS no-code constraint (0 Groq calls).
> **Attribution Confirmation:** `results/phase4/heldout_pipeline_records.jsonl` was produced under frozen Pipeline v1.0 (commit `7ad397f` / `ce19624`), prior to the v1.1 direct SQL path. This evaluation represents the end-to-end progression **v1.0 → v1.3**.

## 1. Progression: Held-Out Per-Category Changes (v1.0 → v1.3)

| Category / Stratum | Sample Size ($n$) | Pipeline v1.0 | Pipeline v1.3 | Delta ($v1.0 \to v1.3$) |
|---|:---:|:---:|:---:|:---:|
| `atomic_sql` | 15 | 3/15 (20.0%) | 11/15 (73.3%) | +8 (+53.3 pp) |
| `atomic_qa` | 15 | 12/15 (80.0%) | 11/15 (73.3%) | -1 (-6.7 pp) |
| `atomic_code` | 15 | 12/15 (80.0%) | 12/15 (80.0%) | +0 (+0.0 pp) |
| `atomic_math` | 15 | 14/15 (93.3%) | 13/15 (86.7%) | -1 (-6.7 pp) |
| `compound_solvable` | 20 | 10/20 (50.0%) | 15/20 (75.0%) | +5 (+25.0 pp) |
| `compound_tool_required` | 20 | 16/20 (80.0%) | 17/20 (85.0%) | +1 (+5.0 pp) |
| `track_b_hypergrid` | 50 | 50/50 (100.0%) | 50/50 (100.0%) | +0 (+0.0 pp) |
| **Track A Total** | **100** | **67/100 (67.0%)** | **79/100 (79.0%)** | **+12 (+12.0 pp)** |
| **Track B Total** | **50** | **50/50 (100.0%)** | **50/50 (100.0%)** | **+0 (+0.0 pp)** |
| **Held-Out Total** | **150** | **117/150 (78.0%)** | **129/150 (86.0%)** | **+12 (+8.0 pp)** |

## 2. Summary Performance (v1.3)

| Track | Sample Size ($n$) | Passed | Accuracy (%) | Mean Latency |
|---|:---:|:---:|:---:|:---:|
| Track A (Multi-Domain Academic) | 100 | 79 | 79.00% | 7.59s |
| Track B (HyperGrid Technical Corpus) | 50 | 50 | 100.00% | 10.34s |
| **Total Held-Out** | **150** | **129** | **86.00%** | **8.50s** |

## 3. Head-to-Head: SLM (v1.3) vs GPT-OSS-120B (B1 with Fair Tools)

### Track A Breakdown (N=100)

- **SLM Win:** 5 items
- **Both Right:** 74 items
- **Both Wrong:** 7 items
- **LLM Win (120B Win):** 14 items
- **Missing / Truncated:** 0 items

### Track B Breakdown (N=50)

- **SLM Win:** 0 items
- **Both Right:** 50 items
- **Both Wrong:** 0 items
- **LLM Win (120B Win):** 0 items
- **Missing / Truncated:** 0 items

### Track A Category Breakdown

| Stratum | SLM Win | Both Right | Both Wrong | 120B Win | Missing |
|---|:---:|:---:|:---:|:---:|:---:|
| `atomic_sql` | 1 | 10 | 3 | 1 | 0 |
| `atomic_qa` | 0 | 11 | 2 | 2 | 0 |
| `atomic_code` | 0 | 12 | 0 | 3 | 0 |
| `atomic_math` | 1 | 12 | 1 | 1 | 0 |
| `compound_tool_required` | 3 | 14 | 1 | 2 | 0 |
| `compound_solvable` | 0 | 15 | 0 | 5 | 0 |

## 4. Head-to-Head: SLM (v1.3) vs Qwen-3.8-27B (B1 with Fair Tools)

### Track A Breakdown (N=100)

- **SLM Win:** 10 items
- **Both Right:** 69 items
- **Both Wrong:** 4 items
- **LLM Win (27B Win):** 17 items
- **Missing / Truncated:** 0 items

### Track B Breakdown (N=50)

- **SLM Win:** 0 items
- **Both Right:** 50 items
- **Both Wrong:** 0 items
- **LLM Win (27B Win):** 0 items
- **Missing / Truncated:** 0 items

### Track A Category Breakdown

| Stratum | SLM Win | Both Right | Both Wrong | 27B Win | Missing |
|---|:---:|:---:|:---:|:---:|:---:|
| `atomic_sql` | 1 | 10 | 3 | 1 | 0 |
| `atomic_qa` | 0 | 11 | 0 | 4 | 0 |
| `atomic_code` | 0 | 12 | 0 | 3 | 0 |
| `atomic_math` | 1 | 12 | 1 | 1 | 0 |
| `compound_tool_required` | 6 | 11 | 0 | 3 | 0 |
| `compound_solvable` | 2 | 13 | 0 | 5 | 0 |
