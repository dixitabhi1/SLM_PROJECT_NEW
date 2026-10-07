"""
Unit tests for the isolated Python sandbox execution.
Verifies pass, crash, hang/timeout, and UTF-8 encoding cases.
"""

import pytest
from src.sandbox.runner import execute_python_code


def test_sandbox_pass_case():
    code = "print('Hello, Sandbox!'); exit(0)"
    res = execute_python_code(code, timeout_seconds=5.0)
    assert res.status == "PASS"
    assert res.exit_code == 0
    assert "Hello, Sandbox!" in res.stdout
    assert not res.timed_out


def test_sandbox_crash_case():
    code = "raise ValueError('Intentional sandbox exception')"
    res = execute_python_code(code, timeout_seconds=5.0)
    assert res.status == "FAIL"
    assert res.exit_code != 0
    assert "ValueError: Intentional sandbox exception" in res.stderr
    assert not res.timed_out


def test_sandbox_timeout_case():
    code = "import time\nwhile True:\n    time.sleep(0.1)"
    res = execute_python_code(code, timeout_seconds=1.0)
    assert res.status == "TIMEOUT"
    assert res.timed_out
    assert res.exit_code == -1
    assert "timed out after 1.0 seconds" in (res.error_message or "")


def test_sandbox_utf8_encoding_case():
    code = "print('UTF-8 test: π ≈ 3.14159, é, 日本語, 🚀')"
    res = execute_python_code(code, timeout_seconds=5.0)
    assert res.status == "PASS"
    assert "π ≈ 3.14159" in res.stdout
    assert "日本語" in res.stdout
    assert "🚀" in res.stdout

