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


def audit_secret_leakage(repo_root: str) -> List[str]:
    """
    Security & Integrity check:
    Ensures no raw API keys (Groq, Google AI Studio, Gemini, OpenAI, etc.) are committed
    or present in tracked repository files.
    """
    errors = []
    SECRET_PATTERNS = [
        (re.compile(r"gsk_[a-zA-Z0-9]{25,70}"), "Groq API key"),
        (re.compile(r"AQ\.[a-zA-Z0-9_\-\.]{25,75}"), "Google AI Studio API key (AQ format)"),
        (re.compile(r"AIzaSy[a-zA-Z0-9_\-]{33}"), "Google Cloud / Gemini API key"),
        (re.compile(r"sk-[a-zA-Z0-9_\-]{32,}"), "OpenAI / Provider API key"),
    ]

    # Check git tracked files
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            tracked_files = [f.strip() for f in proc.stdout.splitlines() if f.strip()]
            for rel_path in tracked_files:
                full_path = os.path.join(repo_root, rel_path)
                if not os.path.exists(full_path):
                    continue
                # Skip binary files
                if any(rel_path.endswith(ext) for ext in [".png", ".jpg", ".ico", ".bin", ".gz", ".zip", ".gguf", ".safetensors"]):
                    continue
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        file_content = f.read()
                    for pattern, secret_type in SECRET_PATTERNS:
                        if pattern.search(file_content):
                            errors.append(
                                f"Secret Leakage Violation: Found potential {secret_type} in tracked file '{rel_path}'"
                            )
                except Exception:
                    pass
    except Exception as e:
        errors.append(f"Secret leakage check failed to list tracked files: {e}")

    # Check untracked files in working tree (excluding gitignored .env, binary models, and adapter binaries)
    try:
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if status_proc.returncode == 0:
            for line in status_proc.stdout.splitlines():
                if line.startswith("??"):
                    rel_path = line[3:].strip()
                    if rel_path.startswith(".env") or "adapters" in rel_path:
                        continue
                    full_path = os.path.join(repo_root, rel_path)
                    if os.path.isfile(full_path):
                        if any(rel_path.endswith(ext) for ext in [".png", ".jpg", ".ico", ".bin", ".gz", ".zip", ".gguf", ".safetensors"]):
                            continue
                        try:
                            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                                file_content = f.read()
                            for pattern, secret_type in SECRET_PATTERNS:
                                if pattern.search(file_content):
                                    errors.append(
                                        f"Secret Leakage Violation: Found potential {secret_type} in untracked file '{rel_path}'"
                                    )
                        except Exception:
                            pass
    except Exception as e:
        errors.append(f"Secret leakage check failed to inspect untracked files: {e}")

    return errors


def audit_split_part_disjointness(repo_root: str) -> List[str]:
    """
    Enforces Part-Level Disjointness across evaluation splits:
    No component item ID may appear in more than one split, whether as an atomic item
    or as a component stage/part of a compound item.
    Also verifies strictly zero leakage of spent items.
    """
    errors = []
    splits = {
        "dev": os.path.join(repo_root, "data", "track_a_dev_split.json"),
        "heldout": os.path.join(repo_root, "data", "track_a_heldout_candidate.json"),
        "reserve": os.path.join(repo_root, "data", "reserve_set_quarantine.json"),
    }
    spent_file = os.path.join(repo_root, "data", "spent_benchmark_items.json")
    spent_ids = set()
    if os.path.exists(spent_file):
        try:
            with open(spent_file, "r", encoding="utf-8") as f:
                spent_data = json.load(f)
                if isinstance(spent_data, dict):
                    for k in ["previous_20_subtasks_spent", "new_50_hard_subtasks_spent"]:
                        spent_ids.update(spent_data.get(k, []))
                elif isinstance(spent_data, list):
                    spent_ids = {s.get("subtask_id", s.get("original_id")) for s in spent_data}
        except Exception:
            pass

    # Map of item/part ID -> list of (split_name, role)
    id_registry: Dict[str, List[Tuple[str, str]]] = {}

    for split_name, split_path in splits.items():
        if not os.path.exists(split_path):
            continue
        try:
            with open(split_path, "r", encoding="utf-8") as f:
                items = json.load(f)
            for item in items:
                orig_id = item.get("original_id")
                is_compound = item.get("is_compound", False) or item.get("stratum") == "composed"

                if not is_compound and orig_id:
                    id_registry.setdefault(orig_id, []).append((split_name, "atomic"))

                # Check component parts if compound
                part_ids = item.get("component_part_ids", item.get("component_ids", []))
                if not part_ids and "stages" in item:
                    part_ids = [st.get("original_id") for st in item["stages"] if st.get("original_id")]
                for pid in part_ids:
                    id_registry.setdefault(pid, []).append((split_name, "compound_part"))
        except Exception as e:
            errors.append(f"Failed to read split {split_name} for disjointness audit: {e}")

    # Check for collisions across splits
    for item_id, occurrences in id_registry.items():
        splits_present = {occ[0] for occ in occurrences}
        if len(splits_present) > 1:
            details = ", ".join(f"{s} ({role})" for s, role in occurrences)
            errors.append(
                f"Part-Level Disjointness Violation: Item ID '{item_id}' appears in multiple splits: {details}"
            )
        if item_id in spent_ids:
            errors.append(
                f"Hard Rule 5 / Benchmark Leakage Violation: Item ID '{item_id}' is in the spent benchmark items ledger!"
            )

    return errors


def audit_track_b_facts(repo_root: str) -> List[str]:
    """
    Enforces Track B constraints:
    1. Master fact pool exists with at least 150 invented facts.
    2. Zero real-world standards (no IEEE, AES, ASTM, MIL-STD).
    3. Strict disjointness between Dev and Held-Out fact pools.
    4. Each fact used in at most 2 questions (when split files exist).
    5. Zero document IDs (DOC-xx) or section numbers in question prompts.
    """
    errors = []
    pool_path = os.path.join(repo_root, "data", "track_b", "master_fact_pool.json")
    if not os.path.exists(pool_path):
        return [f"Missing required Track B Master Fact Pool: {pool_path}"]

    try:
        with open(pool_path, "r", encoding="utf-8") as f:
            pool = json.load(f)

        dev_facts = pool.get("dev_facts", [])
        held_facts = pool.get("heldout_facts", [])
        total_facts = len(dev_facts) + len(held_facts)

        if total_facts < 150:
            errors.append(f"Track B Fact Pool Violation: Expected at least 150 facts, found {total_facts}")

        # Check disjointness
        dev_ids = {f["fact_id"] for f in dev_facts}
        held_ids = {f["fact_id"] for f in held_facts}
        id_overlap = dev_ids & held_ids
        if id_overlap:
            errors.append(f"Track B Disjointness Violation: Fact ID overlap between Dev and Held: {id_overlap}")

        dev_components = {f.get("component") for f in dev_facts if f.get("component")}
        held_components = {f.get("component") for f in held_facts if f.get("component")}
        comp_overlap = dev_components & held_components
        if comp_overlap:
            errors.append(f"Track B Disjointness Violation: Component overlap between Dev and Held: {comp_overlap}")

        dev_vals = {f.get("value") for f in dev_facts if f.get("value")}
        held_vals = {f.get("value") for f in held_facts if f.get("value")}
        val_overlap = dev_vals & held_vals
        if val_overlap:
            errors.append(f"Track B Disjointness Violation: Value overlap between Dev and Held: {val_overlap}")

        # Check for real-world standards
        all_facts = dev_facts + held_facts
        forbidden_patterns = [r"\bIEEE\b", r"\bAES-\b", r"\bASTM\b", r"\bMIL-STD\b"]
        for fact in all_facts:
            text_repr = json.dumps(fact)
            for pat in forbidden_patterns:
                if re.search(pat, text_repr, re.IGNORECASE):
                    errors.append(f"Track B Invented Values Violation: Found forbidden standard '{pat}' in fact {fact.get('fact_id')}")

        # If questions exist, check usage count and prompt formatting
        for split_name, fname in [("dev", "track_b_dev_split.json"), ("heldout", "track_b_heldout_candidate.json")]:
            split_p = os.path.join(repo_root, "data", "track_b", fname)
            if not os.path.exists(split_p):
                continue
            with open(split_p, "r", encoding="utf-8") as sf:
                questions = json.load(sf)
            fact_usage = {}
            for q in questions:
                # Check for doc/section citations
                prompt = q.get("prompt", "")
                if re.search(r"\bDOC-\d+\b", prompt, re.IGNORECASE) or re.search(r"\bSection\s+\d+", prompt, re.IGNORECASE):
                    errors.append(f"Track B Prompt Violation: Question '{q.get('question_id')}' in {split_name} cites document or section number")
                
                # Check fact origin
                q_facts = q.get("fact_ids", [])
                for fid in q_facts:
                    fact_usage[fid] = fact_usage.get(fid, 0) + 1
                    if split_name == "dev" and fid not in dev_ids:
                        errors.append(f"Track B Split Violation: Dev question uses non-dev fact '{fid}'")
                    elif split_name == "heldout" and fid not in held_ids:
                        errors.append(f"Track B Split Violation: Held-out question uses non-held-out fact '{fid}'")

            for fid, count in fact_usage.items():
                if count > 2:
                    errors.append(f"Track B Fact Usage Violation: Fact '{fid}' used in {count} questions (max allowed: 2)")

    except Exception as e:
        errors.append(f"Track B Fact Pool audit failed with error: {e}")

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

    # 4. Secret leakage check
    secret_errors = audit_secret_leakage(repo_root)
    all_errors.extend(secret_errors)

    # 5. Part-level disjointness across splits
    disjoint_errors = audit_split_part_disjointness(repo_root)
    all_errors.extend(disjoint_errors)

    # 6. Track B fact pool and disjointness audit
    track_b_errors = audit_track_b_facts(repo_root)
    all_errors.extend(track_b_errors)

    # 7. Check any existing run record JSONL files in results/
    record_files = glob.glob(os.path.join(repo_root, "results", "**", "*.jsonl"), recursive=True)
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


