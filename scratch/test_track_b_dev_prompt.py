import os
import sys
import json

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import get_bm25_retriever, call_phi
from src.eval.fact_checklist_scorer import score_fact_checklist

dev_items = json.load(open(os.path.join(REPO_ROOT, "data", "track_b", "track_b_dev_split.json"), encoding="utf-8"))
retriever = get_bm25_retriever()

passed_count = 0
for idx, it in enumerate(dev_items[:10], 1):
    prompt = it["prompt"]
    checklist = it["checklist"]
    word_cap = it.get("word_cap", 75)

    # Retrieve using prompt with top_k=5
    passages = retriever.retrieve(prompt, top_k=5)
    ctx = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in passages])

    user_msg = (
        f"Task:\n{prompt}\n\n"
        f"Retrieved Documents:\n{ctx}\n\n"
        f"Provide a concise answer in key-value pairs (max {word_cap} words) based on the retrieved documents.\n"
        f"Conclude with: Final Answer: <key-value pairs>"
    )
    resp = call_phi([
        {"role": "system", "content": "You are an expert technical assistant. Answer the question based on the provided reference documents in concise key-value format."},
        {"role": "user", "content": user_msg}
    ], temperature=0.0, max_tokens=512)

    sc = score_fact_checklist(resp, checklist, max_word_cap=word_cap)
    if sc["binary_pass"]:
        passed_count += 1
    qid = it["question_id"]
    print(f"Item {qid}: Pass={sc['binary_pass']} | Recall={sc['recall']:.2f} | Failed: {sc.get('failed_facts')}")
print(f"Top 10 result: {passed_count}/10 passed!")

