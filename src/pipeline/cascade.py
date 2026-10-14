"""
Frozen Cascaded Inference Engine (Pipeline v1.1 -> openai/gpt-oss-120b with B1 Tools).

Tag: v1.1-cascade-frozen
Architecture:
1. Primary Stage: Specialist Pipeline v1.1 (Phi-4-mini, 3.82B, local GPU).
2. Chosen Frozen Trigger: Tier 3 without Corpus Escalation.
   An item is escalated if:
   (T1 or T2 or T3 or T4 or T5) and (not is_corpus)
   Where:
   - T1: Unclean SQL/code execution.
   - T2: Analyser heuristic fallback.
   - T3: Database identifier fallback.
   - T4: Missing final answer.
   - T5: Solution self-check validator disagreement (call_phi).
   - Filter (is_corpus): Decided strictly by the pipeline's own Analyser (Stage 1)
     identifying the HyperGrid technical corpus. These tasks achieve 96% accuracy
     under v1.1 and are protected from 120B format component token omissions.
3. Escalation Stage: openai/gpt-oss-120b via Groq under exact B1 tool harness:
   - Pure SQL: sql_harness_with_retry
   - Pure Code: code_harness_with_retry
   - Pure QA: qa_harness
   - Pure Math: math_harness
   - Compound: compound_multistep_harness

Strict Integrity Constraint: Zero dataset labels, difficulty tiers, or gold answers
are used in routing. Routing decisions stem exclusively from the pipeline's own execution.
"""

import os
import sys
import json
import time
import re
from typing import Dict, Any, List, Optional, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import run_specialist_pipeline, call_phi
from scripts.run_dev_b1_gpt120b import run_item_with_b1_tools, MODEL_ID

CHECK_SYS = """You are an expert solution validator. Check whether the candidate answer directly and correctly answers the given task.
Respond in exactly this format:
VERIFIED: <YES or NO>
REASON: <brief explanation>"""


def evaluate_self_check(prompt: str, candidate_answer: str) -> Tuple[bool, str]:
    """
    Evaluates solution self-check (Trigger T5) using local model.
    Returns: (is_disagree: bool, explanation: str)
    """
    resp = call_phi([
        {"role": "system", "content": CHECK_SYS},
        {"role": "user", "content": f"Task:\n{prompt}\n\nCandidate Answer:\n{candidate_answer}\n\nValidation:"}
    ], temperature=0.0, max_tokens=120)

    m = re.search(r"VERIFIED:\s*(YES|NO)", resp, re.I)
    if m:
        verdict = m.group(1).upper()
        return (verdict == "NO"), resp
    return True, f"Unparseable self-check response: {resp[:100]}"


def run_cascade_inference(
    prompt: str,
    item_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Executes the frozen cascaded inference pipeline:
    Pipeline v1.1 runs first.
    If the chosen frozen trigger fires, escalates to 120B with B1 tools.
    """
    t0 = time.time()

    # 1. Run Pipeline v1.1
    v11_rec = run_specialist_pipeline(prompt)

    # 2. Extract triggers decided strictly from pipeline's own execution
    clean = v11_rec.get("clean_execution", True)
    fallbacks = v11_rec.get("fallbacks", {})
    t1 = not clean
    t2 = bool(fallbacks.get("analyser", False))
    t3 = bool(fallbacks.get("database_identifier", False))
    final_ans = str(v11_rec.get("final_answer") or v11_rec.get("output", "")).strip()
    t4 = not bool(final_ans)

    # Analyser corpus check (strictly from pipeline Stage 1 analyser model output)
    is_corpus = (v11_rec.get("source") == "CORPUS")

    # Self-check evaluated for non-corpus tasks
    t5 = False
    t5_reason = ""
    if not is_corpus and final_ans:
        t5, t5_reason = evaluate_self_check(prompt, final_ans)

    triggers_fired = {
        "T1_unclean_execution": t1,
        "T2_analyser_fallback": t2,
        "T3_db_fallback": t3,
        "T4_missing_answer": t4,
        "T5_self_check_disagree": t5,
        "is_corpus_task": is_corpus
    }

    # Chosen frozen trigger: (T1 | T2 | T3 | T4 | T5) and not is_corpus
    should_escalate = (t1 or t2 or t3 or t4 or t5) and (not is_corpus)

    if not should_escalate:
        # Kept pipeline v1.1 output
        return {
            "escalated": False,
            "trigger_used": "tier3_no_corpus",
            "triggers_fired": triggers_fired,
            "model_used": "phi-4-mini (pipeline v1.1)",
            "output": v11_rec.get("output", ""),
            "full_output": v11_rec.get("full_output", ""),
            "final_answer": v11_rec.get("final_answer", ""),
            "clean_execution": v11_rec.get("clean_execution", True),
            "120b_calls": 0,
            "120b_tokens": 0,
            "duration": round(time.time() - t0, 2)
        }

    # 3. Escalation to 120B with tools (B1 harness)
    escalate_item = dict(item_metadata) if item_metadata else {}
    escalate_item["prompt"] = prompt

    b1_res = run_item_with_b1_tools(MODEL_ID, escalate_item)

    return {
        "escalated": True,
        "trigger_used": "tier3_no_corpus",
        "triggers_fired": triggers_fired,
        "model_used": MODEL_ID,
        "harness_used": b1_res.get("harness_used", "b1_tools"),
        "output": b1_res.get("output", ""),
        "full_output": b1_res.get("full_output", ""),
        "final_answer": b1_res.get("output", ""),
        "clean_execution": b1_res.get("clean_execution", True),
        "120b_calls": b1_res.get("num_calls", 1),
        "120b_tokens": b1_res.get("total_tokens", 0),
        "duration": round(time.time() - t0, 2)
    }
