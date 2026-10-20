"""
src/adapters/public_adapters.py

Generic input adapters for public validation benchmarks:
1. GSM-Hard (reasoning-machines/gsm-hard)
2. FinQA (czyssrs/FinQA)
3. InfiAgent-DABench (InfiAgent/InfiAgent)

Protocol Constraints:
- Generic format per benchmark: identical transformation for every item.
- Zero item-specific keywords, regexes, gold answers, or hardcoded IDs.
- Strictly formats the question and its associated context (table text, narrative, CSV path)
  into the standard text input expected by the frozen SLM pipeline and LLM baseline harnesses.
"""

import os
import json
from typing import Dict, Any, List, Optional
import pandas as pd


def format_gsmhard_prompt(item: Dict[str, Any]) -> str:
    """
    Generic input adapter for GSM-Hard.
    Takes raw GSM-Hard item containing 'input' string.
    Emits standard prompt requesting exact numerical answer.
    """
    question = item.get("input", "").strip()
    return f"{question}\n\nCompute the exact numerical answer and output: #### <answer>"


def format_finqa_prompt(item: Dict[str, Any]) -> str:
    """
    Generic input adapter for FinQA.
    Serializes financial document narrative and tabular structure into clear markdown text,
    followed by the financial question and numerical answer format.
    """
    pre_text = "\n".join(item.get("pre_text", [])).strip()
    post_text = "\n".join(item.get("post_text", [])).strip()
    
    table = item.get("table", [])
    table_lines = []
    for row in table:
        cleaned_cells = [str(cell).strip() for cell in row]
        table_lines.append(" | ".join(cleaned_cells))
    table_str = "\n".join(table_lines)
    
    qa_dict = item.get("qa", {})
    question = qa_dict.get("question", "").strip()
    
    sections = []
    if pre_text:
        sections.append(f"Financial Document Context:\n{pre_text}")
    if table_str:
        sections.append(f"Table Data:\n{table_str}")
    if post_text:
        sections.append(f"Additional Context:\n{post_text}")
    sections.append(f"Question: {question}")
    sections.append(
        "Compute the exact numerical answer based on the financial document context and table above. "
        "Output the final result as: #### <answer>"
    )
    
    return "\n\n".join(sections)


def format_dabench_prompt(item: Dict[str, Any], tables_dir: str) -> str:
    """
    Generic input adapter for InfiAgent-DABench.
    Inspects CSV schema and sample rows, formatting the data analysis task, constraints,
    and official format requirements for execution in Python.
    """
    file_name = item.get("file_name", "")
    csv_path = os.path.abspath(os.path.join(tables_dir, file_name)).replace("\\", "/")
    
    schema_info = ""
    if os.path.exists(csv_path):
        try:
            df_sample = pd.read_csv(csv_path, nrows=2)
            cols = ", ".join([repr(c) for c in df_sample.columns])
            preview = df_sample.to_string(index=False)
            schema_info = f"CSV File: {csv_path}\nColumns: [{cols}]\nTable Preview:\n{preview}\n\n"
        except Exception:
            schema_info = f"CSV File: {csv_path}\n\n"
    else:
        schema_info = f"CSV File: {csv_path}\n\n"
        
    question = item.get("question", "").strip()
    constraints = item.get("constraints", "").strip()
    format_req = item.get("format", "").strip()
    
    prompt = (
        f"Data Analysis Task:\n"
        f"{schema_info}"
        f"Question: {question}\n\n"
        f"Constraints:\n{constraints}\n\n"
        f"Required Output Format:\n{format_req}\n\n"
        f"Write a Python script to compute the exact answer from the CSV file.\n"
        f"Ensure your Python code prints the final answer enclosed in the required format tag: {format_req}\n"
        f"Output strictly the Python code block."
    )
    return prompt


def adapt_benchmark_item(benchmark: str, item: Dict[str, Any], tables_dir: Optional[str] = None) -> str:
    """
    Universal dispatcher for public benchmark input adapters.
    """
    b_lower = benchmark.lower()
    if "gsm" in b_lower:
        return format_gsmhard_prompt(item)
    elif "finqa" in b_lower:
        return format_finqa_prompt(item)
    elif "dabench" in b_lower or "infi" in b_lower:
        if not tables_dir:
            tables_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "public", "raw", "dabench", "tables"))
        return format_dabench_prompt(item, tables_dir=tables_dir)
    else:
        raise ValueError(f"Unknown benchmark: {benchmark}")
