# Experiment 4b (E4b) Training Pool Construction Report

- **Date:** 2026-10-17T03:24:55Z
- **File:** [`data/router_e4b_train_pool.json`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/data/router_e4b_train_pool.json)
- **Total Size:** **400 items**
- **Random Seed:** `42`
- **Cryptographic SHA-256 Hash:** `33e114331e3094e4e5e2462c51f95f5910f95048b21d81cfd8570476c07089c2`

---

## 1. Composition Breakdown

| Category | Sample Size ($n$) | Source Split | Notes |
|---|:---:|---|---|
| `atomic_math` | 100 | GSM8K `train` (`openai/gsm8k`) | Official public training split |
| `atomic_qa` | 100 | ARC-Challenge `train` (`allenai/ai2_arc`) | Official public training split |
| `atomic_code` | 100 | MBPP `sanitized` `train` (`google-research-datasets/mbpp`) | Official public training split |
| `compound_solvable` | 50 | Agent-Composed from GSM8K `train` | 25 two-stage + 25 three-stage items |
| `compound_tool_required` | 50 | Agent-Composed from GSM8K `train` | 25 two-stage + 25 three-stage items (Collatz, primes, knapsack, LCG, divisor search) |
| **Total Pool** | **400** | **100% Public Training Splits** | **SQL dropped; handled by v1.3 deterministic rule** |

---

## 2. Integrity & Zero Overlap Proof

All items were tested against all 400 evaluation instances across Dev Track A (100), Held-Out Track A (100), Reserve Quarantine (100), and Extended SQL Dev (100):
- **Normalized Question Collisions:** **0 / 400 (0.00%)**
- **Item ID Collisions:** **0 / 400 (0.00%)**
- **Sensitivity Verification:** **100% Passed** (all 100 compound items verified via `verify_sensitivity`).
- **Dynamic Gold Computation:** **100% Passed** (all 100 compound items executed via `execute_ref_code`).
