# Public Benchmark Validation Plan & Pre-Registration Protocol

- **Document Version:** `1.0.0`
- **Creation Date:** 2026-10-20
- **Target Public Benchmarks:**
  - GSM-Hard (`reasoning-machines/gsm-hard`, $N = 150$ test items)
  - FinQA (`czyssrs/FinQA`, $N = 150$ test items)
  - InfiAgent-DABench (`InfiAgent/InfiAgent`, $N = 150$ test items)
- **Primary Hypothesis:** "A 3.8B SLM pipeline with execution tools is competitive with 27B/120B LLMs on computation-heavy tasks."
- **Pipeline Freeze Invariant:** Frozen Specialist Pipeline v1.3 at commit `acef7a5c65b19dd8ed81d0ead5dc279922418edf` (tag `v1.3-slm-frozen`). Only generic adapters allowed under tag `v1.3-public-adapters`.
- **Status:** PRE-REGISTERED PRIOR TO TEST RUN EXECUTION

---

## 1. Executive Mission & Hard Operating Rules

The purpose of this evaluation is to test the generalizability of the small language model (SLM) specialist pipeline on independent, authoritative, public benchmarks that were **not** designed by this project or its agents.

### Strict Protocol Rules:
1. **Pipeline Freezing (Hard Rule 1):**
   The SLM pipeline is strictly frozen at commit `acef7a5` (tag `v1.3-slm-frozen`). Absolutely no changes to the analyser, router, decomposer, colorer, matcher, aggregator, prompts, or rules are permitted. The only new code allowed is a generic input adapter per benchmark that formats the question and its context (table/text/CSV) into the pipeline's existing input format. The adapter must be identical for every item, contain no item-specific text or keywords, and be committed and tagged (`v1.3-public-adapters`) before any test item is evaluated.
2. **No LLM in the SLM Pipeline (Hard Rule 2):**
   The specialist pipeline runs 100% locally on `microsoft/Phi-4-mini-instruct` (3.82B active parameters, RTX 3050 GPU, Vulkan backend, port 8080). LLMs are strictly baselines.
3. **API Secrets Management (Hard Rule 3):**
   Read credentials solely from `.env`. Never print, log, or expose keys, prefixes, or lengths.
4. **Append-Only Immutable Records (Hard Rule 4):**
   Raw result files are append-only. Never edit, reorder, or delete records. Corrections, if required, must be documented in `docs/corrections.md`.
5. **Zero Spend (Hard Rule 5):**
   Strictly zero monetary spend ($0.00). Only local execution and free-tier APIs are permitted. If a rate limit is reached, wait for quota reset and resume.
6. **No Tuning on Test Items (Hard Rule 7):**
   During the test run, fix only crash/format bugs. Log each fix with its rationale in `docs/corrections.md`, re-run affected items as new appended attempts, and report both results.
7. **Symmetric Validity & Honest Accounting (Hard Rules 3, 4, 10):**
   Head-to-head comparisons count only where both systems produce complete, valid answers. Failures, timeouts, and truncations (`finish_reason == "length"`) are never imputed as wins or silently ignored; they are explicitly counted as failed/unsolved items. Real `finish_reason` from the API is recorded for every call.

---

## 2. Official Sources, Commit Pins, Licenses, and Hashes

All raw benchmark data files originate from authoritative repositories and are locked by SHA-256 digests in `data/public/SOURCES.md`.

| Benchmark | Source Repository | Commit Pin | License | Raw Source File(s) | Raw SHA-256 |
|---|---|---|---|---|---|
| **GSM-Hard** | [`reasoning-machines/gsm-hard`](https://huggingface.co/datasets/reasoning-machines/gsm-hard) | `960448f73503112d4226baeb8eb41d3fb5ae2506` | MIT | `gsmhardv2.jsonl` | `2032b0188a49ac0ec38cbe1e695e7d62d6dddc44bbb64f920728aca710e9ddef` |
| **FinQA** | [`czyssrs/FinQA`](https://github.com/czyssrs/FinQA) | `0f16e2867befa6840783e58be38c9efb9229d742` | MIT | `dataset/test.json` | `831dbfb2e785dbc227f895ce3f24046433467aec67b09db2bd6ac7692a8a30dc` |
| **InfiAgent-DABench** | [`InfiAgent/InfiAgent`](https://github.com/InfiAgent/InfiAgent) | `3d6c4a70198e0a41fadf539f5b43c88b8c1a2d9c` | CC-BY-NC 4.0 / Apache 2.0 | `da-dev-questions.jsonl`<br>`da-dev-labels.jsonl`<br>`da-dev-tables/*.csv` | `49ae783b20ecb60449ce1443c524e89f8ca8353a04e05e4d14a055b7a6f06126`<br>`83b8fb8133c1794fcb6b42435e9cce124d22f68b71e2eedb37c973e40b5a18c2`<br>(52 CSV tables) |

---

## 3. Sampling & Cryptographic Split Identifiers

Deterministic sampling was executed using `seed = 42`. The test set consists of 150 items per benchmark ($N = 450$ total items). A disjoint practice set of 20 items per benchmark ($N = 60$ total items) is reserved exclusively for smoke-testing adapters and the baseline harness.

### Practice Splits ($N = 20$ items per benchmark, smoke-test only):
- **GSM-Hard Practice:** `data/public/gsmhard_practice_ids.json`  
  `SHA-256: 9949a69d644eeb5015b60d757547d6d7ab63305a4b22c24013055ede71e038ba`
- **FinQA Practice:** `data/public/finqa_practice_ids.json`  
  `SHA-256: 543e8ed061419cd2833d24506ee2cda5ffdddf1f317807a559c2c46a89f82557`
- **DABench Practice:** `data/public/dabench_practice_ids.json`  
  `SHA-256: ace1675a3bf0c9ba399488f4cbd300b44ca5491463d8de2d12ade405b77e28b0`

### Test Splits ($N = 150$ items per benchmark, locked evaluation):
- **GSM-Hard Test:** `data/public/gsmhard_test_ids.json`  
  `SHA-256: d4efb6fe44099d842a86860a0326db58bfe0f8782c6fc242735daaad99e9b905`
- **FinQA Test:** `data/public/finqa_test_ids.json`  
  `SHA-256: 8fe47f47510a320ffeace8158e138a8c4b42983e03f96d54658ff650b794afab`
- **DABench Test:** `data/public/dabench_test_ids.json`  
  `SHA-256: 890f1c5eecdc78c5e9738948cbc1a9c77416a11da7e89d816341a883a1172922`

---

## 4. Evaluated Systems & Experimental Conditions

All systems are evaluated under identical greedy generation parameters (`temperature = 0.0`, `seed = 42`, `max_tokens = 4096`).

| Condition | System / Model | Parameter Count | Infrastructure | Tool Access & Capabilities |
|---|---|:---:|---|---|
| **C0** | Base SLM (`Phi-4-mini-instruct`) | 3.82B | Local RTX 3050 Laptop GPU (Vulkan backend, port 8080) | Unassisted zero-shot: direct prompt, zero tools, zero execution. |
| **SLM Pipeline v1.3** | Specialist Pipeline (`Phi-4-mini`) | 3.82B | Local RTX 3050 Laptop GPU (Vulkan backend, port 8080) | Multi-stage specialist architecture: Analyser, Router, Decomposer, Colorer with up to 3 execution feedback rounds, Matcher, Aggregator, SQLite tool, isolated Python code execution sandbox. 100% local, $0 spend. |
| **B0 (120B)** | `openai/gpt-oss-120b` | 120B | Groq Cloud API (Free Tier) | Unassisted zero-shot direct generation, zero tools. |
| **B0 (27B)** | `qwen/qwen3.8-27b` | 27B | Groq Cloud API (Free Tier) | Unassisted zero-shot direct generation, zero tools. |
| **B1 (120B)** | `openai/gpt-oss-120b` | 120B | Groq Cloud API (Free Tier) | Standard tool harness: full tool specifications provided (calculator, Python sandbox, SQLite schema, BM25 retrieval); no oracle routing (model autonomously decides whether to call tools). |
| **B1 (27B)** | `qwen/qwen3.8-27b` | 27B | Groq Cloud API (Free Tier) | Standard tool harness: full tool specifications provided; no oracle routing. |
| **B1+code (120B)** | `openai/gpt-oss-120b` | 120B | Groq Cloud API (Free Tier) | Executable Python sandbox with up to 3 execute-and-revise rounds (matching the SLM colorer's 3-round feedback budget), feeding stdout/stderr back to the model. |
| **B1+code (27B)** | `qwen/qwen3.8-27b` | 27B | Groq Cloud API (Free Tier) | Executable Python sandbox with up to 3 execute-and-revise rounds, feeding stdout/stderr back to the model. |

---

## 5. Objective Grading Rules

Grading is 100% automated and deterministic. No LLM judge is used for primary accuracy.

1. **GSM-Hard:**
   - Gold answer is a scalar numeric value.
   - Extraction searches for canonical final answer formats (`The answer is X`, `#### X`, or trailing numeric value).
   - Equivalence criterion: relative numeric tolerance $\le 10^{-4}$ ($0.01\%$):
     $$\frac{|y - \hat{y}|}{\max(|y|, 10^{-9})} \le 10^{-4}$$
2. **FinQA:**
   - Gold answer is numeric (decimal, integer, or percentage).
   - Extraction normalizes percentages and fractions ($0.25 \equiv 25\%$, $0.05 \equiv 5\%$).
   - Currency symbols (`$`, `£`, `€`) and commas are stripped.
   - Equivalence criterion: relative tolerance $\le 1.0\%$ ($0.01$):
     $$\frac{|y - \hat{y}|}{\max(|y|, 10^{-9})} \le 0.01$$
3. **InfiAgent-DABench:**
   - Official closed-form evaluation pattern: extraction of `@answer_name[value]` blocks or explicit final numeric values.
   - Equivalence criterion: exact string match for categorical values, or numerical equivalence within absolute/relative tolerance $\le 10^{-6}$.

---

## 6. Pre-Registered Hypotheses & Success Criteria

1. **Hypothesis 1 (SLM Competitiveness vs. B1):**
   - For each benchmark $b \in \{\text{GSM-Hard}, \text{FinQA}, \text{DABench}\}$ and for each LLM baseline under condition B1 (`gpt-oss-120b` B1, `qwen3.8-27b` B1):
     The SLM specialist pipeline (3.82B) is declared **competitive** if the lower bound of the 95% paired bootstrap confidence interval of $(\text{Acc}_{\text{SLM}} - \text{Acc}_{\text{LLM\_B1}})$ is strictly greater than $-5.00\text{ pp}$:
     $$\text{CI}_{0.95}^{\text{lower}}(\text{Acc}_{\text{SLM}} - \text{Acc}_{\text{LLM\_B1}}) > -5.00\text{ pp}$$
   - The SLM pipeline is declared **superior** if:
     $$\text{CI}_{0.95}^{\text{lower}}(\text{Acc}_{\text{SLM}} - \text{Acc}_{\text{LLM\_B1}}) > 0.00\text{ pp}$$
2. **Hypothesis 2 (Tool Leverage over Base Model):**
   - On each benchmark, the SLM specialist pipeline significantly improves over the unassisted Base SLM (C0):
     $$\text{CI}_{0.95}^{\text{lower}}(\text{Acc}_{\text{SLM}} - \text{Acc}_{\text{C0}}) > 0.00\text{ pp}$$
3. **Hypothesis 3 (Fair Execution under B1+code):**
   - The B1+code condition (allowing up to 3 code execution and revision rounds) will be fully evaluated and reported across all 3 benchmarks for both 27B and 120B baselines, regardless of whether the SLM leads, ties, or trails.

---

## 7. Statistical & Analytical Methodology

- **Resampling:** Paired bootstrap resampling with $B = 10,000$ iterations and fixed random seed $42$, executed separately for each benchmark ($n = 150$) and pooled across all three benchmarks ($N = 450$).
- **Head-to-Head Contingency Matrix:** For each pairwise comparison, report the complete 4-cell table:
  1. SLM-only right
  2. Both right
  3. Both wrong
  4. LLM-only right
- **Failure Accounting:** Count and report real API `finish_reason` distribution per condition. Truncations (`finish_reason == "length"`) are scored as failures.
- **Resource Accounting:** Active weights loaded (3.82B vs 27B vs 120B), local GPU compute vs cloud API, and monetary cost ($0.00 for SLM).
- **Error Analysis:** Qualitative and structural breakdown of 10 SLM losses and 10 SLM wins with single-sentence causal attributions.
