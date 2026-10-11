"""
Unit tests for the automated audit script.
Verifies that rule violations fail loudly and exit non-zero.
"""

import os
import json
import tempfile
import pytest
from src.audit.audit_rules import audit_run_records, run_full_audit


def test_audit_current_repo():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    passed, errors = run_full_audit(repo_root)
    assert passed, f"Audit failed unexpectedly: {errors}"
    assert len(errors) == 0


def test_audit_catches_floating_alias():
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "item_id": "test_1",
                    "model_id": "llama3.1:latest",  # Violation: floating alias
                    "finish_reason": "stop",
                    "completion_tokens": 10,
                    "full_output": "answer",
                    "status": "COMPLETE",
                }
            )
            + "\n"
        )
        temp_path = f.name

    try:
        errors = audit_run_records(temp_path)
        assert any("floating alias" in err for err in errors)
    finally:
        os.remove(temp_path)


def test_audit_catches_silent_failure():
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "item_id": "test_2",
                    "model_id": "qwen2.5:7b-instruct-q4_K_M",
                    "finish_reason": "length",  # Truncated
                    "completion_tokens": 50,
                    "full_output": "incomplete...",
                    "status": "COMPLETE",  # Violation: should be marked FAILED
                }
            )
            + "\n"
        )
        temp_path = f.name

    try:
        errors = audit_run_records(temp_path)
        assert any("Rule 3 Violation" in err for err in errors)
    finally:
        os.remove(temp_path)


def test_audit_catches_invalid_model_digest():
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "item_id": "test_3",
                    "model_id": "phi3.5:3.8b",
                    "model_digest": "invalid_digest_not_hex!",
                    "finish_reason": "stop",
                    "completion_tokens": 10,
                    "full_output": "answer",
                    "status": "COMPLETE",
                }
            )
            + "\n"
        )
        temp_path = f.name

    try:
        errors = audit_run_records(temp_path)
        assert any("invalid model_digest" in err for err in errors)
    finally:
        os.remove(temp_path)


def test_audit_model_digests_in_repo():
    from src.audit.audit_rules import audit_model_digests

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    errors = audit_model_digests(repo_root)
    assert len(errors) == 0, f"Model digest audit failed: {errors}"


def test_audit_catches_google_aq_secret():
    import re
    # Dynamically construct test string to verify regex behavior without triggering static repo scan
    prefix = "AQ."
    fake_val = prefix + ("Ab8" * 15)
    pat = re.compile(r"AQ\.[a-zA-Z0-9_\-\.]{25,75}")
    assert pat.search(fake_val) is not None


def test_audit_secret_leakage_clean():
    from src.audit.audit_rules import audit_secret_leakage

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    errors = audit_secret_leakage(repo_root)
    assert len(errors) == 0, f"Found unexpected secret in repository: {errors}"


def test_audit_benchmark_leakage_clean():
    from src.audit.audit_rules import audit_benchmark_leakage

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    errors = audit_benchmark_leakage(repo_root)
    assert len(errors) == 0, f"Found benchmark leakage in pipeline prompts, adapters, or skills: {errors}"


def test_audit_results_journal_catches_shrink_and_deletion():
    from src.audit.audit_rules import audit_results_journal

    with tempfile.TemporaryDirectory() as tmpdir:
        res_dir = os.path.join(tmpdir, "results")
        os.makedirs(res_dir, exist_ok=True)
        test_file = os.path.join(res_dir, "test_records.jsonl")

        # Step 1: Initial creation of 2 records
        with open(test_file, "w", encoding="utf-8") as f:
            f.write('{"id": 1, "status": "COMPLETE"}\n{"id": 2, "status": "COMPLETE"}\n')

        # Initial audit should register file and pass
        errs = audit_results_journal(tmpdir)
        assert len(errs) == 0

        # Step 2: Shrink the file (remove a line)
        with open(test_file, "w", encoding="utf-8") as f:
            f.write('{"id": 1, "status": "COMPLETE"}\n')

        # Audit must catch shrink
        errs_shrink = audit_results_journal(tmpdir)
        assert any("shrunk" in e or "decreased" in e for e in errs_shrink)

        # Step 3: Delete the file completely
        os.remove(test_file)

        # Audit must catch disappearance
        errs_del = audit_results_journal(tmpdir)
        assert any("disappeared" in e for e in errs_del)





