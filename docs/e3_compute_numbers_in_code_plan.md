# Experiment 3 (E3): Compute Numbers in Code Plan

This document pre-registers the methodology, architecture, and success criteria for **Experiment 3 (Compute Numbers in Code)** evaluated on Dev Track A ($N=100$) under Pipeline v1.3.

---

## 1. Motivation & Empirical Problem

In the Phase 4 Dev Failure Analysis ([`docs/e2_sql_adapter_plan.md`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/docs/e2_sql_adapter_plan.md#L102-L115)), 10 solvable compound reasoning items failed under Pipeline v1.2:
- **7 Subtask Answer Errors (70%):** Model attempted multi-step arithmetic, modular congruences, knapsack optimization, and digit counting purely in text tokens, suffering from hallucinated sums, miscounted bits, and calculation errors (e.g. $185^3$ off by 5,000; $328 \pmod{128} = 32$ instead of $72$).
- **2 Wrong Colour / Route Errors (20%):** Long sequential simulations (106-step Collatz sequence) and exhaustive search (Chinese Remainder Theorem) were routed to text generation, hitting the 1,024-token context cutoff.
- **1 Aggregation Error (10%):** Downstream specialist rounded intermediate float profit to whole dollar rather than truncating.

In exploratory testing on these 10 items, writing and executing a short Python program in the sandbox solved **8 out of 10 items immediately** without any external model assistance.

---

## 2. Generic Rule Definition

Per user specification, the rule must be completely generic and derived from the analyser's output or task type, strictly forbidding item-specific keywords or patterns (no "Collatz", no "binary").

### Rule Formulation:
Any task or decomposed subtask that requires arithmetic calculation, counting, modular mathematics, iterative simulation, or search over cases is routed to a Python computation specialist:
1. The SLM generates a short, self-contained Python program designed to compute the exact answer.
2. The code is executed in the isolated, timeout-guarded Python sandbox (`src/sandbox/runner.py`).
3. If execution succeeds with clean exit code 0 and non-empty stdout, the printed output is extracted and formatted as the final answer (`Final Answer: <val>` or `#### <val>`).
4. If code execution fails (syntax error, runtime error, or timeout), the pipeline falls back gracefully to standard step-by-step reasoning.
5. Qualitative and conceptual tasks (e.g., ARC-Challenge science QA) do not require computation and execute via standard direct reasoning.

---

## 3. Pre-Registered Success Criteria (Dev Track A Only)

To maintain scientific integrity and prevent post-hoc criterion shifting, the following success criteria are pre-registered on Dev Track A ($N=100$):

1. **Criterion 1 (Overall Track A Accuracy Improvement):**
   - Dev Track A accuracy under Pipeline v1.3 must strictly improve over Pipeline v1.2 baseline ($66.00\%$, 66/100).
   - The paired bootstrap difference ($\text{Accuracy}(\text{v1.3}) - \text{Accuracy}(\text{v1.2})$, $B=10{,}000$ resamples) 95% confidence interval lower bound must be strictly **$> 0.0\text{ percentage points}$**.

2. **Criterion 2 (Safety Non-Regression on Core Atomic Categories):**
   - **Atomic GSM8K Math ($N=15$):** Accuracy must drop by no more than **1 item** relative to v1.2 baseline ($\ge 13/15 = 86.67\%$, baseline is $14/15 = 93.33\%$).
   - **Atomic ARC QA ($N=15$):** Accuracy must drop by no more than **1 item** relative to v1.2 baseline ($\ge 11/15 = 73.33\%$, baseline is $12/15 = 80.00\%$).

3. **Criterion 3 (Safety Non-Regression on Track B Retrieval):**
   - Dev Track B accuracy ($N=50$) under Pipeline v1.3 must drop by no more than **1 item** compared with Pipeline v1.2 baseline ($\ge 47/50 = 94.00\%$, v1.2 baseline is $48/50 = 96.00\%$).
   - Generic constraint: No code routing when the analyser's source is CORPUS.

4. **Strict Evaluation Boundary:**
   - Evaluated strictly on Dev splits: Dev Track A ($N=100$) and Dev Track B ($N=50$), Total $N=150$.
   - **The reserve set remains cryptographically locked and completely untouched.**

---

## 4. Required Reporting Metrics

Upon execution of the frozen E3 dev evaluation, the report will document:
1. Accuracy per category across all 6 strata:
   - Atomic SQL ($N=15$)
   - Atomic QA ($N=15$)
   - Atomic Code ($N=15$)
   - Atomic Math ($N=15$)
   - Compound Solvable ($N=20$)
   - Compound Tool-Required ($N=20$)
2. Fixed vs. Broken counts on the 9 arithmetic/routing failures.
3. Count and item IDs of any previously correct items that broke.
4. Latency cost (mean latency per item across all categories and comparison against v1.2).

