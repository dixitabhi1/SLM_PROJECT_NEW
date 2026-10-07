# MASTER PROMPT — SLM Search Framework, Clean Rebuild

Paste this whole file as the first message to the coding agent.

**Owner settings (fixed):**

- Repository: `https://github.com/dixitabhi1/SLM_PROJECT_NEW` (currently holds only `README.md`; build everything here).
- Compute: laptop only — NVIDIA RTX 3050 Laptop GPU, 6 GB VRAM. No cloud GPU. Zero spend.
- Mentor protocol: **open to change.** The old protocol (open-ended queries, LLM-judged, E1 to E4) is a starting point, not a constraint. New task types, new scoring and new conditions may be tried.
- **Track A (section 5, objective scoring) is the primary track.** Track B (private-knowledge and open-ended) is the secondary track.
- Every departure from the old protocol is written up in `docs/protocol_change_proposal.md` (what changed, why, what the old protocol would have measured instead) for the owner to take to the mentor. Nothing is sent to the mentor by the agent.
- The fine-tuning comparisons E1, E2, E3, E4-A, E4-B are still run (section 6b), scored with the new primary metric.

---

## 1. Role and mission

You are the engineer on a clean rebuild of a research project. The previous project tried to show that a pipeline of small language models (each <= 8B parameters) can match large monolithic LLMs (20B to 120B). It failed under fair evaluation (0-3% win rate vs 120B) and most of its positive numbers were later voided as artifacts.

Your mission is to build a new system and a new evaluation in which a small-model system can win honestly, and to measure it so that every number survives an independent audit.

Work in a NEW repository. Do not copy code, prompts, datasets, results or reports from the old repository. You may read the old `PROGRESS.md` only as a list of mistakes to avoid.

## 2. Where the win must come from

A small model will not out-write a 120B model on closed-book open-ended essays scored by an LLM judge. Do not try. Since the protocol may change, move the contest to tasks where verified facts, running code and correct numbers decide the outcome. The win must come from these mechanisms, none of which the old project tested properly:

1. Objectively scored tasks (tests, exact answers, execution match).
2. Tools inside every specialist (code executor, symbolic maths, SQL engine, retriever).
3. Sample-and-verify: several candidates per subtask, selected by a verifier.
4. Private knowledge: a corpus the large model has never seen.
5. Cascade: small system first, large model only when verification fails.
6. Distillation on real verified solutions, not templated synthetic data.

## 3. Hard rules (never break; stop and report instead)

1. **No fabricated numbers.** Every number in any report is produced by a script from files on disk. Never type a metric by hand. Never hard-code a number in a report generator.
2. **Raw files are immutable.** Model outputs, judge outputs and logs are append-only. Never edit, patch, reorder or delete them. Corrections go in a separate `corrections.jsonl` with a reason.
3. **Fail loudly.** Any empty generation, zero completion tokens, timeout, truncated answer (`finish_reason != stop`) or server error aborts that item and marks it FAILED. A failed item is never scored, never imputed, never counted as a loss or a win.
4. **Symmetric validity.** A comparison counts only if BOTH sides produced a complete answer. Report how many pairs were excluded and why.
5. **No tuning on held-out.** Held-out data is locked by SHA-256 before the first pipeline run. You never read, print or inspect held-out items or outputs until the final run. If you look at held-out outputs for any reason, that set is spent; say so.
6. **No benchmark leakage.** No query-specific prompts, keywords, regexes, reference files or few-shot examples that contain or key on an evaluation item. No gold labels, tiers or domain tags passed into the pipeline.
7. **Pinned models.** Every model is recorded by exact ID and revision. No `-latest` aliases. No mid-experiment swaps. A provider outage means stop and ask, not substitute.
8. **Family separation.** Pool models, baseline models and any judge come from different model families. A judge is never also a baseline.
9. **Fair resources.** Any tool, retrieval corpus or sampling budget given to the small system is also given to the baseline in a separate, reported condition.
10. **Parameter accounting.** Report the sum of all distinct weights loaded on the active path. Each model <= 8B. State the total next to every baseline size.
11. **Plain language.** No "breakthrough", "proves", "definitively", "landslide". State n, the confidence interval, and what the result does not show.
12. **Gates are real.** A gate that fails stops the work. You do not proceed "anyway", lower the threshold, or redefine the metric.
13. **Zero cost** unless the owner approves spending.

## 4. Infrastructure to build

Build these first. No pipeline work until section 4 passes its tests.

- **Serving (6 GB laptop).** One inference server (Ollama or llama.cpp server), loaded-model and parallel-slot limits set explicitly to the owner-approved configuration from the parallelism benchmark below (never left at defaults), 4-bit quantised weights, full GPU offload verified before every batch (abort if layers fall back to CPU). Deterministic seeds logged. Per-call timeout 600 s. Health check before every batch and after every 10 items; on a server error, restart the server and resume, never continue with empty outputs.
- **Laptop discipline.** Long runs only on AC power with sleep disabled. Record GPU memory and temperature at batch start. Budget every run in advance: items x calls x seconds, and state the expected finish time. Order work so the model is swapped as rarely as possible (run all calls for one adapter, then the next).
- **Specialist pool: 2-3 base SLMs, each with switching adapters (owner decision).** The pool holds two or three different base models (each <= 8B), and each base carries several swappable LoRA adapters, one per specialist role. Propose candidate bases with evidence (public benchmark scores, licence, quantised size, measured VRAM) and stop for owner choice. A second or third base stays in the pool only if it beats the first base on at least one skill on dev; otherwise it is dropped and that is reported.
- **Parallel execution, proven not assumed.** Independent subtasks must run concurrently. 6 GB VRAM cannot hold two 7-8B models at once, so before building the pipeline, benchmark these configurations on 20 dev subtasks and record throughput, peak VRAM and GPU offload for each:
  - (a) two bases of <= 4B each, co-loaded, one request each in parallel;
  - (b) three bases of <= 3B each, co-loaded;
  - (c) one base at a time with parallel request slots (batched generation), swapping bases between waves of the DAG;
  - (d) fully serial, as a reference.
  Any configuration where layers spill to CPU or a model is evicted mid-batch is disqualified. Stop and show the owner the table; the owner picks. Report measured concurrency (mean subtasks in flight) in every run; never call execution "parallel" if the measured value is 1.0.
- **Adapter switching.** Measure adapter swap time and base swap time. Schedule each wave of the DAG to group subtasks by base, then by adapter, to minimise swaps. Log every swap.
- **Sandbox.** Containerised or temp-dir subprocess execution, UTF-8 forced, time and memory limits, no network. Local stand-ins for databases (SQLite, in-memory) so nothing is "unverified". Unit tests for hang, crash, encoding and pass cases.
- **Tools.** Python executor with test runner, SymPy, SQL engine, BM25 or small-embedding retriever over a pinned corpus. No LLM inside any tool.
- **Run records.** One JSONL row per call: item ID, condition, model ID, prompt hash, seed, full output, token counts, finish reason, latency, tool calls, verifier result, git commit. Resumable, deduplicated by a written rule.
- **Report generator.** One script builds every table from the JSONL files. A traceability test asserts each printed number equals a recomputed value.
- **Audit script.** Checks rules 2-8 automatically and exits non-zero on any violation. Run it before every report.

## 5. Evaluation sets

Build two tracks. Track A is primary: objective scoring, no judge. Track B is secondary and keeps a link to the old open-ended protocol. Given laptop speed, Track A may start at 100 dev and 100 held-out items and Track B at 40 and 40; say so in the dataset card and state the resulting interval widths.

**Track A — objective tasks (no judge).**
- Code generation with hidden unit tests.
- Maths word problems and symbolic problems with exact answers.
- Text-to-SQL scored by execution match.
- Multi-hop question answering over a pinned corpus, scored by exact match / F1 against gold.
- Compound tasks: two or three of the above chained, each stage objectively checkable.
- Source items from established public benchmarks where licences allow; write the compound items yourself with a checker for every stage.
- Size: at least 150 dev and 150 held-out, stratified by task type and number of domains. Reserve a second held-out set of 100 that nobody touches.

**Track B — private-knowledge and open-ended tasks.**
- Build a corpus the baselines cannot know (synthetic but internally consistent technical documentation, or owner-supplied documents). Write 60 dev and 60 held-out questions whose answers require it, each with a gold answer and required facts.
- Score by fact checklist (automatic string/number match) first. Use an LLM judge only for what cannot be checked, with: one pinned judge, both orders, 30 human-graded pairs to validate it (agreement >= 85% required), and sandbox evidence shown to the judge.

Write the dataset card: sources, licences, hashes, known contamination risks.

## 6. Conditions to run (the ladder)

Every condition runs on the same items. Add one mechanism at a time.

| ID | System | Purpose |
|---|---|---|
| C0 | Single base SLM, one greedy answer | Floor |
| C1 | C0 + tools | Value of tools |
| C2 | C1 + sample-and-verify (N candidates, verifier picks) | Value of test-time compute |
| C3 | C2 + decomposition and specialist adapters | Value of the pipeline itself |
| C4 | C3 + distilled adapters | Value of fine-tuning |
| C5 | Cascade: C3/C4 first, baseline LLM on verifier failure | Quality at a fraction of LLM calls |
| B0 | Baseline LLM, one answer, no tools | Reference |
| B1 | Baseline LLM + the same tools and corpus | Fair reference |

Baselines (owner decision): a three-tier ladder of open-weight models with published parameter counts.

- **Tier 1, about 32B** — primary comparison.
- **Tier 2, about 50B** — include only if a real open-weight model of that size with a free endpoint exists; if none does, say so plainly and skip the tier. Do not relabel a model of unknown size to fill it.
- **Tier 3, about 70B** — upper comparison.
- A 120B model is optional, as a ceiling reference only.

Rules for the ladder:
- Exact IDs proposed by you with evidence and approved by the owner. Only state a parameter count that the model's publisher has published; closed models with unpublished sizes cannot fill a tier.
- Before proposing, verify each candidate has a free endpoint that can complete the full dev and held-out sets within its quota. Baseline answers are generated once, checked complete, hashed and cached, so a one-time quota is enough.
- If a tier's endpoint becomes unavailable mid-project, stop and ask; never substitute another model under the same tier label.
- Each tier is reported separately, in both B0 (no tools) and B1 (same tools and corpus) form. Never pool tiers into one win rate.

A mechanism stays in the system only if it beats the previous rung on dev with a paired confidence interval that excludes zero.

Laptop budget for C2: start with N = 3 candidates per subtask; raise to 5 only if the dev gain justifies the time.

### 6b. Mentor protocol experiments

Run the mentor's fine-tuning experiments on the best frozen architecture from the ladder, on Track A (primary metric: task accuracy) and on Track B, against every baseline tier. You may propose additional or replacement experiments (for example cascade, sample-and-verify budget, private-knowledge) in `docs/protocol_change_proposal.md`; run them on dev, and stop for owner approval before they enter the held-out plan.

| Exp | Specialists | Skill-matching / router SLM | Baseline |
|---|---|---|---|
| E1 | No fine-tuning | Not fine-tuned | Not fine-tuned |
| E2 | Query-dependent fine-tuning (only the specialist the query needs) | Not fine-tuned | Not fine-tuned |
| E3 | All specialists fine-tuned | Not fine-tuned | Not fine-tuned (fine-tuned only if feasible) |
| E4-A | As E1-E3 | Fine-tuned | Corresponding baseline |
| E4-B | All fine-tuned | Fine-tuned | Fine-tuned baseline if feasible, else not fine-tuned and stated |

Rules for these experiments:
- Change exactly one thing between adjacent experiments. E3 to E4-A changes only the router.
- Same items, same seeds, same judge, same baseline answers across all five.
- Report each experiment with and without tools (C0-style vs C3-style) so the mentor sees both the plain number and the tool-assisted number.
- Protocol changes are decided on dev evidence only and fixed before the freeze. No protocol change after held-out results are seen.
- Report matched differences (E2-E1, E3-E2, E4A-E3, E4B-E4A) with paired intervals over items.

## 7. Pipeline architecture (C3 onward)

Flow (owner-specified):

```
Query
  → Decomposer
  → Task Analyser
  → Task Colorer ──(subtask has multiple colours/domains)──┐
        │                                                  │
        │            back to Decomposer for that subtask ◄─┘   (max 3 levels)
        ▼
  → Matching SLM (assigns each atomic subtask to a base SLM + adapter)
  → Specialist pool: 2-3 base SLMs with switching adapters, independent subtasks in parallel
  → Aggregator
  → Final answer
```

After 3 levels, a subtask that is still multi-colour is sent to the best-matching specialist as it is, and the event is logged as "depth limit reached".

The pipeline has seven named stages. All seven are mandatory and each must be a real, separately logged component. In the old project several of these existed only as keyword rules or were never implemented; that is not acceptable here.

| # | Stage | Input → output | Must be | Measured on dev against gold |
|---|---|---|---|---|
| 1 | **Decomposer** | Query → DAG of subtasks with dependencies, expected output type and a check per subtask | A model call (base model or adapter, <= 3B effective if a separate small model is used). Never receives gold tiers, domain labels or subtask counts | Subtask count accuracy, dependency (edge) accuracy, graph edit distance |
| 2 | **Task Analyser** | Each subtask → skill vector (skills required, difficulty, tool needed, output type) | A model call producing a fixed-schema vector over the documented skill taxonomy, not a keyword rule | Per-dimension accuracy of the skill vector |
| 3 | **Task Colorer** | Each subtask + skill vector → one domain colour, or a multi-colour flag | A model call or a classifier over the skill vector. A subtask with more than one colour is not atomic | Colour accuracy; precision and recall of the multi-colour flag |
| 4 | **Matching SLM (skill matcher / router)** | Subtask skill vector + specialist skill cards → assigned specialist and a match score | A model call that scores every specialist. Specialist skill cards live in `src/`, one per adapter, written from that adapter's measured dev accuracy per skill | Routing accuracy vs gold assignment; accuracy vs an oracle router |
| 5 | **Feedback loop** | Triggers → re-decomposition of the offending subtask only | Implemented and exercised. Triggers: multi-colour subtask, match score below threshold, verifier FAIL after retries. Hierarchical subtask IDs. Max depth 3, guaranteed termination, every loop event logged with its trigger | Trigger rate, share of loops that fix the problem, termination rate (must be 100%) |
| 6 | **Specialist execution** | Subtask + verified upstream outputs → answer + verifier verdict | Pool of 2-3 base SLMs, each with switching adapters, + tool + sample-and-verify (C2 mechanism). Independent subtasks run in parallel in the owner-approved configuration; dependent ones run in DAG order | Per-skill accuracy, verifier pass rate, repair success rate |
| 7 | **Aggregator** | Verified subtask outputs → final answer in the required format | A model call. Test one-stage and two-stage (per-branch merge, then final synthesis) on dev and keep the one with higher task accuracy, not higher text retention. Must not alter verified code, numbers or citations; check this mechanically | End-to-end accuracy vs an oracle that returns the correct subtask outputs; rate of verified content altered (must be 0) |

Rules for the stages:

- **Gold annotations.** Build gold DAGs, skill vectors, colours and assignments for the dev set only, written before the pipeline is run, stored outside `.agents/` and never passed to the pipeline.
- **Stage ablations.** For each of stages 1-5 and 7, report dev accuracy with the stage replaced by (a) a trivial version (no decomposition, single specialist, keyword rule, plain concatenation) and (b) the gold/oracle version. This shows what each stage adds and how much its errors cost.
- **Fallbacks are visible.** If any stage falls back to a rule or default, log it as a fallback and report the fallback rate. A stage that falls back on more than 10% of dev items is treated as not working.
- **Fine-tuning targets.** The Matching SLM is the "skill-matching SLM" of experiments E4-A and E4-B. Fine-tune it alone when moving from E3 to E4-A; do not change the decomposer or aggregator in the same step.
- **Laptop cost.** Stages 1-4 and 7 should run on one of the pool's bases (different prompts or adapters) so that orchestration does not force extra model loads. Report orchestration time, specialist time, swap time and measured concurrency separately.
- **Parameter accounting.** The footprint is the sum of all distinct base weights in the pool (adapters add their own small counts). State it next to every baseline tier.
- **Pool ablation.** On dev, compare the 2-3 base pool against the single best base with the same adapters and the same sampling budget. This shows whether mixing bases helps.

### General constraints

- Decomposer outputs a typed plan: subtasks, dependencies, required tool, expected output type and a check for each subtask.
- Dependent subtasks receive verified upstream outputs, not raw text.
- Every subtask ends in a verifier verdict: PASS, FAIL or NO_CHECK. Failed subtasks are retried with the error, then resampled, then escalated (C5) or reported as failed.
- The final answer is assembled from verified parts. State which parts passed verification.
- Log time per stage. A stage with 0.0 s latency that is supposed to call a model is a bug; stop.
- Measure each component against gold on dev: plan accuracy, routing accuracy, verifier precision and recall, repair success rate.

## 8. Distillation (C4)

- Training data: real verified solutions only (public training splits, or baseline outputs that passed the checker). At least 2,000 examples per adapter. Zero overlap with dev or held-out, verified by hash and near-duplicate check.
- Hold out 10% for validation. Report validation task accuracy, not token accuracy or training loss.
- An adapter ships only if it beats the base model on dev task accuracy.
- 6 GB limit: before any training, run a 20-step dry run and report peak VRAM and time per step. If the 7-8B base does not fit with 4-bit QLoRA at a usable sequence length, stop and offer the owner the choice of a smaller base (3-4B) for the fine-tuned roles. Never train while an inference server is loaded.

## 9. Statistics

- The unit of analysis is the item, not the trial.
- Report accuracy per condition with 95% bootstrap intervals over items, and paired differences between adjacent rungs.
- For C5 report quality against the fraction of items escalated, as a curve.
- For judged items report win / draw / loss per item (both orders must agree, else draw), judge-human agreement, and swap consistency.
- Report latency and tokens per item for every condition, on stated hardware.
- State the pre-registered success criteria before the held-out run and do not change them.

## 10. Phases and gates

1. **Setup.** Repo, environment check, provider check, model candidates. STOP for owner choice of base model, baselines and judge.
2. **Infrastructure.** Section 4 built, all tests pass, one-item smoke run for C0 and B0.
3. **Datasets.** Section 5 built, dev released, held-out hashed and locked. STOP for owner review of the dataset card.
4. **Baselines.** B0 and B1 on dev, all answers complete, cached and hashed.
5. **Ladder on dev.** C0 to C3, one rung at a time, audit after each. STOP and report after C3.
6. **Distillation.** C4. STOP for owner approval before any training run.
7. **Cascade.** C5 on dev.
8. **Freeze.** Tag the commit, write the success criteria. STOP for owner approval.
9. **Held-out.** One run of every condition, audit, report. No reruns except infrastructure failures, logged as such, with identical frozen code.

## 11. Owner checkpoints (always stop)

Model, baseline or judge choice; dataset lock; any training; any spending; any change to a rule, metric or threshold; the held-out run; anything sent to the mentor.

## 12. Progress file

Keep `PROGRESS.md` short and current:
- A status table of phases.
- A **validity ledger**: every headline number, its source file, and its status (stands / void / superseded).
- An incident log.

Never leave two rows that contradict each other. Mark old entries superseded instead of appending a new version beside them.

## 13. Skill and knowledge files

The agent's own instruction files are part of the experiment and are held to the same standard as code. Create them in the first session, before any other work.

### 13a. Layout

```
AGENTS.md                      # hard rules (section 3), read order, checkpoints
PROGRESS.md                    # status, validity ledger, incidents
.agents/knowledge/             # facts: what is true
  00_index.md
  mentor_protocol_source.md    # verbatim, owner-supplied
  master_prompt.md             # this file, verbatim
  environment.md               # hardware, OS, drivers, server settings
  model_registry.md            # every model: exact ID, revision, size, family, role
  dataset_card.md              # sources, licences, hashes, splits
  metrics_definitions.md       # every metric: formula, unit, script that computes it
  old_project_lessons.md       # mistakes to avoid, no numbers reused as results
.agents/skills/<name>/SKILL.md # procedures: how to do a thing
```

Required skills: `session-start`, `session-end`, `laptop-gpu-ops`, `run-generation-batch`, `run-baselines`, `run-judge`, `audit-results`, `build-report`, `lock-dataset`, `train-adapter`, `incident-response`.

### 13b. Conditions for knowledge files

1. **Facts only.** A knowledge file states what is true. It contains no procedures (those are skills) and no result numbers (those live in result files and the validity ledger).
2. **Sourced and dated.** Every entry carries its source (file path, URL, command output, or "owner, date") and the date it was verified. An entry with no source is deleted.
3. **Verbatim sources are frozen.** `mentor_protocol_source.md` and `master_prompt.md` are copied exactly and never edited, summarised in place or "clarified". Record their SHA-256 in `00_index.md`. Interpretations go in a separate file that cites the source line.
4. **Verified, not remembered.** Model sizes, IDs, API limits and hardware facts are written only after checking them (model card, API response, command output). Never write a parameter count the publisher has not published.
5. **No evaluation content.** No dev or held-out query text, gold answers, answer keys, domain labels or per-query notes may appear in any knowledge file.
6. **Owner-gated files.** Changes to `metrics_definitions.md`, `model_registry.md` (baselines and judge), and anything describing the mentor protocol need owner approval and a changelog line.
7. **One fact, one place.** No duplicated facts across files. If two files disagree, stop and resolve before any run.
8. **Stale facts are replaced, not appended.** Mark the old entry superseded with a date; do not leave two live versions.
9. **Short.** Each file under 200 lines. `00_index.md` lists every file with a one-line description and its hash.

### 13c. Conditions for skill files

1. **Fixed structure.** Front matter with `name` and `description` (when to use it), then: Preconditions, Steps, Verification, Failure handling, Outputs, Changelog.
2. **One procedure per skill.** A skill does one job and is under 150 lines. Long detail goes in a script the skill calls.
3. **Earned, not invented.** A skill is written only after the procedure has been carried out successfully at least twice by script. A skill describes what the scripts do; it never describes something that has not been run.
4. **Verification is mandatory.** Every skill ends with a concrete check (a command and its expected output). A skill with no check is not a skill.
5. **Fail-loud steps.** Every skill that produces data includes the stop conditions from hard rule 3 and says exactly what to do on failure (stop, log incident, do not patch files by hand).
6. **Generic only.** No query IDs, query-specific hints, keyword lists tied to evaluation items, expected answers, or "this query needs X" notes. A skill must work unchanged on a dataset it has never seen.
7. **Cannot weaken rules.** A skill may add checks to the hard rules, never relax, reinterpret or add exceptions to them. If a skill and `AGENTS.md` disagree, `AGENTS.md` wins and the skill is fixed.
8. **No thresholds or targets.** Success criteria, gates and metric definitions live in knowledge files under owner control, not in skills.
9. **Frozen during measurement.** Between the freeze (phase 8) and the end of the held-out run, no skill or knowledge file may change. Record the commit hash of `.agents/` in every run config.
10. **Changes are logged.** Every edit adds a dated changelog line with the reason. A change made because of something seen in held-out outputs is forbidden; one made because of dev outputs must say so.
11. **Pipeline prompts are not skills.** Prompts used by the small models at inference time live in `src/` under version control and are subject to hard rule 6. Never move pipeline behaviour into a skill or knowledge file to avoid that rule.

### 13d. Audit of these files

The audit script (section 4) also checks: required files exist, front matter and sections are present, verbatim hashes match, no evaluation item text or ID appears anywhere under `.agents/`, no file changed after the freeze commit. A failure blocks any run.

## 14. First session

1. Read this file fully and restate the hard rules in your own words.
2. Create `AGENTS.md`, `PROGRESS.md` and the knowledge files in section 13a. Ask the owner for the verbatim mentor protocol document. Do not write any skill yet (condition 13c.3); create the skill folders with a one-line stub stating the skill is not yet earned.
3. Run the environment and provider checks and record them in `environment.md`.
4. Propose base-model, baseline and judge candidates with evidence, sized for a 6 GB GPU.
5. Commit, push, stop and wait for the owner.
