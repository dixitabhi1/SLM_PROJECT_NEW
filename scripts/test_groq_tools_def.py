import urllib.request, json, os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('GROQ_API_KEY')

tools_def = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "Execute a SQLite query",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_name": {"type": "string"},
                    "query": {"type": "string"}
                },
                "required": ["db_name", "query"]
            }
        }
    }
]

payload = {
    'model': 'openai/gpt-oss-120b',
    'messages': [
        {'role': 'user', 'content': 'Query world_1 database for count of cities where CountryCode = "USA"'}
    ],
    'tools': tools_def,
    'max_tokens': 200
}

req = urllib.request.Request(
    'https://api.groq.com/openai/v1/chat/completions',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print("Success with tools def!")
        print("Choice message:", data['choices'][0]['message'])
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code, e.read().decode('utf-8'))

