import os
import sys
import json
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import get_bm25_retriever, call_phi
from src.eval.fact_checklist_scorer import score_fact_checklist

dev_items = json.load(open(os.path.join(REPO_ROOT, "data", "track_b", "track_b_dev_split.json"), encoding="utf-8"))
retriever = get_bm25_retriever()

results = []
passed_count = 0
total = len(dev_items)

t0 = time.time()
for idx, it in enumerate(dev_items, 1):
    prompt = it["prompt"]
    checklist = it["checklist"]
    word_cap = it.get("word_cap", 75)

    # Track B retrieval using prompt with top_k=5
    passages = retriever.retrieve(prompt, top_k=5)
    ctx = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in passages])

    user_msg = (
        f"Task:\n{prompt}\n\n"
        f"Retrieved Documents:\n{ctx}\n\n"
        f"Answer the question in concise key-value pairs (max {word_cap} words). "
        f"Explicitly include all component designations, names, and parameters mentioned in the text.\n"
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
    results.append({
        "question_id": qid,
        "binary_pass": sc["binary_pass"],
        "recall": sc["recall"],
        "precision": sc["precision"],
        "details": f"Recall: {sc['recall']:.2f}, Precision: {sc['precision']:.2f}" + (f" | Failed: {sc['failed_facts'][0]}" if sc.get("failed_facts") else "")
    })
    status = "PASS" if sc["binary_pass"] else "FAIL"
    print(f"[{idx:02d}/{total}] {qid}: {status} (Recall={sc['recall']:.2f})")

dt = time.time() - t0
print(f"\nAll 50 Dev items evaluated in {dt:.1f}s!")
print(f"Passed: {passed_count}/{total} ({passed_count/total*100:.2f}%) vs Original: 2/50 (4.00%)")

with open(os.path.join(REPO_ROOT, "results", "phase4", "track_b_dev_fix_report.json"), "w", encoding="utf-8") as f:
    json.dump({
        "total": total,
        "passes": passed_count,
        "acc": round(passed_count / total * 100, 2),
        "results": results
    }, f, indent=2)

