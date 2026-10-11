import os
import sys
import json
import urllib.request
import sqlite3
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

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

with open("data/calibration_hard_20_items.json", "r", encoding="utf-8") as f:
    item = json.load(f)[0]

sys_prompt = """You are an expert reasoning assistant. You have access to local tools:
1. To run Python:
```python
# your code
print(...)
```
2. To run SQL against a SQLite database:
```sql <database_name>
SELECT ...;
```
Wait for ```tool_output``` before continuing. You may also answer directly without calling a tool.
Conclude your final answer with: Final Answer: <number>"""

user_prompt = f"{item['prompt']}\n\nYou may use python or sql tools. Conclude with 'Final Answer: <number>'."

messages = [
    {"role": "system", "content": sys_prompt},
    {"role": "user", "content": user_prompt}
]

def call_local(messages):
    payload = {
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.0
    }
    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

print("=== Testing Phi-4-mini Fenced Protocol on Item 1 ===")
for turn in range(5):
    res = call_local(messages)
    content = res["choices"][0]["message"]["content"]
    print(f"\n--- Turn {turn+1} Output ---\n{content}")
    messages.append({"role": "assistant", "content": content})
    
    # Check for sql block
    sql_m = re.search(r"```sql(?:\s+([a-zA-Z0-9_\-]+))?\s*\n(.*?)```", content, re.DOTALL | re.IGNORECASE)
    py_m = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL | re.IGNORECASE)
    
    if sql_m:
        db = sql_m.group(1) or "world_1"
        q = sql_m.group(2).strip()
        out = run_local_sql(db, q)
        print(f"Executed SQL on {db}: {out}")
        messages.append({"role": "user", "content": f"```tool_output\n{out}\n```"})
    elif py_m:
        py_code = py_m.group(1).strip()
        p = execute_python_code(py_code, timeout_seconds=10.0)
        out = p.stdout.strip() if p.stdout else f"ERROR: {p.stderr}"
        print(f"Executed Python: {out}")
        messages.append({"role": "user", "content": f"```tool_output\n{out}\n```"})
    else:
        print("Final response received.")
        break

