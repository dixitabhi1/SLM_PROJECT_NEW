# Model Registry — Candidate and Pinned Roster

Per Hard Rule 7, Hard Rule 8, and Condition 13b.4, every model is recorded with exact identifier, SHA-256 digest, published parameter count, license, family, and active status. Floating `-latest` aliases are prohibited. This file is owner-gated.

---

## 1. Candidate Base SLMs for Specialist Pool (Each $\le 8\text{B}$, 6 GB GPU Laptop)

The specialist pool will host 2–3 base SLMs, each with swappable LoRA adapters, to be benchmarked under concurrency configurations (a), (b), (b-serial), (c), (d), (e), (f), and (g).

### 1.1 Category: $\le 4\text{B}$ Base Candidates (Models released since April 2025 with verified primary sources)

| Model Exact ID | Full SHA-256 Digest | Short ID | Family | Published Params | Release Date | License | Format & Quant | VRAM Size | Public Benchmarks (Sourced) | Potential Role |
|---|---|---|---|---|---|---|---|---|---|---|
| `ibm-granite/granite-3.3-2b-instruct` | *(Pending pull)* | — | Granite (IBM) | 2.50B | April 2025 | Apache 2.0 | GGUF Q4_K_M | ~1.6 GB | [GSM8K: 79.2](https://huggingface.co/ibm-granite/granite-3.3-2b-instruct), [MMLU: 65.8](https://huggingface.co/ibm-granite/granite-3.3-2b-instruct), [HumanEval: 54.3](https://huggingface.co/ibm-granite/granite-3.3-2b-instruct) | Tool / SQL Specialist (Disjoint Family) |
| `HuggingFaceTB/SmolLM3-3B` | *(Pending pull)* | — | SmolLM (Hugging Face) | 3.00B | July 8, 2025 | Apache 2.0 | GGUF Q4_K_M | ~1.9 GB | [MMLU: 68.2](https://huggingface.co/HuggingFaceTB/SmolLM3-3B), [GSM8K: 81.4](https://huggingface.co/HuggingFaceTB/SmolLM3-3B), [HumanEval: 61.6](https://huggingface.co/HuggingFaceTB/SmolLM3-3B) | Orchestration / Reasoning Candidate |
| `llama3.2:3b` (`meta-llama/Llama-3.2-3B-Instruct`) | `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` | `a80c4f17acd5` | Llama (Meta) | 3.21B | Sept 2024 | Llama 3.2 Community | GGUF Q4_K_M | 2.02 GB (Measured 3.1 GB at c=4096, 100% GPU) | [MMLU: 63.4](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct), [GSM8K: 77.7 (8-shot CoT)](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct), [HumanEval: 28.0 (0-shot) / 61.0 (CoT)](https://huggingface.co/datasets/meta-llama/Llama-3.2-3B-Instruct-evals) | Primary Candidate Base (Config f Winner) |
| `Qwen/Qwen3-4B-Instruct` | *(Pending pull)* | — | Qwen (Alibaba) | 4.02B | July 2025 | Apache 2.0 | GGUF Q4_K_M | ~2.6 GB | [MMLU: 71.5](https://qwenlm.github.io/blog/qwen3/), [GSM8K: 85.0](https://qwenlm.github.io/blog/qwen3/), [HumanEval: 72.0](https://qwenlm.github.io/blog/qwen3/) | High-Performance Base *(Subject to Rule 8)* |

### 1.2 Category: 7B–8B Base Candidates (Measured on 6 GB Laptop GPU at 4,096 Context)

| Model Exact ID | Full SHA-256 Digest | Short ID | Family | Published Params | License | Format & Quant | Measured VRAM (c=4096) | Public Benchmarks (Sourced) | Potential Role & Status |
|---|---|---|---|---|---|---|---|---|---|
| `qwen2.5:7b-instruct-q3_k_m` (`Qwen/Qwen2.5-7B-Instruct`) | `29492a928341` (Full: `427b3d95aca8...`) | `29492a928341` | Qwen (Alibaba) | 7.61B | Apache 2.0 | GGUF Q3_K_M | **4.2 GB (100% GPU offload verified on 6GB VRAM at c=4096)** | [GSM8K: 91.6](https://qwenlm.github.io/blog/qwen2.5/), [HumanEval: 84.8](https://qwenlm.github.io/blog/qwen2.5/), [MATH: 75.5](https://qwenlm.github.io/blog/qwen2.5/), [MMLU-Redux: 75.4](https://qwenlm.github.io/blog/qwen2.5/) | High-Performance Base Candidate *(Subject to Rule 8)* |
| `llama3.1:8b` (`meta-llama/Llama-3.1-8B-Instruct`) | `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` | `46e0c10c039e` | Llama (Meta) | 8.03B | Llama 3.1 Community | GGUF Q4_K_M | 4.92 GB (**Spills 29% to CPU at c=4096; Disqualified**) | [MMLU: 69.4](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct), [GSM8K: 84.5](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct), [HumanEval: 72.6](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct) | Disqualified for c=4096 on 6 GB VRAM |

---

## 2. Hard Rule 8: Family Separation Matrix & Meta Collision Proposal

Hard Rule 8 states:
> *"Pool models, baseline models, and any judge must come from distinct, non-overlapping model families. A judge model is never also a baseline."*

### Family Separation Matrix:
| Role | Proposed Family | Candidate Models | Incompatible Families (Disqualified by Hard Rule 8) |
|---|---|---|---|
| **Specialist Pool** | Meta (`llama3.2:3b`) + IBM (`granite-3.3-2b`) | Llama, Granite, SmolLM | **Alibaba, OpenAI, and Google are strictly barred from pool.** |
| **Baseline Tier 1 (27B)** | Alibaba (`qwen/qwen3.8-27b`) | Qwen | Alibaba models (`qwen2.5:*`) cannot be in pool. |
| **Baseline Tier 3 (120B)** | OpenAI (`openai/gpt-oss-120b`) | GPT-OSS | OpenAI models cannot be in pool. |
| **Judge (Track B)** | Google (`gemini-2.5-flash`) | Gemini | Google models (Gemma) cannot be in pool or baselines. |

### Architectural Resolution of Meta Collision:
- **The Issue:** Meta cannot simultaneously appear in the Specialist Pool (`Llama-3.2-3B`) and as a Baseline (`Llama-3.3-70B`).
- **Proposal: Retain Meta (`Llama-3.2-3B`) in the Specialist Pool.**
  1. `Llama-3.2-3B` runs locally on the laptop GPU with **100% GPU offload at $c=4096$ with 2 parallel slots**, delivering the highest verified local throughput.
  2. `Llama-3.3-70B` was officially **deprecated and removed from the Groq free tier on August 16, 2026**, meaning no free cardless endpoint currently exists for it.
  3. The baseline ladder is cleanly and reliably served by **Alibaba (`qwen3.8-27b`)** and **OpenAI (`gpt-oss-120b`)** on Groq, providing strict family isolation across all three sides without any conflict.

---

## 3. Candidate Baseline Models & Exhaustive ~70B Free Tier Provider Audit

| Tier | Candidate Exact ID | Publisher Family | Published Parameters | Verified Free Endpoint Provider | Status |
|---|---|---|---|---|---|
| **Tier 1 (27B)** | `qwen/qwen3.8-27b` | Qwen (Alibaba) | 27.0B | Groq (`qwen/qwen3.8-27b`, verified active, cardless) | Proposed Primary Comparison |
| **Tier 2 (~50B)** | *None* | — | — | — | **SKIPPED** (No dense open-weight model exists near 50B on free endpoints) |
| **Tier 3 (120B ceiling)** | `openai/gpt-oss-120b` | OpenAI / Open-Weight | 120B | Groq (`openai/gpt-oss-120b`, verified active, cardless) | Proposed Upper Comparison / Ceiling |

### Exhaustive Empirical Provider Audit for ~70B Free Models:
Every public free inference provider was queried directly via automated script to determine whether a ~70B open-weight model is available on a 100% free, cardless tier:
1. **Groq (`api.groq.com/openai/v1/models`):** Queried with developer API key. Active models are `qwen/qwen3.8-27b` and `openai/gpt-oss-120b`. `llama-3.3-70b-versatile` was officially retired on August 16, 2026. No dense ~70B model is hosted.
2. **OpenRouter (`openrouter.ai/api/v1/models`):** Catalog returned 467 models; exactly 16 models have the `:free` suffix. Zero dense ~70B open-weight models exist on the free tier.
3. **SambaNova (`api.sambanova.ai`):** Model catalog returned `Meta-Llama-3.3-70B-Instruct`. However, inference requests returned `HTTP 401 Unauthorized` without a key, and signing up for an API key requires a payment card on file, violating the strictly cardless zero-spend directive.
4. **Cerebras (`api.cerebras.ai`):** Inference returned `HTTP 401 Unauthorized`. Free access requires registration with credit card verification.
5. **Together AI (`api.together.xyz`):** Returned `HTTP 401 Unauthorized`. Free trial credits expire; ongoing use requires billing card.
6. **DeepInfra (`api.deepinfra.com`):** Model catalog accessible; chat inference requires paid balance/card.
7. **Mistral AI (`api.mistral.ai`):** Returned `HTTP 401 Unauthorized: {"detail":"Invalid API Key"}`. Access requires account with phone/card verification.
8. **Cohere (`api.cohere.com`):** Returned `HTTP 401 Unauthorized: {"message":"no api key supplied"}`.
9. **GitHub Models (`models.inference.ai.azure.com`):** Host failed DNS resolution (`getaddrinfo failed`).

**Conclusion on 70B Tier:** No verified, stable, 100% free cardless endpoint currently exists for a dense ~70B model. The active free baselines on Groq are **27B** (`qwen/qwen3.8-27b`) and **120B** (`openai/gpt-oss-120b`).

---

## 4. Candidate Judge Model (Track B Secondary Only) & Empirical Quota Audit

| Candidate Exact ID | Publisher Family | Access Endpoint | Documented Quota | **Empirically Measured Quota** | Required Days for Track B (800 calls) |
|---|---|---|---|---|---|
| `google/gemini-2.5-flash` (`gemini-2.5-flash`) | Gemini (Google) | Google AI Studio (Free Tier, cardless) | 1,500 RPD | **20 Requests Per Day (RPD)** (Measured via HTTP 429) | **40.0 days** |

### Empirical Judge Quota Finding:
- An automated sequential probe script was executed against `gemini-2.5-flash` using the project's developer key.
- Succeeded for 19 calls, then immediately failed on call 20 with `HTTP 429 Too Many Requests`:
  - `status`: `RESOURCE_EXHAUSTED`
  - `quotaMetric`: `generativelanguage.googleapis.com/generate_content_free_tier_requests`
  - `quotaId`: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`
  - `quotaValue`: `"20"`
- **Empirical Reality:** Unbilled Google AI Studio developer keys have a hard limit of **20 requests per day (RPD)**.
- **Impact on Track B:** Track B requires 800 judge calls ($50\text{ items} \times 4\text{ conditions} \times 2\text{ baselines} \times 2\text{ position swaps}$). At 20 RPD, completing Track B judging would take **40 full days**.
- **Recommendation:** Do not use `gemini-2.5-flash` on an unbilled key for automated judging without an approved protocol modification or billing authorization. Track A (objective execution checkers) requires 0 judge calls, 0 cost, and completes in minutes.

---

## 5. Changelog & Owner Approvals

- **2026-10-07:** Candidate roster created with initial model tags.
- **2026-10-08:** Roster updated per Owner directives:
  - Candidates updated to models released since April 2025 (IBM Granite 3.3, SmolLM3, Qwen3).
  - `qwen2.5:7b-instruct-q3_k_m` pulled and empirically measured at 4.2 GB VRAM (100% GPU offload at c=4096).
  - Family isolation matrix formally documented; Meta collision resolved by proposing Llama in pool and Qwen/GPT-OSS as baselines.
  - Exhaustive provider audit across 9 free providers documented (Groq, OpenRouter, SambaNova, Cerebras, Together, DeepInfra, Mistral, Cohere, GitHub).
  - Empirical judge quota verified: unbilled Gemini key hits hard 20 RPD limit, requiring 40 days for Track B.
