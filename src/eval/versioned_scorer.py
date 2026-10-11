"""
Versioned Objective Scorer Suite (Version 1.0.0).

Unified, versioned scoring module separating evaluation/scoring from inference generation.
Zero keyword rubrics or floating heuristics.

Supports:
1. Python Code (HumanEval execution in sandboxed sub-process with official assertions).
2. GSM8K Math (Exact numeric extraction: #### <number>, \\boxed{<number>}, declared answer).
3. Spider SQL (Execution match against SQLite DB with multiset row equality and column permutation bijection).
4. ARC-Challenge QA (Objective multiple choice extraction: explicit final Answer: (X), boxed, or option letter).
5. Track B HyperGrid (Deterministic fact checklist verification with word cap, numeric tolerances, unit checks, and distractor rejection).
"""

import os
import sys
import re
import sqlite3
import itertools
from typing import Tuple, Dict, Any, List, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from src.sandbox.runner import execute_python_code
from src.eval.fact_checklist_scorer import score_fact_checklist

SCORER_VERSION = "1.0.0"


def extract_code_block(text: str) -> str:
    """Extracts python code from markdown code block or returns clean text."""
    pattern = r"```(?:python)?\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    if matches:
        return "\n".join(matches)
    return text


def extract_sql_query(text: str) -> str:
    """Extracts SQL query from markdown code block or plain text."""
    sql_matches = re.findall(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if sql_matches and "SELECT" in sql_matches[0].upper():
        return sql_matches[0].strip().rstrip(";")

    select_match = re.search(r"(SELECT\s+.*?;)", text, re.DOTALL | re.IGNORECASE)
    if select_match:
        return select_match.group(1).strip().rstrip(";")

    matches = re.findall(r"```(?:sql)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if matches and "SELECT" in matches[0].upper():
        return matches[0].strip().rstrip(";")

    return text.strip().rstrip(";")


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

    # Legacy harnesses
    harnesses = {
        "subtask_01": "assert string_xor('010', '110') == '100'\nassert string_xor('111000', '101010') == '010010'\nassert string_xor('1', '1') == '0'\nprint('PASS')",
        "subtask_02": "assert find_closest_elements([1.0, 2.0, 3.9, 4.0, 5.0, 2.2]) == (3.9, 4.0)\nprint('PASS')",
        "subtask_03": "assert sort_even([1, 2, 3]) == [1, 2, 3]\nassert sort_even([5, 6, 3, 4]) == [3, 6, 5, 4]\nprint('PASS')",
        "subtask_04": "assert correct_bracketing('<>') == True\nassert correct_bracketing('<<><>>') == True\nprint('PASS')",
        "subtask_05": "assert vowels_count('abcde') == 2\nassert vowels_count('ACEDY') == 3\nprint('PASS')",
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


def _normalize_sql_val(val: Any) -> Any:
    """Normalizes cell values for robust comparison (e.g. float rounding)."""
    if isinstance(val, float):
        return round(val, 4)
    if isinstance(val, str):
        return val.strip()
    return val


def _normalize_row(row: Tuple[Any, ...]) -> Tuple[Any, ...]:
    return tuple(_normalize_sql_val(v) for v in row)


def check_sql_subtask(subtask_id: str, output: str, gold_query: str, subtask: Dict[str, Any] = None) -> Tuple[bool, str, str]:
    """
    Executes predicted SQL against real SQLite database and compares result rows.
    Supports multiset row equality and column permutation bijection.
    """
    checker_name = "sqlite_execution_test"
    query = extract_sql_query(output)

    if not query or not query.strip():
        return False, checker_name, "Empty or missing SQL query in output"

    conn = None
    try:
        # 1. Connect to database
        if subtask and "schema_ddl" in subtask:
            conn = sqlite3.connect(":memory:")
            cursor = conn.cursor()
            for stmt in subtask["schema_ddl"].split(";"):
                if stmt.strip():
                    cursor.execute(stmt)
            for stmt in subtask.get("init_sql", "").split(";"):
                if stmt.strip():
                    cursor.execute(stmt)
            gold_sql = subtask.get("gold_sql", gold_query)
        elif subtask and subtask.get("db_id"):
            db_id = subtask["db_id"]
            db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_id, f"{db_id}.sqlite")
            if not os.path.exists(db_path):
                db_path = os.path.join(REPO_ROOT, "data", "spider_databases", "all_databases", db_id, f"{db_id}.sqlite")
            if not os.path.exists(db_path):
                return False, checker_name, f"Database file not found for db_id: {db_id}"
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            gold_sql = subtask.get("gold_query") or subtask.get("gold_sql") or gold_query
        else:
            conn = sqlite3.connect(":memory:")
            cursor = conn.cursor()
            gold_sql = gold_query

        # 2. Execute Gold SQL to obtain reference result rows
        cursor.execute(gold_sql)
        gold_raw_rows = cursor.fetchall()
        gold_rows = [_normalize_row(r) for r in gold_raw_rows]

        # 3. Execute Predicted SQL against the same SQLite database
        try:
            cursor.execute(query)
            pred_raw_rows = cursor.fetchall()
        except sqlite3.Error as sql_err:
            return False, checker_name, f"SQLite syntax/execution error: {str(sql_err)}"

        pred_rows = [_normalize_row(r) for r in pred_raw_rows]

        # 4. Compare result rows
        order_matters = bool(re.search(r"\bORDER\s+BY\b", gold_sql, re.IGNORECASE))
        if order_matters:
            if pred_rows == gold_rows:
                return True, checker_name, f"Ordered result rows match gold ({len(pred_rows)} rows)"
            # Column permutation under ordered rows
            if len(pred_rows) == len(gold_rows) and pred_rows and len(pred_rows[0]) == len(gold_rows[0]):
                k = len(gold_rows[0])
                for perm in itertools.permutations(range(k)):
                    permuted = [tuple(r[i] for i in perm) for r in pred_rows]
                    if permuted == gold_rows:
                        return True, checker_name, f"Ordered result rows match gold under column permutation ({len(pred_rows)} rows)"
            return False, checker_name, f"Ordered rows mismatch: got {pred_rows} != gold {gold_rows}"
        else:
            # Multiset comparison: row count and elements must match regardless of sort
            if sorted(pred_rows, key=lambda r: str(r)) == sorted(gold_rows, key=lambda r: str(r)):
                return True, checker_name, f"Result rows match gold multiset ({len(pred_rows)} rows)"
            # Column permutation under multiset equality
            if len(pred_rows) == len(gold_rows) and pred_rows and len(pred_rows[0]) == len(gold_rows[0]):
                k = len(gold_rows[0])
                for perm in itertools.permutations(range(k)):
                    permuted = [tuple(r[i] for i in perm) for r in pred_rows]
                    if sorted(permuted, key=lambda r: str(r)) == sorted(gold_rows, key=lambda r: str(r)):
                        return True, checker_name, f"Result rows match gold multiset under column permutation ({len(pred_rows)} rows)"
            return False, checker_name, f"Result rows mismatch: got {pred_rows} != gold {gold_rows}"

    except Exception as e:
        return False, checker_name, f"SQLite execution failure: {str(e)[:150]}"
    finally:
        if conn:
            conn.close()


def check_qa_subtask(subtask_id: str, output: str, gold_option: str) -> Tuple[bool, str, str]:
    """Objective multiple-choice letter extraction for ARC-Challenge."""
    checker_name = "multiple_choice_exact_match"
    gold_letter = gold_option.strip("()").upper()

    # 1. Primary: Explicit answer declaration (e.g. "Answer: (B)", "Answer: B", "Final Answer: B")
    # Take the LAST occurrence in case the model discusses options earlier
    explicit_matches = re.findall(
        r"(?:answer\s*(?:is|:)?\s*|final\s+answer\s*(?:is|:)?\s*)(?:\()?([A-D])(?:\))?",
        output,
        re.IGNORECASE,
    )
    if explicit_matches:
        pred_letter = explicit_matches[-1].upper()
        if pred_letter == gold_letter:
            return True, checker_name, f"Selected correct option ({pred_letter})"
        return False, checker_name, f"Selected option ({pred_letter}) != gold ({gold_letter})"

    # 2. Boxed answer format (e.g. \boxed{B} or \boxed{(B)})
    boxed = re.findall(r"\\boxed\{[(\[]?([A-D])[)\]]?\}", output, re.IGNORECASE)
    if boxed:
        pred_letter = boxed[-1].upper()
        if pred_letter == gold_letter:
            return True, checker_name, f"Selected correct boxed option ({pred_letter})"
        return False, checker_name, f"Selected boxed option ({pred_letter}) != gold ({gold_letter})"

    # 3. Secondary: "correct choice is (B)", "option is (B)"
    secondary_matches = re.findall(
        r"(?:correct\s+(?:choice|option)\s*(?:is|:)?\s*|option\s*(?:is|:)?\s*)(?:\()?([A-D])(?:\))?",
        output,
        re.IGNORECASE,
    )
    if secondary_matches:
        pred_letter = secondary_matches[-1].upper()
        if pred_letter == gold_letter:
            return True, checker_name, f"Selected correct option ({pred_letter})"
        return False, checker_name, f"Selected option ({pred_letter}) != gold ({gold_letter})"

    # 4. Fallback: parenthesized letter at the end of the response
    paren_matches = re.findall(r"[(]([A-D])[)]", output)
    if paren_matches:
        pred_letter = paren_matches[-1].upper()
        if pred_letter == gold_letter:
            return True, checker_name, f"Selected parenthesized option ({pred_letter})"
        return False, checker_name, f"Selected parenthesized option ({pred_letter}) != gold ({gold_letter})"

    # 5. Final fallback: standalone letter
    standalone = re.findall(r"\b([A-D])\b", output)
    if standalone:
        pred_letter = standalone[-1].upper()
        if pred_letter == gold_letter:
            return True, checker_name, f"Selected standalone letter matched gold ({gold_letter})"
        return False, checker_name, f"Selected standalone letter ({pred_letter}) != gold ({gold_letter})"

    return False, checker_name, "Could not extract choice letter from output"


def score_record(item: Dict[str, Any], output_text: str) -> Dict[str, Any]:
    """
    Main scoring function for any item given its ground truth and raw output text.
    """
    if "checklist" in item:
        # Track B
        res = score_fact_checklist(output_text, item["checklist"], max_word_cap=item.get("word_cap", 75))
        return {
            "passed": res["binary_pass"],
            "recall": res["recall"],
            "checker": "fact_checklist_scorer",
            "details": f"Recall: {res['recall']:.2f}, Violations: {len(res.get('negative_violations', []))}"
        }
    else:
        # Track A
        st_type = item.get("type") or item.get("task_type") or item.get("stratum") or ""
        st_id = item.get("id") or item.get("subtask_id") or item.get("original_id") or ""
        gold = (
            item.get("gold")
            or item.get("gold_answer")
            or item.get("gold_sql")
            or item.get("gold_query")
            or item.get("gold_number")
            or item.get("gold_letter")
            or ""
        )

        if st_type == "code":
            passed, chk, det = check_code_subtask(st_id, output_text, item)
        elif st_type == "math":
            passed, chk, det = check_math_subtask(st_id, output_text, str(gold))
        elif st_type == "sql":
            passed, chk, det = check_sql_subtask(st_id, output_text, str(gold), item)
        elif st_type == "qa":
            passed, chk, det = check_qa_subtask(st_id, output_text, str(gold))
        elif st_type in ["composed", "compound"]:
            passed, chk, det = check_math_subtask(st_id, output_text, str(gold))
        else:
            return {"passed": False, "recall": 0.0, "checker": "unknown", "details": f"Unknown type {st_type}"}

        return {
            "passed": passed,
            "recall": 1.0 if passed else 0.0,
            "checker": chk,
            "details": det
        }

