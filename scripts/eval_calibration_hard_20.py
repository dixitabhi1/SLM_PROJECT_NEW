"""
Evaluate 20 Hard Calibration Items across C0, C1, B0, and B1.

Targets:
1. C0 (Phi-4-mini w/o tools): 30% - 60%
2. C1 (Phi-4-mini with tools): 40% - 75%
3. B0 (GPT-OSS-120B w/o tools): <= 80%
4. B1 (GPT-OSS-120B with tools): < 100%
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
RESULTS_FILE = os.path.join(REPO_ROOT, "results", "phase4", "calibration_hard_20_eval.json")

TOOL_SYSTEM_PROMPT = """You are a helpful assistant with access to two tools:
1. execute_python(code: str) -> str: Executes Python code in a secure sandbox and returns stdout.
2. execute_sql(db_name: str, query: str) -> str: Executes a SQLite query against the specified database (e.g., world_1, orchestra, battle_death, poker_player, flight_2, tvshow, dog_kennels) and returns row results.

To call a tool, respond with ONLY a markdown code block:
```tool_call
{
  "name": "execute_python" | "execute_sql",
  "arguments": {
    "code": "..." | "query": "...", "db_name": "..."
  }
}
```
When you have the final answer, output:
Final Answer: <your final answer>
"""


def execute_tool_call(tool_name: str, args: Dict[str, Any]) -> str:
    """Executes a tool call locally."""
    if tool_name == "execute_python":
        code = args.get("code", "")
        res = execute_python_code(code, timeout_seconds=10.0)
        if res.timed_out:
            return "ERROR: Execution timed out (10s limit)"
        if res.exit_code != 0:
            return f"ERROR: Exit code {res.exit_code}\nStderr: {res.stderr}\nStdout: {res.stdout}"
        return res.stdout.strip() or "(no stdout output)"
    elif tool_name == "execute_sql":
        db_name = args.get("db_name", "")
        query = args.get("query", "")
        db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_name, f"{db_name}.sqlite")
        if not os.path.exists(db_path):
            return f"ERROR: Database '{db_name}' not found at {db_path}"
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute(query)
            rows = c.fetchmany(50)
            return str(rows)
        except Exception as e:
            return f"ERROR: SQL query failed: {e}"
    else:
        return f"ERROR: Unknown tool '{tool_name}'"


def parse_tool_call(text: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Detects and parses ```tool_call block or fallback code blocks."""
    match = re.search(r"```tool_call\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        raw_content = match.group(1).strip()
        # 1. Try standard JSON parse
        try:
            data = json.loads(raw_content)
            return True, data.get("name", ""), data.get("arguments", {})
        except Exception:
            pass

        # 2. Heuristic extraction if JSON has unescaped control chars
        name_match = re.search(r'"name":\s*"([^"]+)"', raw_content)
        tool_name = name_match.group(1) if name_match else ""

        if tool_name == "execute_python" or "execute_python" in raw_content:
            code_match = re.search(r'"code":\s*"(.*?)"\s*\}\s*\}?$', raw_content, re.DOTALL)
            if not code_match:
                code_match = re.search(r'"code":\s*"""(.*?)"""', raw_content, re.DOTALL)
            if not code_match:
                m2 = re.search(r'"code":\s*["\']?(.*)', raw_content, re.DOTALL)
                code_str = m2.group(1).rstrip('"} \n\r') if m2 else ""
            else:
                code_str = code_match.group(1)
            code_str = code_str.replace("\\n", "\n").replace('\\"', '"')
            return True, "execute_python", {"code": code_str}

        elif tool_name == "execute_sql" or "execute_sql" in raw_content:
            db_match = re.search(r'"db_name":\s*"([^"]+)"', raw_content)
            query_match = re.search(r'"query":\s*"([^"]+)"', raw_content)
            if not query_match:
                query_match = re.search(r'"query":\s*"(.*?)"', raw_content, re.DOTALL)
            db_name = db_match.group(1) if db_match else ""
            query_str = query_match.group(1) if query_match else ""
            return True, "execute_sql", {"db_name": db_name, "query": query_str}

    # 3. Fallback: if model simply output ```python ... ```
    py_match = re.search(r"```python\s*\n(.*?)\n```", text, re.DOTALL)
    if py_match:
        return True, "execute_python", {"code": py_match.group(1).strip()}

    return False, "", {}


def call_local_llama_chat(messages: List[Dict[str, str]], max_tokens: int = 2048) -> Dict[str, Any]:
    """Calls local llama-server on port 8080."""
    url = "http://127.0.0.1:8080/v1/chat/completions"
    payload = {
        "model": "phi-4-mini",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as resp:
        elapsed = time.perf_counter() - t0
        data = json.loads(resp.read().decode("utf-8"))
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "").strip()
        finish_reason = choice.get("finish_reason", "stop")
        usage = data.get("usage", {})
        return {
            "content": content,
            "finish_reason": finish_reason,
            "latency": elapsed,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0)
        }


def call_groq_chat(messages: List[Dict[str, str]], api_key: str, model_id: str = "openai/gpt-oss-120b", max_tokens: int = 2048) -> Dict[str, Any]:
    """Calls Groq API with rate limit backoff."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    for attempt in range(12):
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                elapsed = time.perf_counter() - t0
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "").strip()
                finish_reason = choice.get("finish_reason", "stop")
                usage = data.get("usage", {})
                return {
                    "content": content,
                    "finish_reason": finish_reason,
                    "latency": elapsed,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0)
                }
        except urllib.error.HTTPError as he:
            if he.code == 429:
                err_body = he.read().decode("utf-8")
                wait_match = re.search(r"try again in (\d+(?:\.\d+)?)s", err_body)
                body_wait = float(wait_match.group(1)) if wait_match else 0.0
                sleep_time = max(body_wait + 2.0, 5.0 * (attempt + 1), 10.0)
                time.sleep(sleep_time)
                continue
            raise
    raise RuntimeError("Exceeded 12 retries on Groq API")


def run_model_no_tools(item: Dict[str, Any], is_local: bool, groq_key: str = "") -> str:
    """Runs a single prompt without tools."""
    prompt = f"{item['prompt']}\n\nConclude your reasoning with the exact final numeric answer: Final Answer: <number>"
    messages = [{"role": "user", "content": prompt}]
    if is_local:
        resp = call_local_llama_chat(messages)
    else:
        resp = call_groq_chat(messages, groq_key, model_id="openai/gpt-oss-120b")
        time.sleep(1.0)
    return resp["content"]


def run_model_with_tools(item: Dict[str, Any], is_local: bool, groq_key: str = "", max_turns: int = 8) -> str:
    """Runs a multi-turn conversation with the tool harness."""
    user_prompt = f"{item['prompt']}\n\nYou may use execute_python or execute_sql to calculate values. Conclude with 'Final Answer: <number>'."
    messages = [
        {"role": "system", "content": TOOL_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]

    for turn in range(max_turns):
        if is_local:
            resp = call_local_llama_chat(messages)
        else:
            resp = call_groq_chat(messages, groq_key, model_id="openai/gpt-oss-120b")
            time.sleep(1.0)

        content = resp["content"]
        messages.append({"role": "assistant", "content": content})

        has_tool, tool_name, args = parse_tool_call(content)
        if not has_tool:
            # Model finished
            return content

        tool_output = execute_tool_call(tool_name, args)
        tool_response_msg = f"```tool_response\n{{\n  \"name\": \"{tool_name}\",\n  \"output\": \"{tool_output}\"\n}}\n```"
        messages.append({"role": "user", "content": tool_response_msg})

    return messages[-1]["content"]


def main():
    from dotenv import load_dotenv
    load_dotenv()
    groq_api_key = os.getenv("GROQ_API_KEY", "")

    with open(CALIB_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)

    print(f"Loaded {len(items)} calibration items.")

    conditions = [
        ("C0_Phi4Mini_NoTools", True, False),
        ("C1_Phi4Mini_Tools", True, True),
        ("B0_GPT120B_NoTools", False, False),
        ("B1_GPT120B_Tools", False, True),
    ]

    results = {}

    for cond_name, is_local, use_tools in conditions:
        print(f"\n==========================================")
        print(f"Running Evaluation Condition: {cond_name}")
        print(f"==========================================")
        cond_records = []
        for idx, item in enumerate(items, 1):
            it_id = item["subtask_id"]
            solvability = item["solvability"]
            num_stages = item["num_stages"]

            print(f"[{idx}/{len(items)}] {it_id} ({solvability}, {num_stages}-stage)...", end=" ", flush=True)

            try:
                if use_tools:
                    output = run_model_with_tools(item, is_local=is_local, groq_key=groq_api_key)
                else:
                    output = run_model_no_tools(item, is_local=is_local, groq_key=groq_api_key)

                score = score_record(item, output)
                passed = score["passed"]
                print(f"-> {'PASS' if passed else 'FAIL'} (gold={item['gold_answer']})")
                cond_records.append({
                    "item_id": it_id,
                    "condition": cond_name,
                    "solvability": solvability,
                    "num_stages": num_stages,
                    "output": output,
                    "gold": item["gold_answer"],
                    "passed": passed,
                    "score_details": score["details"]
                })
            except Exception as e:
                print(f"-> ERROR: {e}")
                cond_records.append({
                    "item_id": it_id,
                    "condition": cond_name,
                    "solvability": solvability,
                    "num_stages": num_stages,
                    "output": "",
                    "gold": item["gold_answer"],
                    "passed": False,
                    "score_details": f"Execution error: {e}"
                })

        # Calculate metrics for condition
        total_acc = (sum(1 for r in cond_records if r["passed"]) / len(cond_records)) * 100
        tool_req = [r for r in cond_records if r["solvability"] == "tool-required"]
        tool_req_acc = (sum(1 for r in tool_req if r["passed"]) / len(tool_req)) * 100 if tool_req else 0.0
        solv = [r for r in cond_records if r["solvability"] == "solvable_without_tools"]
        solv_acc = (sum(1 for r in solv if r["passed"]) / len(solv)) * 100 if solv else 0.0

        results[cond_name] = {
            "total_acc": round(total_acc, 2),
            "tool_required_acc": round(tool_req_acc, 2),
            "solvable_w_o_tools_acc": round(solv_acc, 2),
            "records": cond_records
        }

    # Summary Table
    print("\n" + "=" * 70)
    print("CALIBRATION EVALUATION RESULTS (20 ITEMS)")
    print("=" * 70)
    print(f"{'Condition':<25} | {'Total Acc':<10} | {'Tool-Req':<10} | {'Solv w/o Tools':<15} | {'Target Check'}")
    print("-" * 70)

    c0_acc = results["C0_Phi4Mini_NoTools"]["total_acc"]
    c0_pass = 30.0 <= c0_acc <= 60.0
    print(f"{'C0 (Phi-4-mini w/o tools)':<25} | {c0_acc:>8.1f}% | {results['C0_Phi4Mini_NoTools']['tool_required_acc']:>8.1f}% | {results['C0_Phi4Mini_NoTools']['solvable_w_o_tools_acc']:>13.1f}% | {'PASS' if c0_pass else 'FAIL'} (30-60%)")

    c1_acc = results["C1_Phi4Mini_Tools"]["total_acc"]
    c1_pass = 40.0 <= c1_acc <= 75.0
    print(f"{'C1 (Phi-4-mini w/ tools)':<25} | {c1_acc:>8.1f}% | {results['C1_Phi4Mini_Tools']['tool_required_acc']:>8.1f}% | {results['C1_Phi4Mini_Tools']['solvable_w_o_tools_acc']:>13.1f}% | {'PASS' if c1_pass else 'FAIL'} (40-75%)")

    b0_acc = results["B0_GPT120B_NoTools"]["total_acc"]
    b0_pass = b0_acc <= 80.0
    print(f"{'B0 (GPT-120B w/o tools)':<25} | {b0_acc:>8.1f}% | {results['B0_GPT120B_NoTools']['tool_required_acc']:>8.1f}% | {results['B0_GPT120B_NoTools']['solvable_w_o_tools_acc']:>13.1f}% | {'PASS' if b0_pass else 'FAIL'} (<=80%)")

    b1_acc = results["B1_GPT120B_Tools"]["total_acc"]
    b1_pass = b1_acc < 100.0
    print(f"{'B1 (GPT-120B w/ tools)':<25} | {b1_acc:>8.1f}% | {results['B1_GPT120B_Tools']['tool_required_acc']:>8.1f}% | {results['B1_GPT120B_Tools']['solvable_w_o_tools_acc']:>13.1f}% | {'PASS' if b1_pass else 'FAIL'} (<100%)")
    print("=" * 70)

    # Save to JSON
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved evaluation results to {RESULTS_FILE}")


if __name__ == "__main__":
    main()

