# Model Registry — Candidate and Pinned Roster

Per Hard Rule 7, Hard Rule 8, and Condition 13b.4, every model is recorded with exact identifier, SHA-256 digest, published parameter count, license, family, and active status. Floating `-latest` aliases are prohibited. This file is owner-gated.

---

## 1. Candidate Base SLMs for Specialist Pool (Each $\le 8\text{B}$, 6 GB GPU Laptop)

The specialist pool will host 2–3 base SLMs, each with swappable LoRA adapters, to be benchmarked under concurrency configurations (a), (b), (c), (d), and (e).

### 1.1 Category: Co-load Base Candidates ($\le 4\text{B}$, for Configs (a) & (e))
| Model Exact ID | Full SHA-256 Digest | Short ID | Family | Published Params | License | Format & Quant | VRAM Size | Public Benchmarks (MMLU / Code / Math) | Role |
|---|---|---|---|---|---|---|---|---|---|
| `phi3.5:3.8b` (`microsoft/Phi-3.5-mini-instruct`) | `61819fb370a3c1a9be6694869331e5f85f867a079e9271d66cb223acb81d04ba` | `61819fb370a3` | Phi (Microsoft) | 3.82B | MIT | GGUF Q4_0 | 2.18 GB | MMLU: 69.0, HumanEval: 70.1, MATH: 54.1 | Co-load Base A (Reasoning / Math) |
| `llama3.2:3b` (`meta-llama/Llama-3.2-3B-Instruct`) | `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` | `a80c4f17acd5` | Llama (Meta) | 3.21B | Llama 3.2 Community | GGUF Q4_K_M | 2.02 GB | MMLU: 63.4, HumanEval: 61.0, MATH: 44.4 | Co-load Base B (Orchestration / QA) |
| `qwen2.5-coder:3b` (`Qwen/Qwen2.5-Coder-3B-Instruct`) | `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225` | `f72c60cabf62` | Qwen (Alibaba) | 3.09B | Apache 2.0 | GGUF Q4_K_M | 1.93 GB | HumanEval: 75.6, EvalPlus: 71.3 | Co-load Base C (Code / SQL) |

### 1.2 Category: Mini Base Candidates ($\le 3\text{B}$ / 1.5B, for Config (b): Three Bases Co-loaded)
| Model Exact ID | Full SHA-256 Digest | Short ID | Family | Published Params | License | Format & Quant | VRAM Size | Public Benchmarks (MMLU / Code / Math) | Role |
|---|---|---|---|---|---|---|---|---|---|
| `qwen2.5:1.5b` (`Qwen/Qwen2.5-1.5B-Instruct`) | `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` | `65ec06548149` | Qwen (Alibaba) | 1.54B | Apache 2.0 | GGUF Q4_K_M | 986 MB | MMLU: 60.9, HumanEval: 57.3, MATH: 52.5 | Mini Base 1 (Tools / SQL / Code) |
| `llama3.2:3b` (`meta-llama/Llama-3.2-3B-Instruct`) | `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` | `a80c4f17acd5` | Llama (Meta) | 3.21B | Llama 3.2 Community | GGUF Q4_K_M | 2.02 GB | MMLU: 63.4, HumanEval: 61.0, MATH: 44.4 | Mini Base 2 (Decomposer / Router) |
| `deepseek-r1:1.5b` (`deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B`) | `e0979632db5a88d1a53884cb2a941772d10ff5d055aabaa6801c4e36f3a6c2d7` | `e0979632db5a` | DeepSeek / Qwen | 1.78B | MIT | GGUF Q4_K_M | 1.12 GB | MATH: 83.9, GSM8K: 88.9 | Mini Base 3 (Math Verifier) |

### 1.3 Category: 7B–8B Base Candidates (for Configs (c) & (d): Single Base at a Time)
| Model Exact ID | Full SHA-256 Digest | Short ID | Family | Published Params | License | Format & Quant | VRAM Size | Public Benchmarks (MMLU / Code / Math) | Role |
|---|---|---|---|---|---|---|---|---|---|
| `llama3.1:8b` (`meta-llama/Llama-3.1-8B-Instruct`) | `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` | `46e0c10c039e` | Llama (Meta) | 8.03B | Llama 3.1 Community | GGUF Q4_K_M | 4.92 GB | MMLU: 69.4, HumanEval: 72.6, MATH: 51.9 | Base Candidate 1 (General reasoning/Retrieval) |
| `qwen2.5-coder:7b` (`Qwen/Qwen2.5-Coder-7B-Instruct`) | `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364` | `dae161e27b0e` | Qwen (Alibaba) | 7.61B | Apache 2.0 | GGUF Q4_K_M | 4.68 GB | HumanEval: 84.8, EvalPlus: 79.9, MATH: 75.5 | Base Candidate 2 (Coding/Math/Orchestration) |

---

## 2. Candidate Baseline Models (Three-Tier Open-Weight Ladder)

| Tier | Candidate Exact ID | Publisher Family | Published Parameters | Verified Free Endpoint Provider | Status |
|---|---|---|---|---|---|
| **Tier 1 (~32B)** | `qwen/qwen3.8-27b` | Qwen (Alibaba) | 27.0B | Groq (`qwen/qwen3.8-27b`, 0 spend verified) | Proposed Primary Comparison |
| **Tier 2 (~50B)** | *None* | — | — | — | **SKIPPED** (No dense open-weight model exists near 50B with free endpoint; per Section 6 rule) |
| **Tier 3 (~70B / 120B ceiling)** | `openai/gpt-oss-120b` | OpenAI / Open-Weight | 120B | Groq (`openai/gpt-oss-120b`, 0 spend verified) | Proposed Upper Comparison / Ceiling |

---

## 3. Candidate Judge Models (Track B Secondary Only — Family Separation)

Per Hard Rule 8, the judge family must not overlap with the SLM pool family or baseline families.

| Candidate Exact ID | Publisher Family | Access Endpoint | Family Separation Verification | Status |
|---|---|---|---|---|
| `google/gemini-2.5-flash` (`gemini-2.5-flash`) | Gemini (Google) | Google AI Studio (Free Tier, 0 spend verified) | Disjoint from Meta (Llama), Alibaba (Qwen), Microsoft (Phi), and OpenAI | Proposed Primary Judge |

---

## 4. Changelog & Owner Approvals

- **2026-10-07:** Candidate roster updated with full SHA-256 digests and short IDs for all local models. Awaiting explicit Owner selection before advancing past Phase 1.
