import urllib.request, json, os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('GROQ_API_KEY')

payload = {
    'model': 'openai/gpt-oss-120b',
    'messages': [
        {'role': 'system', 'content': 'You are a helpful assistant.'},
        {'role': 'user', 'content': 'Hello'}
    ],
    'max_tokens': 10
}

req = urllib.request.Request(
    'https://api.groq.com/openai/v1/chat/completions',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
)
try:
    with urllib.request.urlopen(req) as resp:
        print('System role works!')
except urllib.error.HTTPError as e:
    print('HTTP Error:', e.code, e.read().decode('utf-8'))

