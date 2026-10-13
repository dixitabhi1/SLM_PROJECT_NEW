"""
Rerun Track B for Baseline B1 (GPT-OSS-120B) with exact top_k=5 retrieval and exact format instruction.
"""

import os
import sys
import json
import time
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
load_dotenv()

from src.pipeline.specialist_pipeline import get_bm25_retriever
from src.eval.fact_checklist_scorer import score_fact_checklist
from scripts.run_all_outstanding_reruns import call_groq_api

TRACK_B_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_heldout_split.json")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
B1_GPT_PATH = os.path.join(RESULTS_DIR, "b1_gpt120b_heldout_records.jsonl")

with open(TRACK_B_PATH, "r", encoding="utf-8") as f:
    track_b_items = json.load(f)

retriever = get_bm25_retriever()

print(f"--- Running B1 GPT-120B Track B: {len(track_b_items)} items with exact top_k=5 retrieval ---")
with open(B1_GPT_PATH, "a", encoding="utf-8") as f_out:
    for idx, it in enumerate(track_b_items, 1):
        iid = it.get("question_id") or it.get("item_id")
        word_cap = it.get("word_cap", 75)
        raw_prompt = it["prompt"]

        query_str = f"{raw_prompt}\n\nProvide a concise answer in key-value pairs (max {word_cap} words). Conclude with 'Final Answer: <key-value pairs>'."
        passages = retriever.retrieve(query_str, top_k=5)
        context_str = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in passages])

        augmented_prompt = (
            f"[Retrieved Reference Documents]:\n{context_str}\n\n"
            f"Question:\n{raw_prompt}\n\n"
            f"Provide a concise answer in key-value pairs (max {word_cap} words).\n"
            f"Conclude with 'Final Answer: <key-value pairs>'."
        )

        resp = call_groq_api(
            "openai/gpt-oss-120b",
            augmented_prompt,
            system_prompt="You are an expert technical assistant. Answer the question based on the provided reference documents.",
            max_tokens=4096
        )
        final_text = resp["content"]

        sc_strict = score_fact_checklist(final_text, it["checklist"], max_word_cap=word_cap)
        sc_facts = score_fact_checklist(final_text, it["checklist"], max_word_cap=999999)

        rec = {
            "item_id": iid,
            "model": "openai/gpt-oss-120b",
            "condition": "B1",
            "track": "B",
            "stratum": "track_b_rag",
            "task_type": "rag",
            "solvability": "tool-required",
            "prompt": raw_prompt,
            "output": final_text[:300],
            "full_output": final_text,
            "finish_reason": resp["finish_reason"],
            "prompt_tokens": resp["prompt_tokens"],
            "completion_tokens": resp["completion_tokens"],
            "total_tokens": resp["total_tokens"],
            "status": resp["status"],
            "clean_execution": resp["status"] == "COMPLETE",
            "passed": sc_strict["binary_pass"],
            "passed_facts_alone": sc_facts["binary_pass"],
            "details": f"Strict: {sc_strict['binary_pass']}, Facts: {sc_facts['binary_pass']}",
            "duration": resp["latency_seconds"],
            "rerun_topk5_fair": True,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        f_out.write(json.dumps(rec) + "\n")
        f_out.flush()
        print(f"  [{idx:02d}/50] GPT Track B {iid}: strict={sc_strict['binary_pass']}, facts={sc_facts['binary_pass']}, tokens={resp['completion_tokens']}")
        time.sleep(2.0)

print("Finished B1 GPT-120B Track B.")

