import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

with open("data/calibration_hard_20_items.json", "r", encoding="utf-8") as f:
    item = json.load(f)[0]

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

req = urllib.request.Request(
    "https://api.groq.com/openai/v1/chat/completions",
    data=json.dumps({
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": sys_fenced},
            {"role": "user", "content": user_msg}
        ],
        "max_tokens": 1024
    }).encode("utf-8"),
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
)
try:
    with urllib.request.urlopen(req) as resp:
        print("Success!")
except urllib.error.HTTPError as e:
    print("HTTP Error 400 body:", e.read().decode("utf-8"))

