"""
Unit tests for frozen cascaded inference routing (src/pipeline/cascade.py).
Verifies:
1. Trigger rules: (T1 or T2 or T3 or T4 or T5) and (source != "CORPUS").
2. Corpus items (source == "CORPUS") are protected from escalation regardless of triggers.
3. Non-corpus items escalate when triggers fire.
4. Zero evaluation keywords ("hypergrid", "v4.2") in routing logic.
"""

import inspect
from unittest.mock import patch
import pytest

from src.pipeline import cascade


def test_no_corpus_keywords_in_cascade():
    """Verifies that cascade.py does not contain prompt keyword matching for hypergrid or v4.2."""
    source_lines = inspect.getsource(cascade.run_cascade_inference)
    assert "hypergrid" not in source_lines.lower(), "Found 'hypergrid' keyword in run_cascade_inference!"
    assert "v4.2" not in source_lines.lower(), "Found 'v4.2' keyword in run_cascade_inference!"


def test_cascade_corpus_protection():
    """Corpus items identified by the analyser must not be escalated even if self-check flags."""
    mock_v11 = {
        "output": "Component A: 12.5 ohm",
        "final_answer": "Component A: 12.5 ohm",
        "clean_execution": True,
        "fallbacks": {},
        "source": "CORPUS"
    }

    with patch("src.pipeline.cascade.run_specialist_pipeline", return_value=mock_v11), \
         patch("src.pipeline.cascade.evaluate_self_check", return_value=(True, "disagree")):
        res = cascade.run_cascade_inference("What is the resistance of Component A?")
        assert res["escalated"] is False
        assert res["model_used"] == "phi-4-mini (pipeline v1.1)"
        assert res["triggers_fired"]["is_corpus_task"] is True


def test_cascade_non_corpus_clean_no_escalate():
    """Non-corpus clean item without triggers must not escalate."""
    mock_v11 = {
        "output": "42",
        "final_answer": "42",
        "clean_execution": True,
        "fallbacks": {},
        "source": "NONE"
    }

    with patch("src.pipeline.cascade.run_specialist_pipeline", return_value=mock_v11), \
         patch("src.pipeline.cascade.evaluate_self_check", return_value=(False, "agreed")):
        res = cascade.run_cascade_inference("What is 6 * 7?")
        assert res["escalated"] is False
        assert res["model_used"] == "phi-4-mini (pipeline v1.1)"


def test_cascade_non_corpus_trigger_escalates():
    """Non-corpus item with unclean execution or self-check flag must escalate to 120B."""
    mock_v11 = {
        "output": "15",
        "final_answer": "15",
        "clean_execution": False,
        "fallbacks": {},
        "source": "DATABASE"
    }
    mock_b1 = {
        "output": "SELECT count(*) FROM table",
        "full_output": "SELECT count(*) FROM table",
        "clean_execution": True,
        "harness_used": "sql_harness_with_retry",
        "num_calls": 1,
        "total_tokens": 250
    }

    with patch("src.pipeline.cascade.run_specialist_pipeline", return_value=mock_v11), \
         patch("src.pipeline.cascade.run_item_with_b1_tools", return_value=mock_b1):
        res = cascade.run_cascade_inference("SELECT query...")
        assert res["escalated"] is True
        assert res["model_used"] == cascade.MODEL_ID
        assert res["harness_used"] == "sql_harness_with_retry"
        assert res["120b_tokens"] == 250
