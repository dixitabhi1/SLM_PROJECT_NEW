"""
One-item smoke run for C0 (Single base SLM, greedy, no tools)
and B0 (Baseline LLM, greedy, no tools).
Verifies complete run record logging, latency capture, and audit compliance.
"""

import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.serving.ollama_client import OllamaClient
from src.serving.remote_client import GroqClient
from src.records.logger import RunRecordsLogger
from src.tools.math_tool import SymbolicMathTool
from src.eval.report_generator import ReportGenerator
from src.audit.audit_rules import run_full_audit


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    log_file = os.path.join(repo_root, "results", "smoke_test_records.jsonl")
    logger = RunRecordsLogger(log_file)

    item_id = "smoke_item_01"
    prompt = "Compute 25 * 4. Respond with only the final number."
    gold_answer = "100"

    print("=" * 60)
    print("PHASE 2 SMOKE TEST: C0 (Local SLM) vs B0 (Groq Baseline LLM)")
    print("=" * 60)

    # 1. Condition C0: Single local base SLM (greedy)
    print("\n[1/2] Executing Condition C0 (Local SLM: phi3.5:3.8b)...")
    ollama = OllamaClient()
    assert ollama.ensure_server_running(), "Ollama server failed to respond"

    c0_resp = ollama.generate(
        model_id="phi3.5:3.8b",
        prompt=prompt,
        seed=42,
        temperature=0.0,
    )
    print(f"  C0 Status: {c0_resp.status}")
    print(f"  C0 Output: {c0_resp.content.strip()[:80]}")
    print(f"  C0 Latency: {c0_resp.latency_seconds:.3f}s | Tokens: {c0_resp.completion_tokens}")

    # Verify math correctness
    math_tool = SymbolicMathTool()
    c0_verdict = math_tool.verify_equivalence(c0_resp.content, gold_answer)

    rec_c0 = logger.log_call(
        item_id=item_id,
        condition="C0",
        model_id=c0_resp.model_id,
        prompt=prompt,
        seed=c0_resp.seed,
        full_output=c0_resp.content,
        prompt_tokens=c0_resp.prompt_tokens,
        completion_tokens=c0_resp.completion_tokens,
        total_tokens=c0_resp.total_tokens,
        finish_reason=c0_resp.finish_reason,
        latency_ms=c0_resp.latency_seconds * 1000.0,
        verifier_result={"verdict": c0_verdict.verdict, "is_match": c0_verdict.is_equivalent},
        status=c0_resp.status,
    )
    assert rec_c0.status == "COMPLETE", f"C0 failed: {c0_resp.error_message}"

    # 2. Condition B0: Baseline LLM via Groq (greedy)
    print("\n[2/2] Executing Condition B0 (Groq Baseline: qwen/qwen3.8-27b)...")
    groq = GroqClient()
    b0_resp = groq.generate(
        model_id="qwen/qwen3.8-27b",
        prompt=prompt,
        seed=42,
        temperature=0.0,
    )
    print(f"  B0 Status: {b0_resp.status}")
    print(f"  B0 Output: {b0_resp.content.strip()[:80]}")
    print(f"  B0 Latency: {b0_resp.latency_seconds:.3f}s | Tokens: {b0_resp.completion_tokens}")

    b0_verdict = math_tool.verify_equivalence(b0_resp.content, gold_answer)

    rec_b0 = logger.log_call(
        item_id=item_id,
        condition="B0",
        model_id=b0_resp.model_id,
        prompt=prompt,
        seed=b0_resp.seed,
        full_output=b0_resp.content,
        prompt_tokens=b0_resp.prompt_tokens,
        completion_tokens=b0_resp.completion_tokens,
        total_tokens=b0_resp.total_tokens,
        finish_reason=b0_resp.finish_reason,
        latency_ms=b0_resp.latency_seconds * 1000.0,
        verifier_result={"verdict": b0_verdict.verdict, "is_match": b0_verdict.is_equivalent},
        status=b0_resp.status,
    )
    assert rec_b0.status == "COMPLETE", f"B0 failed: {b0_resp.error_message}"

    print("\n" + "=" * 60)
    print("TRACEABILITY & AUDIT VERIFICATION")
    print("=" * 60)

    # 3. Report Generator & Traceability
    gen = ReportGenerator(log_file)
    c0_summary = gen.compute_summary_by_condition("C0")
    b0_summary = gen.compute_summary_by_condition("B0")

    assert gen.verify_traceability("C0", c0_summary)
    assert gen.verify_traceability("B0", b0_summary)
    print("  [OK] Traceability test passed: All computed metrics match recomputed raw values.")

    # 4. Run automated rules audit
    passed, errors = run_full_audit(repo_root)
    assert passed, f"Audit failed: {errors}"
    print("  [OK] Automated Rules Audit passed: Zero violations of Rules 2-8.")

    print("\nGenerated Results Table:")
    print(gen.generate_markdown_table(["C0", "B0"]))
    print("\nSmoke test successfully completed!")


if __name__ == "__main__":
    main()
