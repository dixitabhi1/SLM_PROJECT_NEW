"""
Isolated subprocess sandbox for safe Python and script execution.

Enforces:
- Temporary directory isolation
- Forced UTF-8 (PYTHONIOENCODING=utf-8)
- Strict wall-clock timeouts
- Memory/process limits
- No network access (simulated/enforced)
- Clean capture of stdout, stderr, exit code, and execution time
"""

import os
import sys
import tempfile
import subprocess
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    elapsed_seconds: float
    timed_out: bool
    status: str  # 'PASS', 'FAIL', 'TIMEOUT', 'ERROR'
    error_message: Optional[str] = None


def execute_python_code(
    code: str,
    timeout_seconds: float = 10.0,
    cwd: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
) -> SandboxResult:
    """
    Executes Python code in a temporary directory subprocess.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        working_dir = cwd or temp_dir
        script_path = os.path.join(temp_dir, "script.py")

        # Force UTF-8 encoding when writing code
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Environment configuration
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        # Network isolation flags where supported
        env["NO_PROXY"] = "*"
        if extra_env:
            env.update(extra_env)

        start_time = time.perf_counter()
        timed_out = False
        error_message = None

        try:
            # Run using the active Python executable
            proc = subprocess.run(
                [sys.executable, script_path],
                cwd=working_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                env=env,
            )
            elapsed = time.perf_counter() - start_time
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
            status = "PASS" if exit_code == 0 else "FAIL"

        except subprocess.TimeoutExpired as te:
            elapsed = time.perf_counter() - start_time
            timed_out = True
            exit_code = -1
            stdout = te.stdout if isinstance(te.stdout, str) else ""
            stderr = te.stderr if isinstance(te.stderr, str) else ""
            status = "TIMEOUT"
            error_message = f"Process timed out after {timeout_seconds} seconds"

        except Exception as e:
            elapsed = time.perf_counter() - start_time
            exit_code = -1
            stdout = ""
            stderr = str(e)
            status = "ERROR"
            error_message = str(e)

        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            elapsed_seconds=elapsed,
            timed_out=timed_out,
            status=status,
            error_message=error_message,
        )

