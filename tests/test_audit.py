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

