# Phase 3 Owner Review & Sign-Off Checkpoint: Complete Dataset Card & Splits

**Date:** 2026-10-08  
**Author:** Antigravity Autonomous Coding Agent  
**Status:** **READY FOR OWNER HELD-OUT LOCK REVIEW**  
**Governing Documents:** [AGENTS.md](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/AGENTS.md), [.agents/knowledge/dataset_card.md](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/.agents/knowledge/dataset_card.md)

---

## 1. Executive Summary & Verification of Owner Directives

All Phase 3 requirements have been generated, validated, and audited:
1. **Official Downloads & Provenance:** 100% of atomic items in Track A originate from official Hugging Face / benchmark downloads with verified IDs (`spider_val_xxxx`, `Mercury_xxxx`, `HumanEval/xx`, `gsm8k_test_xxxx`). Zero agent-written items exist in any evaluation split.
2. **Quarantine of Spent Benchmarks:** All 50 previous subtasks and 10 newly evaluated compound calibration items are locked as spent in [`data/spent_benchmark_items.json`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/spent_benchmark_items.json).
3. **Serving Chat Template Audit:** `llama-server.exe` queries confirm the embedded GGUF Jinja template is a 100% byte-for-byte match to `microsoft/Phi-4-mini-instruct`'s official `tokenizer_config.json`. No fallback is used.
4. **Track A Stratification:** Enlarged to **100 items per split** across Dev, Held-Out Candidate, and Reserve Quarantine, each with exactly **40.0% compound stratum** (34 2-stage, 6 3-stage tasks). Every item carries a self-contained reference Python program; table schemas are embedded in all SQL tasks; $\ge 60\%$ are solvable without tools.
5. **Track B Private Knowledge:** Built around the *HyperGrid Autonomous Transit Network Specification v4.2*. Contains 50 corpus documents (~26,500 words) and a master pool of **160 invented facts** (80 Dev, 80 Held-Out). Zero real-world standards (IEEE, AES, ASTM, MIL-STD eliminated). Dev and Held-Out fact sets are strictly disjoint. Questions are multi-hop, contain plausible distractors, cite zero document or section IDs, and are scored by a deterministic checklist with a **75-word maximum length cap**.
6. **Integrity & Audits:** Automated audit suite ([`src/audit/audit_rules.py`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/src/audit/audit_rules.py)) passes with 0 violations (`AUDIT PASSED`). All 21 unit tests in `tests/` pass in 3.78s.

---

## 2. Track A: Objective Splits & Stratification

### 2.1 Split Inventory & Cryptographic Hashes

| Split Name | File Path | Total Items | Atomic (60%) | Composed (40%) | Solvable w/o Tools | Tool-Required | Cryptographic SHA-256 Hash | Status |
|---|---|:---:|:---:|:---:|:---:|:---:|---|---|
| **Track A Dev Split** | [`data/track_a_dev_split.json`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/track_a_dev_split.json) | 100 | 60 | 40 | 24 (60.0%) | 16 (40.0%) | `E3E6CCCCF3A856F318E60B249A016145653FC0CF5E191616DF40EE184AE046DE` | Active for Dev Ladder |
| **Track A Held-Out Candidate** | [`data/track_a_heldout_candidate.json`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/track_a_heldout_candidate.json) | 100 | 60 | 40 | 25 (62.5%) | 15 (37.5%) | `0D959CE08B613D3DD3054CB6601807C50D415A3FABE1CFE31550B5A4388FCF31` | **Candidate (Pending Owner Lock)** |
| **Track A Reserve Quarantine** | [`data/reserve_set_quarantine.json`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/reserve_set_quarantine.json) | 100 | 60 | 40 | 25 (62.5%) | 15 (37.5%) | `18D43DE45B8B4AC43DCD9D3A0B227D0078C5E8C6CC466792D9F649D860262CCE` | Untouched Reserve |

### 2.2 Stratum Composition per Split
Each 100-item split is composed of:
* **Atomic Stratum (60 items):**
  * 15 Spider SQL queries (verified against SQLite databases on disk)
  * 15 ARC-Challenge Multiple Choice science questions
  * 15 HumanEval Python code implementation tasks
  * 15 GSM8K Multi-step math reasoning problems
* **Compound Stratum (40 items):**
  * 14 SQL + Math tasks
  * 14 Math + Code tasks
  * 6 SQL + Code tasks
  * 6 SQL + Math + Code 3-stage tasks

### 2.3 Overlap & Disjointness Ledger
* $\text{len}(\text{Dev} \cap \text{Held-Out}) = 0$
* $\text{len}(\text{Dev} \cap \text{Reserve}) = 0$
* $\text{len}(\text{Held-Out} \cap \text{Reserve}) = 0$
* $\text{len}((\text{Dev} \cup \text{Held-Out} \cup \text{Reserve}) \cap \text{Spent}) = 0$
* Verified at the part level by `audit_part_level_disjointness` in `src/audit/audit_rules.py`.

---

## 3. Track B: Private Knowledge Corpus & Evaluation Splits

### 3.1 Corpus & Master Fact Pool
* **Corpus Documentation:** 50 chapters in [`data/track_b/corpus/`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/track_b/corpus/) (`doc_01.md` to `doc_50.md`, ~26,500 words).
* **Master Fact Pool:** 160 invented facts in [`data/track_b/master_fact_pool.json`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/track_b/master_fact_pool.json) (`SHA-256: 706D7E6817610669A50BFA0863AC7F6F70D562076AE39A3FBDEAD010EBE045EA`).
  * **Dev Pool:** 80 facts across 8 subsystems.
  * **Held-Out Pool:** 80 facts across 8 subsystems.
  * **Zero Real-World Standards:** No IEEE, AES, ASTM, or MIL-STD references.
  * **Disjointness:** Strictly zero shared component names, property keys, or values between Dev and Held-Out.

### 3.2 Evaluation Splits

| Split Name | File Path | Questions | Multi-Hop Structure | Scorer | Cryptographic SHA-256 Hash | Status |
|---|---|:---:|---|---|---|---|
| **Track B Dev Split** | [`data/track_b/track_b_dev_split.json`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/track_b/track_b_dev_split.json) | 50 | Combines $\ge 2$ facts from Dev pool; fact usage $\le 2$; zero doc citations | Automated Fact Checklist ($\le 75$ words) | `01FA3BC98933459A26662F271F037CFC9A15A016F6E07287A580F1D8593260EA` | Complete for Dev progression |
| **Track B Held-Out Candidate** | [`data/track_b/track_b_heldout_candidate.json`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/data/track_b/track_b_heldout_candidate.json) | 50 | Combines $\ge 2$ facts from Held pool; fact usage $\le 2$; zero doc citations | Automated Fact Checklist ($\le 75$ words) | `B021E2D0032D15A20F24315FB4538FE59ECD3ECB323F9A8CA295C2B421D7ED6D` | **Candidate (Pending Owner Lock)** |

### 3.3 Scorer Safeguards
* **Length Capping:** Maximum answer length is capped at **75 words**. Verbose outputs or full-corpus copy-pasting automatically trigger failure.
* **Negative Guards:** Plausible distractors (superseded v4.1 parameters and secondary subsystem units) are explicitly banned in the checklist. Answers containing distractors fail precision checks.
* **Self-Verification:** All 100 gold outputs score 100% precision, 100% recall, and binary pass in [`src/eval/fact_checklist_scorer.py`](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/src/eval/fact_checklist_scorer.py).

---

## 4. Serving Infrastructure Status

* **Engine:** `tools/llama_bin/llama-server.exe` running on Vulkan GPU (`-c 12288 -np 3`).
* **Active Base Model:** `microsoft/Phi-4-mini-instruct` (GGUF `3c168af1...`).
* **Context Budget:** 4,096 tokens per slot across 3 concurrent execution slots (peak VRAM: 4,297 MiB / 6,144 MiB, 100% GPU offload).
* **Adapter Switching:** In-memory runtime LoRA scaling via `POST /lora-adapters` measured at **1.815 ms** average switch latency (8,700x faster than process reloads).
* **Concurrency:** Simultaneous requests dispatched with distinct LoRA adapters verified with zero cross-talk.

---

## 5. Required Owner Action (Mandatory Checkpoint 2)

Per [AGENTS.md](file:///c:/Users/ACER/OneDrive/Desktop/Desktop%201/SLM_PROJECT_NEW/AGENTS.md) Mandatory Owner Checkpoint 2, held-out evaluation splits remain in **candidate quarantine** until explicit owner review and sign-off.

### Decisions Requested:
1. **Approve Dataset Card & Hashes:** Approve the enlarged Track A splits (100 Dev, 100 Held-Out, 100 Reserve) and Track B splits (50 Dev, 50 Held-Out).
2. **Lock Held-Out Splits:** Authorize recording the SHA-256 hashes as permanently locked, cryptographically isolating `track_a_heldout_candidate.json` and `track_b_heldout_candidate.json`.
3. **Approve Transition to Phase 4:** Authorize running B0 (greedy direct prompt) and B1 (tool-augmented) baseline evaluations on the **Dev** split for Qwen-27B and GPT-OSS-120B.
