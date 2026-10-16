# Experiment 4b (E4b): Retrained Learned Router Plan & Pre-Registration

**Project:** SLM Clean Rebuild (CoLabTEL Thrust 1)  
**Date:** 2026-10-17  
**Status:** PRE-REGISTERED (PRIOR TO RETRAINING & DEV EVALUATION)  
**Base Pipeline:** Frozen Pipeline v1.3 (`v1.3-slm-frozen`, commit `acef7a5`)  
**Hardware & Serving:** Local RTX 3050 Laptop GPU (6 GB VRAM), `llama-server` on Vulkan0 (port 8080), 3 parallel slots, context 12,288  
**Model:** `phi-4-mini` (3.82B active parameters, GGUF Q4_K_M)  
**Financial Spend:** Strictly **$0.00** (0 external API calls for pipeline evaluation)

---

## 1. Context, Motivation, & Root Cause Analysis of E4

In Experiment 4 (E4), the learned adaptive router passed the Step 0 headroom check (+10.00 pp headroom: Oracle 87.0% vs v1.3 77.0%) and achieved 69.00% 5-fold cross-validation accuracy on the training pool (+19.0 pp over the single best static route).

However, during Dev evaluation ($N=150$), E4 achieved 76/100 (76.0%) on Dev Track A vs v1.3 77.0% (-1.00 pp, 95% bootstrap CI `[-6.00 pp, +4.00 pp]`), failing Criterion 1 (lower bound $\le 0.0\text{ pp}$) and Criterion 2 (`compound_tool_required` dropped from 16 to 14, a -2 item regression). Per Hard Rule 12, E4 was immediately gated and rejected.

### Diagnostic Root Causes Identified
1. **Shortcut Learning on Procedural Pool Compound Items:**  
   In E4, the training pool's tool-required compound items were self-contained Collatz sequences starting from a single literal integer specified directly in the prompt. Single-stage `code_execution` solved them directly in ~5.0s, while multi-stage `decompose_code` took ~16.0s. When combined with the latency penalty ($\lambda=0.005$), the router learned to strongly favor single-stage code execution over multi-stage decomposition for compound tasks. On Dev, real compound tool-required tasks possess multi-stage dependencies (e.g. Stage 1 queries a database or computes an initial metric; Stage 2 executes code using that metric). Single-stage code execution failed on these tasks because it lacked the fetched intermediate context.
2. **Invalid SQL Labels on Empty Schemas:**  
   The initial pool's SQL items were evaluated on empty schema-only SQLite databases, checking syntax and keyword Jaccard overlap rather than execution output equality on populated tables. Because official Spider train databases from Yale's distribution cannot be obtained due to server 404s, learned SQL routing is dropped to prevent label noise.
3. **Latency Penalty Over-Penalizing Multi-Stage Reasoning:**  
   The latency regularization term $\lambda \cdot \text{latency}$ penalized decomposition routes (`decompose_code` ~16s, `decompose_reasoner` ~20s) by 0.08–0.10 probability points, causing the router to select brittle single-stage shortcuts.

---

## 2. E4b Architectural Modifications & Pre-Registered Fixes

Experiment 4b executes **one retry only** on Dev only, incorporating four structural fixes:

1. **Rebuilt Compound Training Pool ($N=100$):**  
   All 100 compound training instances (50 solvable without tools, 50 tool-required) are rebuilt using `scripts/generate_compound_items.py` with multi-stage dependencies sourced strictly from public training splits (GSM8K train):
   - **50 Solvable Items:** 25 two-stage and 25 three-stage multi-step word problems with business rules, partitioning, and rate calculations solvable without tools.
   - **50 Tool-Required Items:** 25 two-stage and 25 three-stage tasks where Stage 1 computes an initial quantity from a natural language problem, and Stage 2 executes an intensive algorithmic simulation (Collatz sequence, prime sieve, 0/1 knapsack DP, LCG pseudorandom cycles, divisor search) strictly requiring sandbox Python execution.
   - **Strict Verification:** Every compound item is verified via `verify_sensitivity` (perturbing intermediate variables strictly alters the final answer) and `execute_ref_code` (dynamic execution computes the gold answer).
2. **Drop SQL from Learned Router (Retain v1.3 Deterministic SQL Rule):**  
   SQL is excluded from the learned classifier training pool. The pipeline preserves Pipeline v1.3's proven deterministic SQL rule: if `task_asks_for_query` is detected by the Stage 1 analyser, the task routes directly to `direct_sql`.
3. **Zero Latency Penalty ($\lambda = 0.0$):**  
   $\lambda$ is set strictly to **0.00**. This eliminates the latency penalty that biased the router toward single-stage shortcuts, enabling the classifier to select multi-stage decomposition whenever it estimates a higher probability of correct execution.
4. **Hard Guards & Thresholds:**  
   - `analyser.source == 'CORPUS'`: Code execution routes remain strictly forbidden (hard rule).
   - Confidence threshold $\tau = 0.40$: If the maximum route probability falls below $\tau$, the router falls back to Pipeline v1.3's default route.

---

## 3. Training Pool Composition & Cryptographic Lock

The rebuilt training pool [`data/router_e4b_train_pool.json`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/router_e4b_train_pool.json) comprises 400 items:

| Category | Sample Size ($n$) | Source Split | Verification |
|---|:---:|---|---|
| `atomic_math` | 100 | GSM8K `train` (`openai/gsm8k`) | Exact numeric check |
| `atomic_qa` | 100 | ARC-Challenge `train` (`allenai/ai2_arc`) | Multiple choice check |
| `atomic_code` | 100 | MBPP `sanitized` `train` (`google-research-datasets/mbpp`) | Isolated test execution |
| `compound_solvable` | 50 | GSM8K `train` components | Sensitivity verified; dynamic execution |
| `compound_tool_required` | 50 | GSM8K `train` components + algorithmic simulations | Sensitivity verified; dynamic execution |
| **Total Pool** | **400** | **100% Public Training Splits** | **Cryptographically Locked** |

- **Cryptographic SHA-256 Hash:** `33e114331e3094e4e5e2462c51f95f5910f95048b21d81cfd8570476c07089c2`
- **Zero Evaluation Overlap Proven:** Tested against all 400 evaluation instances (Dev Track A, Held-Out Track A, Reserve Quarantine, Extended SQL Dev):
  - Normalized question collisions: **0 / 400 (0.00%)**
  - Item ID collisions: **0 / 400 (0.00%)**

---

## 4. Pre-Registered Success Criteria (Dev Evaluation: $N=150$)

Evaluation is conducted on all 150 Dev items ($100\text{ Track A} + 50\text{ Track B}$) under Pipeline v1.4b (E4b). All three criteria must pass simultaneously:

### Criterion 1: Overall Track A Accuracy Improvement
- **Metric:** Paired bootstrap difference ($B=10{,}000$ iterations, seed `42`) between Pipeline v1.4b (E4b) and Pipeline v1.3 ($77.0\%$) on Dev Track A ($N=100$).
- **Requirement:** The 95% bootstrap confidence interval lower bound must be strictly **$> 0.0\text{ percentage points}$**.

### Criterion 2: Safety Non-Regression on Track A Categories
- **Metric:** Per-category accuracy across all 6 Dev Track A categories:
  - `atomic_code` ($n=15$, v1.3: $13/15$)
  - `atomic_math` ($n=15$, v1.3: $13/15$)
  - `atomic_qa` ($n=15$, v1.3: $11/15$)
  - `atomic_sql` ($n=15$, v1.3: $7/15$)
  - `compound_solvable` ($n=20$, v1.3: $17/20$)
  - `compound_tool_required` ($n=20$, v1.3: $16/20$)
- **Requirement:** No single Track A category may drop by more than **1 item** compared with Pipeline v1.3.

### Criterion 3: Safety Non-Regression on Track B
- **Metric:** Technical QA accuracy on Dev Track B ($N=50$, v1.3: $48/50$, $96.0\%$).
- **Requirement:** Dev Track B accuracy must drop by **$\le 1$ item** compared with Pipeline v1.3 (accuracy $\ge 47/50$, $94.0\%$).

---

## 5. Strict Governance & Stop Condition

1. **One Retry Only:** E4b is the final evaluation of learned adaptive routing.
2. **Dev Only:** Held-out and Reserve splits remain cryptographically quarantined and completely untouched.
3. **No Code Edits After Dev Run:** No router weights, threshold $\tau$, $\lambda$, features, or evaluation code may be edited after the first dev run. Any reporting formatting issues must be handled in a separate script.
4. **Negative Result Close:** If any of the three criteria fail, Experiment 4 is definitively closed as a negative result, and Pipeline v1.3 (`v1.3-slm-frozen`) stands as the production frozen pipeline. No further routing experiments will be attempted.
