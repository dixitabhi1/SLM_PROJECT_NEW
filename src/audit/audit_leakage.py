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
    "original_id",
    "subtask_id",
}


def _resolve_str_expr(node: ast.AST, var_map: dict) -> str:
    """Recursively resolves string constants, additions, and variable aliases."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_str_expr(node.left, var_map)
        right = _resolve_str_expr(node.right, var_map)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.Name) and node.id in var_map:
        return var_map[node.id]
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            s = _resolve_str_expr(v, var_map)
            if s is not None:
                parts.append(s)
            else:
                return None
        return "".join(parts)
    return None


def audit_file_leakage(fpath: str) -> List[str]:
    """Audits a single python file for forbidden metadata field access."""
    errors = []
    if not os.path.exists(fpath):
        return [f"File not found: {fpath}"]

    with open(fpath, "r", encoding="utf-8") as f:
        code_text = f.read()

    try:
        tree = ast.parse(code_text, filename=fpath)
    except Exception as e:
        return [f"AST parse error in {fpath}: {e}"]

    var_map = {}
    # First pass: map local variable string assignments
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    val_str = _resolve_str_expr(node.value, var_map)
                    if val_str is not None:
                        var_map[target.id] = val_str

    # Second pass: check for subscript, get() calls, or membership tests accessing forbidden fields
    for node in ast.walk(tree):
        # Check dict.get("field") or dict.get(var)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
                if node.args:
                    field_name = _resolve_str_expr(node.args[0], var_map)
                    if field_name and field_name in FORBIDDEN_FIELDS:
                        errors.append(
                            f"Leakage Violation in {os.path.basename(fpath)}: line {node.lineno} accesses forbidden metadata field '{field_name}'"
                        )

        # Check dict["field"] or dict[var]
        if isinstance(node, ast.Subscript):
            slice_name = _resolve_str_expr(node.slice, var_map)
            if slice_name and slice_name in FORBIDDEN_FIELDS:
                errors.append(
                    f"Leakage Violation in {os.path.basename(fpath)}: line {node.lineno} indexes forbidden metadata field '{slice_name}'"
                )

        # Check membership: "field" in dict
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.In, ast.NotIn)):
                    field_name = _resolve_str_expr(node.left, var_map)
                    if field_name and field_name in FORBIDDEN_FIELDS:
                        errors.append(
                            f"Leakage Violation in {os.path.basename(fpath)}: line {node.lineno} tests membership of forbidden metadata field '{field_name}'"
                        )

        # Check function signature of run_specialist_pipeline
        if isinstance(node, ast.FunctionDef) and node.name == "run_specialist_pipeline":
            arg_names = [arg.arg for arg in node.args.args]
            if "item" in arg_names:
                errors.append(
                    f"Leakage Violation in {os.path.basename(fpath)}: run_specialist_pipeline signature accepts 'item' dict. Must accept only 'prompt'."
                )

    return errors


def audit_paths_leakage(paths: List[str]) -> List[str]:
    """Audits multiple files or directories recursively."""
    all_errors = []
    py_files = []
    for p in paths:
        if os.path.isfile(p):
            py_files.append(p)
        elif os.path.isdir(p):
            py_files.extend(glob.glob(os.path.join(p, "**", "*.py"), recursive=True))

    for fpath in sorted(set(py_files)):
        all_errors.extend(audit_file_leakage(fpath))
    return all_errors


def audit_pipeline_leakage(pipeline_dir: str) -> List[str]:
    """Backward-compatible audit for src/pipeline."""
    return audit_paths_leakage([pipeline_dir])


if __name__ == "__main__":
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if len(sys.argv) > 1:
        target_paths = [os.path.abspath(arg) for arg in sys.argv[1:]]
    else:
        # Default: scan src/ and scripts/
        target_paths = [
            os.path.join(repo_root, "src"),
            os.path.join(repo_root, "scripts"),
        ]

    errs = audit_paths_leakage(target_paths)
    if errs:
        print(f"LEAKAGE AUDIT FAILED with {len(errs)} error(s):")
        for e in errs:
            print(f"  [LEAKAGE] {e}")
        sys.exit(1)
    else:
        print("LEAKAGE AUDIT PASSED: Zero forbidden metadata field accesses detected.")
        sys.exit(0)


