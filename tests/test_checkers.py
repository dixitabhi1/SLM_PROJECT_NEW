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
    # 5. Column permutation equivalence (e.g. city, count vs count, city)
    perm_subtask = {
        "id": "perm_sql_test",
        "type": "sql",
        "schema_ddl": "CREATE TABLE city (name TEXT, pop INT);",
        "init_sql": "INSERT INTO city VALUES ('Tokyo', 10), ('Kyoto', 5);",
        "gold_sql": "SELECT pop, name FROM city;",
    }
    from src.eval.versioned_scorer import score_record
    res_perm = score_record(perm_subtask, "SELECT name, pop FROM city;")
    assert res_perm["passed"], f"Column permutation failed: {res_perm}"




def test_qa_checkers():
    # 1. ARC-Challenge: direct statement (B)
    ok, _, _ = evaluate_subtask({"id": "subtask_16", "type": "qa", "gold": "(B)"}, "The correct choice is (B).")
    assert ok
    fail, _, _ = evaluate_subtask({"id": "subtask_16", "type": "qa", "gold": "(B)"}, "The correct choice is (A).")
    assert not fail

    # 2. CoT reasoning evaluating (A), (B), (C), (D) in order, then declaring Answer: (B)
    cot_reasoning = (
        "Let's evaluate each option:\n"
        "* (A) This option is incorrect because proteins denature.\n"
        "* (B) Heating changes the chemical bonds, causing coagulation.\n"
        "* (C) Incorrect, solids do not rise.\n"
        "* (D) Incorrect, bacteria death is secondary.\n\n"
        "Therefore, option B is correct.\n"
        "Answer: (B)"
    )
    ok_cot, _, reason_cot = evaluate_subtask({"id": "subtask_16", "type": "qa", "gold": "B"}, cot_reasoning)
    assert ok_cot, f"CoT reasoning failed: {reason_cot}"

    # 3. Boxed answer format
    ok_box, _, _ = evaluate_subtask({"id": "subtask_16", "type": "qa", "gold": "C"}, "The answer is \\boxed{C}")
    assert ok_box


def test_track_b_scorer_innocent_numbers():
    from src.eval.fact_checklist_scorer import score_fact_checklist

    # Test checklist with numeric targets (units: kHz, kW) and distractors (banned numbers and tokens)
    checklist = [
        {"type": "token", "value": "Inverter-ZX9", "description": "primary component Inverter-ZX9"},
        {"type": "numeric", "target": 731.4, "tolerance": 0.5, "unit": "kHz", "description": "switching frequency 731.4 kHz"},
        {"type": "numeric", "target": 1840.0, "tolerance": 1.0, "unit": "kW", "description": "continuous power 1840 kW"},
        {
            "type": "negative",
            "banned_tokens": ["680.0", "1650", "Inverter-AX2", "512.0", "420"],
            "banned_numbers": [
                {"target": 680.0, "unit": "kHz"},
                {"target": 1650.0, "unit": "kW"},
                {"target": 512.0, "unit": "kHz"},
                {"target": 420.0, "unit": "kW"}
            ],
            "description": "banned superseded v4.1 and auxiliary inverter values"
        }
    ]

    # Case 1: Correct answer with innocent numbers ("680 cycles", "15 minutes", "step 420")
    # Must PASS because innocent numbers do not match on number boundaries with the banned unit!
    ans_with_innocent_numbers = (
        "In step 15, we evaluated Inverter-ZX9 over 680 operating cycles and 420 test runs.\n"
        "switching_frequency: 731.4 kHz\n"
        "continuous_power: 1840 kW"
    )
    res_innocent = score_fact_checklist(ans_with_innocent_numbers, checklist)
    assert res_innocent["binary_pass"] is True, f"Innocent numbers falsely failed: {res_innocent['negative_violations']}"
    assert res_innocent["recall"] == 1.0
    assert len(res_innocent["negative_violations"]) == 0

    # Case 2: Output contains distractor WITH its unit ("680.0 kHz")
    # Must FAIL with negative violation
    ans_with_distractor_unit = (
        "component: Inverter-ZX9\n"
        "switching_frequency: 680.0 kHz\n"
        "continuous_power: 1840 kW"
    )
    res_distractor = score_fact_checklist(ans_with_distractor_unit, checklist)
    assert res_distractor["binary_pass"] is False
    assert any("680" in v and "kHz" in v for v in res_distractor["negative_violations"])

    # Case 3: Output contains banned component name ("Inverter-AX2")
    # Must FAIL
    ans_with_banned_comp = (
        "component: Inverter-AX2\n"
        "switching_frequency: 731.4 kHz\n"
        "continuous_power: 1840 kW"
    )
    res_comp = score_fact_checklist(ans_with_banned_comp, checklist)
    assert res_comp["binary_pass"] is False
    assert any("Inverter-AX2" in v for v in res_comp["negative_violations"])

    # Case 4: Answer exceeds 75-word cap
    long_answer = "Inverter-ZX9 731.4 kHz 1840 kW " + " ".join(["word"] * 80)
    res_long = score_fact_checklist(long_answer, checklist)
    assert res_long["binary_pass"] is False
    assert "exceeds length cap" in res_long["failed_facts"][0]

