# Secondary Check (v2): Held-Out Evaluation (Pipeline v1.3 / E3 Candidate)

> [!NOTE]
> **Provenance Status:** secondary: held-out previously inspected.
> Evaluated on locked held-out splits ($N=150$) using pure SLM pipeline with Python sandbox numeric execution and generic CORPUS no-code constraint (0 Groq calls).

## 1. Summary Performance

| Track | Sample Size ($n$) | Passed | Accuracy (%) | Mean Latency |
|---|:---:|:---:|:---:|:---:|
| Track A (Multi-Domain Academic) | 100 | 79 | 79.00% | 7.59s |
| Track B (HyperGrid Technical Corpus) | 50 | 50 | 100.00% | 10.34s |
| **Total Held-Out** | **150** | **129** | **86.00%** | **8.50s** |

## 2. Head-to-Head: SLM (E3 v2) vs GPT-OSS-120B (B1 with Fair Tools)

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

## 3. Head-to-Head: SLM (E3 v2) vs Qwen-3.8-27B (B1 with Fair Tools)

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
