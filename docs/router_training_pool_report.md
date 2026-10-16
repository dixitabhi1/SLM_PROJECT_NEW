# Router Training Pool Report (Experiment 4 / CoLabTEL Thrust 1)

- **Date:** 2026-10-16 17:29:27 UTC
- **Seed:** `42`
- **Output File:** [`data/router_train_pool.json`](file:///C:/Users/ACER/OneDrive/Desktop/Desktop 1/SLM_PROJECT_NEW/data/router_train_pool.json)
- **Cryptographic SHA-256 Hash:** `3fe3e5213fcdb7a484e31b3b9f64c544672251b5240d524fd35e5c3abec21a0f`
- **Total Instances:** 500

## 1. Category Composition

| Category | Stratum | Source Split | Count | Checker Type |
|---|---|---|:---:|---|
| `atomic_sql` | atomic | official Spider train | 100 | tolerant SQLite execution |
| `atomic_math` | atomic | official GSM8K train | 100 | exact numeric match |
| `atomic_qa` | atomic | official ARC-Challenge train | 100 | multiple choice exact key |
| `atomic_code` | atomic | official MBPP sanitized train | 100 | Python test harness execution |
| `compound_solvable` | composed | agent-composed (training domain) | 50 | exact match via reference code |
| `compound_tool_required` | composed | agent-composed (training domain) | 50 | exact match via reference code |
| **Total Pool** | — | **100% public training splits** | **500** | — |

## 2. Cryptographic Non-Overlap Proof

Every candidate question was lowercased, punctuation-stripped, and whitespace-collapsed. The normalized text and item IDs were tested against all 400 evaluation instances:
- Dev Track A ($N=100$)
- Held-Out Track A ($N=100$)
- Reserve Track A Quarantine ($N=100$)
- Extended SQL Dev Set ($N=100$)

**Audit Results:**
- Normalized question overlap: **0 / 500 (0.00%)**
- Item ID collision: **0 / 500 (0.00%)**
- Database collision (Spider train vs validation databases): **0 / 100 (0.00%)**
