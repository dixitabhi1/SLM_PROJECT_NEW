# Lessons and Mistakes from the Prior Project

All items in this document are derived from the prior project history (`dixitabhi1/SLM_PROJECT/PROGRESS.md`) and the master audit findings. They serve as an explicit catalog of failure modes to prevent recurrence.

---

## 1. Catalog of Pitfalls & Root Causes

| Failure Mode in Prior Project | Root Cause | Clean Rebuild Prevention Rule |
|---|---|---|
| **High claimed win rates (57.1%) collapsed to 0–3% under fair audit** | Win rates were artifacts of small sample sizes ($n=7$ queries), LLM judge subjectivity, and prompt phrasing rather than genuine model superiority. | **Hard Rule 1, 11 & Section 2:** Primary evaluation moved to Track A (objectively scored: unit tests, exact symbolic match, execution match). No LLM judge on primary track. |
| **LLM Judge Inconsistency & Bias** | Position-swap agreement was only 68.6% (over 31% of judgments flipped when order was swapped). The judge favored longer, verbosely formatted outputs. | **Hard Rule 8 & Track B Rule:** Dual-order consistency required (both orders must agree, else recorded as DRAW); 30 human-validated calibration pairs (agreement $\ge 85\%$ required); sandbox execution evidence provided to judge. |
| **Aggregator Truncation & Information Loss** | Multi-stage pipeline aggregator compressed or truncated specialist outputs, omitting crucial code snippets and mathematical steps. | **Section 7:** Decomposer outputs typed plans; downstream stages receive verified upstream outputs rather than lossy summaries; final answer assembly verifies component integrity. |
| **Testing on Subjective Open-Ended Prose** | Pitting an SLM ($\le 8\text{B}$) against 70B–120B models on open-domain essay writing where param count dominates memory and fluency. | **Section 2:** Move contest to tasks where tool use, deterministic code execution, symbolic solvers, and private retrieval govern the outcome. |
| **Unrecorded Hardware CPU Fallback & Latency Spikes** | Inference runs intermittently spilled layers to system RAM / CPU, causing 400s+ latencies without raising exceptions. | **Section 4 & `environment.md`:** Pre-batch verification of 100% GPU VRAM offload. Abort if any layer falls back to CPU. |
| **Silent Failures and Incomplete Records** | Timeouts, server dropouts, or empty tokens were sometimes ignored or inconsistently dropped without accounting for exclusion rates. | **Hard Rule 3 & 4 (Fail Loudly & Symmetric Validity):** Non-zero exit on truncation/error; items marked `FAILED` are never scored or imputed; exclusions reported with reasons. |
| **Contamination & Tuning on Test Sets** | Evaluation queries were inspected during prompt debugging, inadvertently tuning the pipeline to specific evaluation instances. | **Hard Rule 5 & 6:** Cryptographic SHA-256 locking of held-out sets before first run. Zero inspection of held-out data until final frozen audit. |
| **Hand-Edited Tables & Unverified Aggregations** | Intermediate summary tables were manually compiled or altered across iterations. | **Hard Rule 1:** Zero manual entry. Automated end-to-end report scripts compute every metric directly from raw append-only JSONL files. Traceability test asserts exact match. |
