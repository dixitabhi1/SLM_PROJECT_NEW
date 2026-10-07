"""
Unit tests for the 20 subtask objective checkers.
Tests both correct solutions (must return True) and broken solutions (must return False).
"""

import pytest
from src.eval.subtask_checkers import evaluate_subtask


def test_code_checkers():
    # Subtask 01: Palindrome
    good_code_1 = """
def is_palindrome(s: str) -> bool:
    clean = [c.lower() for c in s if c.isalnum()]
    return clean == clean[::-1]
"""
    bad_code_1 = "def is_palindrome(s: str) -> bool: return False"
    ok, chk, _ = evaluate_subtask({"id": "subtask_01", "type": "code"}, good_code_1)
    assert ok
    fail, _, _ = evaluate_subtask({"id": "subtask_01", "type": "code"}, bad_code_1)
    assert not fail

    # Subtask 02: Fibonacci
    good_code_2 = """
def fibonacci(n: int) -> int:
    if n <= 0: return 0
    if n == 1: return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
"""
    ok, chk, _ = evaluate_subtask({"id": "subtask_02", "type": "code"}, good_code_2)
    assert ok


def test_math_checkers():
    # Subtask 06: x = 9
    ok, _, _ = evaluate_subtask({"id": "subtask_06", "type": "math"}, "The value of x is 9.")
    assert ok
    fail, _, _ = evaluate_subtask({"id": "subtask_06", "type": "math"}, "The value is 42.")
    assert not fail

    # Subtask 07: Derivative
    ok, _, _ = evaluate_subtask({"id": "subtask_07", "type": "math"}, "f'(x) = 9*x^2 - 10*x + 7")
    assert ok

    # Subtask 08: Circle Area
    ok, _, _ = evaluate_subtask({"id": "subtask_08", "type": "math"}, "Area = 49*pi")
    assert ok

    # Subtask 09: Speed
    ok, _, _ = evaluate_subtask({"id": "subtask_09", "type": "math"}, "The average speed is 72 km/h")
    assert ok

    # Subtask 10: Factors
    ok, _, _ = evaluate_subtask({"id": "subtask_10", "type": "math"}, "(x - 3)(x - 4)")
    assert ok


def test_sql_checkers():
    # Subtask 11
    sql_11 = "SELECT * FROM students WHERE grade = 10 AND age > 15;"
    ok, _, _ = evaluate_subtask({"id": "subtask_11", "type": "sql"}, sql_11)
    assert ok

    # Subtask 12
    sql_12 = "SELECT AVG(total_amount) FROM orders;"
    ok, _, _ = evaluate_subtask({"id": "subtask_12", "type": "sql"}, sql_12)
    assert ok


def test_qa_checkers():
    # Subtask 16
    qa_16 = "An index in a relational database speeds up data retrieval and accelerates queries without full table scans."
    ok, _, _ = evaluate_subtask({"id": "subtask_16", "type": "qa"}, qa_16)
    assert ok

    # Subtask 17
    qa_17 = "Synchronous execution is blocking and executes sequentially, whereas asynchronous execution is non-blocking and enables concurrent execution."
    ok, _, _ = evaluate_subtask({"id": "subtask_17", "type": "qa"}, qa_17)
    assert ok

