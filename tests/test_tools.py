"""
Unit tests for deterministic local tools:
Python executor, SymPy math tool, SQLite engine, BM25 retriever.
Zero LLM inside.
"""

import pytest
from src.tools.python_tool import PythonExecutionTool
from src.tools.math_tool import SymbolicMathTool
from src.tools.sql_tool import SQLExecutionTool
from src.tools.retriever_tool import BM25RetrieverTool


def test_python_tool_pass():
    tool = PythonExecutionTool(timeout_seconds=5.0)
    code = "def add(a, b): return a + b"
    tests = ["assert add(2, 3) == 5", "assert add(-1, 1) == 0"]
    verdict = tool.verify_against_tests(code, tests)
    assert verdict.verdict == "PASS"


def test_python_tool_fail():
    tool = PythonExecutionTool(timeout_seconds=5.0)
    code = "def add(a, b): return a * b"  # Buggy implementation
    tests = ["assert add(2, 3) == 5"]
    verdict = tool.verify_against_tests(code, tests)
    assert verdict.verdict == "FAIL"


def test_math_tool_symbolic_equivalence():
    tool = SymbolicMathTool()
    # (x + 1)^2 == x^2 + 2x + 1
    v1 = tool.verify_equivalence("(x + 1)**2", "x**2 + 2*x + 1")
    assert v1.is_equivalent
    assert v1.verdict == "PASS"

    # 1/2 == 0.5
    v2 = tool.verify_equivalence("1/2", "0.5")
    assert v2.is_equivalent
    assert v2.verdict == "PASS"

    # LaTeX boxed format
    v3 = tool.verify_equivalence("\\boxed{42}", "42")
    assert v3.is_equivalent
    assert v3.verdict == "PASS"

    # Non-equivalent
    v4 = tool.verify_equivalence("2*x + 1", "2*x + 2")
    assert not v4.is_equivalent
    assert v4.verdict == "FAIL"


def test_sql_tool_execution_match():
    tool = SQLExecutionTool(":memory:")
    ddl = """
    CREATE TABLE employees (id INT, name TEXT, salary INT);
    INSERT INTO employees VALUES (1, 'Alice', 90000), (2, 'Bob', 80000), (3, 'Charlie', 85000);
    """
    tool.execute_script(ddl)

    gold = "SELECT name FROM employees WHERE salary > 82000;"
    cand = "SELECT name FROM employees WHERE salary >= 85000;"
    verdict = tool.verify_query_execution_match(cand, gold)
    assert verdict.is_match
    assert verdict.verdict == "PASS"
    assert verdict.cand_row_count == 2
    assert verdict.gold_row_count == 2

    bad_cand = "SELECT name FROM employees WHERE salary > 100000;"
    bad_verdict = tool.verify_query_execution_match(bad_cand, gold)
    assert not bad_verdict.is_match
    assert bad_verdict.verdict == "FAIL"
    tool.close()


def test_bm25_retriever():
    retriever = BM25RetrieverTool()
    docs = [
        {"id": "doc_1", "text": "Python is a high-level general-purpose programming language."},
        {"id": "doc_2", "text": "SQLite is a C-language library that implements a small fast SQL database engine."},
        {"id": "doc_3", "text": "SymPy is a Python library for symbolic mathematics and algebra."},
    ]
    retriever.index_corpus(docs)

    results = retriever.retrieve("symbolic mathematics algebra", top_k=1)
    assert len(results) == 1
    assert results[0].doc_id == "doc_3"
    assert "SymPy" in results[0].text
    assert results[0].rank == 1

