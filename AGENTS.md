# AGENTS.md — Operational Rules, Protocol, and Checkpoints

All agents working on this project are bound by the rules in this document. No agent may bypass, relax, reinterpret, or invent exceptions to these requirements.

---

## 1. Hard Rules (Immutable — Violations Abort Work)

1. **No fabricated numbers:** Every single number in any report, table, or summary is produced by an automated script directly from immutable files on disk. Never type a metric by hand. Never hard-code a number in a report generator.
2. **Raw files are immutable:** Model outputs, judge outputs, and execution logs are append-only. Never edit, patch, reorder, or delete raw records. Corrections must be written to a dedicated `corrections.jsonl` with an explicit reason.
3. **Fail loudly:** Any empty generation, zero completion tokens, timeout, truncated answer (`finish_reason != stop`), or server error immediately aborts that item and marks it `FAILED`. A failed item is never scored, never imputed, and never counted as a loss or a win.
4. **Symmetric validity:** A head-to-head comparison counts only if BOTH sides produced a complete, valid answer. All exclusions must be explicitly reported with item IDs and reasons.
5. **No tuning on held-out:** Held-out datasets are cryptographically locked by SHA-256 before the first pipeline run. You never read, print, or inspect held-out items or outputs until the final frozen run. If held-out outputs are inspected for any reason, that set is spent and must be declared as spent.
6. **No benchmark leakage:** No query-specific prompts, keywords, regexes, reference files, or few-shot examples may contain or key on an evaluation item. No gold labels, difficulty tiers, or domain tags may be passed into the pipeline.
7. **Pinned models:** Every model must be recorded by exact identifier and revision. No floating `-latest` aliases. No mid-experiment swaps. A provider outage means stop and ask the owner, not substitute.
8. **Family separation:** Pool models, baseline models, and any judge must come from distinct, non-overlapping model families. A judge model is never also a baseline.
9. **Fair resources:** Any tool, sandbox, retrieval corpus, or sampling budget given to the small system must be provided to the baseline in a separate, reported condition (`B1`).
10. **Parameter accounting:** Report the exact sum of distinct weights loaded on the active execution path. Each individual model must be <= 8B parameters. State the active total alongside every baseline size.
11. **Plain language:** Strictly avoid hype words ("breakthrough", "proves", "definitively", "landslide"). Always report sample size $n$, the 95% bootstrap confidence interval, and what the result does not show.
12. **Gates are real:** A gate that fails immediately stops the work. You do not proceed anyway, lower the threshold, or redefine the metric.
13. **Zero cost:** Strictly zero monetary spend unless explicitly approved in advance by the owner.

---

## 2. Agent Read Order

Every agent entering this workspace MUST read documents in the following strict sequence:
1. `PROGRESS.md`: Current phase status, validity ledger of active findings, incident log.
2. `AGENTS.md`: This file — rules, stop conditions, and operating constraints.
3. `.agents/knowledge/00_index.md`: Index of truth, verification dates, and file hashes.
4. Specific task knowledge:
   - Inference / GPU setup: `.agents/knowledge/environment.md`
   - Model selection / IDs: `.agents/knowledge/model_registry.md`
   - Metrics calculation: `.agents/knowledge/metrics_definitions.md`
   - Datasets & splits: `.agents/knowledge/dataset_card.md`
   - Historical pitfalls: `.agents/knowledge/old_project_lessons.md`
5. Associated skill file under `.agents/skills/<name>/SKILL.md` (when earned).

---

## 3. Mandatory Owner Checkpoints (Always Stop & Wait)

You MUST pause and request explicit owner sign-off before proceeding past any of the following:
1. **Model & Architecture Selection:** Choice of 2–3 base SLMs for specialist pool, selection of concurrency configuration from parallelism benchmark (a, b, c, or d), multi-tier baselines roster, and judge.
2. **Dataset Lock:** Locking dev and held-out splits with SHA-256 hashes.
3. **Training & Distillation:** Any fine-tuning run (including the 20-step QLoRA dry run).
4. **Financial Spend:** Any action that incurs API or cloud costs (default: zero spend).
5. **Protocol or Metric Changes:** Any modification to thresholds, metrics, or test conditions (documented in `docs/protocol_change_proposal.md`).
6. **Held-Out Evaluation:** Unlocking and executing the frozen pipeline on held-out data.
7. **External Communication:** Anything to be shared with the mentor or outside parties.

---

## 4. Integrity Constraints for Instructions and Skills

- **Facts in Knowledge Only:** Knowledge files (`.agents/knowledge/`) record facts, sources, and dates. No procedures and no unverified claims.
- **Skills Must Be Earned:** Per condition 13c.3, a skill is written only after the procedure has been executed successfully at least twice via automated script. Unearned skills remain stubs.
- **Fail-Loud Enforcement:** Any script failure must trigger an immediate pause, logging to `PROGRESS.md`, and an audit check. Never silently patch data.
