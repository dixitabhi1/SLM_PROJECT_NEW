import os
import sys
import json
import urllib.request
import sqlite3
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

from src.sandbox.runner import execute_python_code

def run_local_sql(db_name: str, query: str) -> str:
    db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_name, f"{db_name}.sqlite")
    if not os.path.exists(db_path):
        return f"ERROR: Database '{db_name}' not found."
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        conn.close()
        return str(rows[:10])
    except Exception as e:
        return f"ERROR: {str(e)}"

# Load Item 1
with open(os.path.join(REPO_ROOT, "data", "calibration_hard_20_items.json"), "r", encoding="utf-8") as f:
    item = json.load(f)[0]

print("=== TESTING ITEM 1 ===")
print("Prompt:", item["prompt"][:100], "...")
print("Gold:", item["gold_answer"])

# 1. Test Fenced Protocol on Qwen-27B
print("\n--- Test 1: Fenced Protocol on Qwen-27B ---")
sys_fenced = """You are an expert reasoning assistant. You have access to tools:
1. To run Python:
```python
# python code
print(...)
```
2. To run SQL:
```sql <database_name>
SELECT ...;
```
Wait for ```tool_output``` before continuing. Conclude with: Final Answer: <answer>"""

user_msg = f"{item['prompt']}\n\nYou may use python or sql tools. Conclude with 'Final Answer: <number>'."

def test_fenced_groq(model_name: str):
    messages = [
        {"role": "system", "content": sys_fenced},
        {"role": "user", "content": user_msg}
    ]
    for turn in range(4):
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps({
                "model": model_name,
                "messages": messages,
                "max_tokens": 1024,
                "temperature": 0.0
            }).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        print(f"Turn {turn+1} Output ({model_name}):\n{content[:200]}...")
        messages.append({"role": "assistant", "content": content})
        
        # Check if sql block
        import re
        sql_match = re.search(r"```sql(?:\s+([a-zA-Z0-9_\-]+))?\s*\n(.*?)```", content, re.DOTALL | re.IGNORECASE)
        py_match = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL | re.IGNORECASE)
        
        if sql_match:
            db = sql_match.group(1) or "world_1"
            q = sql_match.group(2).strip()
            out = run_local_sql(db, q)
            print(f"Executed SQL on {db}: {out}")
            messages.append({"role": "user", "content": f"```tool_output\n{out}\n```"})
        elif py_match:
            py_code = py_match.group(1).strip()
            res = execute_python_code(py_code, timeout_seconds=10.0)
            out = res.stdout if res.stdout else f"ERROR: {res.stderr}"
            print(f"Executed Python: {out.strip()}")
            messages.append({"role": "user", "content": f"```tool_output\n{out.strip()}\n```"})
        else:
            print("No tool call emitted. Finished!")
            break

print("Testing Qwen-27B Fenced...")
test_fenced_groq("qwen/qwen3.8-27b")

print("\nTesting GPT-OSS-120B Fenced...")
test_fenced_groq("openai/gpt-oss-120b")
