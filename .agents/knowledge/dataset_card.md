# Dataset Card — SLM Search Framework Rebuild

Specification and provenance card for evaluation datasets. Per Condition 13b.5, this card describes sources, licenses, split design, and statistical power without containing query text, gold answers, or answer keys.

---

## 1. Track A: Objective Evaluation Suite (Primary Track)

### 1.1 Task Composition & Provenance
Track A consists of objectively verifiable tasks requiring deterministic execution, symbolic mathematics, code verification, and structured data querying:

| Task Sub-type | Public Benchmark Source | License | Objective Verification Method |
|---|---|---|---|
| **Python Code Generation** | HumanEval / MBPP | MIT / CC-BY-4.0 | Hidden pytest assertions executed in isolated sandbox |
| **Maths & Symbolic Reasoning** | GSM8K / MATH | MIT | Exact numerical match & SymPy algebraic equivalence |
| **Text-to-SQL** | Spider / BIRD | CC BY-SA 4.0 | Exact execution result-set match against target SQLite DB |
| **Multi-Hop QA** | HotpotQA (distractor split) | CC BY-SA 4.0 | Normalized Exact Match & token F1 against gold answer |
| **Compound Tasks** | Custom chained pipelines (QA + SQL + Math) | Project Custom | Multi-stage pipeline verification check at every stage |

### 1.2 Split Allocation & Power Analysis
- **Dev Split:** 150 items stratified across all 5 task types.
- **Primary Held-Out Split:** 150 items stratified identically; locked by SHA-256 before any pipeline run.
- **Secondary Reserve Held-Out:** 100 items untouched reserve for final audit validation.
- **Statistical Power & Interval Width:**
  With $N = 100$ items, a 95% confidence interval for a proportion near $0.50$ has a margin of error of $\pm 9.8\%$. With $N = 150$, the margin of error narrows to $\pm 8.0\%$.

### 1.3 Contamination Mitigation
- Items sampled strictly from evaluation splits of public benchmarks where permissible.
- Compound tasks synthesized with freshly generated logic to eliminate memorized contamination.
- Full text of held-out items cryptographically sealed before any model run.

---

## 2. Track B: Private-Knowledge & Open-Ended Suite (Secondary Track)

### 2.1 Private Corpus Provenance
- An isolated, internally consistent synthetic technical documentation corpus describing a novel system (unseen by any web-crawled baseline model pre-training data) or owner-supplied documents.

### 2.2 Split Allocation
- **Dev Split:** 60 questions requiring multi-hop synthesis of the private corpus.
- **Held-Out Split:** 60 questions with identical structure; locked by SHA-256.

### 2.3 Verification & Scoring Hierarchy
1. Primary: Deterministic Fact Checklist matching (string, numerical, and regex ground-truth verification).
2. Secondary: LLM judge with dual-order presentation, calibrated against 30 human-annotated anchor pairs with mandatory $\ge 85\%$ agreement gate.
