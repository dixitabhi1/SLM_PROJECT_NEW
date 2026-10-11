"""
Leakage Audit Script.
Ensures that no dataset metadata fields are accessed or read under src/pipeline/.
Specifically forbids reading:
- 'task_type'
- 'num_stages'
- 'solvability'
- 'stratum'
- 'domains'
- 'gold_answer'
- 'gold_query'
- 'gold_rows'
- 'gold_rows_sample'
- 'reference_code'
- 'component_parts'
- 'checker_type'
- 'original_id'
- 'subtask_id'

Also enforces that run_specialist_pipeline accepts only prompt text as its primary input.
"""

import os
import sys
import ast
import glob
from typing import List

FORBIDDEN_FIELDS = {
    "task_type",
    "num_stages",
    "solvability",
    "stratum",
    "domains",
    "gold_answer",
    "gold_query",
    "gold_rows",
    "gold_rows_sample",
    "reference_code",
    "component_parts",
    "checker_type",
}


def audit_pipeline_leakage(pipeline_dir: str) -> List[str]:
    errors = []
    py_files = glob.glob(os.path.join(pipeline_dir, "**", "*.py"), recursive=True)

    for fpath in py_files:
        with open(fpath, "r", encoding="utf-8") as f:
            code_text = f.read()

        try:
            tree = ast.parse(code_text, filename=fpath)
        except Exception as e:
            errors.append(f"AST parse error in {fpath}: {e}")
            continue

        # Check for subscript or get() calls accessing forbidden fields
        for node in ast.walk(tree):
            # Check dict.get("field")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
                    if node.args and isinstance(node.args[0], ast.Constant):
                        field_name = str(node.args[0].value)
                        if field_name in FORBIDDEN_FIELDS:
                            errors.append(
                                f"Leakage Violation in {os.path.basename(fpath)}: line {node.lineno} accesses forbidden metadata field '{field_name}'"
                            )

            # Check dict["field"]
            if isinstance(node, ast.Subscript):
                if isinstance(node.slice, ast.Constant):
                    field_name = str(node.slice.value)
                    if field_name in FORBIDDEN_FIELDS:
                        errors.append(
                            f"Leakage Violation in {os.path.basename(fpath)}: line {node.lineno} indexes forbidden metadata field '{field_name}'"
                        )

            # Check function signature of run_specialist_pipeline
            if isinstance(node, ast.FunctionDef) and node.name == "run_specialist_pipeline":
                arg_names = [arg.arg for arg in node.args.args]
                if "item" in arg_names:
                    errors.append(
                        f"Leakage Violation in {os.path.basename(fpath)}: run_specialist_pipeline signature accepts 'item' dict. Must accept only 'prompt'."
                    )

    return errors


if __name__ == "__main__":
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    pipeline_dir = os.path.join(repo_root, "src", "pipeline")
    errs = audit_pipeline_leakage(pipeline_dir)
    if errs:
        print(f"PIPELINE LEAKAGE AUDIT FAILED with {len(errs)} error(s):")
        for e in errs:
            print(f"  [LEAKAGE] {e}")
        sys.exit(1)
    else:
        print("PIPELINE LEAKAGE AUDIT PASSED: Zero dataset metadata fields read under src/pipeline/.")
        sys.exit(0)

