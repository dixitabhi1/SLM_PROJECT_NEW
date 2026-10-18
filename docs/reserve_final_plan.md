# Final Reserve Evaluation Plan & Pre-Registration Protocol

- **Document Version:** `1.0.0`
- **Creation Date:** 2026-10-17
- **Target Dataset:** Track A Reserve Split ($N = 100$ items)
- **Quarantine File:** [`data/reserve_set_quarantine.json`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/reserve_set_quarantine.json)
- **Cryptographic SHA-256 Lock:** `bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db`
- **Evaluation Script:** [`scripts/run_reserve_final.py`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/scripts/run_reserve_final.py)
- **Status:** PREPARED — STOPPED PENDING EXPLICIT OWNER CHECKPOINT APPROVAL

---

## 1. Executive Mission & Hard Operating Constraints

This experiment constitutes the definitive, final evaluation of the pure SLM specialist system against multi-tier external baselines on the cryptographically quarantined Track A Reserve split.

### Strict Protocol Rules (Hard Rules & AGENTS.md Compliance):
1. **Cryptographic Reserve Verification:** The reserve set SHA-256 hash (`bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db`) must be verified before execution starts and immediately upon completion. If the hash diverges at any point, the run immediately aborts.
2. **Immutable Append-Only Records:** Each system writes to its own dedicated, new append-only records file. No existing file is overwritten, modified, or reordered:
   - Specialist Pipeline: `results/phase4/reserve_final_pipeline_records.jsonl`
   - Baseline B1 (GPT-OSS-120B): `results/phase4/reserve_final_b1_gpt120b_records.jsonl`
   - Baseline B1 (Qwen-3.8-27B): `results/phase4/reserve_final_b1_qwen27b_records.jsonl`
3. **Pure SLM Execution & Strict Provenance:**
   - The specialist pipeline runs 100% locally on `phi-4-mini` (3.82B active parameters, RTX 3050 GPU, Vulkan0, port 8080).
   - Every pipeline record writes `answered_by: "phi-4-mini"` and logs `groq_calls: 0`.
   - Exactly zero API tokens or monetary spend are incurred by the pipeline ($0.00 spend).
4. **Fair Resources for Baselines (Rule 9):**
   - The external comparison baselines (120B and 27B) are evaluated under condition `B1` (with fair tools matching the specialist pipeline):
     - SQLite database schema inspection and query execution via tolerant harness with 1 retry on syntax error.
     - BM25 retriever for any technical specification context.
     - Isolated Python sandbox execution for programming and arithmetic subtasks with 1 retry on error.
   - API credentials read strictly from `.env` (`GROQ_API_KEY`). No secrets in scripts or logs.
   - Groq API rate-limit wait time (HTTP 429 backoff) is recorded separately from active model inference latency.
5. **Symmetric Head-to-Head Accounting (Rule 4):**
   - Head-to-head comparisons count only where both systems produced a complete, valid answer.
   - Missing or rate-limited records are explicitly marked `MISSING` and excluded from win/loss percentages (never imputed as 0s or silent losses).
6. **No Tuning on Reserve:** The reserve set has never been viewed, printed, or inspected. The pipeline code is 100% frozen.

---

## 2. Systems under Evaluation

| System ID | Role / Family | Model Identifier | Parameter Count | Serving Hardware / Environment | Tools / Condition |
|---|---|---|:---:|---|---|
| **Specialist Pipeline** | Base SLM (Phi family) | `microsoft/Phi-4-mini-instruct` (GGUF Q4_K_M) | **3.82B** | Local Laptop (RTX 3050 6GB VRAM, Vulkan0, `llama-server` port 8080) | Frozen Pipeline v1.3 (or v1.4 if E2 adapter passes): Generic code compute (`specialist_pipeline_e3.py`), SQLite tool, Python sandbox |
| **Baseline 1 (120B)** | Multi-tier Baseline (Ceiling) | `openai/gpt-oss-120b` | **120B** | Groq Cloud API (Free Tier, unclamped `max_tokens=4096`, `temperature=0.0`) | Condition B1: Fair tools (SQLite harness with 1 retry, BM25 retriever, Python sandbox with 1 retry) |
| **Baseline 2 (27B)** | Multi-tier Baseline (Peer Tier) | `qwen/qwen3.8-27b` | **27B** | Groq Cloud API (Free Tier, unclamped `max_tokens=4096`, `temperature=0.0`) | Condition B1: Fair tools (SQLite harness with 1 retry, BM25 retriever, Python sandbox with 1 retry) |

---

## 3. Stratification of the Reserve Split ($N = 100$)

The Track A Reserve set contains exactly 100 items stratified identically to the Dev and Held-Out splits:

| Stratum / Category | Sample Size ($n$) | Description & Primary Requirements |
|---|:---:|---|
| `atomic_sql` | 15 | Single-turn Text-to-SQL queries over real Spider SQLite databases |
| `atomic_qa` | 15 | Science and technical multiple-choice QA (ARC Challenge) |
| `atomic_code` | 15 | Python programming implementations (HumanEval / MBPP) |
| `atomic_math` | 15 | Multi-step mathematical reasoning (GSM8K) |
| `compound_solvable` | 20 | Multi-stage composed tasks solvable via pure step-by-step reasoning |
| `compound_tool_required` | 20 | Multi-stage composed tasks requiring execution tools (SQLite or Python sandbox) |
| **Total Reserve Set** | **100** | Full stratified benchmark split |

---

## 4. Statistical Analysis Plan & Bootstrap Protocol

1. **Paired Difference Metric:**
   For each item $i \in \{1, \dots, N\}$, the paired difference $d_i = y_{\text{SLM}, i} - y_{\text{LLM}, i} \in \{-1, 0, +1\}$.
2. **Paired Bootstrap:**
   - Resampling with replacement across all valid paired items ($B = 10{,}000$ iterations).
   - Fixed random seed: `42`.
   - Report the mean difference $\Delta$ and the empirical 95% bootstrap confidence interval $[\text{CI}_{2.5\%}, \text{CI}_{97.5\%}]$.
3. **Head-to-Head Quadrant:**
   Report the full symmetric contingency table:
   - **SLM Win:** $y_{\text{SLM}} = 1$ and $y_{\text{LLM}} = 0$
   - **Both Right:** $y_{\text{SLM}} = 1$ and $y_{\text{LLM}} = 1$
   - **Both Wrong:** $y_{\text{SLM}} = 0$ and $y_{\text{LLM}} = 0$
   - **LLM Win:** $y_{\text{SLM}} = 0$ and $y_{\text{LLM}} = 1$
   - **Missing / Excluded:** Count of incomplete items excluded from scoring.

---

## 5. Output Reporting Template

The automated evaluation generates [`docs/reserve_final_evaluation_report.md`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/docs/reserve_final_evaluation_report.md) following this standardized structure:

```markdown
# Final Reserve Evaluation Report (Track A, N=100)

- **Date:** <ISO Timestamp>
- **Reserve File:** data/reserve_set_quarantine.json
- **Reserve SHA-256 (Pre-Run):** bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db [VERIFIED]
- **Reserve SHA-256 (Post-Run):** bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db [VERIFIED]
- **Pipeline Version:** <Pipeline Version>
- **Pipeline Active Parameters:** 3.82B
- **Groq API Calls by Pipeline:** Strictly 0 ($0.00 spend)

## 1. Executive Head-to-Head Summary

| Comparison | Specialist SLM (3.82B) | Baseline LLM | Paired Difference (SLM - LLM) | 95% Bootstrap CI (B=10,000) |
|---|:---:|:---:|:---:|:---:|
| **SLM vs GPT-OSS-120B (B1 with Fair Tools)** | X.X% (X/100) | Y.Y% (Y/100) | Delta pp | [Lower pp, Upper pp] |
| **SLM vs Qwen-3.8-27B (B1 with Fair Tools)** | X.X% (X/100) | Z.Z% (Z/100) | Delta pp | [Lower pp, Upper pp] |

## 2. Head-to-Head Symmetric Contingency Tables

### SLM (3.82B) vs GPT-OSS-120B (B1 Fair Tools)
- **SLM Win:** X items
- **Both Right:** Y items
- **Both Wrong:** Z items
- **120B Win:** W items
- **Missing / Excluded:** 0 items

### SLM (3.82B) vs Qwen-3.8-27B (B1 Fair Tools)
- **SLM Win:** X items
- **Both Right:** Y items
- **Both Wrong:** Z items
- **27B Win:** W items
- **Missing / Excluded:** 0 items

## 3. Stratified Per-Category Breakdown

| Category / Stratum | Sample Size (n) | Specialist SLM (3.82B) | GPT-OSS-120B (B1) | Qwen-3.8-27B (B1) |
|---|:---:|:---:|:---:|:---:|
| `atomic_sql` | 15 | X/15 (X%) | Y/15 (Y%) | Z/15 (Z%) |
| `atomic_qa` | 15 | X/15 (X%) | Y/15 (Y%) | Z/15 (Z%) |
| `atomic_code` | 15 | X/15 (X%) | Y/15 (Y%) | Z/15 (Z%) |
| `atomic_math` | 15 | X/15 (X%) | Y/15 (Y%) | Z/15 (Z%) |
| `compound_solvable` | 20 | X/20 (X%) | Y/20 (Y%) | Z/20 (Z%) |
| `compound_tool_required` | 20 | X/20 (X%) | Y/20 (Y%) | Z/20 (Z%) |
| **Track A Total** | **100** | **X/100 (X%)** | **Y/100 (Y%)** | **Z/100 (Z%)** |

## 4. Latency & Provenance Accounting

| System | Mean Latency (s) | Median Latency (s) | API Rate-Limit Wait Time (s) | Answered By | Monetary Cost |
|---|:---:|:---:|:---:|---|:---:|
| Specialist Pipeline | X.Xs | X.Xs | 0.0s (N/A) | `phi-4-mini` (local Vulkan0 GPU) | $0.00 |
| GPT-OSS-120B (B1) | Y.Ys | Y.Ys | W.Ws | `gpt-oss-120b` (Groq API) | $0.00 |
| Qwen-3.8-27B (B1) | Z.Zs | Z.Zs | W.Ws | `qwen3.8-27b` (Groq API) | $0.00 |
```

---

## 6. Execution Checkpoint

Per Mandatory Owner Checkpoints (AGENTS.md Section 3, Checkpoint 6), **the execution of `scripts/run_reserve_final.py` is strictly stopped**. Execution requires explicit owner sign-off.

---

## 7. Protocol Amendment: Condition B1+code (2026-10-18)

- **Amendment Date:** 2026-10-18
- **Motivation:** In the initial reserve run (`B1`), while the baseline LLMs were prompted that they "may write Python", no sandbox executed their code, whereas the Specialist SLM (v1.3) autonomously executes Python code via its Python Sandbox Specialist (`specialist_pipeline_e3.py`). To guarantee true tool fairness and prevent tool asymmetry on compound tasks, this amendment pre-registers condition **B1+code**.
- **Scope:** Evaluated on the 40 reserve compound tasks (20 `compound_solvable` and 20 `compound_tool_required`).
- **Protocol & Execution Flow:**
  1. For database-linked compound tasks, the model first queries SQLite (with 1 retry if needed) exactly as in B1.
  2. For the calculation, logic, or processing stage, the LLM is instructed: "You may write a single Python code block enclosed in ```python ... ``` to perform calculations or data processing."
  3. If a ```python ... ``` block is emitted by the LLM, the code is extracted and executed in the project's standard sandbox (`src/sandbox/runner.py`) under identical constraints: 10.0-second timeout, zero external network access.
  4. The stdout (or error traceback) is returned to the LLM in a second conversation turn:
     ```
     [Code Execution Result]:
     <stdout>

     Using the execution result above, state your final answer. Conclude with 'Final Answer: <answer>' or '#### <answer>'.
     ```
  5. The LLM produces its final answer following code execution feedback.
  6. If no Python block is emitted, the LLM's initial response is scored directly.
  7. Identical protocol applies to both `openai/gpt-oss-120b` and `qwen/qwen3.8-27b`.
- **API Response & Truncation Integrity:**
  - The exact, actual `finish_reason` returned by the Groq API (e.g., `"stop"`, `"length"`) is recorded for every call.
  - Any completion truncated by token limits (`finish_reason == "length"`) is treated as truncated and scored as 0 per Hard Rule 3.
  - No hardcoded `"stop"` finish reasons are permitted.
- **Append-Only Immutability:**
  - B1+code records are written to dedicated new append-only files:
    - `results/phase4/reserve_final_b1_plus_code_gpt120b_records.jsonl`
    - `results/phase4/reserve_final_b1_plus_code_qwen27b_records.jsonl`
  - The original B1 results are preserved; both B1 and B1+code are reported side by side.

