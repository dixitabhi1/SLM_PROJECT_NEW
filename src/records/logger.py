"""
Append-only JSONL run records logger.
Enforces Hard Rule 2 (Raw files immutable) and Master Prompt Section 4 schema.
Zero fabricated records.
"""

import os
import json
import hashlib
import datetime
import subprocess
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, asdict


def get_current_git_commit() -> str:
    """Returns the current git HEAD commit SHA, or 'unknown'."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def compute_prompt_hash(prompt_text: str) -> str:
    """Calculates SHA-256 hex digest of prompt string."""
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


@dataclass
class CallRecord:
    item_id: str
    condition: str
    model_id: str
    prompt_hash: str
    seed: int
    full_output: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str
    latency_ms: float
    tool_calls: List[Dict[str, Any]]
    verifier_result: Dict[str, Any]
    git_commit: str
    status: str  # 'COMPLETE' or 'FAILED'
    timestamp: str


class RunRecordsLogger:
    """
    Append-only logger for experimental runs.
    """

    def __init__(self, log_file_path: str):
        self.log_file_path = log_file_path
        os.makedirs(os.path.dirname(os.path.abspath(log_file_path)), exist_ok=True)
        # Verify file existence or touch it
        if not os.path.exists(self.log_file_path):
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                pass

    def log_call(
        self,
        item_id: str,
        condition: str,
        model_id: str,
        prompt: str,
        seed: int,
        full_output: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        finish_reason: str,
        latency_ms: float,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        verifier_result: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
    ) -> CallRecord:
        """
        Appends a single CallRecord to the JSONL log file.
        Hard Rule 2: Strictly append-only.
        """
        p_hash = compute_prompt_hash(prompt)
        commit = get_current_git_commit()
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Hard Rule 3: Fail loudly enforcement
        if status is None:
            if not full_output or completion_tokens == 0 or finish_reason != "stop":
                inferred_status = "FAILED"
            else:
                inferred_status = "COMPLETE"
        else:
            inferred_status = status

        record = CallRecord(
            item_id=item_id,
            condition=condition,
            model_id=model_id,
            prompt_hash=p_hash,
            seed=seed,
            full_output=full_output,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            finish_reason=finish_reason,
            latency_ms=round(latency_ms, 2),
            tool_calls=tool_calls or [],
            verifier_result=verifier_result or {},
            git_commit=commit,
            status=inferred_status,
            timestamp=ts,
        )

        line = json.dumps(asdict(record), ensure_ascii=False)
        with open(self.log_file_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        return record

    def get_completed_items(self, condition: str) -> Set[str]:
        """
        Returns the set of item_ids that have a 'COMPLETE' status record for the condition.
        Used to make batch runs resumable without redundant calls.
        """
        completed = set()
        if not os.path.exists(self.log_file_path):
            return completed

        with open(self.log_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("condition") == condition and data.get("status") == "COMPLETE":
                        completed.add(data.get("item_id"))
                except Exception:
                    continue
        return completed

    def load_all_records(self) -> List[Dict[str, Any]]:
        """Reads all records from the append-only log."""
        records = []
        if not os.path.exists(self.log_file_path):
            return records

        with open(self.log_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        return records

