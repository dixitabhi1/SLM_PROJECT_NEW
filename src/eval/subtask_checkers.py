"""
Deterministic, objective evaluation checkers for the 20 public benchmark subtasks.
Zero keyword rubrics.
- Code (HumanEval 11, 20, 37, 56, 64): Sandboxed execution with official assertions.
- Math (GSM8K dev 001-005): Exact numeric answer match (integer/fraction).
- SQL (Spider dev): SQLite execution match against reference query result sets.
- QA (ARC-Challenge dev 01-05): Exact multiple-choice option letter match.
"""

import re
import sqlite3
from typing import Tuple, Dict, Any, List
from src.sandbox.runner import execute_python_code


def extract_code_block(text: str) -> str:
    """Extracts python code from markdown code block or returns clean text."""
    pattern = r"```(?:python)?\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    if matches:
        return "\n".join(matches)
    return text


def extract_sql_query(text: str) -> str:
    """Extracts SQL query from markdown code block or plain text."""
    pattern = r"```(?:sql)?\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    if matches:
        raw = matches[0].strip()
    else:
        select_match = re.search(r"(SELECT\s+.*?;)", text, re.DOTALL | re.IGNORECASE)
        if select_match:
            raw = select_match.group(1).strip()
        else:
            raw = text.strip()
    return raw.strip().rstrip(";")


def check_code_subtask(subtask_id: str, output: str, subtask: Dict[str, Any] = None) -> Tuple[bool, str, str]:
    """Runs code in sandbox with official HumanEval assertions."""
    code = extract_code_block(output)
    checker_name = "python_sandbox_test"

    if subtask and "test" in subtask:
        entry_point = subtask.get("entry_point", "")
        test_code = subtask["test"]
        prompt = subtask.get("prompt", "")
        helpers = ""
        if "def poly(" in prompt and "def poly(" not in code:
            helpers += """
def poly(xs: list, x: float):
    import math
    return sum([coeff * math.pow(x, i) for i, coeff in enumerate(xs)])
"""
        full_script = f"""import math
import copy
import random
import re
from typing import List, Tuple, Optional, Any, Dict, Set

{helpers}
{code}

{test_code}

check({entry_point})
print("PASS")
"""
        res = execute_python_code(full_script, timeout_seconds=10.0)
        if res.exit_code == 0 and "PASS" in res.stdout:
            return True, checker_name, "HumanEval assertions passed"
        else:
            err = res.stderr.strip() or res.stdout.strip() or f"Exit code {res.exit_code}"
            return False, checker_name, f"Execution failed: {err[:150]}"

    harnesses = {
        "subtask_01": """
assert string_xor('010', '110') == '100'
assert string_xor('111000', '101010') == '010010'
assert string_xor('1', '1') == '0'
print("PASS")
""",
        "subtask_02": """
assert find_closest_elements([1.0, 2.0, 3.9, 4.0, 5.0, 2.2]) == (3.9, 4.0)
assert find_closest_elements([1.0, 2.0, 5.9, 4.0, 5.0]) == (5.0, 5.9) or find_closest_elements([1.0, 2.0, 5.9, 4.0, 5.0]) == (5.9, 5.0)
print("PASS")
""",
        "subtask_03": """
assert sort_even([1, 2, 3]) == [1, 2, 3]
assert sort_even([5, 6, 3, 4]) == [3, 6, 5, 4]
assert sort_even([1, 2, 3, 0, 5, 6]) == [1, 2, 3, 0, 5, 6]
print("PASS")
""",
        "subtask_04": """
assert correct_bracketing("<>") == True
assert correct_bracketing("<<><>>") == True
assert correct_bracketing("><<>") == False
assert correct_bracketing("<") == False
print("PASS")
""",
        "subtask_05": """
assert vowels_count("abcde") == 2
assert vowels_count("ACEDY") == 3
assert vowels_count("fly") == 1
assert vowels_count("why") == 1
print("PASS")
""",
    }

    harness = harnesses.get(subtask_id)
    if not harness:
        return False, checker_name, f"Unknown code subtask {subtask_id}"

    full_script = f"from typing import List, Tuple, Optional\n{code}\n\n# Test harness\n{harness}"
    res = execute_python_code(full_script, timeout_seconds=10.0)
    if res.exit_code == 0 and "PASS" in res.stdout:
        return True, checker_name, "HumanEval assertions passed"
    else:
        err = res.stderr.strip() or res.stdout.strip() or f"Exit code {res.exit_code}"
        return False, checker_name, f"Execution failed: {err[:150]}"


def check_math_subtask(subtask_id: str, output: str, gold: str) -> Tuple[bool, str, str]:
    """Evaluates GSM8K answers via exact numeric extraction."""
    checker_name = "exact_numeric_test"
    try:
        gold_num = int(gold)
    except Exception:
        return False, checker_name, f"Invalid gold integer '{gold}'"

    # 1. Look for '#### <number>' standard GSM8K delimiter
    hash_match = re.search(r"####\s*(-?\d+)", output)
    if hash_match:
        pred_num = int(hash_match.group(1))
        if pred_num == gold_num:
            return True, checker_name, f"Matched #### {gold_num}"
        return False, checker_name, f"Extracted #### {pred_num} != gold {gold_num}"

    # 2. Look for final sentence number or boxed number
    boxed_match = re.search(r"\\boxed\{(-?\d+)\}", output)
    if boxed_match:
        pred_num = int(boxed_match.group(1))
        if pred_num == gold_num:
            return True, checker_name, f"Matched \\boxed{{{gold_num}}}"
        return False, checker_name, f"Extracted boxed {pred_num} != gold {gold_num}"

    # 3. Look for explicit answer declaration: 'answer is 72' or '= 72'
    decl_match = re.findall(r"(?:answer\s+is\s+|total\s+is\s+|equal\s+to\s+|=\s*)(-?\d+)", output, re.IGNORECASE)
    if decl_match:
        if int(decl_match[-1]) == gold_num:
            return True, checker_name, f"Matched declared {gold_num}"

    # 4. Fallback: extract last standalone integer in output
    all_nums = re.findall(r"\b(-?\d+)\b", output)
    if all_nums and int(all_nums[-1]) == gold_num:
        return True, checker_name, f"Last integer matched gold {gold_num}"

    return False, checker_name, f"Did not find gold number {gold_num} in output"


def check_sql_subtask(subtask_id: str, output: str, gold_query: str, subtask: Dict[str, Any] = None) -> Tuple[bool, str, str]:
    """Executes generated SQL against Spider schema and compares result set against gold SQL."""
    checker_name = "sqlite_result_match_test"
    query = extract_sql_query(output)

    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    try:
        if subtask and "schema_ddl" in subtask:
            for stmt in subtask["schema_ddl"].split(";"):
                if stmt.strip():
                    cursor.execute(stmt)
            for stmt in subtask["init_sql"].split(";"):
                if stmt.strip():
                    cursor.execute(stmt)
            cursor.execute(subtask["gold_sql"])
            gold_results = set(cursor.fetchall())

            cursor.execute(query)
            pred_results = set(cursor.fetchall())

            if pred_results == gold_results:
                return True, checker_name, f"Result set matches gold exactly: {pred_results}"
            else:
                return False, checker_name, f"Result mismatch: predicted {pred_results} vs gold {gold_results}"

        # Legacy fixed subtasks fallback
        if subtask_id == "subtask_11":
            cursor.execute("CREATE TABLE departments(dept_id INT, name TEXT, budget REAL, building TEXT);")
            cursor.execute("INSERT INTO departments VALUES (1, 'CS', 600000, 'Baker'), (2, 'Math', 400000, 'Baker'), (3, 'Physics', 700000, 'Turing');")
        elif subtask_id == "subtask_12":
            cursor.execute("CREATE TABLE courses(course_id INT, course_name TEXT, credits INT);")
            cursor.execute("INSERT INTO courses VALUES (101, 'Intro', 3), (102, 'Advanced', 5), (103, 'Seminar', 1);")
        elif subtask_id == "subtask_13":
            cursor.execute("CREATE TABLE cars(car_id INT, make TEXT, model TEXT, year INT, horsepower INT);")
            cursor.execute("INSERT INTO cars VALUES (1, 'Ford', 'Mustang', 2020, 450), (2, 'Chevy', 'Corvette', 2021, 495), (3, 'Tesla', 'Model 3', 2022, 350);")
        elif subtask_id == "subtask_14":
            cursor.execute("CREATE TABLE city(id INT, name TEXT, countrycode TEXT, population INT);")
            cursor.execute("INSERT INTO city VALUES (1, 'Tokyo', 'JPN', 14000000), (2, 'Kyoto', 'JPN', 1475000), (3, 'Nara', 'JPN', 360000);")
        elif subtask_id == "subtask_15":
            cursor.execute("CREATE TABLE flights(flight_id INT, origin TEXT, destination TEXT, distance REAL);")
            cursor.execute("INSERT INTO flights VALUES (1, 'JFK', 'LAX', 2475.0), (2, 'JFK', 'ORD', 740.0), (3, 'BOS', 'MIA', 1258.0);")

        cursor.execute(gold_query)
        gold_results = set(cursor.fetchall())

        cursor.execute(query)
        pred_results = set(cursor.fetchall())

        if pred_results == gold_results:
            return True, checker_name, f"Result set matches gold exactly: {pred_results}"
        else:
            return False, checker_name, f"Result mismatch: predicted {pred_results} vs gold {gold_results}"

    except Exception as e:
        return False, checker_name, f"SQLite query execution error: {str(e)[:150]}"
    finally:
        conn.close()


def check_qa_subtask(subtask_id: str, output: str, gold_option: str) -> Tuple[bool, str, str]:
    """Objective multiple-choice letter extraction for ARC-Challenge."""
    checker_name = "multiple_choice_exact_match"
    gold_letter = gold_option.strip("()").upper()

    match = re.search(r"(?:answer\s*(?:is|:)?\s*|option\s*|[(\[])([A-D])[)\]]", output, re.IGNORECASE)
    if match:
        pred_letter = match.group(1).upper()
        if pred_letter == gold_letter:
            return True, checker_name, f"Selected correct option ({pred_letter})"
        return False, checker_name, f"Selected option ({pred_letter}) != gold ({gold_letter})"

    standalone = re.findall(r"\b([A-D])\b", output)
    if standalone:
        pred_letter = standalone[0].upper()
        if pred_letter == gold_letter:
            return True, checker_name, f"Selected standalone letter matched gold ({gold_letter})"
        return False, checker_name, f"Selected standalone letter ({pred_letter}) != gold ({gold_letter})"

    return False, checker_name, f"Could not extract choice letter from output"


def evaluate_subtask(subtask: Dict[str, Any], output: str) -> Tuple[bool, str, str]:
    """Routes subtask to the appropriate objective checker."""
    st_type = subtask.get("type", "")
    st_id = subtask.get("id", "")
    gold = subtask.get("gold") or subtask.get("gold_answer") or subtask.get("gold_sql") or subtask.get("gold_letter") or ""

    if st_type == "code":
        return check_code_subtask(st_id, output, subtask)
    elif st_type == "math":
        return check_math_subtask(st_id, output, gold)
    elif st_type == "sql":
        return check_sql_subtask(st_id, output, gold, subtask)
    elif st_type == "qa":
        return check_qa_subtask(st_id, output, gold)
    else:
        return False, "unknown_type", f"Unrecognized subtask type '{st_type}'"
