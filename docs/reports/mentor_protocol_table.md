# Mentor Protocol Table: Secondary Evaluation Layer (LLM-as-a-Judge)

**Judge Evaluation Scope:** Held-Out Split ($N=150$: Track A $N=100$, Track B $N=50$).  
**Judge Model:** `prometheus-eval/prometheus-7b-v2.0` (GGUF Q4_K_M, SHA-256 `5bb7b0fa...`, local execution on port 8081).  
**Protocol Invariants:** Temperature 0.0, reference-free (no answer key), native 1–5 rubrics. Quality Proximity computed on native scale ($QP = 1 - |Q_S - Q_L|/4$).  

> [!WARNING]
> **RELIABILITY STATUS: UNRELIABLE (judge agreement with answer key 50% < 80%)**  
> Prometheus-2 7B failed Validity Check (a) with only 50.0% concordance with answer-key winners on disagreement items (threshold $\ge 80\%$), and exhibited 46.9%–56.2% false-high scores ($\ge 4/5$) on objectively wrong answers (Check b). Consequently, all Quality Proximity (QP) and CQS metrics are designated **UNRELIABLE (judge agreement with answer key 50% < 80%)**. Primary answer-key accuracy (Exact Match) remains the headline and authoritative evaluation metric.

| Experiment | SLM Fine-Tuning | Skill-Matching SLM | LLM Fine-Tuning | LLM Win | SLM Win | Draw | Quality Proximity [95% CI]* | SLM CQS* | LLM CQS* | Check (a) Concordance | Check (b) False High | Swap Cons. | Reliability Status |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| E1 (vs GPT-OSS-120B B1) | None (Base Phi-4-mini 3.82B, prompt/tool-only) | Single-model pool (no router) | None (Frozen API B1) | 53 (36.1%) | 26 (17.7%) | 68 (46.3%) | 0.7483 [0.7007, 0.7925]* | 3.81* | 4.14* | 50.0\% (9/18) | 56.2% (18/32) | 70.7% | **UNRELIABLE (judge agreement with answer key 50% < 80%)** |
| E1 (vs qwen/qwen3.8-27b B1) | None (Base Phi-4-mini 3.82B, prompt/tool-only) | Single-model pool (no router) | None (Frozen API B1) | 58 (40.0%) | 14 (9.7%) | 73 (50.3%) | 0.7810 [0.7345, 0.8241]* | 3.84* | 4.40* | 50.0\% (12/24) | 46.9% (15/32) | 77.2% | **UNRELIABLE (judge agreement with answer key 50% < 80%)** |
| E2 | Query-dependent LoRA adapters (SQL specialist) | Single-model pool | None | — | — | — | Not run | — | — | — | — | — | Not run (training pipeline prepared, run pending owner sign-off) |
| E3 | All specialist SLMs fine-tuned | Multi-SLM pool | None | — | — | — | Not run | — | — | — | — | — | Not run (mentor multi-model pool not configured; repo E3 was compute-in-code) |
| E4-A | None | Skill-matching SLM (router) | None | — | — | — | Not run | — | — | — | — | — | Not run as specified (repo E4 learned router rejected on dev headroom gate) |
| E4-B | Fine-tuned skill matcher | Fine-tuned router | None | — | — | — | Not run | — | — | — | — | — | Not run (repo E4b retry failed dev regression gate) |

* **UNRELIABLE (judge agreement with answer key 50% < 80%):** Designated UNRELIABLE because judge validity check (a) agreement with answer key is 50.0% (< 80%).

**Footnote:** Mapping to repo experiments: Our frozen pipeline v1.3 corresponds to mentor E1 (no fine-tuning, autonomous tool execution). Our repo "E3" designates compute-in-code routing (accepted into v1.3), not all-SLM fine-tuning. Our repo "E4" designates learned router experiments (E4 and E4b, both rejected at dev gates). The active specialist pool is a single 3.82B parameter model (Phi-4-mini) with specialized execution tools, not a 5–8B multi-model pool.
