"""
Unit test verifying that run_specialist_pipeline operates strictly on a prompt string alone.
Enforces that no dataset dictionary or metadata fields are passed or required.
"""

import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import run_specialist_pipeline
from src.audit.audit_leakage import audit_pipeline_leakage


def test_leakage_audit():
    """Verifies that zero dataset fields are read under src/pipeline/."""
    pipeline_dir = os.path.join(REPO_ROOT, "src", "pipeline")
    errs = audit_pipeline_leakage(pipeline_dir)
    assert len(errs) == 0, f"Leakage audit violations found: {errs}"


def test_pipeline_pure_prompt_direct():
    """Verifies that pipeline executes on a pure prompt string without outside data."""
    raw_prompt = (
        "Solve this math problem step by step:\n"
        "A bakery makes 48 loaves of bread. 12 are sourdough, 16 are rye, and the rest are wheat. "
        "How many loaves are wheat?\n\n"
        "Conclude your final answer with: #### <number>"
    )
    res = run_specialist_pipeline(raw_prompt)
    assert isinstance(res, dict)
    assert "full_output" in res
    assert res["clean_execution"] is True
    assert res["routed_to"] == "direct"
    assert "20" in res["full_output"]


def test_pipeline_pure_prompt_outside_data():
    """Verifies that pipeline executes on a pure prompt string with database query."""
    raw_prompt = (
        "Query the poker_player database [Database Schema: CREATE TABLE poker_player ( poker_player_id int, Nationality text )] "
        "to give the nationality that is most common across all people.\n"
        "Return only the requested column."
    )
    res = run_specialist_pipeline(raw_prompt)
    assert isinstance(res, dict)
    assert "full_output" in res
    assert res["clean_execution"] is True
    assert res["routed_to"] == "outside_data"
    assert "SELECT" in res["full_output"].upper()


if __name__ == "__main__":
    test_leakage_audit()
    print("test_leakage_audit PASSED")
    test_pipeline_pure_prompt_direct()
    print("test_pipeline_pure_prompt_direct PASSED")
    test_pipeline_pure_prompt_outside_data()
    print("test_pipeline_pure_prompt_outside_data PASSED")

