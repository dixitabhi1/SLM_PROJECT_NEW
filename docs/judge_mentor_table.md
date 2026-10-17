# Mentor Protocol Table: Secondary Evaluation Layer (LLM-as-a-Judge)

**Judge Evaluation Scope:** Held-Out Split ($N=150$: Track A $N=100$, Track B $N=50$), position-swap testing ($2 \times 150 = 300$ calls per baseline).  
**Protocol Invariants:** Temperature 0.0, zero thinking tokens (`thinkingBudget: 0`), strict schema validation.  
**Publication Gate:** In accordance with integrity rules, judge metrics are published only when each baseline achieves $\ge 95\%$ completed items ($N \ge 143/150$). Prior to complete execution, all active cells remain marked *pending*.

| Experiment | SLM Fine-Tuning Configuration | Skill-Matching SLM | LLM Fine-Tuning | LLM Wins | SLM Wins | Draws | Quality Proximity | SLM CQS | LLM CQS |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| E1 (vs GPT-OSS-120B B1) | None (Base Phi-4-mini 3.82B, prompt/tool-only) | Single-model pool (no router) | None (Frozen API B1) | pending | pending | pending | pending | pending | pending |
| E1 (vs qwen/qwen3.8-27b B1) | None (Base Phi-4-mini 3.82B, prompt/tool-only) | Single-model pool (no router) | None (Frozen API B1) | pending | pending | pending | pending | pending | pending |
| E2 | Query-dependent LoRA adapters (SQL specialist) | Single-model pool | None | — | — | — | Not run (training pipeline prepared, run pending owner sign-off) | — | — |
| E3 | All specialist SLMs fine-tuned | Multi-SLM pool | None | — | — | — | Not run (mentor multi-model pool not configured; repo E3 was compute-in-code) | — | — |
| E4-A | None | Skill-matching SLM (router) | None | — | — | — | Not run as specified (repo E4 learned router rejected on dev headroom gate) | — | — |
| E4-B | Fine-tuned skill matcher | Fine-tuned router | None | — | — | — | Not run (repo E4b retry failed dev regression gate) | — | — |

\*\*Footnote:\*\* Mapping to repo experiments: Our frozen pipeline v1.3 corresponds to mentor E1 (no fine-tuning, autonomous tool execution). Our repo "E3" designates compute-in-code routing (accepted into v1.3), not all-SLM fine-tuning. Our repo "E4" designates learned router experiments (E4 and E4b, both rejected at dev gates). The active specialist pool is a single 3.82B parameter model (Phi-4-mini) with specialized execution tools, not a 5–8B multi-model pool.
