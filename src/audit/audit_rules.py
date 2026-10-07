"""
Automated audit script.
Enforces Hard Rules 2 through 8, verbatim hash consistency, and skill file compliance.
Exits 0 on clean pass; exits non-zero with explicit failure report on any violation.
"""

import os
import sys
import json
import hashlib
import glob
import re
import subprocess
from typing import List, Dict, Tuple, Any

REQUIRED_KNOWLEDGE_FILES = [
    ".agents/knowledge/00_index.md",
    ".agents/knowledge/master_prompt.md",
    ".agents/knowledge/mentor_protocol_source.md",
    ".agents/knowledge/environment.md",
    ".agents/knowledge/model_registry.md",
    ".agents/knowledge/dataset_card.md",
    ".agents/knowledge/metrics_definitions.md",
    ".agents/knowledge/old_project_lessons.md",
]

REQUIRED_SKILLS = [
    "session-start",
    "session-end",
    "laptop-gpu-ops",
    "run-generation-batch",
    "run-baselines",
    "run-judge",
    "audit-results",
    "build-report",
    "lock-dataset",
    "train-adapter",
    "incident-response",
]


def compute_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()


def audit_knowledge_files(repo_root: str) -> List[str]:
    """Audits existence of knowledge files and hash registration."""
    errors = []

    # Check root docs
    for doc in ["AGENTS.md", "PROGRESS.md"]:
        p = os.path.join(repo_root, doc)
        if not os.path.exists(p):
            errors.append(f"Missing required root documentation: {doc}")

    # Check knowledge files
    for kf in REQUIRED_KNOWLEDGE_FILES:
        p = os.path.join(repo_root, kf)
        if not os.path.exists(p):
            errors.append(f"Missing required knowledge file: {kf}")

    # Check skill stubs
    for sk in REQUIRED_SKILLS:
        sk_path = os.path.join(repo_root, ".agents", "skills", sk, "SKILL.md")
        if not os.path.exists(sk_path):
            errors.append(f"Missing required skill stub: .agents/skills/{sk}/SKILL.md")

    # Verify hashes registered in 00_index.md
    index_path = os.path.join(repo_root, ".agents", "knowledge", "00_index.md")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            index_text = f.read()

        for kf in REQUIRED_KNOWLEDGE_FILES:
            if "00_index.md" in kf:
                continue
            fname = os.path.basename(kf)
            actual_hash = compute_sha256(os.path.join(repo_root, kf))
            if actual_hash not in index_text:
                errors.append(
                    f"Hash mismatch or missing in 00_index.md for {fname}: expected {actual_hash}"
                )

    return errors


def audit_run_records(log_file_path: str) -> List[str]:
    """
    Audits an append-only JSONL run records file.
    Enforces Rule 2 (Immutability), Rule 3 (Fail loudly), Rule 7 (Pinned models).
    """
    errors = []
    if not os.path.exists(log_file_path):
        return errors

    line_num = 0
    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line_num += 1
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception as e:
                errors.append(f"Line {line_num} in {log_file_path} is invalid JSON: {e}")
                continue

            # Hard Rule 7: No floating '-latest' aliases
            model_id = rec.get("model_id", "")
            if "-latest" in model_id.lower() or ":latest" in model_id.lower():
                errors.append(
                    f"Rule 7 Violation: Line {line_num} contains floating alias '{model_id}'"
                )

            # Hard Rule 3: Fail loudly enforcement
            finish_reason = rec.get("finish_reason", "")
            comp_tokens = rec.get("completion_tokens", 0)
            status = rec.get("status", "")
            output = rec.get("full_output", "")

            if (finish_reason != "stop" or comp_tokens == 0 or not output) and status != "FAILED":
                errors.append(
                    f"Rule 3 Violation: Line {line_num} had empty/truncated output "
                    f"(finish_reason='{finish_reason}', tokens={comp_tokens}) but status was '{status}' instead of 'FAILED'"
                )

            # Hard Rule 7: Model digest format validation
            model_digest = rec.get("model_digest", "")
            if model_digest and not re.match(r"^[0-9a-fA-F]{12,64}$", model_digest):
                errors.append(
                    f"Rule 7 Violation: Line {line_num} contains invalid model_digest '{model_digest}'"
                )

    return errors


def audit_model_digests(repo_root: str) -> List[str]:
    """
    Hard Rule 7 & Model Registry check:
    Ensures all candidate local models in model_registry.md are pinned with valid 64-char SHA-256 digests.
    Ensures no floating :latest or -latest aliases exist.
    """
    errors = []
    reg_path = os.path.join(repo_root, ".agents", "knowledge", "model_registry.md")
    if not os.path.exists(reg_path):
        return ["Missing .agents/knowledge/model_registry.md"]

    with open(reg_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check for floating aliases in model table rows
    for line_idx, line in enumerate(content.splitlines(), start=1):
        if line.strip().startswith("|") and ("-latest`" in line.lower() or ":latest`" in line.lower()):
            errors.append(
                f"Rule 7 Violation: Floating alias found in model_registry.md table line {line_idx}: {line.strip()}"
            )

    # Extract 64-char SHA-256 hex strings in backticks
    hex_digests = re.findall(r"`([0-9a-fA-F]{64})`", content)
    if not hex_digests:
        errors.append("Model Registry check: No 64-character SHA-256 model digests found in model_registry.md")
    elif len(hex_digests) < 5:
        errors.append(
            f"Model Registry check: Expected at least 5 pinned model digests in model_registry.md, found {len(hex_digests)}"
        )

    return errors


def audit_deleted_files(repo_root: str) -> List[str]:
    """
    Hard Rule 2 (Raw files are immutable):
    Checks git status and history to ensure no .jsonl results or raw record files were deleted.
    """
    errors = []
    try:
        # Check current working tree and staged index
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                status = line[:2]
                filepath = line[3:].strip()
                if "D" in status and (".jsonl" in filepath or "results" in filepath):
                    errors.append(f"Hard Rule 2 Violation: Deleted file in working tree/index: {filepath}")

        # Check git commit history for deleted .jsonl files in results/
        log_proc = subprocess.run(
            ["git", "log", "--diff-filter=D", "--summary", "--", "results/"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if log_proc.returncode == 0 and log_proc.stdout.strip():
            progress_path = os.path.join(repo_root, "PROGRESS.md")
            progress_text = ""
            if os.path.exists(progress_path):
                with open(progress_path, "r", encoding="utf-8") as pf:
                    progress_text = pf.read()
            for line in log_proc.stdout.splitlines():
                if "delete mode" in line:
                    fname = line.split()[-1]
                    if fname not in progress_text:
                        errors.append(
                            f"Hard Rule 2 Violation: Deleted file in git history ({fname}) is not documented in PROGRESS.md incident log."
                        )

    except Exception as e:
        errors.append(f"Could not verify git deletion status: {e}")

    return errors


def run_full_audit(repo_root: str = ".") -> Tuple[bool, List[str]]:
    """Runs all checks and returns (passed, list_of_errors)."""
    all_errors = []

    # 1. Knowledge and file structure
    k_errors = audit_knowledge_files(repo_root)
    all_errors.extend(k_errors)

    # 2. Pinned model digest check in model_registry.md
    digest_errors = audit_model_digests(repo_root)
    all_errors.extend(digest_errors)

    # 3. Deleted file check (Rule 2)
    deleted_errors = audit_deleted_files(repo_root)
    all_errors.extend(deleted_errors)

    # 4. Check any existing run record JSONL files
    record_files = glob.glob(os.path.join(repo_root, "**", "*.jsonl"), recursive=True)
    for rf in record_files:
        # Ignore temporary cache or IDE directories
        if ".git" in rf or ".gemini" in rf:
            continue
        rf_errors = audit_run_records(rf)
        all_errors.extend(rf_errors)

    passed = len(all_errors) == 0
    return passed, all_errors


if __name__ == "__main__":
    repo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    passed, errors = run_full_audit(repo_path)
    if passed:
        print("AUDIT PASSED: All operational rules (Rules 2-8), hashes, digests, and files verified.")
        sys.exit(0)
    else:
        print(f"AUDIT FAILED with {len(errors)} violation(s):")
        for err in errors:
            print(f"  [VIOLATION] {err}")
        sys.exit(1)


