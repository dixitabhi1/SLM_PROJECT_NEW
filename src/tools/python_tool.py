"""
Python execution tool with test runner for objective code verification.
Zero LLM inside.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from src.sandbox.runner import execute_python_code, SandboxResult


@dataclass
class CodeExecutionVerdict:
    verdict: str  # 'PASS', 'FAIL', 'TIMEOUT', 'ERROR'
    stdout: str
    stderr: str
    elapsed_seconds: float
    details: Optional[str] = None


class PythonExecutionTool:
    """
    Executes Python candidate code against verification test cases.
    """

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    def execute_code(self, candidate_code: str) -> SandboxResult:
        """Runs candidate code standalone."""
        return execute_python_code(candidate_code, timeout_seconds=self.timeout_seconds)

    def verify_against_tests(
        self, candidate_code: str, test_assertions: List[str]
    ) -> CodeExecutionVerdict:
        """
        Combines candidate code with test assertions into a unified execution block.
        All assertions must pass for a 'PASS' verdict.
        """
        harness = [candidate_code, "\n# Verification Test Cases:"]
        for idx, assertion in enumerate(test_assertions):
            harness.append(f"# Test {idx + 1}")
            harness.append(assertion)

        combined_script = "\n".join(harness)
        result = execute_python_code(combined_script, timeout_seconds=self.timeout_seconds)

        if result.timed_out:
            return CodeExecutionVerdict(
                verdict="TIMEOUT",
                stdout=result.stdout,
                stderr=result.stderr,
                elapsed_seconds=result.elapsed_seconds,
                details=result.error_message,
            )
        elif result.exit_code == 0:
            return CodeExecutionVerdict(
                verdict="PASS",
                stdout=result.stdout,
                stderr=result.stderr,
                elapsed_seconds=result.elapsed_seconds,
                details="All assertions passed successfully.",
            )
        else:
            return CodeExecutionVerdict(
                verdict="FAIL",
                stdout=result.stdout,
                stderr=result.stderr,
                elapsed_seconds=result.elapsed_seconds,
                details=result.stderr.strip().splitlines()[-1] if result.stderr else "Assertion failed",
            )

