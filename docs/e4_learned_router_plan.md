# Experiment 4 (E4): Learned Adaptive Router Plan & Pre-Registration

**Project:** SLM Clean Rebuild / CoLabTEL Thrust 1 (Learned Adaptive Orchestration)  
**Date:** 2026-10-16  
**Status:** PRE-REGISTERED PRIOR TO DEV EVALUATION  
**Base Pipeline:** Frozen Pipeline v1.3 (`v1.3-slm-frozen`, commit `acef7a5`)  
**Target File:** [`docs/e4_learned_router_plan.md`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/docs/e4_learned_router_plan.md)

---

## 1. Executive Summary & Objective

The objective of Experiment 4 (CoLabTEL Thrust 1) is to replace heuristic stage routing with a **learned, lightweight adaptive router** that predicts the optimal execution route for each task based on surface prompt features, task analyser outputs, and an explicit latency penalty.

### Fixed Immutable Rules
1. **Pure SLM Execution:** Every pipeline call is executed locally by `phi-4-mini` (3.82B active parameters) on local GPU via `llama-server` (Vulkan0, port 8080). Every record logs `answered_by: "phi-4-mini"`. Outgoing API calls to Groq or external LLMs during pipeline runs are strictly **0**.
2. **Hard Rule for CORPUS:** If the Analyser detects `source == 'CORPUS'` (e.g. Track B retrieval items), the pipeline MUST NEVER route to code execution (`code_execution` or `decompose_code`). This rule is hard-coded into the router constraint logic; it is NOT learned.
3. **Quarantine Reserve Set:** `data/reserve_set_quarantine.json` (SHA-256: `bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db`, $N=100$) remains strictly locked, untouched, and uninspected.
4. **Append-Only Records:** All raw evaluation records are strictly append-only.

---

## 2. Step 0: Dev Track A Headroom Verification (PASSED)

Before investing in router training, a systematic headroom evaluation was conducted on all 100 Dev Track A items across the 5 canonical pipeline routes:
1. `direct_reasoner`: Greedy direct zero-shot reasoning.
2. `direct_sql`: Schema lookup, SQLite query generation, tolerant SQLite execution, and 1 retry.
3. `code_execution`: Python sandbox execution with stdout parsing or function stub completion.
4. `decompose_reasoner`: 2-stage task decomposition + data fetch + downstream direct reasoner.
5. `decompose_code`: 2-stage task decomposition + data fetch + downstream Python sandbox execution.

### Viability Condition
If the Oracle accuracy (the best route chosen per item) is less than **5.0 percentage points** above Pipeline v1.3 ($77.0\%$), Experiment 4 is declared unviable and stopped.

### Empirical Headroom Results ($N=100$ Dev Track A Items)
- **Pipeline v1.3 Accuracy:** **77/100 (77.00%)**
- **Oracle Route Accuracy:** **87/100 (87.00%)**
- **Observed Headroom ($\text{Oracle} - v1.3$):** **+10.00 percentage points**
- **Viability Verdict:** **PASS** (10.00 pp $\ge 5.00$ pp, double the minimum viability requirement).

### Single Static Route Accuracies ($N=100$ Dev Items)
- `direct_reasoner`: 57/100 (57.0%), Mean Latency: 7.74s
- `direct_sql`: 18/100 (18.0%), Mean Latency: 5.31s
- `code_execution`: 50/100 (50.0%), Mean Latency: 10.11s
- `decompose_reasoner`: 44/100 (44.0%), Mean Latency: 20.33s
- `decompose_code`: 45/100 (45.0%), Mean Latency: 16.25s

### Per-Category Oracle vs Pipeline v1.3 Breakdown
| Category | Sample Size ($n$) | Pipeline v1.3 | Oracle Best Route | Headroom Delta |
|---|:---:|:---:|:---:|:---:|
| `atomic_code` | 15 | 13/15 (86.7%) | 13/15 (86.7%) | +0 (+0.0 pp) |
| `atomic_math` | 15 | 13/15 (86.7%) | 14/15 (93.3%) | +1 (+6.7 pp) |
| `atomic_qa` | 15 | 11/15 (73.3%) | 15/15 (100.0%) | +4 (+26.7 pp) |
| `atomic_sql` | 15 | 7/15 (46.7%) | 9/15 (60.0%) | +2 (+13.3 pp) |
| `compound_solvable` | 20 | 17/20 (85.0%) | 19/20 (95.0%) | +2 (+10.0 pp) |
| `compound_tool_required` | 20 | 16/20 (80.0%) | 17/20 (85.0%) | +1 (+5.0 pp) |
| **Dev Track A Total** | **100** | **77/100 (77.0%)** | **87/100 (87.0%)** | **+10 (+10.0 pp)** |

---

## 3. Step 1: Training Pool Construction (COMPLETE)

A dedicated, non-overlapping training pool was constructed from public training splits:
- **File:** [`data/router_train_pool.json`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/router_train_pool.json)
- **Seed:** `42`
- **Total Size:** 500 instances (~100 items per category)
- **Cryptographic SHA-256 Hash:** `3fe3e5213fcdb7a484e31b3b9f64c544672251b5240d524fd35e5c3abec21a0f`
- **Documentation Report:** [`docs/router_training_pool_report.md`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/docs/router_training_pool_report.md)

### Category Breakdown
1. `atomic_sql` ($n=100$): Official Spider training split (`xlangai/spider`, split `train`). All 100 items use databases strictly disjoint from validation databases.
2. `atomic_math` ($n=100$): Official GSM8K training split (`openai/gsm8k`, split `train`).
3. `atomic_qa` ($n=100$): Official ARC-Challenge training split (`allenai/ai2_arc`, split `train`).
4. `atomic_code` ($n=100$): Official MBPP sanitized training split (`google-research-datasets/mbpp`, split `train`).
5. `compound_solvable` ($n=50$): Composed multi-step arithmetic/simulation items solvable without tools.
6. `compound_tool_required` ($n=50$): Composed multi-step simulation / Collatz / algorithmic search items requiring tool execution.

### Cryptographic Non-Overlap Proof
Every candidate question was lowercased, stripped of punctuation, and whitespace-collapsed. The normalized strings and item IDs were tested against all 400 evaluation instances across Dev Track A (100), Held-Out Track A (100), Reserve Quarantine (100), and Extended SQL Dev (100):
- Normalized question collisions: **0 / 500 (0.00%)**
- Item ID collisions: **0 / 500 (0.00%)**
- Database overlap (Spider train vs validation databases): **0 / 100 (0.00%)**

---

## 4. Step 2: Router Architecture, Feature Space, & Training Objective

### Feature Vector Design ($X \in \mathbb{R}^d$)
The feature extraction operates in two tiers:

1. **Surface Prompt Features:**
   - `char_len`: Total prompt character count.
   - `word_len`: Total word count.
   - `num_digits`: Count of numerical digits `\d`.
   - `num_symbols`: Count of punctuation / math symbols (`?`, `$`, `%`, `&`, `_`, `*`, `/`, etc.).
   - `has_question_mark`: Binary indicator for `?`.
   - `has_dollar`: Binary indicator for `$`.
   - `has_code_syntax`: Binary indicator for Python tokens (`def `, `import `, `return `, `class `).
   - `has_sql_syntax`: Binary indicator for SQL keywords (`SELECT `, `FROM `, `TABLE `, `WHERE `).
   - `has_multiple_choice`: Binary indicator for option patterns `\([A-D]\)`.
   - `num_lines`: Total newline count.

2. **Task Analyser Features (SLM Stage 1 Output):**
   - `analyser_task_type`: One-hot encoded (`sql`, `math`, `code`, `qa`, `compound`, `other`).
   - `analyser_solvability`: One-hot encoded (`atomic`, `solvable_without_tools`, `tool_required`, `unknown`).
   - `analyser_source`: One-hot encoded (`DB`, `SANDBOX`, `CORPUS`, `NONE`).
   - `db_identified`: Binary indicator if database was resolved.
   - `plan_present`: Binary indicator if decomposition plan is non-empty.
   - `step_count`: Number of plan steps.
   - `task_asks_for_query`: Binary indicator from SQL query intent detector.

### Decision Rule with Latency Penalty & Fallback
For an incoming task $x$:
1. **Hard Guard:** If `analyser_source == 'CORPUS'`, restrict allowed routes to $\{\text{direct\_reasoner}, \text{decompose\_reasoner}\}$.
2. **Success Probability Estimation:** The classifier estimates $\hat{P}(Y_r = 1 \mid x)$ for each allowed route $r$.
3. **Objective Function:**
   $$r^* = \arg\max_{r \in \mathcal{R}_{\text{allowed}}} \left[ \hat{P}(Y_r = 1 \mid x) - \lambda \cdot \overline{\text{latency}}_r \right]$$
   where $\lambda \ge 0$ is a small latency regularization parameter tuned on cross-validation.
4. **Low Confidence Fallback:**
   If $\max_r \hat{P}(Y_r = 1 \mid x) < \tau$ (confidence threshold), the router falls back to the frozen Pipeline v1.3 rule.

### Cross-Validation Constraint
Model selection, hyperparameter tuning ($\lambda, \tau$), and feature importance analyses are evaluated strictly via 5-fold cross-validation on the 500 items of `data/router_train_pool.json`. The router model is never trained or tuned on Dev items.

---

## 5. Step 3: Pre-Registered Success Criteria (Dev Evaluation)

Evaluation will be conducted on all 150 Dev items ($N=100\text{ Track A} + 50\text{ Track B}$) under frozen Pipeline v1.4 (E4). All three criteria must pass simultaneously:

### Criterion 1: Overall Track A Accuracy Improvement
- **Metric:** Paired bootstrap difference ($B=10{,}000$ iterations, seed `42`) between Pipeline v1.4 (E4) and Pipeline v1.3 ($77.0\%$) on Dev Track A ($N=100$).
- **Threshold:** The 95% bootstrap confidence interval lower bound must be strictly **$> 0.0\text{ percentage points}$**.

### Criterion 2: Safety Non-Regression on Track A Categories
- **Metric:** Per-category accuracy across all 6 Dev Track A categories:
  - `atomic_code` ($n=15$, v1.3: $13/15$)
  - `atomic_math` ($n=15$, v1.3: $13/15$)
  - `atomic_qa` ($n=15$, v1.3: $11/15$)
  - `atomic_sql` ($n=15$, v1.3: $7/15$)
  - `compound_solvable` ($n=20$, v1.3: $17/20$)
  - `compound_tool_required` ($n=20$, v1.3: $16/20$)
- **Threshold:** No single Track A category may drop by more than **1 item** compared with Pipeline v1.3.

### Criterion 3: Safety Non-Regression on Track B
- **Metric:** Technical QA accuracy on Dev Track B ($N=50$, v1.3: $48/50$, $96.0\%$).
- **Threshold:** Dev Track B accuracy must drop by **$\le 1$ item** compared with Pipeline v1.3 (accuracy $\ge 47/50$, $94.0\%$).

---

## 6. Required Reporting Deliverables
Upon completion of the Dev evaluation, the final report must include:
1. Accuracy per category (Track A + Track B).
2. Paired head-to-head comparison vs Pipeline v1.3 (wins, both right, both wrong, losses).
3. Mean latency and token cost.
4. Router fallback rate (fraction of queries where low confidence triggered v1.3 rule).
5. Feature importance analysis (coefficients or SHAP/Gini values showing which features drove routing decisions).
