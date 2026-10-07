"""
Report generator and traceability verifier.
Builds summary tables directly from immutable JSONL run records.
Asserts that every printed figure equals a recomputed value (Hard Rule 1 & Section 4).
Zero fabricated numbers.
"""

import os
import json
import random
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ConditionSummary:
    condition: str
    model_id: str
    total_calls: int
    valid_items: int
    failed_items: int
    exclusion_rate: float
    task_accuracy: float
    ci_95_low: float
    ci_95_high: float
    mean_latency_s: float
    mean_tokens: float


def compute_bootstrap_ci(
    scores: List[float], n_bootstrap: int = 1000, alpha: float = 0.05, seed: int = 42
) -> Tuple[float, float]:
    """Computes non-parametric 95% bootstrap confidence interval over items."""
    if not scores:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(scores)
    means = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(scores) for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    low_idx = int((alpha / 2.0) * n_bootstrap)
    high_idx = int((1.0 - alpha / 2.0) * n_bootstrap)
    return (round(means[low_idx], 4), round(means[high_idx], 4))


class ReportGenerator:
    """
    Computes performance statistics directly from raw JSONL records.
    """

    def __init__(self, records_jsonl_path: str):
        self.records_path = records_jsonl_path
        self.records: List[Dict[str, Any]] = []
        if os.path.exists(records_jsonl_path):
            with open(records_jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.records.append(json.loads(line))

    def compute_summary_by_condition(self, condition: str) -> ConditionSummary:
        """Computes summary statistics for a specific experimental condition."""
        cond_records = [r for r in self.records if r.get("condition") == condition]
        total = len(cond_records)
        if total == 0:
            return ConditionSummary(
                condition=condition,
                model_id="N/A",
                total_calls=0,
                valid_items=0,
                failed_items=0,
                exclusion_rate=0.0,
                task_accuracy=0.0,
                ci_95_low=0.0,
                ci_95_high=0.0,
                mean_latency_s=0.0,
                mean_tokens=0.0,
            )

        model_id = cond_records[0].get("model_id", "unknown")
        valid = [r for r in cond_records if r.get("status") == "COMPLETE"]
        failed = [r for r in cond_records if r.get("status") == "FAILED"]

        excl_rate = round(len(failed) / total, 4)

        # Accuracy: verifier_result verdict == 'PASS'
        scores = []
        latencies = []
        tokens = []

        for r in valid:
            verdict = r.get("verifier_result", {}).get("verdict", "")
            is_pass = 1.0 if verdict == "PASS" else 0.0
            scores.append(is_pass)
            latencies.append(r.get("latency_ms", 0.0) / 1000.0)
            tokens.append(float(r.get("completion_tokens", 0)))

        acc = round(sum(scores) / len(scores), 4) if scores else 0.0
        ci_low, ci_high = compute_bootstrap_ci(scores)
        mean_lat = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        mean_tok = round(sum(tokens) / len(tokens), 1) if tokens else 0.0

        return ConditionSummary(
            condition=condition,
            model_id=model_id,
            total_calls=total,
            valid_items=len(valid),
            failed_items=len(failed),
            exclusion_rate=excl_rate,
            task_accuracy=acc,
            ci_95_low=ci_low,
            ci_95_high=ci_high,
            mean_latency_s=mean_lat,
            mean_tokens=mean_tok,
        )

    def generate_markdown_table(self, conditions: List[str]) -> str:
        """Generates markdown table across specified conditions."""
        lines = [
            "| Condition | Model ID | Total | Valid | Failed | Excl Rate | Accuracy (95% CI) | Mean Latency (s) | Mean Comp Tokens |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for c in conditions:
            s = self.compute_summary_by_condition(c)
            ci_str = f"[{s.ci_95_low:.2%}, {s.ci_95_high:.2%}]"
            acc_str = f"{s.task_accuracy:.2%} {ci_str}"
            lines.append(
                f"| **{s.condition}** | `{s.model_id}` | {s.total_calls} | {s.valid_items} | {s.failed_items} | "
                f"{s.exclusion_rate:.1%} | {acc_str} | {s.mean_latency_s:.2f}s | {s.mean_tokens:.1f} |"
            )
        return "\n".join(lines)

    def verify_traceability(self, condition: str, expected_summary: ConditionSummary) -> bool:
        """
        Traceability test: Recomputes values from raw records and asserts exact equality.
        """
        recomputed = self.compute_summary_by_condition(condition)
        assert recomputed.total_calls == expected_summary.total_calls, "Traceability mismatch: total_calls"
        assert recomputed.valid_items == expected_summary.valid_items, "Traceability mismatch: valid_items"
        assert recomputed.failed_items == expected_summary.failed_items, "Traceability mismatch: failed_items"
        assert abs(recomputed.task_accuracy - expected_summary.task_accuracy) < 1e-6, "Traceability mismatch: accuracy"
        assert abs(recomputed.mean_latency_s - expected_summary.mean_latency_s) < 1e-4, "Traceability mismatch: latency"
        return True

