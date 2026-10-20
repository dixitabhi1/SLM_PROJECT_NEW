# Repository Backup Registry

This document records offline snapshots and repository state backups created prior to major experimental phases, ensuring complete auditability and disaster recovery.

---

## 1. Snapshot: Pre-Public Benchmarks (`2026-10-20`)

Created immediately prior to initializing the public benchmark evaluation phase (GSM-Hard, FinQA, InfiAgent-DABench).

### 1.1 Git Commit & Tag State
- **Base Commit Hash:** `413a6de0c93ca2635b531c39b1d0ffb2d1f38a6b`
- **Frozen Pipeline Commit Hash:** `acef7a5c65b19dd8ed81d0ead5dc279922418edf`
- **Git Tags:**
  - `v1.3-slm-frozen` -> `acef7a5c65b19dd8ed81d0ead5dc279922418edf` ("freeze Pipeline v1.3 with generic CORPUS no-code fix and record v1.0 -> v1.3 attribution")
  - `pre-public-benchmarks` -> `413a6de0c93ca2635b531c39b1d0ffb2d1f38a6b`
- **Backup Branch:** `backup/pre-public-benchmarks` (pushed to `origin/backup/pre-public-benchmarks`; permanently immutable)

### 1.2 Git History Bundle
- **Bundle File:** `../SLM_backup_20261020.bundle`
- **SHA-256 Digest:** `4e3022fa633b459f7601a2bcd79598df5f4978c87426787be5780b2210d51371`
- **Verification Status:** Verified via `git bundle verify ../SLM_backup_20261020.bundle` (15 refs verified, complete history recorded).

### 1.3 Gitignored Essentials Archive
- **Archive File:** `../SLM_backup_20261020_ignored.zip`
- **SHA-256 Digest:** `c9570e2b9459e8660d6dd564ce427c97b620e3a01275ce2e5402991bcbe60a40`
- **Excluded Files:** `.env` and all credential/key files strictly excluded.
- **Included Files:**
  - `data/reserve_set_quarantine.json` (SHA-256: `bacd6c5ea2443cb087cf743b6bfe0434e52e5280df68937a6edcd5c15f8dd3db`)
  - `data/track_a_heldout_candidate.json` (SHA-256: `b61b369a45cefc6dfa538258384218eb85287f311c0f0a4f54d4ff909a96bb21`)
  - `data/track_b/master_fact_pool.json`
  - `data/track_b/track_b_heldout_candidate.json`
  - `.agents/knowledge/model_registry.md`
  - `.agents/knowledge/00_index.md`
