# Protocol Change Proposal: Clean Rebuild Evaluation Framework

**Target Audience:** For the Project Owner to present to the Academic Mentor.  
*(Per operational rules, this document is internal to the repository; no materials are communicated directly to outside parties or the mentor by the agent.)*

---

## Executive Summary

The previous iteration of the SLM evaluation protocol relied on open-ended queries evaluated by a proprietary LLM judge across four fine-tuning conditions (E1 to E4). Under rigorous auditing, that evaluation protocol exhibited severe structural vulnerabilities:
1. Small Language Models ($\le 8\text{B}$) evaluated on closed-book open-ended text generation were subjected to stylistic and length discrepancies compared against large models (120B).
2. Metrics were susceptible to LLM-judge length and stylistic preferences.
3. Concurrency and hardware resource constraints were underspecified, obscuring actual GPU execution bottlenecks.

This document outlines the proposed departures from the mentor protocol, explains the architectural and methodological rationale for each modification, and details what the original protocol measured versus what the new protocol measures.

---

## 1. Primary Track Shift: Track A (Objective Scoring) vs. Track B (Subjective Scoring)

### What Changed:
- **Track A (Objective Tasks) is established as the primary evaluation track.** The benchmark contest centers on tasks where success is deterministically verifiable:
  - Unit-test execution match (Python code generation)
  - Result set equivalence on SQLite queries (Spider / Text-to-SQL)
  - Exact numerical match on multi-step reasoning (GSM8K)
  - Exact multiple-choice verification (ARC-Challenge)
- **Track B (Private Knowledge Evaluation) is retained as the secondary track**, evaluating synthesis over an immutable, private corpus that large models have not seen during pre-training. Scored on dev by an automated fact checklist (deterministic extraction); LLM judging postponed to the final held-out evaluation at most.

### Why:
Evaluating models purely on open-ended generation conflates linguistic fluency with factual and procedural correctness. By establishing deterministically verifiable tasks (with access to execution runtimes and tools), the evaluation directly tests correctness and procedural accuracy rather than stylistic preference.

### What the Old Protocol Measured Instead:
The old protocol measured the LLM judge's stylistic preference for lengthy, fluent, but unverified natural language text.

---

## 2. Integration of Specialist Tools and Sample-and-Verify

### What Changed:
- Every specialist SLM in the active execution pipeline is paired with sandboxed execution tools (local Python runner, SQLite engine, calculator).
- Pipelines utilize a **sample-and-verify** strategy ($N \ge 3$ candidate generations filtered by deterministic test passing before escalating).

### Why:
Autoregressive generation without execution feedback allows compounding errors in algorithmic, syntactic, and numeric tasks. Providing an isolated execution sandbox and verification filter tests the system's ability to validate and self-correct solutions prior to final response generation.

### What the Old Protocol Measured Instead:
The old protocol evaluated raw zero-shot autoregressive completion without tools or execution feedback.

---

## 3. Concurrency Definition and Usable Context Length ($\ge 4096$ Tokens)

### What Changed:
- Concurrency metric is mathematically formalized as continuous time-weighted concurrency:
  $$\bar{C} = \frac{\sum_{i=1}^n (e_i - s_i)}{T_{\text{active}}}$$
  where $s_i$ and $e_i$ are exact hardware request start and end timestamps. Serial configurations strictly measure $\bar{C} = 1.0$.
- All pipeline evaluations enforce a production-grade context length of **$\ge 4096$ tokens per request** across all loaded models.
- Utilization of **Config (f)** (Single $\le 4\text{B}$ model with 2–3 parallel slots) to guarantee 100% GPU offload on 6 GB VRAM without spilling layers or KV cache to CPU.

### Why:
At short context lengths (e.g., 1024 tokens), multiple models fit artificially in VRAM. However, real-world retrieval-augmented and multi-step pipelines require at least 4096 tokens of KV cache per request. At 4096 tokens, co-loading an 8B model with parallel slots or co-loading multiple bases simultaneously causes KV buffer overflow and layer spillover to CPU. Single-base slotting (Config f) maintains full GPU residency across the active context window.

### What the Old Protocol Measured Instead:
The old protocol either ran unverified concurrent workers or measured wall-clock concurrency without tracking exact timestamp overlaps or VRAM-induced CPU offloading.

---

## 4. Multi-Tier Open-Weight Baseline Ladder

### What Changed:
- Instead of a single ambiguous baseline, the evaluation establishes a structured three-tier open-weight ladder:
  - **Tier 1 (27B):** `qwen/qwen3.8-27b` (Alibaba)
  - **Tier 2 (~50B):** *Skipped* (no dense open-weight model exists near 50B on free cardless endpoints)
  - **Tier 3 (120B):** `openai/gpt-oss-120b` (OpenAI open-weight ceiling)
- Pinned exact revisions with zero floating tags (`-latest`).

### Why:
A multi-tier ladder isolates whether the SLM framework can defeat intermediate-scale models (27B) and where performance plateaus relative to frontier-class open models (120B).

### What the Old Protocol Measured Instead:
A single non-transparent comparison, often comparing an SLM against a model with dissimilar prompting or undisclosed parameter scales.

---

## 5. Enforcement of Strict Integrity Safeguards (Rules 1–13)

### What Changed:
- **Hard Rule 1 (Zero fabricated numbers):** All metrics generated by automated scripts directly from disk.
- **Hard Rule 2 (Raw files immutable):** Append-only logs; corrections tracked in `corrections.jsonl`.
- **Hard Rule 3 (Fail loudly):** Any generation truncation, timeout, or empty response aborts that item as `FAILED` (no imputation).
- **Hard Rule 4 (Symmetric validity):** Head-to-head comparisons count only if BOTH sides produced valid answers.
- **Hard Rule 5 (Cryptographic held-out lock):** Evaluation splits locked by SHA-256 before any pipeline run.
- **Hard Rule 8 (Family separation):** Strict non-overlapping families between specialist pool, baselines, and judge.

### Why:
Guarantees that every finding, chart, and win rate survives independent forensic auditing and replication.

---

## 6. Training Compute Offload: Free Kaggle GPU (Owner-Approved Exception to Laptop-Only)

### What Changed:
- Adapter fine-tuning (Phase 6, Rung C4) will run on a free Kaggle GPU (16 GB VRAM) instead of the local 6 GB laptop GPU.
- Serving (`llama-server`), the pipeline orchestration, tools, and all evaluation runs remain strictly local on the host laptop.
- Zero monetary spend is strictly preserved ($0.00).

### Why:
Empirical exploration on the local RTX 3050 Laptop GPU (6,144 MiB physical VRAM) demonstrated that 4-bit QLoRA fine-tuning for sequence lengths $\ge 512$ tokens requires $\ge 7.1$ GB VRAM, triggering CUDA OutOfMemory errors unless paged into host system RAM at severe throughput degradation. Kaggle provides free access to 16 GB GPUs (NVIDIA T4 / P100), enabling QLoRA training up to 2,048 tokens in standard dedicated VRAM with zero financial cost.

### Rigorous Kaggle Operating Rules:
1. **Agent Prepares, Owner Runs:** Agent prepares a self-contained notebook and training data file; owner executes it on Kaggle.
2. **Strict Evaluation Isolation:** Training data contains strictly zero dev, held-out, reserve, or spent items, verified by cryptographic hash and near-duplicate scanning prior to upload. No evaluation data is ever uploaded to Kaggle.
3. **Zero Secrets:** No API keys, credentials, or secrets in notebooks or data files.
4. **Reproducibility & Pinned Artifacts:** Exact library versions, fixed seed (42), and the exact Hugging Face snapshot hash of Phi-4-mini from the registry are pinned.
5. **Local Verification Gate:** Trained adapters, training logs, validation curves, and configs are downloaded to `adapters/<name>/`, cryptographically hashed, converted to GGUF using repo tooling, and verified locally on `llama-server`. An adapter is accepted only if it beats the base model on dev task accuracy.
6. **Execution Gating:** Fine-tuning starts only after Rungs C0 to C3 are measured on dev and owner gives explicit sign-off.

---

## 7. Comparison Table: Protocol Mapping

| Dimension | Old Mentor Protocol | Clean Rebuild Proposed Protocol |
|---|---|---|
| **Primary Evaluation Track** | Open-ended queries (E1–E4) judged by LLM | Track A: Objective tasks (code, SQL, math, QA) with deterministic checkers |
| **Secondary Evaluation Track** | None | Track B: Private knowledge corpus evaluated via automated fact checklist (dev); LLM judge postponed |
| **Tool Integration** | None (pure parametric generation) | Integrated Python sandbox, SQLite executor, symbolic math engine |
| **Verification Mechanism** | Single-pass generation | Sample-and-verify ($N=3$) with deterministic acceptance criteria |
| **Context Length** | Undefined / ~1024 tokens | Strictly $\ge 4096$ tokens per request |
| **Concurrency Metric** | Worker count / thread count | Continuous time-weighted overlap $\bar{C}$; serial strictly 1.0 |
| **Baselines** | Single baseline | Multi-tier ladder: 27B (`qwen3.8-27b`) and 120B (`gpt-oss-120b`) |
| **Training Compute** | Undefined / Local | Free Kaggle GPU (16 GB VRAM) for QLoRA training; serving & eval strictly laptop; $0 spend |
| **Failure Handling** | Implicit imputation / omission | Fail loudly: item marked `FAILED`, zero imputation, symmetric exclusion |
| **Data Integrity** | Manual tables | Cryptographically hashed raw records, automated audit scripts |

