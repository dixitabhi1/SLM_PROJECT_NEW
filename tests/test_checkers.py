"""
Unit tests for the objective benchmark checkers.
Tests HumanEval execution, GSM8K numeric parsing, Spider SQLite matching, and ARC-Challenge option parsing.
"""

import pytest
from src.eval.subtask_checkers import evaluate_subtask


def test_code_checkers():
    # HumanEval 11: XOR
    good_xor = "def string_xor(a: str, b: str) -> str:\n    return ''.join(str(int(x) ^ int(y)) for x, y in zip(a, b))"
    bad_xor = "def string_xor(a: str, b: str) -> str:\n    return a + b"
    ok, chk, _ = evaluate_subtask({"id": "subtask_01", "type": "code"}, good_xor)
    assert ok
    fail, _, _ = evaluate_subtask({"id": "subtask_01", "type": "code"}, bad_xor)
    assert not fail


def test_math_checkers():
    # GSM8K dev 001: 72
    ok, _, _ = evaluate_subtask({"id": "subtask_06", "type": "math", "gold": "72"}, "Natalia sold 48 in April and 24 in May.\n#### 72")
    assert ok
    fail, _, _ = evaluate_subtask({"id": "subtask_06", "type": "math", "gold": "72"}, "Natalia sold 48 in April and 24 in May.\n#### 96")
    assert not fail


def test_sql_checkers():
    # Spider: department_store
    good_sql = "SELECT name FROM departments WHERE budget > 500000 AND building = 'Baker';"
    bad_sql = "SELECT name FROM departments WHERE budget < 500000;"
    ok, _, _ = evaluate_subtask({"id": "subtask_11", "type": "sql", "gold": "SELECT name FROM departments WHERE budget > 500000 AND building = 'Baker'"}, good_sql)
    assert ok
    fail, _, _ = evaluate_subtask({"id": "subtask_11", "type": "sql", "gold": "SELECT name FROM departments WHERE budget > 500000 AND building = 'Baker'"}, bad_sql)
    assert not fail


def test_qa_checkers():
    # ARC-Challenge: (B)
    ok, _, _ = evaluate_subtask({"id": "subtask_16", "type": "qa", "gold": "(B)"}, "The correct choice is (B).")
    assert ok
    fail, _, _ = evaluate_subtask({"id": "subtask_16", "type": "qa", "gold": "(B)"}, "The correct choice is (A).")
    assert not fail
