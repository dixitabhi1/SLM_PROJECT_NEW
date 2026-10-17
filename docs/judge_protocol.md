# LLM-as-a-Judge Evaluation Protocol (Secondary Layer)

**Pre-Registration Date:** 2026-10-17  
**Status:** Pre-Registered (Locked Before Execution)  
**Governing Document:** Phase 2 Checkpoint  
**Primary Metric Invariant:** Answer-Key Programmatic Correctness remains the PRIMARY metric. The LLM-as-a-Judge layer is strictly SECONDARY to assess qualitative response nuances, reasoning depth, and instruction compliance.

---

## 1. Judge Model Specification & Family Separation

- **Selected Judge Model:** `allam-2-7b` (ALLaM 2.0 7B Instruct, SDAIA) served via Groq Cloud API.
- **Provider & Endpoint:** Groq Cloud (`https://api.groq.com/openai/v1/chat/completions`).
- **Family Separation Audit (Hard Rule 8):**
  - Specialist SLM Pool: Microsoft / Phi family (`Phi-4-mini`, 3.82B).
  - Frontier Baseline 1: OpenAI family (`openai/gpt-oss-120b`).
  - Peer Baseline 2: Alibaba / Qwen family (`qwen/qwen3.8-27b`).
  - Judge Model: SDAIA / ALLaM family (`allam-2-7b`).
  - **Verdict:** Fully disjoint, non-overlapping model families. The judge model is completely independent of all evaluated models and baselines.
- **Competitor Check:** Neither `openai/gpt-oss-120b` nor `qwen/qwen3.8-27b` nor any planned 70B baseline is used as judge.

---

## 2. Blind Pairwise Evaluation Design

1. **Information Masking (Double-Blind):**
   - The judge prompt receives only:
     1. User Query Prompt (exact text string).
     2. Answer 1.
     3. Answer 2.
   - For SQL items, the minimal SQLite table schema is appended to the query only if required for query semantics.
   - The judge is NEVER given:
     - Model names, parameter counts, system identifiers, or timestamps.
     - Gold reference answers, answer keys, or solutions.
     - Benchmark stratum, task type, or solvability tags.
2. **Deterministic Order Randomization:**
   - For each item, the initial assignment (System A as Answer 1 vs System B as Answer 2) is randomized using a deterministic pseudorandom seed (`seed = 42`).
   - The exact mapping is logged in the raw output record.

---

## 3. Position-Swap Consistency Test

To eliminate position bias (first-answer or second-answer preference), every pairwise item is evaluated twice in two distinct passes:
- **Pass A (Original):** System 1 as Answer 1, System 2 as Answer 2.
- **Pass B (Swapped):** System 2 as Answer 1, System 1 as Answer 2.

### Aggregate Scoring per Item:
Let $Q^{(A)}$ and $Q^{(B)}$ be the holistic scores assigned in Pass A and Pass B:
$$Q_{S,i} = \frac{Q_{S,i}^{(A)} + Q_{S,i}^{(B)}}{2}$$
$$Q_{L,i} = \frac{Q_{L,i}^{(A)} + Q_{L,i}^{(B)}}{2}$$

### Swap Consistency Metric:
An item is swap-consistent if and only if the winning system identified in Pass A matches the winning system identified in Pass B (or both passes declare a Draw).
$$\text{Swap Consistency} = \frac{\sum_{i=1}^N \mathbf{1}[\text{Winner}^{(A)}_i \equiv \text{Winner}^{(B)}_i]}{N}$$

---

## 4. Scoring Criteria & Structured Output Schema

The judge operates at `temperature = 0.0` with strict JSON mode enabled (`response_format: {"type": "json_object"}`).

### Scoring Dimensions:
1. **Holistic Score (1–10):** Overall answer quality, factual validity, logical coherence, and utility.
2. **Four Fine-Grained Criteria (1–5 each):**
   - `correctness`: Accuracy of facts, calculations, logic, and code.
   - `completeness`: Fully addresses all sub-questions and constraints.
   - `reasoning_quality`: Step-by-step clarity, sound argumentation, lack of hallucinations.
   - `formatting`: Clean structure, adherence to requested output format (no extraneous fluff).

### Composite Quality Score (CQS):
$$\text{CQS} = \frac{\text{correctness} + \text{completeness} + \text{reasoning\_quality} + \text{formatting}}{4}$$

### Strict JSON Output Schema:
```json
{
  "answer_1": {
    "holistic": 9,
    "correctness": 5,
    "completeness": 5,
    "reasoning_quality": 5,
    "formatting": 4
  },
  "answer_2": {
    "holistic": 7,
    "correctness": 4,
    "completeness": 4,
    "reasoning_quality": 3,
    "formatting": 4
  },
  "winner": "Answer 1",
  "explanation": "Answer 1 provides exact calculation with full working, whereas Answer 2 has a minor arithmetic error."
}
```

### Parsing & Retry Invariant:
- Raw LLM output strings are immutably written to `results/judge/judge_trials_raw.jsonl`.
- If JSON parsing fails, exactly one retry is executed with a clarifying schema prompt.
- Both the initial failed attempt and retry attempt are recorded.

---

## 5. Secondary Metrics & Mathematical Definitions

1. **Pairwise Win / Draw / Loss:**
   - **SLM Win:** $Q_{S,i} > Q_{L,i}$
   - **LLM Win:** $Q_{L,i} > Q_{S,i}$
   - **Draw:** $Q_{S,i} = Q_{L,i}$
   - **Effective Win Rate (SLM Not Beaten):** $\frac{\text{SLM Wins} + \text{Draws}}{N} \times 100\%$
2. **Quality Proximity ($QP$):**
   Measures relative quality parity on a normalized 0 to 1 scale:
   $$QP_i = 1 - \frac{|Q_{S,i} - Q_{L,i}|}{9}$$
   - $QP_i = 1.0$: Exact quality parity ($|Q_S - Q_L| = 0$).
   - $QP_i = 0.0$: Maximum possible quality disparity ($|Q_S - Q_L| = 9$).
   - The mean Quality Proximity is reported alongside its 95% bootstrap percentile confidence interval ($B=10,000$, seed 42).
3. **Quality Difference ($\Delta Q$):**
   $$\Delta Q = \frac{1}{N} \sum_{i=1}^N (Q_{S,i} - Q_{L,i})$$
   Reported with 95% bootstrap confidence interval.

---

## 6. Judge Validity Verification (Hard Integrity Check)

Before any LLM-as-a-judge score can be accepted, the judge must pass two empirical sanity checks:
1. **Check (a) — Disagreement Concordance:**
   On all items where exactly one model was correct according to the immutable programmatic answer key (from `versioned_scorer.py`), the judge must select the answer-key-correct model as the winner:
   $$\text{Concordance Rate} = \frac{\sum_{i \in \text{Disagreements}} \mathbf{1}[\text{Judge Winner}_i \equiv \text{Answer-Key Winner}_i]}{|\text{Disagreements}|}$$
   - **Hard Threshold:** Concordance Rate must be $\ge 80.0\%$.
   - If Concordance Rate $< 80.0\%$, the judge fails validity; every report table must mark Quality Proximity as **"unreliable (judge validity < 80%)"**.
2. **Check (b) — False-Positive Hallucination Rate:**
   The proportion of answers verified as WRONG by the deterministic answer-key checker that the judge erroneously scored $\ge 8/10$ (high quality):
   $$\text{False High Score Rate} = \frac{\sum_{i \in \text{Wrong}} \mathbf{1}[Q_i \ge 8]}{|\text{Wrong}|}$$
   - Must be explicitly reported in the audit ledger.

---

## 7. Execution Scope for Phase 3

- **Target Splits:** Held-Out Track A ($N=100$) and Held-Out Track B ($N=50$), total 150 items.
- **Competitors Evaluated against Specialist SLM v1.3:**
  1. Baseline B1 GPT-OSS-120B (Tool-equipped).
  2. Baseline B1 qwen/qwen3.8-27b (Tool-equipped).
- **Total Calls:** 150 items $\times$ 2 baselines $\times$ 2 passes (swap test) = **600 judge calls**.
- **Data Source:** Existing immutable generation records from `results/phase4/`:
  - `heldout_e3_v2_pipeline_records.jsonl`
  - `b1_gpt120b_heldout_records.jsonl`
  - `b1_qwen27b_heldout_records.jsonl`
- **Zero New Model Inferences:** Evaluates frozen outputs already logged on disk.
- **Append-Only Output:** All trial records append to `results/judge/judge_trials_raw.jsonl`.

---

## 8. Protocol Amendment (2026-10-17): Judge Model Migration to gemini-2.5-flash

**Amendment Date:** 2026-10-17  
**Authorization:** Owner Checkpoint (Phase 2 Review)

### Rationale:
During the Phase 2 limit check across 5 development items (`spider_val_0676`, `NYSEDREGENTS_2014_4_22`, `HumanEval/2`, `gsm8k_test_0530`, `compound_dev_v2_0001`), the candidate judge `allam-2-7b` demonstrated multiple critical evaluation failures:
1. **Schema Violations:** Broke criteria range constraints, scoring criteria as high as 10/10 despite explicit instructions for a 1–5 range.
2. **Internal Scoring Contradictions:** On `HumanEval/2`, assigned Answer 1 a holistic score of 8/10 and Answer 2 a 9/10, but declared "Winner: Answer 1" (inverting its own score).
3. **Severe Over-Scoring of Incomplete/Broken Answers:** Assigned 8/10 and 9/10 to answers that cut off mid-sentence or failed to execute, failing baseline qualitative discrimination.

In contrast, `gemini-2.5-flash` adhered 100% to the JSON schema, scored broken outputs appropriately low (1/10 and 2/10), and accurately declared draws on mutual non-completions.

### Updated Judge Specification:
- **Judge Model ID:** `gemini-2.5-flash`
- **Family Separation (Hard Rule 8):** Google DeepMind family. Completely distinct and non-overlapping from Microsoft/Phi-4-mini, OpenAI/GPT-OSS-120B, and Alibaba/qwen3.8-27b.
- **Provider & Authentication:** Google Cloud / Generative Language API (`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`).
- **Security & Key Handling:** API key is transmitted strictly via the `x-goog-api-key` HTTP request header, NEVER in the query URL string or logged to disk/records.
- **Pinned Hyperparameters & Generation Configuration:**
  - `temperature`: `0.0` (deterministic greedy evaluation)
  - `thinkingBudget`: `0` (disables extended thinking tokens, enforcing direct structured judgment, ~2.2s latency, and zero thinking token overhead)
  - `response_mime_type`: `"application/json"` (strict JSON response type)
- **Model Version Logging:** The exact `modelVersion` string returned in each API response payload is recorded in every raw trial record in `results/judge/judge_trials_raw.jsonl`.

---

## 9. Protocol Amendment (2026-10-17): Judge Model Migration to gemini-3.8-flash & Input Standardization

**Amendment Date:** 2026-10-17  
**Authorization:** Owner Checkpoint (Phase 3 Pre-Execution)

### Rationale:
1. **Quota Ceiling on gemini-2.5-flash:** During the initial trial run of Phase 3, Google Generative Language API hard-capped `gemini-2.5-flash` at a free-tier limit of 20 requests per day (`RESOURCE_EXHAUSTED` with 429 quota failure).
2. **Groq Catalog Audit:** An exhaustive audit of GroqCloud endpoints confirmed that candidate models (`meta-llama/llama-4-maverick-*`, `meta-llama/llama-4-scout-*`, `moonshotai/kimi-k2-*`) are not deployed on Groq (HTTP 404), legacy models are decommissioned (HTTP 400), and `allam-2-7b` was previously disqualified for schema failures and score inversions. No eligible non-competitor instruction model exists on Groq.
3. **Selection of gemini-3.8-flash:** `gemini-3.8-flash` operates on the standard free tier (15 RPM, 1,500 RPD, 1,000,000 TPM), achieved 100% schema adherence on the 5-item dev check, demonstrated 100% internal consistency, and penalized broken answers ($\le 3/10$) while maintaining zero monetary spend.

### Pinned Configuration:
- **Judge Model ID:** `gemini-3.8-flash`
- **Family Separation (Hard Rule 8):** Google DeepMind family. Completely disjoint from Microsoft (`Phi-4-mini`), OpenAI (`gpt-oss-120b`), and Alibaba (`qwen3.8-27b`).
- **Endpoint:** `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent`
- **Security & Key Handling:** The API key is sent strictly via the `x-goog-api-key` HTTP header, never in the request URL string or logged to disk/records.
- **Generation Settings:** `temperature=0.0`, `thinkingBudget=0`, strict JSON response type (`response_mime_type: "application/json"`).
- **Model Version Recording:** The exact `modelVersion` string returned in every API response payload is recorded in each raw trial record.

### Standardized Judge Input Definition (`get_user_facing_response`):
To ensure symmetric and fair evaluation semantics across all systems:
- **Baseline LLMs (GPT-OSS-120B and qwen/qwen3.8-27b):** Provide `full_output` (contains full step-by-step reasoning trace).
- **Specialist SLM v1.3:** If `final_answer` is an extracted short target string ($< 50$ chars) and `output` contains the generated execution code or reasoning steps, provide `output + final_answer` (or `output` if already included). If `final_answer` is a complete full response ($\ge \text{output}$), provide `final_answer`.

#### Per-Category Field Usage Breakdown ($N=150$ Held-Out Items):
| Task Category / Stratum | Items | `final_answer` Used | `output + final_answer` Used |
| :--- | :---: | :---: | :---: |
| Atomic SQL (`spider`) | 15 | 15 (100.0%) | 0 (0.0%) |
| Atomic QA (`arc_challenge`) | 15 | 12 (80.0%) | 3 (20.0%) |
| Atomic Code (`humaneval`) | 15 | 15 (100.0%) | 0 (0.0%) |
| Atomic Math (`gsm8k`) | 15 | 0 (0.0%) | 15 (100.0%) |
| Compound Solvable without Tools | 20 | 0 (0.0%) | 20 (100.0%) |
| Compound Tool-Required | 20 | 1 (5.0%) | 19 (95.0%) |
| Track B Fact-Checklist (`hypergrid`) | 50 | 50 (100.0%) | 0 (0.0%) |
| **Total Split** | **150** | **93 (62.0%)** | **57 (38.0%)** |

### Superseded Trials Declaration:
The 11 partial trial records previously evaluated using `gemini-2.5-flash` in `results/judge/judge_trials_raw.jsonl` are formally declared **superseded** (logged in `results/phase4/corrections.jsonl`) and are excluded from all reported metrics and tables. The frozen evaluation is recorded fresh to `results/judge/judge_trials_raw_gemini38.jsonl`.



