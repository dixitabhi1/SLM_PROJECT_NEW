import json
from src.eval.fact_checklist_scorer import score_fact_checklist

with open('data/track_b/track_b_heldout_split.json', 'r', encoding='utf-8') as f:
    items = {it['question_id']: it for it in json.load(f)}

b1_gpt_recs = {r['item_id']: r for r in [json.loads(l) for l in open('results/phase4/b1_gpt120b_heldout_records.jsonl', encoding='utf-8') if 'track_b_heldout_v2' in l]}
b1_qwen_recs = {r['item_id']: r for r in [json.loads(l) for l in open('results/phase4/b1_qwen27b_heldout_records.jsonl', encoding='utf-8') if 'track_b_heldout_v2' in l]}

lines = []
lines.append('=== GPT-120B FAILURES (17 items) ===')
for qid in sorted(b1_gpt_recs.keys()):
    r = b1_gpt_recs[qid]
    it = items[qid]
    out = r.get('full_output') or r.get('output', '')
    res = score_fact_checklist(out, it['checklist'], max_word_cap=it.get('word_cap', 75))
    if not res['binary_pass']:
        lines.append(f"{qid}: failed={res.get('failed_facts')} | neg={res.get('negative_violations')}")
        lines.append(f"  OUT: {repr(out)}")

lines.append('\n=== QWEN-27B FAILURES (8 items) ===')
for qid in sorted(b1_qwen_recs.keys()):
    r = b1_qwen_recs[qid]
    it = items[qid]
    out = r.get('full_output') or r.get('output', '')
    res = score_fact_checklist(out, it['checklist'], max_word_cap=it.get('word_cap', 75))
    if not res['binary_pass']:
        lines.append(f"{qid}: failed={res.get('failed_facts')} | neg={res.get('negative_violations')}")
        lines.append(f"  OUT: {repr(out)}")

with open('scratch/classify_failures.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('Written to scratch/classify_failures.txt successfully')

