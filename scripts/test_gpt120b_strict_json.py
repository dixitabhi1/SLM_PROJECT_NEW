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

tools_def = [
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Executes Python code in a secure local sandbox and returns standard output. Arguments must be valid JSON: {\"code\": \"<python code>\"}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The Python code string to execute."}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "Executes a SQL SELECT query against a target SQLite database. Arguments must be valid JSON: {\"db_name\": \"<db>\", \"query\": \"<sql>\"}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_name": {"type": "string", "description": "The SQLite database identifier (e.g. 'world_1', 'orchestra', 'flight_2')."},
                    "query": {"type": "string", "description": "The SQL query to execute."}
                },
                "required": ["db_name", "query"]
            }
        }
    }
]

with open("data/calibration_hard_20_items.json", "r", encoding="utf-8") as f:
    item = json.load(f)[0]

print("=== Testing GPT-OSS-120B with JSON Instruction ===")
messages = [
    {
        "role": "system",
        "content": (
            "You are an expert reasoning assistant. Use tools when needed. "
            "IMPORTANT: When calling tools, ensure the arguments are strictly formatted as a valid JSON object. "
            "For execute_python, provide {\"code\": \"print(...)\"}. "
            "Conclude your final answer with: Final Answer: <number>"
        )
    },
    {"role": "user", "content": f"{item['prompt']}\n\nConclude with 'Final Answer: <number>'."}
]

for turn in range(5):
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": messages,
        "tools": tools_def,
        "max_tokens": 1024,
        "temperature": 0.0
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print("HTTP Error 400 on Turn", turn + 1, ":", e.read().decode("utf-8"))
        break
    
    choice = res["choices"][0]
    msg = choice["message"]
    messages.append(msg)
    
    tool_calls = msg.get("tool_calls")
    if not tool_calls:
        print(f"\nFinal message (Turn {turn+1}):\n", msg.get("content"))
        break
        
    for tc in tool_calls:
        func = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"])
        print(f"Turn {turn+1}: Call {func}({args})")
        if func == "execute_sql":
            out = run_local_sql(args["db_name"], args["query"])
        elif func == "execute_python":
            p = execute_python_code(args["code"], timeout_seconds=10.0)
            out = p.stdout.strip() if p.stdout else f"ERROR: {p.stderr}"
        else:
            out = "Tool not implemented"
        print(f"-> Tool Output: {out}")
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "name": func,
            "content": out
        })

