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
    # 1. Spider legacy schema test
    good_sql = "SELECT name FROM departments WHERE budget > 500000 AND building = 'Baker';"
    bad_sql = "SELECT name FROM departments WHERE budget < 500000;"
    ok, chk, _ = evaluate_subtask({"id": "subtask_11", "type": "sql", "gold": "SELECT name FROM departments WHERE budget > 500000 AND building = 'Baker'"}, good_sql)
    assert ok
    assert chk == "sqlite_execution_test"
    fail, _, _ = evaluate_subtask({"id": "subtask_11", "type": "sql", "gold": "SELECT name FROM departments WHERE budget > 500000 AND building = 'Baker'"}, bad_sql)
    assert not fail

    # 2. Semantically equivalent query with completely different text (lowercase, alias, rearranged WHERE clause)
    # Proves it is REAL EXECUTION, not text matching!
    equiv_sql = "```sql\nselect d.name from departments as d where d.building = 'Baker' and d.budget > 500000;\n```"
    ok_equiv, _, reason = evaluate_subtask({"id": "subtask_11", "type": "sql", "gold": "SELECT name FROM departments WHERE budget > 500000 AND building = 'Baker'"}, equiv_sql)
    assert ok_equiv, f"Equivalent SQL failed: {reason}"

    # 3. Syntax error in SQL returns failure cleanly
    broken_sql = "SELECT name FROM WHERE syntax error;"
    fail_syn, _, reason_syn = evaluate_subtask({"id": "subtask_11", "type": "sql", "gold": "SELECT name FROM departments;"}, broken_sql)
    assert not fail_syn
    assert "SQLite syntax/execution error" in reason_syn

    # 4. Dynamic subtask with schema_ddl and init_sql
    dynamic_subtask = {
        "id": "hard_sql_test",
        "type": "sql",
        "schema_ddl": "CREATE TABLE employees (id INT, salary REAL);",
        "init_sql": "INSERT INTO employees VALUES (1, 50000), (2, 80000), (3, 120000);",
        "gold_sql": "SELECT COUNT(*) FROM employees WHERE salary >= 75000;",
    }
    # Model uses slightly different valid query
    model_sql = "SELECT count(id) FROM employees WHERE salary > 74999.0"
    ok_dyn, _, _ = evaluate_subtask(dynamic_subtask, model_sql)
    assert ok_dyn



def test_qa_checkers():
    # ARC-Challenge: (B)
    ok, _, _ = evaluate_subtask({"id": "subtask_16", "type": "qa", "gold": "(B)"}, "The correct choice is (B).")
    assert ok
    fail, _, _ = evaluate_subtask({"id": "subtask_16", "type": "qa", "gold": "(B)"}, "The correct choice is (A).")
    assert not fail
