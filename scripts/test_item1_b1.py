import urllib.request, json, os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('GROQ_API_KEY')

import sys
sys.path.insert(0, ".")
from scripts.eval_calibration_hard_20 import TOOL_SYSTEM_PROMPT, CALIB_FILE

with open(CALIB_FILE) as f:
    item = json.load(f)[0]

user_prompt = f"{item['prompt']}\n\nYou may use execute_python or execute_sql to calculate values. Conclude with 'Final Answer: <number>'."
messages = [
    {"role": "system", "content": TOOL_SYSTEM_PROMPT},
    {"role": "user", "content": user_prompt}
]

req = urllib.request.Request(
    'https://api.groq.com/openai/v1/chat/completions',
    data=json.dumps({'model': 'openai/gpt-oss-120b', 'messages': messages, 'max_tokens': 2048}).encode('utf-8'),
    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
)
try:
    with urllib.request.urlopen(req) as resp:
        print('Success!')
except urllib.error.HTTPError as e:
    print('HTTP Error:', e.code, e.read().decode('utf-8'))
