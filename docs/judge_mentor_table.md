# Mentor Protocol Table: Secondary Evaluation Layer (LLM-as-a-Judge)

**Judge Evaluation Scope:** Held-Out Split ($N=150$: Track A $N=100$, Track B $N=50$).  
**Judge Model:** `prometheus-eval/prometheus-7b-v2.0` (GGUF Q4_K_M, SHA-256 `5bb7b0fa...`, local execution on port 8081).  
**Protocol Invariants:** Temperature 0.0, reference-free (no answer key), native 1–5 rubrics. Quality Proximity computed on native scale ($QP = 1 - |Q_S - Q_L|/4$).  

| Experiment | SLM Fine-Tuning Configuration | Skill-Matching SLM | LLM Fine-Tuning | LLM Wins | SLM Wins | Draws | Quality Proximity | SLM CQS | LLM CQS |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| E1 (vs GPT-OSS-120B B1) | None (Base Phi-4-mini 3.82B, prompt/tool-only) | Single-model pool (no router) | None (Frozen API B1) | 53 (36.1%) | 26 (17.7%) | 68 (46.3%) | 0.7483 [0.7007, 0.7925] | 3.81 | 4.14 |
| E1 (vs qwen/qwen3.8-27b B1) | None (Base Phi-4-mini 3.82B, prompt/tool-only) | Single-model pool (no router) | None (Frozen API B1) | 58 (40.0%) | 14 (9.7%) | 73 (50.3%) | 0.7810 [0.7345, 0.8241] | 3.84 | 4.40 |
| E2 | Query-dependent LoRA adapters (SQL specialist) | Single-model pool | None | — | — | — | Not run (training pipeline prepared, run pending owner sign-off) | — | — |
| E3 | All specialist SLMs fine-tuned | Multi-SLM pool | None | — | — | — | Not run (mentor multi-model pool not configured; repo E3 was compute-in-code) | — | — |
| E4-A | None | Skill-matching SLM (router) | None | — | — | — | Not run as specified (repo E4 learned router rejected on dev headroom gate) | — | — |
| E4-B | Fine-tuned skill matcher | Fine-tuned router | None | — | — | — | Not run (repo E4b retry failed dev regression gate) | — | — |

**Footnote:** Mapping to repo experiments: Our frozen pipeline v1.3 corresponds to mentor E1 (no fine-tuning, autonomous tool execution). Our repo "E3" designates compute-in-code routing (accepted into v1.3), not all-SLM fine-tuning. Our repo "E4" designates learned router experiments (E4 and E4b, both rejected at dev gates). The active specialist pool is a single 3.82B parameter model (Phi-4-mini) with specialized execution tools, not a 5–8B multi-model pool.
