# Dataset Card — SLM Search Framework Clean Rebuild

Authoritative specification, provenance card, and split manifest for evaluation datasets.
Per Condition 13b.5 and Hard Rules 5/6, this card describes sources, licenses, split design, cryptographic integrity, and statistical power without containing query text, gold answers, or few-shot prompts.

---

## 1. Track A: Objective Evaluation Suite (Primary Track)

### 1.1 Task Composition & Canonical Provenance
Track A consists strictly of 100% downloaded benchmark items with preserved official IDs and reproducible download commands. Zero agent-written items are included in the atomic stratum.

| Task Domain | Benchmark Source | Upstream Split | License | Exact Download Command / API Source | Verification Checker |
|---|---|---|---|---|---|
| **Text-to-SQL** | Yale Spider (`taoyds/spider`) | `validation` (1,034 items, 791 verified) | CC BY-SA 4.0 | `python -c "from datasets import load_dataset; ds = load_dataset('xlangai/spider', split='validation')"` | Real SQLite execution against on-disk database & result row comparison |
| **Science QA & Reasoning** | AI2 ARC-Challenge (`allenai/ai2_arc`) | `validation` (299 items) | CC BY-SA 4.0 | `python -c "from datasets import load_dataset; ds = load_dataset('allenai/ai2_arc', 'ARC-Challenge', split='validation')"` | Deterministic multiple-choice option letter match |
| **Python Code Generation** | OpenAI HumanEval (`openai/human-eval`) | `test` (164 items total, 149 fresh) | MIT | `curl -L -o data/HumanEval.jsonl.gz https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz` | Sandboxed Python unit test execution |
| **Math & Multi-Step Reasoning** | OpenAI GSM8K (`openai/grade-school-math`) | `test` (1,319 items total, 1,304 fresh) | MIT | `curl -L -o data/gsm8k_test.jsonl https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl` | Exact numerical value match after `####` |

**Spider Database Mirror & Coverage Specification:**
- **Database Mirror Origin:** SQLite `.sqlite` database files are retrieved from third-party community mirror repository `lklimkiewicz/Spider-Raw` on Hugging Face (`data/spider_databases/`).
- **Domain Coverage:** The official Spider validation benchmark covers 20 distinct database domains. The third-party mirror provides complete SQLite files for **14 of the 20 databases** (`activity_1`, `orchestra`, `singer`, `pets_1`, `car_1`, `world_1`, `tvshow`, `network_1`, `poker_player`, `flight_2`, `course_teach`, `student_transcripts_tracking`, `museum_visit`, `wta_1`), covering 791 of 1,034 validation items (76.5% coverage).
- **Integrity Rule:** All Spider items in Track A (both atomic and compound parts) are drawn strictly from this verified 14-database pool where the SQLite database exists on disk, table schemas are confirmed, and the gold query executes successfully with non-empty results prior to split sampling.

### 1.2 Public Benchmark Pretraining Contamination Disclaimer
**Mandatory Methodological Disclosure:**
All public benchmarks utilized in Track A (Spider, AI2 ARC-Challenge, HumanEval, and GSM8K) have high likelihood of representation within the pretraining and instruction-tuning corpora of modern open-weight and proprietary baseline models (including Qwen, Llama, and GPT-family models). High raw accuracy on these tasks reflects in part pretraining memorization and benchmark familiarity. Track B (HyperGrid Synthetic Technical Specification) provides the strictly leak-free, zero-contamination evaluation track on private, unseen technical knowledge.

### 1.3 Spent Benchmark Items Quarantined (Permanently Excluded)
Per Hard Rule 5 and Phase 3 protocol, all 50 items used during Phase 1 & 2 infrastructure testing and candidate evaluation are permanently spent and quarantined in `data/spent_benchmark_items.json` (`SHA-256: bf362ea3e70404049dd2afe0d25470ef49244ada5a6a275ffd52c87ad5ea1d18`).
- **HumanEval Spent (15 items):** `HumanEval/32`, `50`, `65`, `78`, `83`, `93`, `107`, `115`, `126`, `128`, `129`, `130`, `137`, `140`, `145`.
- **GSM8K Spent (15 items):** `gsm8k_test_0025` through `gsm8k_test_0039`.
- **Agent-Written Benchmark Items Quarantined (20 items):** `spider_dev_complex_01` to `10`, `ARC_Challenge_MC_01` to `10`. None of these will ever enter dev, held-out, or reserve splits.

### 1.4 Stratification, Compound Tasks & Split Allocations
Track A is enlarged to **100 items per split**, partitioned deterministically with sampling seed `42` into:
1. **Atomic Stratum (60% / 60 items):**
   - 15 Spider SQL (verified on real SQLite databases on disk)
   - 15 ARC-Challenge QA
   - 15 HumanEval Python Code
   - 15 GSM8K Math Reasoning
2. **Compound / Composed Stratum (40% / 40 items):**
   - 14 SQL + Math, 14 Math + Code, 6 SQL + Code, 6 SQL + Math + Code (3-stage)
   - Solvability: 24 solvable without tools (60.0%), 16 tool-required (40.0%)
   - Every item carries and is verified by a self-contained Python reference program; table schemas embedded in SQL prompts.

| Split Name | File Path | Item Count | Compound Ratio | Cryptographic SHA-256 Hash | Status |
|---|---|---|---|---|---|
| **Track A Dev Split** | `data/track_a_dev_split.json` | 100 | 40.0% (40 items) | `e3e6ccccf3a856f318e60b249a016145653fc0cf5e191616df40ee184ae046de` | Complete for Dev progression |
| **Track A Held-Out Candidate** | `data/track_a_heldout_candidate.json` | 100 | 40.0% (40 items) | `0d959ce08b613d3dd3054cb6601807c50d415a3fabe1cfe31550b5a4388fcf31` | **CANDIDATE PENDING OWNER REVIEW BEFORE LOCK** |
| **Track A Reserve Quarantine** | `data/reserve_set_quarantine.json` | 100 | 40.0% (40 items) | `18d43de45b8b4ac43dcd9d3a0b227d0078c5e8c6cc466792d9f649d860262cce` | Untouched, quarantined reserve |

### 1.5 Overlap & Independence Verification
- $\text{len}(\text{Dev} \cap \text{Held-Out}) = 0$ (strictly zero item or part overlap).
- $\text{len}(\text{Dev} \cap \text{Reserve}) = 0$ (strictly zero item or part overlap).
- $\text{len}(\text{Held-Out} \cap \text{Reserve}) = 0$ (strictly zero item or part overlap).
- $\text{len}((\text{Dev} \cup \text{Held-Out} \cup \text{Reserve}) \cap \text{Spent}) = 0$ (strictly zero leakage of spent items).
- Verified by automated `audit_part_level_disjointness` in `src/audit/audit_rules.py`.

### 1.6 Statistical Power Analysis
- For $N = 100$ items per split, a two-sided 95% bootstrap confidence interval for an observed accuracy of $60\%$ ($p = 0.60$) has a margin of error of $\pm 9.6\%$ ($[50.4\%, 69.6\%]$).
- For head-to-head paired McNemar testing on $N = 100$ items, a true accuracy difference of $\ge 10\%$ (e.g. 70% vs 60%) achieves statistical power $\beta \approx 0.81$ at $\alpha = 0.05$.
- For compound stratum specific reporting ($N = 40$ items), 95% CI margin of error is $\pm 15.2\%$.

---

## 2. Track B: Private-Knowledge & Fact Checklist Suite (Secondary Track)

### 2.1 Private Corpus Specification (HyperGrid v4.2)
- **Domain:** *HyperGrid Autonomous Transit Network Specification v4.2* (synthetic high-speed vacuum maglev technical documentation).
- **Contamination Risk:** Strictly 0% (synthesized in-repo, zero crawl presence, never in pre-training data of any public model).
- **Corpus Size:** 50 structured markdown specification chapters in `data/track_b/corpus/doc_01.md` through `doc_50.md` (~26,500 words total across 8 subsystems).
- **Invented Fact Pool:** 160 invented facts in `data/track_b/master_fact_pool.json` (`SHA-256: 706d7e6817610669a50bfa0863ac7f6f70d562076ae39a3fbdead010ebe045ea`).
  - Zero real-world standards (all IEEE, AES, ASTM, MIL-STD references eliminated).
  - Dev (80 facts) and Held-Out (80 facts) pools are strictly disjoint in IDs, component tokens, and scalar values.
  - Every fact incorporates superseded v4.1 values and secondary/auxiliary distractor values.

### 2.2 Split Allocation & Multi-Hop Question Structure
- **Dev Split:** 50 multi-hop questions in `data/track_b/track_b_dev_split.json` (`SHA-256: 01fa3bc98933459a26662f271f037cfc9a15a016f6e07287a580f1d8593260ea`).
- **Held-Out Candidate Split:** 50 multi-hop questions in `data/track_b/track_b_heldout_candidate.json` (`SHA-256: b021e2d0032d15a20f24315fb4538fe59ecd3ecb323f9a8ca295c2b421d7ed6d`).
- **Constraints & Guardrails:**
  - Every question combines at least 2 distinct facts (bridging component properties, cross-subsystem calculations, or dual-parameter queries).
  - Maximum fact usage across questions: $\le 2$ usages per fact.
  - Zero citations of document IDs (`DOC-xx`) or section numbers in question prompts.
  - Maximum answer length cap: **75 words**. Verbose full-corpus dumping fails immediately.
- **Scoring Engine:** Automated Fact Checklist Scorer (`src/eval/fact_checklist_scorer.py`) evaluating exact token matches, numerical tolerances, required keys, and negative distractor rejection with zero LLM judge and zero API spend.

---

## 3. Mandatory Checkpoint Notice
Per Mandatory Owner Checkpoint 2 (`AGENTS.md`), held-out splits are NOT cryptographically locked and pipeline execution on held-out data is NOT started until explicit owner sign-off on this Dataset Card is granted.

