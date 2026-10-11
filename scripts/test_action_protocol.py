import urllib.request, json, os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('GROQ_API_KEY')

prompt = """You have access to two tools:
1. execute_python(code: str) -> str
2. execute_sql(db_name: str, query: str) -> str

To invoke a tool, write:
Action: execute_sql
Action Input: {"db_name": "world_1", "query": "SELECT count(*) FROM city WHERE CountryCode = 'USA'"}

How many cities in world_1 have CountryCode 'USA'?"""

req = urllib.request.Request(
    'https://api.groq.com/openai/v1/chat/completions',
    data=json.dumps({'model': 'openai/gpt-oss-120b', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 100}).encode('utf-8'),
    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print("Success! Generated content:")
        print(data['choices'][0]['message']['content'])
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code, e.read().decode('utf-8'))

