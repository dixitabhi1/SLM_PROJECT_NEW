import os, sys, json, urllib.request, urllib.error
sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
from src.pipeline.specialist_pipeline import get_bm25_retriever

with open("data/track_b/track_b_heldout_split.json", "r", encoding="utf-8") as f:
    items = json.load(f)

it = items[1]
raw_prompt = it["prompt"]
word_cap = it.get("word_cap", 75)
retriever = get_bm25_retriever()
query_str = f"{raw_prompt}\n\nProvide a concise answer in key-value pairs (max {word_cap} words). Conclude with 'Final Answer: <key-value pairs>'."
passages = retriever.retrieve(query_str, top_k=5)
context_str = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in passages])
augmented_prompt = f"[Retrieved Reference Documents]:\n{context_str}\n\nQuestion:\n{raw_prompt}\n\nProvide a concise answer in key-value pairs (max {word_cap} words).\nConclude with 'Final Answer: <key-value pairs>'."

url = "https://api.groq.com/openai/v1/chat/completions"
payload = {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": augmented_prompt}], "max_tokens": 4096}
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
try:
    with urllib.request.urlopen(req) as resp:
        print("SUCCESS:", resp.read().decode("utf-8")[:200])
except urllib.error.HTTPError as e:
    print("HTTP ERROR:", e.code)
    print("BODY:", e.read().decode("utf-8"))

