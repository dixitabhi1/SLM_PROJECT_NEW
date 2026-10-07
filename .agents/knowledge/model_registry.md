# Model Registry — Candidate and Pinned Roster

Per Hard Rule 7, Hard Rule 8, and Condition 13b.4, every model is recorded with exact identifier, SHA-256 digest, published parameter count, license, family, and active status. Floating `-latest` aliases are prohibited. This file is owner-gated.

---

## 1. Candidate Base SLMs for Specialist Pool (Each $\le 8\text{B}$, 6 GB GPU Laptop)

The specialist pool will host 2–3 base SLMs, each with swappable LoRA adapters, to be benchmarked under concurrency configurations (a), (b), (b-serial), (c), (d), (e), (f), and (g).

### 1.1 Category: $\le 4\text{B}$ Base Candidates (Released in last 18 months, with verified source links)

| Model Exact ID | Full SHA-256 Digest | Short ID | Family | Published Params | License | Format & Quant | VRAM Size | Public Benchmarks (Sourced) | Potential Role |
|---|---|---|---|---|---|---|---|---|---|
| `phi3.5:3.8b` (`microsoft/Phi-3.5-mini-instruct`) | `61819fb370a3c1a9be6694869331e5f85f867a079e9271d66cb223acb81d04ba` | `61819fb370a3` | Phi (Microsoft) | 3.82B | MIT | GGUF Q4_0 | 2.18 GB | [MMLU: 69.0](https://huggingface.co/microsoft/Phi-3.5-mini-instruct), [GSM8K: 86.2](https://huggingface.co/microsoft/Phi-3.5-mini-instruct), [HumanEval: 62.8](https://huggingface.co/microsoft/Phi-3.5-mini-instruct) | Reasoning / Math Specialist |
| `llama3.2:3b` (`meta-llama/Llama-3.2-3B-Instruct`) | `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` | `a80c4f17acd5` | Llama (Meta) | 3.21B | Llama 3.2 Community | GGUF Q4_K_M | 2.02 GB | [MMLU: 63.4](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct), [GSM8K: 77.7 (8-shot CoT)](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct), [HumanEval: 28.0 (0-shot) / 61.0 (CoT)](https://huggingface.co/datasets/meta-llama/Llama-3.2-3B-Instruct-evals) | Orchestration / QA Specialist |
| `qwen2.5-coder:3b` (`Qwen/Qwen2.5-Coder-3B-Instruct`) | `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225` | `f72c60cabf62` | Qwen (Alibaba) | 3.09B | Apache 2.0 | GGUF Q4_K_M | 1.93 GB | [HumanEval: 75.6](https://qwenlm.github.io/blog/qwen2.5-coder/), [EvalPlus: 71.3](https://qwenlm.github.io/blog/qwen2.5-coder/) | Code / SQL Specialist *(Subject to Rule 8)* |
| `qwen2.5:1.5b` (`Qwen/Qwen2.5-1.5B-Instruct`) | `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` | `65ec06548149` | Qwen (Alibaba) | 1.54B | Apache 2.0 | GGUF Q4_K_M | 986 MB | [MMLU: 60.9](https://qwenlm.github.io/blog/qwen2.5/), [HumanEval: 57.3](https://qwenlm.github.io/blog/qwen2.5/), [MATH: 52.5](https://qwenlm.github.io/blog/qwen2.5/) | Compact Tool / SQL Specialist *(Subject to Rule 8)* |
| `granite-3.0-2b-instruct` (`ibm-granite/granite-3.0-2b-instruct`) | *(Pending download)* | — | Granite (IBM) | 2.50B | Apache 2.0 | GGUF Q4_K_M | ~1.6 GB | [GSM8K: 59.7](https://huggingface.co/ibm-granite/granite-3.0-2b-instruct), [MMLU-Pro: 23.8](https://huggingface.co/ibm-granite/granite-3.0-2b-instruct) | Alternative Tool Specialist (Disjoint Family) |

### 1.2 Category: 7B–8B Base Candidates (Fitting 6 GB VRAM on Laptop GPU)

| Model Exact ID | Full SHA-256 Digest | Short ID | Family | Published Params | License | Format & Quant | VRAM Size | Public Benchmarks (Sourced) | Potential Role |
|---|---|---|---|---|---|---|---|---|---|
| `llama3.1:8b` (`meta-llama/Llama-3.1-8B-Instruct`) | `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` | `46e0c10c039e` | Llama (Meta) | 8.03B | Llama 3.1 Community | GGUF Q4_K_M | 4.92 GB (Note: spills to CPU if context > 2048) | [MMLU: 69.4](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct), [GSM8K: 84.5](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct), [HumanEval: 72.6](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct), [MATH: 51.9](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct) | Monolithic 8B Base Candidate |
| `qwen2.5:7b` (`Qwen/Qwen2.5-7B-Instruct`) | *(Pending Q3_K_M build)* | — | Qwen (Alibaba) | 7.61B | Apache 2.0 | GGUF Q3_K_M | ~3.6 GB (Fits 100% in 5.1 GiB VRAM at 4096 context) | [GSM8K: 91.6](https://qwenlm.github.io/blog/qwen2.5/), [HumanEval: 84.8](https://qwenlm.github.io/blog/qwen2.5/), [MATH: 75.5](https://qwenlm.github.io/blog/qwen2.5/), [MMLU-Redux: 75.4](https://qwenlm.github.io/blog/qwen2.5/) | High-Performance 7B Base Candidate *(Subject to Rule 8)* |

---

## 2. Hard Rule 8: Family Separation Matrix

Hard Rule 8 states:
> *"Pool models, baseline models, and any judge must come from distinct, non-overlapping model families. A judge model is never also a baseline."*

The enforcement constraint operates as follows:

| Role | Active Family | Candidate Families | Incompatible Families (Disqualified by Hard Rule 8) |
|---|---|---|---|
| **Judge** | Google (`gemini-2.5-flash`) | Google (Gemini) | Google models (Gemma) cannot be in pool or baseline. |
| **Baseline 1 (27B)** | Alibaba (`qwen/qwen3.8-27b`) | Alibaba (Qwen) | Alibaba models (`qwen2.5:*`) **CANNOT** be in the pool if Qwen is baseline. |
| **Baseline 2 (120B)** | OpenAI (`openai/gpt-oss-120b`) | OpenAI | OpenAI models cannot be in the pool. |
| **Specialist Pool** | Microsoft (`phi3.5:3.8b`) + Meta (`llama3.2:3b`) | Microsoft, Meta, IBM | **Alibaba, OpenAI, and Google are strictly barred from pool.** |

### Architectural Decision for Owner:
- **Option 1 (Recommended):** Use `qwen/qwen3.8-27b` as Baseline Tier 1. Under this option, the SLM Pool consists exclusively of **Microsoft (`phi3.5:3.8b`)** and **Meta (`llama3.2:3b`)** (plus optional IBM Granite). This provides 100% strict family isolation across all three sides (Google Judge vs. Alibaba/OpenAI Baselines vs. Microsoft/Meta Pool).
- **Option 2:** If the owner wishes to place Qwen (e.g., `qwen2.5-coder:3b` or `qwen2.5:7b-q3`) into the Specialist Pool due to coding strength, Alibaba/Qwen **CANNOT** be used as a baseline, and an alternative non-overlapping free baseline must be selected.

---

## 3. Candidate Baseline Models (Three-Tier Open-Weight Ladder)

| Tier | Candidate Exact ID | Publisher Family | Published Parameters | Verified Free Endpoint Provider | Status |
|---|---|---|---|---|---|
| **Tier 1 (27B)** | `qwen/qwen3.8-27b` | Qwen (Alibaba) | 27.0B | Groq (`qwen/qwen3.8-27b`, verified free, cardless) | Proposed Primary Comparison |
| **Tier 2 (~50B)** | *None* | — | — | — | **SKIPPED** (No dense open-weight model exists near 50B with free endpoint; per Section 6 rule) |
| **Tier 3 (~70B / 120B ceiling)** | `openai/gpt-oss-120b` | OpenAI / Open-Weight | 120B | Groq (`openai/gpt-oss-120b`, verified free, cardless) | Proposed Upper Comparison / Ceiling |

### Audit Findings: Search for ~70B Open-Weight Free Baseline
A comprehensive search was conducted across public free inference APIs:
1. **Groq:** `llama-3.3-70b-versatile` was officially retired from Groq free tier on August 16, 2026. The only active large models are `qwen3.8-27b` and `openai/gpt-oss-120b`.
2. **SambaNova:** Requires a payment card on file even to access the free tier (violates the strictly cardless zero-spend directive).
3. **OpenRouter:** The dynamic `:free` tier rotates periodically and currently does not host a stable dense 70B open-weight model.
4. **GitHub Models (`models.inference.ai.azure.com`):** DNS resolution fails in this environment.

**Conclusion:** No verified, stable, 100% free cardless endpoint currently exists for a dense ~70B model. The active free baselines on Groq are **27B** (`qwen/qwen3.8-27b`) and **120B** (`openai/gpt-oss-120b`).

---

## 4. Candidate Judge Model (Track B Secondary Only) & Quota Budget

| Candidate Exact ID | Publisher Family | Access Endpoint | Free Daily Quota & Rate Limits | Track B Timeline |
|---|---|---|---|---|
| `google/gemini-2.5-flash` (`gemini-2.5-flash`) | Gemini (Google) | Google AI Studio (Free Tier, cardless) | **1,500 RPD**, **10 RPM**, 250,000 TPM | **0.53 days** (800 calls) |

### Track B Judging Workload Breakdown:
- Dev evaluation set: 50 items.
- Evaluated conditions: 4 conditions (e.g., C0, C1, C2, C3).
- Baselines: 2 baselines (27B and 120B).
- Position swap (Rule 4 symmetric debiasing): 2 calls per comparison ($A \text{ vs } B$ and $B \text{ vs } A$).
- **Total Judge Calls:** $50 \times 4 \times 2 \times 2 = 800\text{ calls}$.
- **Daily Quota Utilization:** $800 / 1500 = \mathbf{53.3\%}$ of a single day's quota.
- **Clock Time:** At the 10 RPM limit, 800 calls execute in $800 / 10 = 80\text{ minutes}$.

---

## 5. Changelog & Owner Approvals

- **2026-10-07:** Candidate roster created with initial model tags.
- **2026-10-08:** Roster updated per Owner directives:
  - All benchmark scores annotated with official primary source links.
  - Unsourced benchmark claims removed.
  - Tier 1 model strictly relabeled as 27B (`qwen/qwen3.8-27b`).
  - Hard Rule 8 family isolation matrix formally documented between pool, baselines, and judge.
  - Results of ~70B free endpoint search and Gemini judge daily quota budget (1,500 RPD / 0.53 days) documented.
