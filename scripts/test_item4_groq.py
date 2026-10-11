import urllib.request, json, os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('GROQ_API_KEY')

with open('data/calibration_hard_20_items.json') as f:
    items = json.load(f)

prompt = items[3]['prompt'] + "\n\nConclude your reasoning with the exact final numeric answer: Final Answer: [number]"
req = urllib.request.Request(
    'https://api.groq.com/openai/v1/chat/completions',
    data=json.dumps({'model': 'openai/gpt-oss-120b', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 2048}).encode('utf-8'),
    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
)
try:
    with urllib.request.urlopen(req) as resp:
        print('Success!')
except urllib.error.HTTPError as e:
    print('HTTP Error:', e.code, e.read().decode('utf-8'))

