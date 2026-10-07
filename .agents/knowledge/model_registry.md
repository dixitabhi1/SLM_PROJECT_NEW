# Model Registry — Candidate and Pinned Roster

Per Hard Rule 7, Hard Rule 8, and Condition 13b.4, every model is recorded with exact identifier, revision, published parameter count, license, family, and active status. No floating `-latest` aliases are permitted. This file is owner-gated.

---

## 1. Candidate Base SLMs for Specialist Pool (Each $\le 8\text{B}$, 6 GB GPU Laptop)

The pool will host 2–3 base SLMs, each with swappable LoRA adapters, to be benchmarked under concurrency configurations (a), (b), (c), and (d).

### 1.1 Category: 7B–8B Base Candidates (for Configs (c) & (d))
| Model Exact ID | Family | Published Params | License | Q4_K_M Size | Benchmarks (MMLU / Code / Math) | Role |
|---|---|---|---|---|---|---|
| `Qwen/Qwen2.5-7B-Instruct` (`qwen2.5:7b`) | Qwen (Alibaba) | 7.61B | Apache 2.0 | 4.7 GB | MMLU: 74.2, HumanEval: 84.8, MATH: 75.5 | Pool Base Candidate 1 (Coding/Math/Orchestration) |
| `meta-llama/Llama-3.1-8B-Instruct` (`llama3.1:8b`) | Llama (Meta) | 8.03B | Llama 3.1 Community | 4.9 GB | MMLU: 69.4, HumanEval: 72.6, MATH: 51.9 | Pool Base Candidate 2 (General reasoning/Retrieval) |

### 1.2 Category: $\le 4\text{B}$ Base Candidates (for Co-loading Config (a): Two Bases $\le 4\text{B}$)
| Model Exact ID | Family | Published Params | License | Q4_K_M Size | Benchmarks (MMLU / Code / Math) | Role |
|---|---|---|---|---|---|---|
| `microsoft/Phi-3.5-mini-instruct` (`phi3.5:3.8b`) | Phi (Microsoft) | 3.82B | MIT | 2.2 GB | MMLU: 69.0, HumanEval: 70.1, MATH: 54.1 | Co-load Base A (Reasoning / Math) |
| `meta-llama/Llama-3.2-3B-Instruct` (`llama3.2:3b`) | Llama (Meta) | 3.21B | Llama 3.2 Community | 2.0 GB | MMLU: 63.4, HumanEval: 61.0, MATH: 44.4 | Co-load Base B (Orchestration / QA) |
| `Qwen/Qwen2.5-Coder-3B-Instruct` (`qwen2.5-coder:3b`) | Qwen (Alibaba) | 3.09B | Apache 2.0 | 1.9 GB | HumanEval: 75.6, EvalPlus: 71.3 | Co-load Base C (Code / SQL) |

### 1.3 Category: $\le 3\text{B}$ / 1.5B Base Candidates (for Co-loading Config (b): Three Bases Co-loaded)
| Model Exact ID | Family | Published Params | License | Q4_K_M Size | Benchmarks (MMLU / Code / Math) | Role |
|---|---|---|---|---|---|---|
| `Qwen/Qwen2.5-1.5B-Instruct` (`qwen2.5:1.5b`) | Qwen (Alibaba) | 1.54B | Apache 2.0 | 986 MB | MMLU: 60.9, HumanEval: 57.3, MATH: 52.5 | Mini Base 1 (Tools / SQL / Code) |
| `meta-llama/Llama-3.2-1B-Instruct` (`llama3.2:1b`) | Llama (Meta) | 1.24B | Llama 3.2 Community | ~800 MB | MMLU: 49.3, HumanEval: 37.2 | Mini Base 2 (Decomposer / Router) |
| `deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B` (`deepseek-r1:1.5b`) | DeepSeek | 1.58B | MIT | 1.1 GB | MATH: 83.9, GSM8K: 88.9 | Mini Base 3 (Math Verifier) |

---

## 2. Candidate Baseline Models (Three-Tier Open-Weight Ladder)

| Tier | Candidate Exact ID | Publisher Family | Published Parameters | Verified Free Endpoint Provider | Status |
|---|---|---|---|---|---|
| **Tier 1 (~32B)** | `Qwen/Qwen2.5-32B-Instruct` | Qwen (Alibaba) | 32.8B | Groq (`qwen-2.5-32b`) / OpenRouter | Proposed Primary Comparison |
| **Tier 1 Alt** | `google/gemma-2-27b-it` | Gemma (Google) | 27.2B | OpenRouter / HuggingFace API | Proposed Alternative (if Qwen is SLM base) |
| **Tier 2 (~50B)** | *None* | — | — | — | **SKIPPED** (No dense open-weight model exists near 50B with free endpoint; per Section 6 rule) |
| **Tier 3 (~70B)** | `meta-llama/Llama-3.3-70B-Instruct` | Llama (Meta) | 70.6B | Groq (`llama-3.3-70b-versatile`) / OpenRouter | Proposed Upper Comparison |
| **Tier 3 Alt** | `Qwen/Qwen2.5-72B-Instruct` | Qwen (Alibaba) | 72.7B | OpenRouter / SambaNova | Proposed Alternative (if Llama is SLM base) |

---

## 3. Candidate Judge Models (Track B Secondary Only — Family Separation)

Per Hard Rule 8, the judge family must not overlap with the SLM pool family or baseline families.

| Candidate Exact ID | Publisher Family | Access Endpoint | Family Separation Verification | Status |
|---|---|---|---|---|
| `google/gemini-2.5-flash` | Gemini (Google) | Google AI Studio (Free Tier) | Disjoint from Meta (Llama) and Alibaba (Qwen) | Proposed Primary Judge |
| `mistralai/mistral-large-2407` | Mistral (Mistral AI) | Mistral API / OpenRouter | Disjoint from Meta (Llama) and Alibaba (Qwen) | Proposed Alternative Judge |

---

## 4. Changelog & Owner Approvals

- **2026-10-07:** Initial candidate roster drafted for Owner review and selection. No models pinned yet.
