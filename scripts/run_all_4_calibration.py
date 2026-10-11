"""
Run all 4 conditions on the 20 Hard Calibration Items:
1. C0 (Phi-4-mini w/o tools)
2. C1 (Phi-4-mini with tools)
3. B0 (GPT-OSS-120B w/o tools)
4. B1 (GPT-OSS-120B with tools)
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
import sqlite3
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.sandbox.runner import execute_python_code
from src.eval.versioned_scorer import score_record

CALIB_FILE = os.path.join(REPO_ROOT, "data", "calibration_hard_20_items.json")
RESULTS_FILE = os.path.join(REPO_ROOT, "results", "phase4", "calibration_hard_20_results.json")


def execute_tool_call(tool_name: str, args: Dict[str, Any]) -> str:
    if tool_name == "execute_python":
        code = args.get("code", "")
        res = execute_python_code(code, timeout_seconds=10.0)
        if res.timed_out:
            return "ERROR: Execution timed out"
        if res.exit_code != 0:
            return f"ERROR: {res.stderr[:200]}"
        return res.stdout.strip() or "(no stdout output)"
    elif tool_name == "execute_sql":
        db_name = args.get("db_name", "")
        query = args.get("query", "")
        db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_name, f"{db_name}.sqlite")
        if not os.path.exists(db_path):
            return f"ERROR: Database '{db_name}' not found"
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute(query)
            rows = c.fetchmany(50)
            return str(rows)
        except Exception as e:
            return f"ERROR: {e}"
    return f"ERROR: Unknown tool '{tool_name}'"


def parse_action_or_tool(text: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Detects either ```tool_call or Action: protocol."""
    # 1. Check Action protocol
    act_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", text)
    inp_match = re.search(r"Action Input:\s*(\{.*?\})", text, re.DOTALL)
    if act_match and inp_match:
        try:
            tool_name = act_match.group(1).strip()
            args = json.loads(inp_match.group(1).strip())
            return True, tool_name, args
        except Exception:
            pass

    # 2. Check ```tool_call
    tc_match = re.search(r"```tool_call\s*\n(.*?)\n```", text, re.DOTALL)
    if tc_match:
        raw = tc_match.group(1).strip()
        try:
            data = json.loads(raw)
            return True, data.get("name", ""), data.get("arguments", {})
        except Exception:
            # Heuristic
            if "execute_python" in raw:
                code_m = re.search(r'"code":\s*"(.*?)"\s*\}', raw, re.DOTALL)
                code_str = code_m.group(1) if code_m else ""
                return True, "execute_python", {"code": code_str.replace("\\n", "\n").replace('\\"', '"')}
            elif "execute_sql" in raw:
                db_m = re.search(r'"db_name":\s*"([^"]+)"', raw)
                q_m = re.search(r'"query":\s*"([^"]+)"', raw)
                return True, "execute_sql", {"db_name": db_m.group(1) if db_m else "", "query": q_m.group(1) if q_m else ""}

    # 3. Check ```python ... ```
    py_match = re.search(r"```python\s*\n(.*?)\n```", text, re.DOTALL)
    if py_match:
        return True, "execute_python", {"code": py_match.group(1).strip()}

    return False, "", {}


def call_local_llama(messages: List[Dict[str, str]], max_tokens: int = 2048) -> str:
    url = "http://127.0.0.1:8080/v1/chat/completions"
    payload = {
        "model": "phi-4-mini",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


def call_groq_120b(messages: List[Dict[str, str]], api_key: str, max_tokens: int = 2048) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    for attempt in range(10):
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0].get("message", {})
                content = choice.get("content", "").strip()
                reasoning = choice.get("reasoning", "").strip()
                return content or reasoning
        except urllib.error.HTTPError as he:
            if he.code == 429:
                err_body = he.read().decode("utf-8")
                wait_m = re.search(r"try again in (\d+(?:\.\d+)?)s", err_body)
                wait_s = float(wait_m.group(1)) if wait_m else 10.0
                time.sleep(max(wait_s + 2.0, 10.0))
                continue
            raise
    raise RuntimeError("Exceeded 10 retries on Groq")


def run_c1_tools(item: Dict[str, Any]) -> str:
    prompt = f"{item['prompt']}\n\nYou may use execute_python or execute_sql if helpful, or solve directly. Conclude with 'Final Answer: <number>'."
    messages = [{"role": "user", "content": prompt}]
    for turn in range(8):
        content = call_local_llama(messages)
        messages.append({"role": "assistant", "content": content})
        has_tool, tool_name, args = parse_action_or_tool(content)
        if not has_tool or "Final Answer:" in content:
            return content
        out = execute_tool_call(tool_name, args)
        messages.append({"role": "user", "content": f"Tool output: {out}\nNow proceed to calculate the final answer. Conclude with 'Final Answer: <number>'."})
    return messages[-1]["content"]


def run_b1_tools(item: Dict[str, Any], api_key: str) -> str:
    prompt = f"{item['prompt']}\n\nYou may use execute_python or execute_sql if helpful, or solve directly. Conclude with 'Final Answer: <number>'."
    messages = [{"role": "user", "content": prompt}]
    for turn in range(8):
        content = call_groq_120b(messages, api_key)
        messages.append({"role": "assistant", "content": content})
        has_tool, tool_name, args = parse_action_or_tool(content)
        if not has_tool or "Final Answer:" in content:
            return content
        out = execute_tool_call(tool_name, args)
        messages.append({"role": "user", "content": f"Tool output: {out}\nNow proceed to calculate the final answer. Conclude with 'Final Answer: <number>'."})
        time.sleep(1.0)
    return messages[-1]["content"]


def main():
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY", "")

    with open(CALIB_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)

    # 1. Load previously completed C0 and B0 runs
    c0_eval_path = os.path.join(REPO_ROOT, "results", "phase4", "calibration_c0_c1_eval.json")
    b0_eval_path = os.path.join(REPO_ROOT, "results", "phase4", "calibration_gpt_b0_b1_eval.json")

    with open(c0_eval_path, "r", encoding="utf-8") as f:
        c0_data = json.load(f)
    with open(b0_eval_path, "r", encoding="utf-8") as f:
        b0_data = json.load(f)

    c0_acc = c0_data["c0_total_acc"] # 40.0%
    b0_acc = b0_data["b0_total_acc"] # 45.0%

    print(f"C0 Total Acc: {c0_acc:.1f}% (Target: 30-60%)")
    print(f"B0 Total Acc: {b0_acc:.1f}% (Target: <= 80%)")

    # 2. Run C1 (Phi-4-mini with tools)
    print("\n--- Running C1 (Phi-4-mini with tools) ---")
    c1_records = []
    for idx, it in enumerate(items, 1):
        print(f"[C1 {idx}/20] {it['subtask_id']} ({it['solvability']})...", end=" ", flush=True)
        out = run_c1_tools(it)
        sc = score_record(it, out)
        passed = sc["passed"]
        print(f"-> {'PASS' if passed else 'FAIL'} (gold={it['gold_answer']})")
        c1_records.append({"item_id": it["subtask_id"], "passed": passed, "output": out})

    c1_acc = (sum(1 for r in c1_records if r["passed"]) / len(c1_records)) * 100
    print(f"C1 Total Acc: {c1_acc:.1f}% (Target: 40-75%)")

    # 3. Run B1 (GPT-120B with tools)
    print("\n--- Running B1 (GPT-120B with tools) ---")
    b1_records = []
    for idx, it in enumerate(items, 1):
        print(f"[B1 {idx}/20] {it['subtask_id']} ({it['solvability']})...", end=" ", flush=True)
        out = run_b1_tools(it, api_key)
        sc = score_record(it, out)
        passed = sc["passed"]
        print(f"-> {'PASS' if passed else 'FAIL'} (gold={it['gold_answer']})")
        b1_records.append({"item_id": it["subtask_id"], "passed": passed, "output": out})
        time.sleep(1.0)

    b1_acc = (sum(1 for r in b1_records if r["passed"]) / len(b1_records)) * 100
    print(f"B1 Total Acc: {b1_acc:.1f}% (Target: < 100%)")

    summary = {
        "c0_total_acc": c0_acc,
        "c1_total_acc": c1_acc,
        "b0_total_acc": b0_acc,
        "b1_total_acc": b1_acc,
        "targets_check": {
            "c0_in_30_60": 30.0 <= c0_acc <= 60.0,
            "c1_in_40_75": 40.0 <= c1_acc <= 75.0,
            "b0_le_80": b0_acc <= 80.0,
            "b1_lt_100": b1_acc < 100.0,
            "all_hold": (30.0 <= c0_acc <= 60.0 and 40.0 <= c1_acc <= 75.0 and b0_acc <= 80.0 and b1_acc < 100.0)
        }
    }

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("FINAL 4-WAY CALIBRATION VERDICT:")
    print(f"  C0 (Phi-4-mini w/o tools): {c0_acc:.1f}% [Target: 30-60%] -> {'PASS' if 30 <= c0_acc <= 60 else 'FAIL'}")
    print(f"  C1 (Phi-4-mini w/ tools):   {c1_acc:.1f}% [Target: 40-75%] -> {'PASS' if 40 <= c1_acc <= 75 else 'FAIL'}")
    print(f"  B0 (GPT-120B w/o tools):   {b0_acc:.1f}% [Target: <= 80%] -> {'PASS' if b0_acc <= 80 else 'FAIL'}")
    print(f"  B1 (GPT-120B w/ tools):     {b1_acc:.1f}% [Target: < 100%] -> {'PASS' if b1_acc < 100 else 'FAIL'}")
    print("=" * 60)


if __name__ == "__main__":
    main()

