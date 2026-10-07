# Progress Tracker — SLM Clean Rebuild

This file tracks project phase progression, the authoritative validity ledger of reported results, and the incident log. Read this first in every session.

---

## 1. Phase Status

| Phase | Description | Status | Gate / Owner Checkpoint | Notes |
|---|---|---|---|---|
| **1. Setup** | Repo initialization, environment audit, candidate proposals, verbatim sources lock | COMPLETE | Model, baseline & judge choice by owner (done) | GPU/OS/keys audited, Option 1 selected, master prompt & mentor protocol locked |
| **2. Infrastructure** | Serving setup, parallelism benchmark (configs a, b, c, d), adapter switching, sandbox, tools, run records, audit & report scripts | COMPLETE | Smoke test pass (C0 & B0 1-item) & owner config choice | All 13 unit tests pass; C0 & B0 smoke pass; 4 concurrency configs benchmarked on 20 subtasks |
| **3. Datasets** | Track A (objective) & Track B (private knowledge), dev release, held-out hash lock | PENDING | Owner sign-off on Dataset Card | Section 5 build |
| **4. Baselines** | B0 & B1 baseline generation on dev, response caching & hashing | PENDING | Complete answers verified | 3-tier baselines |
| **5. Ladder on Dev** | C0 to C3 progression, paired bootstrap tests, dev audit | PENDING | Report after C3; gate verification | N=3 sampling, decomposition |
| **6. Distillation** | C4 adapters, 20-step dry run on 6GB VRAM, task accuracy check | PENDING | Owner approval before any training | Real verified solutions |
| **7. Cascade** | C5 cascade routing on dev | PENDING | Verification-driven escalation | Tradeoff curve analysis |
| **8. Freeze** | Tag commit, register success criteria | PENDING | Owner freeze approval | No code/prompt edits after freeze |
| **9. Held-Out** | Single execution run across all frozen conditions, audit, report | PENDING | Final report sign-off | Immutable evaluation |

---

## 2. Validity Ledger

Every headline number reported in any publication, brief, or table must appear here with its source file and current verification status (`stands`, `void`, or `superseded`).

| ID | Metric / Finding | Value | Source File | Status | Effective Date | Notes |
|---|---|---|---|---|---|---|
| VL-001 | Config (a) Throughput (Phi-3.5 + Llama-3.2-3B) | 0.0567 subtasks/s (352.77s / 20 items, peak VRAM 4051 MiB) | `results/benchmarks/parallelism_benchmark.json` | stands | 2026-10-07 | Fastest concurrency config, 0 CPU spill |
| VL-002 | Config (b) Throughput (3 bases co-loaded) | 0.0455 subtasks/s (439.56s / 20 items, peak VRAM 5123 MiB) | `results/benchmarks/parallelism_benchmark.json` | stands | 2026-10-07 | Highest VRAM pressure (5123 MiB / 6 GB) |
| VL-003 | Config (c) Throughput (8B with 2 parallel slots) | 0.0415 subtasks/s (482.28s / 20 items, peak VRAM 4599 MiB) | `results/benchmarks/parallelism_benchmark.json` | stands | 2026-10-07 | Batched generation, 0 CPU spill |
| VL-004 | Config (d) Throughput (8B serial reference) | 0.0444 subtasks/s (450.74s / 20 items, peak VRAM 4599 MiB) | `results/benchmarks/parallelism_benchmark.json` | stands | 2026-10-07 | Serial execution reference |
| VL-005 | Model Swap Latency (Phi-3.5 to Llama-3.2-3B) | 11.837 s | `results/benchmarks/model_swap_benchmarks.json` | stands | 2026-10-07 | Full GPU reload time |
| VL-006 | Model Swap Latency (Llama-3.2-3B to Llama-3.1-8B) | 20.301 s | `results/benchmarks/model_swap_benchmarks.json` | stands | 2026-10-07 | Full GPU reload time |
| VL-007 | Smoke Test C0 (Local SLM Phi-3.5) Accuracy & Latency | 100% pass (1/1 valid), 0.14s latency | `results/smoke_test_records.jsonl` | stands | 2026-10-07 | Single greedy response, exact match |
| VL-008 | Smoke Test B0 (Groq Qwen-3.8-27B) Accuracy & Latency | 100% pass (1/1 valid), 0.41s latency | `results/smoke_test_records.jsonl` | stands | 2026-10-07 | Single greedy response, exact match |

---

## 3. Incident Log

Any failure, unhandled exception, hardware interruption, timeout, or protocol irregularity must be logged here immediately.

| Incident ID | Timestamp | Category | Description | Root Cause | Impact | Resolution |
|---|---|---|---|---|---|---|
| INC-001 | 2026-10-07 22:01:47 | Environment | Ollama client auto-launch timeout when running `ollama list` | Ollama background daemon was not running as a persistent service on Windows | Diagnostic command exited non-zero | Manually tested `ollama serve` and verified listener on port 11434; documented in `environment.md` |
| INC-002 | 2026-10-07 22:28:33 | Infrastructure | GitHub remote rejected git push with Internal Server Error (`500`) | Upstream GitHub service error | Commit `599761d` saved locally on branch `main`; remote push pending upstream recovery | Monitored and queued for retry |
