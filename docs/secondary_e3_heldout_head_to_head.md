# Secondary Check: Held-Out Evaluation (Pipeline v1.3 / E3 Candidate)

> [!NOTE]
> **Provenance Status:** secondary: held-out previously inspected.
> Evaluated on locked held-out splits ($N=150$) using pure SLM pipeline with Python sandbox numeric execution (0 Groq calls).

## 1. Summary Performance

| Track | Sample Size ($n$) | Passed | Accuracy (%) | Mean Latency |
|---|:---:|:---:|:---:|:---:|
| Track A (Multi-Domain Academic) | 100 | 79 | 79.00% | 8.00s |
| Track B (HyperGrid Technical Corpus) | 50 | 31 | 62.00% | 14.70s |
| **Total Held-Out** | **150** | **110** | **73.33%** | **10.23s** |

## 2. Head-to-Head: SLM (E3) vs GPT-OSS-120B (B1 with Fair Tools)

### Track A Breakdown (N=100)

- **SLM Win:** 5 items
- **Both Right:** 74 items
- **Both Wrong:** 7 items
- **LLM Win (120B Win):** 14 items
- **Missing / Truncated:** 0 items

### Track B Breakdown (N=50)

- **SLM Win:** 0 items
- **Both Right:** 31 items
- **Both Wrong:** 0 items
- **LLM Win (120B Win):** 19 items
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

## 3. Head-to-Head: SLM (E3) vs Qwen-3.8-27B (B1 with Fair Tools)

### Track A Breakdown (N=100)

- **SLM Win:** 10 items
- **Both Right:** 69 items
- **Both Wrong:** 4 items
- **LLM Win (27B Win):** 17 items
- **Missing / Truncated:** 0 items

### Track B Breakdown (N=50)

- **SLM Win:** 0 items
- **Both Right:** 31 items
- **Both Wrong:** 0 items
- **LLM Win (27B Win):** 19 items
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
