"""
Unit tests for append-only JSONL run records and traceability.
"""

import os
import json
import tempfile
import pytest
from src.records.logger import (
    RunRecordsLogger,
    compute_prompt_hash,
    get_current_git_commit,
)
from src.eval.report_generator import ReportGenerator


def test_records_logger_append_only():
    with tempfile.TemporaryDirectory() as temp_dir:
        log_path = os.path.join(temp_dir, "test_runs.jsonl")
        logger = RunRecordsLogger(log_path)

        # Log complete record
        r1 = logger.log_call(
            item_id="item_01",
            condition="C0",
            model_id="qwen2.5:7b",
            prompt="Compute 2+2",
            seed=42,
            full_output="4",
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
            finish_reason="stop",
            latency_ms=150.0,
            verifier_result={"verdict": "PASS"},
        )
        assert r1.status == "COMPLETE"
        assert r1.prompt_hash == compute_prompt_hash("Compute 2+2")

        # Log failed record (fail loudly)
        r2 = logger.log_call(
            item_id="item_02",
            condition="C0",
            model_id="qwen2.5:7b",
            prompt="Broken item",
            seed=42,
            full_output="",
            prompt_tokens=10,
            completion_tokens=0,
            total_tokens=10,
            finish_reason="empty_output",
            latency_ms=50.0,
            verifier_result={"verdict": "FAIL"},
        )
        assert r2.status == "FAILED"

        # Check completed set
        completed = logger.get_completed_items("C0")
        assert "item_01" in completed
        assert "item_02" not in completed

        # Verify ReportGenerator and Traceability
        report_gen = ReportGenerator(log_path)
        summary = report_gen.compute_summary_by_condition("C0")
        assert summary.total_calls == 2
        assert summary.valid_items == 1
        assert summary.failed_items == 1
        assert summary.exclusion_rate == 0.5
        assert summary.task_accuracy == 1.0

        assert report_gen.verify_traceability("C0", summary)

