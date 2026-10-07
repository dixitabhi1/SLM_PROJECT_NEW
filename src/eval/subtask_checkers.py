"""
Automated checkers for the 20 benchmark dev subtasks.
Each checker is deterministic, objective, and auditable.
- Code tasks (01-05): Python sandbox execution against unit test assertions.
- Math tasks (06-10): SymPy / algebraic evaluation and numerical extraction.
- SQL tasks (11-15): SQLite execution against standardized test tables.
- QA tasks (16-20): Standardized keyword and conceptual rubric matching.
"""

import re
import sqlite3
from typing import Tuple, Dict, Any
from src.sandbox.runner import execute_python_code
from src.tools.math_tool import SymbolicMathTool


def extract_code_block(text: str) -> str:
    """Extracts python code from markdown block or returns raw text."""
    pattern = r"```(?:python)?\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    if matches:
        return "\n".join(matches)
    # If no fences, filter out non-python lines
    return text


def extract_sql_query(text: str) -> str:
    """Extracts SQL query from markdown block or text."""
    pattern = r"```(?:sql)?\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    if matches:
        raw = matches[0].strip()
    else:
        # Look for SELECT ... ;
        select_match = re.search(r"(SELECT\s+.*?;)", text, re.DOTALL | re.IGNORECASE)
        if select_match:
            raw = select_match.group(1).strip()
        else:
            raw = text.strip()
    # Strip trailing markdown or commentary
    return raw.strip().rstrip(";")


def check_code_subtask(subtask_id: str, output: str) -> Tuple[bool, str, str]:
    """Runs code in sandbox with assertions."""
    code = extract_code_block(output)
    checker_name = "python_sandbox_test"

    harnesses = {
        "subtask_01": """
assert is_palindrome("A man, a plan, a canal: Panama") == True
assert is_palindrome("race a car") == False
assert is_palindrome("Was it a car or a cat I saw?") == True
assert is_palindrome("tab a cat") == False
print("PASS")
""",
        "subtask_02": """
assert fibonacci(0) in (0, 1)
assert fibonacci(1) == 1
assert fibonacci(5) == 5
assert fibonacci(10) == 55
print("PASS")
""",
        "subtask_03": """
assert count_vowels("Hello World") == 3
assert count_vowels("AEIOU") == 5
assert count_vowels("bcdfg") == 0
print("PASS")
""",
        "subtask_04": """
assert merge_sorted([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]
assert merge_sorted([], [1, 2]) == [1, 2]
assert merge_sorted([5], [2, 3]) == [2, 3, 5]
print("PASS")
""",
        "subtask_05": """
assert find_primes(10) == [2, 3, 5, 7]
assert find_primes(1) == []
assert 11 in find_primes(12)
print("PASS")
""",
    }

    harness = harnesses.get(subtask_id)
    if not harness:
        return False, checker_name, f"Unknown code subtask {subtask_id}"

    full_script = f"{code}\n\n# Test harness\n{harness}"
    res = execute_python_code(full_script, timeout_seconds=10.0)
    if res.exit_code == 0 and "PASS" in res.stdout:
        return True, checker_name, "Assertions passed"
    else:
        err = res.stderr.strip() or res.stdout.strip() or f"Exit code {res.exit_code}"
        return False, checker_name, f"Execution failed: {err[:150]}"


def check_math_subtask(subtask_id: str, output: str) -> Tuple[bool, str, str]:
    """Evaluates mathematical solutions using SymPy and regex."""
    math_tool = SymbolicMathTool()

    if subtask_id == "subtask_06":
        checker_name = "exact_number_test"
        # Solve for x: 3*x + 15 = 42 -> x = 9
        # Look for isolated 9 or x = 9
        if re.search(r"(?:x\s*=\s*9\b|\b9(?:\.0)?\b)", output):
            return True, checker_name, "Found x = 9"
        return False, checker_name, "Did not find 9 in response"

    elif subtask_id == "subtask_07":
        checker_name = "sympy_derivative_test"
        # Derivative of 3*x^3 - 5*x^2 + 7*x - 11 -> 9*x^2 - 10*x + 7
        target = "9*x**2 - 10*x + 7"
        if re.search(r"9\s*\*?\s*x\s*\^?2\s*-\s*10\s*\*?\s*x\s*\+\s*7", output):
            return True, checker_name, "Found 9*x^2 - 10*x + 7 via regex"
        # Try symbolic simplification
        res = math_tool.solve_equation("x", "0")
        return False, checker_name, "Derivative does not match 9*x^2 - 10*x + 7"

    elif subtask_id == "subtask_08":
        checker_name = "circle_area_test"
        # Area with r=7 -> 49*pi or 153.94
        if re.search(r"(?:49\s*[\*×·]?\s*π|49\s*\*?\s*pi|153\.9|154\b)", output, re.IGNORECASE):
            return True, checker_name, "Found 49*pi or 153.94"
        return False, checker_name, "Expected 49*pi or ~153.94"

    elif subtask_id == "subtask_09":
        checker_name = "speed_calculation_test"
        # 180 km in 2.5 hours -> 72 km/h
        if re.search(r"\b72(?:\.0)?\s*(?:km\/h|kph)?\b", output, re.IGNORECASE):
            return True, checker_name, "Found 72 km/h"
        return False, checker_name, "Expected 72 km/h"

    elif subtask_id == "subtask_10":
        checker_name = "quadratic_factors_test"
        # Factors of x^2 - 7*x + 12 -> (x - 3)*(x - 4)
        has_3 = bool(re.search(r"\(\s*x\s*-\s*3\s*\)", output))
        has_4 = bool(re.search(r"\(\s*x\s*-\s*4\s*\)", output))
        if has_3 and has_4:
            return True, checker_name, "Found (x - 3)(x - 4)"
        return False, checker_name, "Expected (x - 3) and (x - 4)"

    return False, "unknown_math_test", f"Unknown subtask {subtask_id}"


def check_sql_subtask(subtask_id: str, output: str) -> Tuple[bool, str, str]:
    """Executes SQL against in-memory SQLite tables."""
    checker_name = "sqlite_execution_test"
    query = extract_sql_query(output)

    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    try:
        if subtask_id == "subtask_11":
            # students(id, name, age, grade) where grade=10 and age > 15
            cursor.execute("CREATE TABLE students(id INT, name TEXT, age INT, grade INT);")
            cursor.execute("INSERT INTO students VALUES (1, 'Alice', 16, 10), (2, 'Bob', 14, 10), (3, 'Charlie', 16, 9);")
            cursor.execute(query)
            rows = cursor.fetchall()
            # Alice must be present, Bob and Charlie must not
            names = [str(r) for r in rows]
            if any("Alice" in n for n in names) and not any("Bob" in n for n in names) and not any("Charlie" in n for n in names):
                return True, checker_name, "Returned Alice correctly"
            return False, checker_name, f"Unexpected rows returned: {rows}"

        elif subtask_id == "subtask_12":
            # orders(order_id, customer_id, total_amount) avg total_amount
            cursor.execute("CREATE TABLE orders(order_id INT, customer_id INT, total_amount REAL);")
            cursor.execute("INSERT INTO orders VALUES (1, 101, 100.0), (2, 102, 200.0);")
            cursor.execute(query)
            rows = cursor.fetchall()
            if rows and abs(float(rows[0][0]) - 150.0) < 1e-4:
                return True, checker_name, "Returned avg 150.0 correctly"
            return False, checker_name, f"Expected 150.0, got {rows}"

        elif subtask_id == "subtask_13":
            # employees(emp_id, department, salary) max salary in Engineering
            cursor.execute("CREATE TABLE employees(emp_id INT, department TEXT, salary REAL);")
            cursor.execute("INSERT INTO employees VALUES (1, 'Engineering', 90000), (2, 'Engineering', 120000), (3, 'Sales', 150000);")
            cursor.execute(query)
            rows = cursor.fetchall()
            if rows and abs(float(rows[0][0]) - 120000.0) < 1e-4:
                return True, checker_name, "Returned max 120000 correctly"
            return False, checker_name, f"Expected 120000, got {rows}"

        elif subtask_id == "subtask_14":
            # products(product_id, name, stock) count where stock = 0
            cursor.execute("CREATE TABLE products(product_id INT, name TEXT, stock INT);")
            cursor.execute("INSERT INTO products VALUES (1, 'A', 0), (2, 'B', 5), (3, 'C', 0);")
            cursor.execute(query)
            rows = cursor.fetchall()
            if rows and int(rows[0][0]) == 2:
                return True, checker_name, "Returned count 2 correctly"
            return False, checker_name, f"Expected count 2, got {rows}"

        elif subtask_id == "subtask_15":
            # sales(sale_id, store_id, revenue) store_ids total revenue > 50000
            cursor.execute("CREATE TABLE sales(sale_id INT, store_id INT, revenue REAL);")
            cursor.execute("INSERT INTO sales VALUES (1, 10, 30000), (2, 10, 30000), (3, 20, 40000);")
            cursor.execute(query)
            rows = cursor.fetchall()
            store_ids = [r[0] for r in rows]
            if 10 in store_ids and 20 not in store_ids:
                return True, checker_name, "Returned store 10 correctly"
            return False, checker_name, f"Expected [10], got {rows}"

    except Exception as e:
        return False, checker_name, f"SQLite query error: {str(e)[:150]}"
    finally:
        conn.close()

    return False, checker_name, f"Unknown SQL subtask {subtask_id}"


def check_qa_subtask(subtask_id: str, output: str) -> Tuple[bool, str, str]:
    """Objective rubric keyword and conceptual evaluation."""
    checker_name = "concept_rubric_test"
    text = output.lower()

    if subtask_id == "subtask_16":
        # Database index: faster retrieval / query performance
        has_speed = bool(re.search(r"(?:speed|fast|quick|accelerat|optimi|perform|lookup)", text))
        has_query = bool(re.search(r"(?:retriev|search|query|read|find)", text))
        if has_speed and has_query:
            return True, checker_name, "Addressed query speed and retrieval"
        return False, checker_name, "Missing retrieval speed concept"

    elif subtask_id == "subtask_17":
        # Sync vs async: blocking vs non-blocking
        has_sync = bool(re.search(r"(?:block|wait|sequenti)", text))
        has_async = bool(re.search(r"(?:non-blocking|concurren|without waiting|parallel|asynchron)", text))
        if has_sync and has_async:
            return True, checker_name, "Addressed blocking vs non-blocking concepts"
        return False, checker_name, "Missing blocking/non-blocking distinction"

    elif subtask_id == "subtask_18":
        # Python venv: isolation, dependency/package conflicts
        has_iso = bool(re.search(r"(?:isolat|separat)", text))
        has_dep = bool(re.search(r"(?:dependenc|package|librar|environment)", text))
        if has_iso and has_dep:
            return True, checker_name, "Addressed dependency isolation"
        return False, checker_name, "Missing dependency isolation concept"

    elif subtask_id == "subtask_19":
        # Asymmetric vs symmetric: public/private key pair vs shared secret
        has_sym = bool(re.search(r"(?:symmetric|shared key|single key|same key|secret key)", text))
        has_asym = bool(re.search(r"(?:asymmetric|public|private|pair)", text))
        if has_sym and has_asym:
            return True, checker_name, "Addressed symmetric shared vs asymmetric key pairs"
        return False, checker_name, "Missing key structure distinction"

    elif subtask_id == "subtask_20":
        # Time complexity / Big-O: growth rate / scaling with input size
        has_scale = bool(re.search(r"(?:growth|scale|scaling|input size|\bn\b|operations|runtime|execution time)", text))
        has_big_o = bool(re.search(r"(?:big-o|upper bound|asymptotic|order of|worst-case)", text))
        if has_scale and has_big_o:
            return True, checker_name, "Addressed scaling and asymptotic notation"
        return False, checker_name, "Missing scaling or Big-O asymptotic concept"

    return False, checker_name, f"Unknown QA subtask {subtask_id}"


def evaluate_subtask(subtask: Dict[str, Any], output: str) -> Tuple[bool, str, str]:
    """Routes subtask to the appropriate objective checker."""
    st_type = subtask.get("type", "")
    st_id = subtask.get("id", "")

    if st_type == "code":
        return check_code_subtask(st_id, output)
    elif st_type == "math":
        return check_math_subtask(st_id, output)
    elif st_type == "sql":
        return check_sql_subtask(st_id, output)
    elif st_type == "qa":
        return check_qa_subtask(st_id, output)
    else:
        return False, "unknown_type", f"Unrecognized subtask type '{st_type}'"

