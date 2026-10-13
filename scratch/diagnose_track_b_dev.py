import os
import sys
import json
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import get_bm25_retriever
from src.eval.fact_checklist_scorer import score_fact_checklist

dev_items = json.load(open(os.path.join(REPO_ROOT, "data", "track_b", "track_b_dev_split.json"), encoding="utf-8"))
dev_recs = [json.loads(l) for l in open(os.path.join(REPO_ROOT, "results", "phase4", "dev_rerun_clean_pipeline_records.jsonl"), encoding="utf-8") if l.strip()]
trb_recs = {r["item_id"]: r for r in dev_recs if r.get("track") == "B"}

retriever = get_bm25_retriever()

total = len(dev_items)
routing_hits = 0
retrieval_hits = 0
score_passes = 0

print(f"{'QID':<20} | {'Route':<10} | {'RetrHit':<8} | {'Score':<6} | {'Failed Rule / Detail'}")
print("-" * 85)

for it in dev_items:
    qid = it["question_id"]
    rec = trb_recs.get(qid, {})
    prompt = it["prompt"]
    checklist = it["checklist"]
    
    # 1. Routing decision
    routed = rec.get("route") or rec.get("routed_to") or "CORPUS"
    if routed in ["CORPUS", "outside_data", None]:
        routing_hits += 1
        
    # 2. Retrieval hit: did top-3 passages contain required positive facts?
    passages = retriever.retrieve(prompt, top_k=3)
    p_text = " ".join([p.text for p in passages])
    
    missing_in_context = []
    for f in checklist:
        if f.get("type") == "token":
            tok = f.get("value") or f.get("token")
            if tok and tok not in p_text:
                missing_in_context.append(tok)
        elif f.get("type") == "numeric":
            val_str = str(f["target"])
            val_g = f"{float(f['target']):g}"
            if val_str not in p_text and val_g not in p_text:
                missing_in_context.append(f"{val_str} {f.get('unit', '')}")
                
    retr_hit = len(missing_in_context) == 0
    if retr_hit:
        retrieval_hits += 1
        
    # 3. Model Answer scoring
    passed = rec.get("passed", False)
    if passed:
        score_passes += 1
    detail = rec.get("details", "")
    if missing_in_context:
        detail_note = f"Context missed: {missing_in_context[:2]}"
    else:
        detail_note = detail[:40]

    print(f"{qid:<20} | {str(routed):<10} | {str(retr_hit):<8} | {str(passed):<6} | {detail_note}")

print("-" * 85)
print(f"Summary over {total} items:")
print(f"  Routing hits:   {routing_hits}/{total} ({routing_hits/total*100:.1f}%)")
print(f"  Retrieval hits: {retrieval_hits}/{total} ({retrieval_hits/total*100:.1f}%)")
print(f"  Passed scores:  {score_passes}/{total} ({score_passes/total*100:.1f}%)")
