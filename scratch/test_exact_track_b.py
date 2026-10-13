import os
import sys
import json
import urllib.request
from dotenv import load_dotenv

REPO_ROOT = "."
sys.path.insert(0, REPO_ROOT)
load_dotenv()

from src.pipeline.specialist_pipeline import get_bm25_retriever
from src.eval.fact_checklist_scorer import score_fact_checklist

with open("data/track_b/track_b_heldout_split.json", "r", encoding="utf-8") as f:
    tb_items = json.load(f)

retriever = get_bm25_retriever()
item = tb_items[0]
raw_prompt = item["prompt"]
word_cap = item.get("word_cap", 75)
pipe_prompt = f"{raw_prompt}\n\nProvide a concise answer in key-value pairs (max {word_cap} words). Conclude with 'Final Answer: <key-value pairs>'."
passages = retriever.retrieve(pipe_prompt, top_k=5)
context_str = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in passages])

augmented = (
    f"[Retrieved Reference Documents]:\n{context_str}\n\n"
    f"Question:\n{raw_prompt}\n\n"
    f"Provide a concise answer in key-value pairs (max {word_cap} words).\n"
    f"Conclude with 'Final Answer: <key-value pairs>'."
)

api_key = os.getenv("GROQ_API_KEY")

def call(model):
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an expert technical assistant. Answer the question based on the provided reference documents."},
                {"role": "user", "content": augmented}
            ],
            "max_tokens": 4096,
            "temperature": 0.0,
            "seed": 42
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]

print("--- Qwen ---")
q_out = call("qwen/qwen3.8-27b")
print(q_out)
sc_q = score_fact_checklist(q_out, item["checklist"], max_word_cap=word_cap)
print("Qwen Passed:", sc_q["binary_pass"], sc_q.get("failed_facts"))

print("--- GPT ---")
g_out = call("openai/gpt-oss-120b")
print(g_out)
sc_g = score_fact_checklist(g_out, item["checklist"], max_word_cap=word_cap)
print("GPT Passed:", sc_g["binary_pass"], sc_g.get("failed_facts"))

