# Metrics Definitions & Statistical Standards

All metrics are computed exclusively by automated evaluation scripts from append-only raw JSONL files.

---

## 1. Track A Primary Metrics (Objective Scoring — No LLM Judge)

### 1.1 Task Accuracy ($Acc$)
- **Formula:**
  $$Acc = \frac{1}{N_{\text{valid}}} \sum_{i=1}^{N_{\text{valid}}} \mathbb{I}(\text{verdict}_i = \text{PASS})$$
  where $\text{verdict}_i = \text{PASS}$ requires:
  - Code generation: All hidden unit tests pass in isolated sandbox without exception.
  - Math / Symbolic: Exact numeric or SymPy symbolic equivalence with gold answer.
  - Text-to-SQL: Result set of generated query exactly matches gold query execution against target SQLite DB.
  - Compound tasks: Every chained sub-stage passes its verification check.
- **Unit:** Percentage ($0.0\%$ to $100.0\%$) or proportion $[0.0, 1.0]$.
- **Script:** `src/eval/compute_metrics.py` (to be implemented in Phase 2).

### 1.2 Multi-Hop QA Exact Match (EM) & Token F1
- **Formula:**
  $$\text{EM} = \frac{1}{N} \sum_{i=1}^N \mathbb{I}(\text{normalize}(\hat{y}_i) == \text{normalize}(y_i^*))$$
  $$\text{F1} = \frac{2 \cdot P \cdot R}{P + R}$$
- **Unit:** Proportion $[0.0, 1.0]$.
- **Script:** `src/eval/compute_metrics.py`.

### 1.3 Symmetric Validity & Exclusion Rate
- **Rule:** A comparison pair $(i, \text{System}_A, \text{System}_B)$ is valid if and only if both systems produced complete outputs (`finish_reason == 'stop'`).
- **Exclusion Rate:**
  $$ExclRate = \frac{N_{\text{total}} - N_{\text{valid}}}{N_{\text{total}}}$$
- **Reporting:** Every comparative report must declare $N_{\text{total}}$, $N_{\text{valid}}$, and the breakdown of exclusion reasons.

### 1.4 Paired Difference ($\Delta$) & 95% Bootstrap Confidence Interval
- **Unit of Analysis:** The item ($i \in [1, N]$), never the trial.
- **Paired Difference:**
  $$\Delta_{A-B} = \frac{1}{N_{\text{valid}}} \sum_{i=1}^{N_{\text{valid}}} (\text{score}_{A, i} - \text{score}_{B, i})$$
- **Confidence Interval:** Non-parametric bootstrap with $B = 10,000$ resamples over items, reporting the 2.5th and 97.5th percentiles: $[CI_{2.5\%}, CI_{97.5\%}]$.
- **Decision Rule (Rung Retention):** A mechanism in C1–C4 remains in the pipeline only if $\Delta$ on dev has $CI_{2.5\%} > 0$.

---

## 2. Track B Secondary Metrics (Private Knowledge & Open-Ended)

### 2.1 Fact Checklist Match Rate
- **Formula:** Fraction of gold checklist facts detected via deterministic regex/substring match in generated output.
- **Unit:** Proportion $[0.0, 1.0]$.

### 2.2 Dual-Order Pairwise Win Rate (Judge)
- **Rule:** Item evaluated twice with flipped presentation order: $(A, B)$ and $(B, A)$.
- **Win:** System A wins if and only if the judge selects System A in BOTH presentations.
- **Draw:** System A and B draw if the judge reports a tie OR if the judge flips preference across presentations (swap inconsistency).
- **Swap Consistency:** Fraction of items where relative order is consistent:
  $$\text{SwapAgreement} = \frac{1}{N} \sum_{i=1}^N \mathbb{I}(\text{pref}_{A,B} == \text{reverse}(\text{pref}_{B,A}))$$

### 2.3 Judge-Human Agreement
- **Metric:** Percentage agreement and Cohen’s Kappa ($\kappa$) on 30 human-annotated anchor pairs.
- **Gate:** Minimum $85\%$ agreement required before accepting any LLM judge run.

---

## 3. Operational & Efficiency Metrics

### 3.1 Active Parameter Footprint
- **Definition:** Total distinct model weights in active VRAM at any stage of the execution path.
- **Constraint:** Each individual model $\le 8\text{B}$ parameters.

### 3.2 Latency per Item
- **Unit:** Wall-clock seconds ($\text{s}$). Measured from initial request ingestion to final output delivery. Zero-second stages are treated as bugs.

### 3.3 Token Usage
- **Unit:** Prompt tokens and completion tokens logged per call and aggregated per item.
