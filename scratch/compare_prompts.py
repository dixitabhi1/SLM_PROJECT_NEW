import os
import sys
import json

REPO_ROOT = "."
sys.path.insert(0, REPO_ROOT)
from src.pipeline.specialist_pipeline import get_bm25_retriever

with open("data/track_b/track_b_heldout_split.json", "r", encoding="utf-8") as f:
    tb_items = json.load(f)

retriever = get_bm25_retriever()

pipe_recs = {}
with open("results/phase4/heldout_pipeline_records.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        pipe_recs[r["item_id"]] = r

b1_qwen_recs = {}
with open("results/phase4/b1_qwen27b_heldout_records.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        b1_qwen_recs[r["item_id"]] = r

b1_gpt_recs = {}
with open("results/phase4/b1_gpt120b_heldout_records.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        b1_gpt_recs[r["item_id"]] = r

target_ids = ["track_b_heldout_v2_0001", "track_b_heldout_v2_0002", "track_b_heldout_v2_0003"]

output_data = {}
for iid in target_ids:
    it = next(x for x in tb_items if (x.get("question_id") or x.get("item_id")) == iid)
    raw_prompt = it["prompt"]
    word_cap = it.get("word_cap", 75)

    pipe_prompt_in = f"{raw_prompt}\n\nProvide a concise answer in key-value pairs (max {word_cap} words). Conclude with 'Final Answer: <key-value pairs>'."
    pipe_passages = retriever.retrieve(pipe_prompt_in, top_k=5)
    pipe_docs = [p.doc_id for p in pipe_passages]
    pipe_texts = [p.text for p in pipe_passages]

    base_passages = retriever.retrieve(raw_prompt, top_k=3)
    base_docs = [p.doc_id for p in base_passages]
    base_texts = [p.text for p in base_passages]

    # Pipeline exact prompt given to LLM in downstream reasoning stage:
    p_rec = pipe_recs.get(iid, {})
    subtask_2 = p_rec.get("subtasks", ["", ""])[1] if len(p_rec.get("subtasks", [])) > 1 else ""
    pipe_context_str = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in pipe_passages])
    pipe_llm_user_prompt = (
        f"Task:\n{pipe_prompt_in}\n\n"
        f"Retrieved Context:\nThe data retrieved is:\n{pipe_context_str}\n\n"
        f"Step to Complete:\n{subtask_2}\n\n"
        f"Reason step-by-step and conclude with 'Final Answer: <answer>' or '#### <answer>'."
    )
    pipe_llm_sys_prompt = "You are an expert reasoning assistant. Use the provided retrieved data to solve the task step-by-step. Conclude with 'Final Answer: <answer>' or '#### <answer>'."

    # Baseline prompt:
    base_context_str = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in base_passages])
    base_llm_user_prompt = (
        f"[Retrieved Reference Documents]:\n{base_context_str}\n\n"
        f"Question:\n{raw_prompt}\n\n"
        f"Based on the retrieved documents above, provide a concise answer in key-value pairs (max {word_cap} words).\n"
        f"Conclude with 'Final Answer: <key-value pairs>'."
    )
    base_llm_sys_prompt = "You are an expert technical assistant. Answer the question based on the provided reference documents."

    output_data[iid] = {
        "item_id": iid,
        "question": raw_prompt,
        "word_cap": word_cap,
        "pipeline": {
            "retrieval_query": pipe_prompt_in,
            "top_k": 5,
            "retrieved_doc_ids": pipe_docs,
            "retrieved_passages": pipe_texts,
            "system_prompt": pipe_llm_sys_prompt,
            "user_prompt": pipe_llm_user_prompt,
            "format_instruction": f"Provide a concise answer in key-value pairs (max {word_cap} words). Conclude with 'Final Answer: <key-value pairs>'."
        },
        "baseline_run": {
            "retrieval_query": raw_prompt,
            "top_k": 3,
            "retrieved_doc_ids": base_docs,
            "retrieved_passages": base_texts,
            "system_prompt": base_llm_sys_prompt,
            "user_prompt": base_llm_user_prompt,
            "format_instruction": f"Based on the retrieved documents above, provide a concise answer in key-value pairs (max {word_cap} words).\nConclude with 'Final Answer: <key-value pairs>'."
        }
    }

with open("scratch/prompt_comparison_3items.json", "w", encoding="utf-8") as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)

print("Saved prompt comparison to scratch/prompt_comparison_3items.json successfully.")

