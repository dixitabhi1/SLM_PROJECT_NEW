"""
src/pipeline/specialist_pipeline_e3.py

Pipeline implementation for Experiment 3 (E3: Compute Numbers in Code).
Generic Rule: Any task or subtask that needs arithmetic, counting, modular maths,
iteration or a search over cases gets a short Python program from the SLM,
executed in the isolated sandbox (src/sandbox/runner.py); the result is used
as the answer.

Zero keywords or patterns tied to specific benchmark items.
"""

import os
import sys
import re
import json
import time
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import (
    call_phi,
    task_asks_for_query,
    get_table_schema,
    execute_sql_tolerant,
    extract_sql_from_text,
    analyse_task_model_call,
    decompose_task_model_call,
    color_subtasks_with_feedback,
    execute_data_fetch,
    execute_downstream_reasoning,
    KNOWN_DATABASES
)
from src.sandbox.runner import execute_python_code


def is_function_completion(prompt: str) -> bool:
    """Generic detection of whether the prompt is a Python function implementation stub."""
    p_stripped = prompt.strip()
    if p_stripped.startswith("def ") or p_stripped.startswith("from ") or p_stripped.startswith("import "):
        if "def " in prompt and '"""' in prompt:
            return True
    if re.search(r"^\s*def\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(", prompt, re.MULTILINE):
        return True
    return False


def is_numeric_computation_task(prompt: str) -> bool:
    """
    Generic detection of whether a self-contained task requires mathematical calculation,
    counting, modular arithmetic, iterative simulation, or search over cases.
    """
    p_lower = prompt.lower()
    
    # GSM8K indicator: prompt ends with instruction or asks a math problem
    if "####" in prompt or "cost" in p_lower or "how many" in p_lower or "calculate" in p_lower or "compute" in p_lower:
        # Avoid pure conceptual multiple choice questions (like ARC)
        if not re.search(r"\([A-D]\)\s+[A-Za-z]+", prompt):
            return True
            
    math_indicators = [
        "calculate", "compute", "sum of", "product of", "total",
        "modulo", "remainder", "simulation", "sequence", "count of",
        "how many", "minimum", "maximum", "average", "ratio", "rate"
    ]
    if any(ind in p_lower for ind in math_indicators):
        if not re.search(r"Which of the following", prompt, re.IGNORECASE):
            return True
            
    return False


def execute_computation_code(code: str, retry_prompt_base: str = "", timeout: float = 5.0) -> Tuple[bool, str, str]:
    """
    Executes Python code in sandbox with 1 retry on execution error.
    Returns: (clean_execution: bool, raw_stdout: str, parsed_numeric_answer: str)
    """
    res = execute_python_code(code, timeout_seconds=timeout)
    if res.exit_code == 0 and res.stdout.strip():
        out_v = res.stdout.strip()
        ans_lines = [l.strip() for l in out_v.splitlines() if l.strip()]
        last_line = ans_lines[-1] if ans_lines else out_v
        ans_nums = re.findall(r"-?\d+(?:\.\d+)?", last_line)
        v = ans_nums[-1] if ans_nums else last_line
        if v:
            try:
                fv = float(v)
                if fv.is_integer():
                    v = str(int(fv))
            except Exception:
                pass
        return True, out_v, v

    # 1 Retry if execution failed and retry prompt context provided
    if retry_prompt_base and res.exit_code != 0:
        err_msg = res.stderr.strip() or f"Exit code {res.exit_code}"
        retry_msg = (
            f"The script failed execution with error:\n{err_msg}\n\n"
            f"Please fix the error. Remember: when converting floats to integers or using functions "
            f"requiring int, use int(round(x)). Print only the final numeric result to stdout. Enclose in ```python ... ```."
        )
        resp_retry = call_phi([
            {"role": "system", "content": "You are an expert computational assistant. Write a short Python program to compute the exact answer."},
            {"role": "user", "content": retry_prompt_base},
            {"role": "assistant", "content": f"```python\n{code}\n```"},
            {"role": "user", "content": retry_msg}
        ], temperature=0.0, max_tokens=512)

        code_m = re.search(r"```python\s*(.*?)\s*```", resp_retry, re.DOTALL | re.IGNORECASE)
        if code_m:
            code_2 = code_m.group(1).strip()
            res_2 = execute_python_code(code_2, timeout_seconds=timeout)
            if res_2.exit_code == 0 and res_2.stdout.strip():
                out_v = res_2.stdout.strip()
                ans_lines = [l.strip() for l in out_v.splitlines() if l.strip()]
                last_line = ans_lines[-1] if ans_lines else out_v
                ans_nums = re.findall(r"-?\d+(?:\.\d+)?", last_line)
                v = ans_nums[-1] if ans_nums else last_line
                if v:
                    try:
                        fv = float(v)
                        if fv.is_integer():
                            v = str(int(fv))
                    except Exception:
                        pass
                return True, out_v, v

    return False, res.stderr.strip() or res.stdout.strip(), ""


def run_specialist_pipeline_e3(prompt: str) -> Dict[str, Any]:
    """
    Experiment 3 Specialist Pipeline.
    Strictly accepts ONLY the prompt text string (prompt: str).
    Returns execution record dictionary.
    """
    t0 = time.time()
    fallbacks = {
        "analyser": False,
        "database_identifier": False,
        "decomposer": False,
        "colorer": False,
        "matcher": False
    }

    # Stage 1: Analyser (Model Call)
    analysis, fb_analyser = analyse_task_model_call(prompt)
    fallbacks["analyser"] = fb_analyser
    needs_outside = analysis["needs_outside_data"]

    # 1. DIRECT SQL PATH (v1.1 SQL FIX)
    if analysis.get("asks_for_query", False):
        t_sql = time.time()
        db_to_use = analysis.get("database_name", "")
        if not db_to_use or db_to_use not in KNOWN_DATABASES:
            for db in KNOWN_DATABASES:
                if db.lower() in prompt.lower():
                    db_to_use = db
                    break
        if not db_to_use:
            fallbacks["database_identifier"] = True
            schema_str = ""
        else:
            schema_str = get_table_schema(db_to_use)

        if "[database schema:" not in prompt.lower() and schema_str:
            query_prompt = f"Database: {db_to_use}\nSchema:\n{schema_str}\n\n{prompt}"
        else:
            query_prompt = prompt

        direct_sql_sys = (
            "You are an expert SQL assistant. Given the database schema and question, write a single valid SQLite query that answers the question.\n"
            "Guidelines:\n"
            "- Return ONLY the exact column(s) requested by the question. Do not include auxiliary count or aggregate columns in the SELECT clause unless explicitly asked.\n"
            "- Ensure necessary table joins are included when attributes belong to relational tables.\n"
            "- Output strictly the SQL query enclosed in ```sql\n<query>\n```. Do not provide conversational explanations."
        )

        resp_1 = call_phi([
            {"role": "system", "content": direct_sql_sys},
            {"role": "user", "content": query_prompt}
        ], temperature=0.0, max_tokens=256)
        query_1 = extract_sql_from_text(resp_1)
        clean_1, out_1 = execute_sql_tolerant(db_to_use, query_1, prompt_context=prompt)
        final_query = query_1
        retried = False
        all_clean = clean_1

        if not clean_1:
            retried = True
            retry_msg = (
                f"The query failed execution with error:\n{out_1}\n"
                f"Please fix the query and provide a valid SQLite query in ```sql ... ```."
            )
            resp_2 = call_phi([
                {"role": "system", "content": direct_sql_sys},
                {"role": "user", "content": query_prompt},
                {"role": "assistant", "content": f"```sql\n{query_1}\n```"},
                {"role": "user", "content": retry_msg}
            ], temperature=0.0, max_tokens=256)
            query_2 = extract_sql_from_text(resp_2)
            clean_2, out_2 = execute_sql_tolerant(db_to_use, query_2, prompt_context=prompt)
            final_query = query_2
            all_clean = clean_2

        formatted_output = f"```sql\n{final_query}\n```"
        dt = time.time() - t0

        return {
            "routed_to": "direct_sql",
            "answered_by": "phi-4-mini",
            "source": analysis.get("source", "DATABASE"),
            "needs_outside_data": True,
            "clean_execution": all_clean,
            "output": formatted_output,
            "full_output": formatted_output,
            "final_answer": formatted_output,
            "fallbacks": fallbacks,
            "subtasks": [prompt],
            "colors": ["SQL_DATA"],
            "retried": retried,
            "duration": dt
        }

    # 2. OUTSIDE DATA PATH (Composed multi-stage tasks)
    if needs_outside:
        subtasks, fb_decomp = decompose_task_model_call(prompt)
        fallbacks["decomposer"] = fb_decomp
        colors, fb_colorer = color_subtasks_with_feedback(subtasks, prompt, source=analysis["source"], max_levels=3)
        fallbacks["colorer"] = fb_colorer

        # E3 Generic Rule: If Subtask 2 involves calculation, counting, or modular arithmetic -> CODE_EXEC
        is_calc = any(w in subtasks[1].lower() for w in [
            "calculate", "compute", "sum", "multiply", "divide", "add", "score",
            "total", "fee", "rate", "percentage", "ratio", "count", "modulo"
        ])
        if is_calc or colors[1] == "CODE_EXEC":
            colors[1] = "CODE_EXEC"

        clean_fetch, fetch_summary, fetched_val = execute_data_fetch(
            subtask_1=subtasks[0],
            color_1=colors[0],
            db_name=analysis.get("database_name", ""),
            prompt=prompt
        )

        if colors[1] == "CODE_EXEC":
            down_prompt = (
                f"Task: {prompt}\n\n"
                f"Retrieved Context:\n{fetch_summary}\n\n"
                f"Step to Complete:\n{subtasks[1]}\n\n"
                "Write a short, self-contained Python program to compute the exact answer to this step using the retrieved data.\n"
                "Guidelines:\n"
                "- Implement the arithmetic or logic directly in Python.\n"
                "- When converting floats to integers or using functions requiring int, use int(round(x)).\n"
                "- Print only the final numeric result to stdout using print().\n"
                "- Output strictly the Python code block enclosed in ```python\n<code>\n```."
            )
            resp = call_phi([
                {"role": "system", "content": "You are an expert computational assistant. Write a short Python program to compute the exact answer."},
                {"role": "user", "content": down_prompt}
            ], temperature=0.0, max_tokens=512)

            code_m = re.search(r"```python\s*(.*?)\s*```", resp, re.DOTALL | re.IGNORECASE)
            v = ""
            if code_m:
                code = code_m.group(1).strip()
                clean_exec, out_v, v = execute_computation_code(code, retry_prompt_base=down_prompt, timeout=5.0)

            if v:
                clean_ans = f"Final Answer: {v}"
                combined = f"{fetch_summary}\n\n{resp}\n\nExecuted Python Output:\n{out_v}\n\n{clean_ans}"
                dt = time.time() - t0
                return {
                    "routed_to": "outside_data_code",
                    "answered_by": "phi-4-mini",
                    "source": analysis.get("source", "DATABASE"),
                    "needs_outside_data": True,
                    "clean_execution": clean_fetch and clean_exec,
                    "output": combined[:300],
                    "full_output": combined,
                    "final_answer": clean_ans,
                    "fallbacks": fallbacks,
                    "subtasks": subtasks,
                    "colors": colors,
                    "duration": dt
                }

        # Downstream reasoning fallback (Track B or qualitative)
        clean_down, full_down, clean_ans = execute_downstream_reasoning(
            subtasks[1], fetched_val, fetch_summary, colors[1], prompt
        )
        dt = time.time() - t0
        return {
            "routed_to": "outside_data",
            "answered_by": "phi-4-mini",
            "source": analysis.get("source", "NONE"),
            "needs_outside_data": True,
            "clean_execution": clean_fetch and clean_down,
            "output": full_down[:300],
            "full_output": full_down,
            "final_answer": clean_ans,
            "fallbacks": fallbacks,
            "subtasks": subtasks,
            "colors": colors,
            "duration": dt
        }

    # 3. SELF-CONTAINED PATH (needs_outside == False)
    # 3A. Function implementation (HumanEval)
    if is_function_completion(prompt):
        code_sys = "You are an expert Python programmer. Complete the function implementation cleanly inside ```python\n<code>\n```."
        resp = call_phi([
            {"role": "system", "content": code_sys},
            {"role": "user", "content": prompt}
        ], temperature=0.0, max_tokens=512)
        dt = time.time() - t0
        return {
            "routed_to": "code_implementation",
            "answered_by": "phi-4-mini",
            "source": "NONE",
            "needs_outside_data": False,
            "clean_execution": bool(resp.strip()),
            "output": resp[:300],
            "full_output": resp,
            "final_answer": resp,
            "fallbacks": fallbacks,
            "duration": dt
        }

    # 3B. Numeric Computation (E3 Rule: arithmetic, counting, modular maths, iteration, search)
    if is_numeric_computation_task(prompt):
        comp_prompt = (
            f"Problem:\n{prompt}\n\n"
            "Write a short, self-contained Python program to compute the exact answer to the problem.\n"
            "Guidelines:\n"
            "- Implement the arithmetic, counting, modular math, simulation, or search directly in Python.\n"
            "- When converting floats to integers or using functions requiring int, use int(round(x)).\n"
            "- Print only the final numeric result to stdout using print().\n"
            "- Output strictly the Python code block enclosed in ```python\n<code>\n```."
        )
        resp = call_phi([
            {"role": "system", "content": "You are an expert computational assistant. Write a short Python program to compute the exact answer."},
            {"role": "user", "content": comp_prompt}
        ], temperature=0.0, max_tokens=512)

        code_m = re.search(r"```python\s*(.*?)\s*```", resp, re.DOTALL | re.IGNORECASE)
        v = ""
        if code_m:
            code = code_m.group(1).strip()
            clean_exec, out_v, v = execute_computation_code(code, retry_prompt_base=comp_prompt, timeout=5.0)

        if v:
            clean_ans = f"#### {v}" if "####" in prompt else f"Final Answer: {v}"
            dt = time.time() - t0
            return {
                "routed_to": "code_compute",
                "answered_by": "phi-4-mini",
                "source": "NONE",
                "needs_outside_data": False,
                "clean_execution": clean_exec,
                "output": f"{resp}\n\nExecuted Python Output:\n{out_v}\n\n{clean_ans}",
                "full_output": f"{resp}\n\nExecuted Python Output:\n{out_v}\n\n{clean_ans}",
                "final_answer": clean_ans,
                "fallbacks": fallbacks,
                "duration": dt
            }

    # 3C. Conceptual Reasoning (QA, qualitative reasoning)
    direct_resp = call_phi([
        {"role": "system", "content": "You are a helpful, precise assistant. Reason step-by-step and provide your final answer in the requested format."},
        {"role": "user", "content": prompt}
    ], temperature=0.0, max_tokens=1024)
    dt = time.time() - t0
    return {
        "routed_to": "direct",
        "answered_by": "phi-4-mini",
        "source": "NONE",
        "needs_outside_data": False,
        "clean_execution": bool(direct_resp.strip()),
        "output": direct_resp[:300],
        "full_output": direct_resp,
        "final_answer": direct_resp,
        "fallbacks": fallbacks,
        "duration": dt
    }

