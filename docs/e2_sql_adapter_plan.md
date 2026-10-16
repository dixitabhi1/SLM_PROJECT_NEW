# Experiment 2 (E2): Kaggle SQL LoRA Adapter Fine-Tuning Plan

This document outlines the pre-registered execution plan for **Experiment 2 (Query-Dependent Fine-Tuning)** from the mentor protocol (`mentor_protocol_source.md`), targeting the SQL stratum.

---

## 1. Objective & Empirical Rationale

- **Mentor Protocol Mapping:** Experiment 2 prescribes query-dependent fine-tuning where specialized capability is injected into the SLM for the specific domain required by the query, rather than using a generic unspecialized model.
- **Empirical Motivation:** In the held-out head-to-head model comparison ([`docs/per_item_head_to_head_comparison.md`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/docs/per_item_head_to_head_comparison.md)), Spider SQL is the pipeline's primary deficit:
  - Base SLM pipeline: 46.7% (7/15)
  - 120B baseline: 86.7% (13/15) — **8 direct losses, 0 SLM wins**
  - 27B baseline: 86.7% (13/15) — **8 direct losses, 0 SLM wins**
- **Target:** Train a specialized QLoRA adapter for Phi-4-mini to raise SQLite schema understanding, complex JOIN resolution, and column selection without altering the base model weights.

---

## 2. Base Model Specification

Per Hard Rule 7, the base model is cryptographically pinned to the official Hugging Face snapshot:
- **Model ID:** `microsoft/Phi-4-mini-instruct`
- **Published Parameters:** 3.82B
- **Exact Pinned Hugging Face Snapshot:** `cfbefacb99257ffa30c83adab238a50856ac3083` (verified in [`.agents/knowledge/model_registry.md`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/.agents/knowledge/model_registry.md#L15))
- **Local GGUF Base:** `phi-4-mini-instruct-q4_k_m.gguf` (SHA-256: `78fad5d182a7c33065e153a5f8ba210754207ba9d91973f57dffa7f487363753`)

---

## 3. Training Data & Strict Non-Overlap Proof

### 3.1 Dataset Sources
- **Sources:** Official Yale Spider training sets:
  1. `train_spider.json` (~7,000 question-SQL pairs across 140 databases)
  2. `train_others.json` (~1,659 question-SQL pairs from Academic, GeoQuery, etc., across 6 databases)
- **Total Training Instances:** ~8,659 text-to-SQL pairs.

### 3.2 Cryptographic Database Disjointness
The Spider benchmark was explicitly constructed by Yu et al. (EMNLP 2018) with strict, database-level cross-domain separation: no database in the validation split appears in the training split.

All 12 SQL databases appearing across our Dev, Held-Out, and Reserve splits:
`['concert_singer', 'cre_Doc_Template_Mgt', 'dog_kennels', 'employee_hire_evaluation', 'flight_2', 'orchestra', 'pets_1', 'poker_player', 'student_transcripts_tracking', 'tvshow', 'world_1', 'wta_1']`

- **Split Provenance:** All 12 databases belong exclusively to the 20 databases of the official Spider validation split (`data/raw_official/spider_val.json`).
- **Disjointness Theorem:** Because the official Spider split defines:
  $$\text{Databases}(\text{Train}) \cap \text{Databases}(\text{Val}) = \emptyset$$
  none of the 12 evaluation databases appear in `train_spider.json` or `train_others.json`.
- **Pre-Training Verification Script:** Before any fine-tuning begins, an automated script will parse the database IDs from the downloaded training files and assert:
  $$\text{set}(\text{Train DBs}) \cap \text{set}(\text{Evaluation DBs}) == \emptyset$$
  Failing this assertion aborts execution immediately.

---

## 4. Training Environment & Configuration

Per Hard Rule 13, the training incurs strictly zero financial spend ($0.00) using free cloud compute:
- **Platform:** Kaggle Notebooks (Free Tier)
- **Hardware:** NVIDIA Tesla T4 or P100 GPU (16 GB dedicated VRAM)
- **Rationale for Kaggle:** Overcomes the 6 GB local laptop GPU VRAM ceiling documented in empirical benchmarks VL-032 and VL-040 (where sequence lengths $>256$ triggered CUDA OutOfMemoryError). The 16 GB VRAM allows full 1,024-token context length to accommodate multi-table schemas and complex join queries.

### 4.1 Hyperparameters
- **Method:** QLoRA (4-bit NormalFloat base quantization, 16-bit LoRA adapters)
- **LoRA Rank ($r$):** 16
- **LoRA Alpha ($\alpha$):** 32
- **LoRA Dropout:** 0.05
- **Target Modules:** All linear attention and MLP layers:
  `["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]`
- **Max Sequence Length:** 1,024 tokens
- **Optimizer:** `paged_adamw_8bit`
- **Learning Rate:** $2 \times 10^{-4}$ with cosine learning rate schedule
- **Batch Size:** 4 per device, 4 gradient accumulation steps (effective batch size: 16)
- **Warmup Ratio:** 0.03
- **Epochs:** 2 (approx. 1,080 optimization steps)

---

## 5. GGUF Conversion & Runtime LoRA Integration

1. **Export:** Export LoRA adapter weights (`adapter_model.safetensors` and `adapter_config.json`).
2. **Conversion:** Convert adapter to GGUF format using `convert_lora_to_gguf.py` from `llama.cpp`:
   ```bash
   python convert_lora_to_gguf.py --base-model-id microsoft/Phi-4-mini-instruct ./phi4_mini_sql_lora --outtype f16 --outfile phi4-mini-sql-lora.gguf
   ```
3. **Runtime Switching in `llama-server`:**
   - As demonstrated in benchmarks VL-034 and VL-037, `llama-server` switches LoRA adapters via `POST /lora-adapters` in **1.8 ms** with zero process reload.
   - When the Analyser classifies `task_asks_for_query(prompt) == True`, the pipeline request specifies the SQL specialist adapter `[{"id": 0, "scale": 1.0}]`.
   - All other tasks (QA, Math, Code, Compound Reasoning) execute with adapter scale `0.0` (pure base model).

---

## 6. Extended SQL Dev Set & Baseline Metrics

Per owner directive, an enlarged SQL dev set was constructed to ensure statistical power for Criterion 1:
- **File:** [`data/sql_dev_extended.json`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/sql_dev_extended.json)
- **Selection Script:** [`scripts/build_sql_dev_extended.py`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/scripts/build_sql_dev_extended.py)
- **Random Seed:** `42`
- **Item Count:** 100 items from `data/raw_official/spider_val.json`
- **Disjointness Constraint:** Strict rejection of any item present in Dev Track A (15 SQL items), Held-Out Track A (15 SQL items), or Reserve Track A (15 SQL items).
- **Cryptographic SHA-256 Hash:** `1af2bb2a2bc9702c9c2a944069678b4630ce22a73ce6281a7b10f5cb24a287a3`
- **Pipeline v1.2 Baseline Performance:**
  - Evaluated on all 100 items via [`scripts/eval_sql_dev_extended_v12.py`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/scripts/eval_sql_dev_extended_v12.py)
  - Raw records: [`results/phase4/sql_dev_extended_v12_records.jsonl`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/results/phase4/sql_dev_extended_v12_records.jsonl)
  - Baseline Accuracy: **66.00% (66/100)**
  - Mean Latency: **2.24s**
  - Provenance: 100% answered locally by `phi-4-mini` via `direct_sql`; 0 Groq calls.

---

## 7. Pre-Registered Success Criteria (Dev Split Only)

To prevent overfitting or post-hoc threshold adjustment, the following criteria are pre-registered:

1. **SQL Dev Accuracy Increase (Primary Criterion):**
   - Evaluated on the 100 items of [`data/sql_dev_extended.json`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/sql_dev_extended.json).
   - Paired bootstrap difference (E2 Adapter vs Pipeline v1.2 Base, $B=10{,}000$) 95% confidence interval lower bound must be strictly $> 0.0\text{ percentage points}$.
2. **Non-Regression on Non-SQL Categories (Safety Criterion):**
   - Across the 85 non-SQL Dev Track A items (ARC QA, GSM8K Math, HumanEval Code, Compound Solvable, Compound Tool-Required), overall accuracy must not drop by more than **$2.0\text{ percentage points}$** relative to v1.2.
3. **Strict Evaluation Boundary:**
   - Evaluated strictly on Dev splits (`data/sql_dev_extended.json` and `data/track_a_dev_split.json`).
   - **The reserve set remains cryptographically locked and completely untouched.**

---

## 8. Dev Compound Solvable Failure Analysis (Diagnostic)

Concurrently performed failure analysis on all 10 failed compound items solvable without tools from Dev Track A ($N=20$, 10 failed under v1.2):

| Failure Cause | Count | Share | Example Item IDs | Detailed Mechanism |
|---|---|---|---|---|
| **Subtask Answer Error (Knowledge or Reasoning)** | 7 | 70.0% | `compound_dev_v2_0011`<br>`compound_dev_v2_0013`<br>`compound_dev_v2_0016` | **0011**: Flight table filter error (included delay < 30 min flights, missed dist > 800 flight).<br>**0013**: LCG modular arithmetic error ($328 \pmod{128} = 32$ instead of $72$).<br>**0016**: Arithmetic cubing error ($185^3 = 6,336,625$, off by 5,000 from $6,331,625$). |
| **Wrong Colour or Route** | 2 | 20.0% | `compound_dev_v2_0017`<br>`compound_dev_v2_0034` | **0017**: Collatz sequence (106 steps) routed to `direct` instead of `CODE_EXEC`; hit 1,024-token context cutoff at step 50.<br>**0034**: Chinese Remainder Theorem brute-force search routed to `direct` instead of `CODE_EXEC`; enumerated $k=0\dots 33$ in text until truncated. |
| **Aggregation Error** | 1 | 10.0% | `compound_dev_v2_0031` | Decomposed into SQL + Reason. Intermediate revenue calculated correctly ($840), but downstream specialist rounded profit to `$227` instead of whole-dollar truncation `$226`. |
| **Decomposition Error** | 0 | 0.0% | — | Zero decomposition failures. |
| **Format or Scoring Issue** | 0 | 0.0% | — | Zero format/checker rejections. |

**Key Architectural Insight:** 70% of solvable compound failures stem from base SLM arithmetic and multi-constraint table filtering errors during pure textual reasoning. Routing simulation and search items to `CODE_EXEC` represents a secondary opportunity, but no pipeline changes are made prior to owner authorization.

---

## 9. Mandatory Owner Checkpoint

Per Section 3 of `AGENTS.md` (Checkpoints 3 & 6), work pauses after preparation. No fine-tuning execution will begin on Kaggle without explicit owner sign-off.

---

## 10. Note on Attribution & SQL Baseline Score

> [!NOTE]
> **Attribution Clarification:** Section 1 references an SLM SQL accuracy of 46.7% (7/15), which was measured on the **Dev** split under Pipeline v1.1. On the frozen v1.0 held-out split (`results/phase4/heldout_pipeline_records.jsonl`), the exact SLM SQL score was **3/15 (20.0%)** (and 11/15 under v1.3). The extended SQL dev set (`data/sql_dev_extended.json`, $N=100$) serves as the objective, pre-registered benchmark for Criterion 1.
