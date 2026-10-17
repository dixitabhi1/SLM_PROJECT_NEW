"""
scripts/run_judge_limit_check.py

Phase 2 Checkpoint: LLM-as-a-Judge Rate Limit & Token Usage Check.
Evaluates 5 development items only (zero held-out items, zero reserve items).
Uses judge model 'allam-2-7b' via Groq Cloud API.
Enforces Hard Rule 6 (Zero Benchmark Leakage): prompts and answers only, no answer keys.
"""

import os
import sys
import json
import time
import requests
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.rerun_dev_phase4_fix import format_eval_prompt

JUDGE_MODEL = "allam-2-7b"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

DEV_SPLIT_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
DEV_SLM_RECORDS = os.path.join(REPO_ROOT, "results", "phase4", "dev_e3_v2_pipeline_records.jsonl")
DEV_120B_RECORDS = os.path.join(REPO_ROOT, "results", "phase4", "dev_b1_gpt120b_records.jsonl")
OUT_DIR = os.path.join(REPO_ROOT, "results", "judge")
OUT_FILE = os.path.join(OUT_DIR, "dev_limit_check_records.jsonl")

JUDGE_SYS_PROMPT = """You are an impartial expert judge evaluating two competing AI model answers to a user query.
Evaluate both answers on their merits without knowing which model produced which.
Rate each answer:
1. Holistic score: 1 to 10 (overall quality, usefulness, correctness)
2. Four criteria (each 1 to 5):
   - correctness (1-5)
   - completeness (1-5)
   - reasoning_quality (1-5)
   - formatting (1-5)

Output STRICT valid JSON only with this schema:
{
  "answer_1": {
    "holistic": <int 1-10>,
    "correctness": <int 1-5>,
    "completeness": <int 1-5>,
    "reasoning_quality": <int 1-5>,
    "formatting": <int 1-5>
  },
  "answer_2": {
    "holistic": <int 1-10>,
    "correctness": <int 1-5>,
    "completeness": <int 1-5>,
    "reasoning_quality": <int 1-5>,
    "formatting": <int 1-5>
  },
  "winner": "Answer 1" | "Answer 2" | "Draw",
  "explanation": "<short explanation>"
}"""


def call_judge_with_headers(query_prompt: str, ans1: str, ans2: str, api_key: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
    user_content = f"User Query:\n{query_prompt}\n\nAnswer 1:\n{ans1}\n\nAnswer 2:\n{ans2}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": JUDGE_MODEL,
        "messages": [
            {"role": "system", "content": JUDGE_SYS_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.0,
        "max_tokens": 500,
        "response_format": {"type": "json_object"}
    }

    t0 = time.time()
    resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
    dur = time.time() - t0

    resp_headers = {k: v for k, v in resp.headers.items() if "ratelimit" in k.lower()}
    
    if resp.status_code != 200:
        raise RuntimeError(f"Groq API error ({resp.status_code}): {resp.text}")

    data = resp.json()
    data["_request_duration"] = dur
    return data, resp_headers


def main():
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[ERROR] GROQ_API_KEY not found in environment.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)

    # 1. Load dev items
    with open(DEV_SPLIT_PATH, "r", encoding="utf-8") as f:
        dev_items_list = json.load(f)

    # Index dev items by item_id or original_id
    dev_items = {}
    for i, it in enumerate(dev_items_list):
        iid = it.get("item_id") or it.get("original_id") or f"dev_{i}"
        dev_items[iid] = it

    # 2. Load SLM and 120B dev responses
    slm_recs = {}
    with open(DEV_SLM_RECORDS, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                slm_recs[d["item_id"]] = d

    llm_recs = {}
    with open(DEV_120B_RECORDS, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                llm_recs[d["item_id"]] = d

    # 3. Select 5 stratified dev items
    target_types = ["sql", "qa", "code", "math", "compound"]
    selected_ids = []
    
    for t_type in target_types:
        for iid, it in dev_items.items():
            it_type = it.get("task_type") or it.get("type")
            if it_type == t_type and iid in slm_recs and iid in llm_recs:
                if iid not in selected_ids:
                    selected_ids.append(iid)
                    break

    print(f"Selected 5 Dev Items for Limit Check: {selected_ids}")

    results = []
    token_usages = []
    durations = []
    last_headers = {}

    for idx, item_id in enumerate(selected_ids, 1):
        item = dev_items[item_id]
        prompt = format_eval_prompt(item)
        
        slm_ans = slm_recs[item_id].get("output") or slm_recs[item_id].get("final_answer") or ""
        llm_ans = llm_recs[item_id].get("output") or llm_recs[item_id].get("full_output") or ""

        # Order: System 1 (SLM), System 2 (120B)
        print(f"\n[{idx}/5] Calling judge on dev item: {item_id} ({item.get('task_type')})...")
        
        res_data, r_headers = call_judge_with_headers(prompt, str(slm_ans), str(llm_ans), api_key)
        last_headers = r_headers

        usage = res_data.get("usage", {})
        dur = res_data.get("_request_duration", 0)
        
        token_usages.append(usage)
        durations.append(dur)

        content = res_data["choices"][0]["message"]["content"]
        parsed_json = json.loads(content)

        record = {
            "item_id": item_id,
            "task_type": item.get("task_type"),
            "judge_model": JUDGE_MODEL,
            "system_1": "Specialist SLM v1.3",
            "system_2": "GPT-OSS-120B B1",
            "usage": usage,
            "duration": dur,
            "judge_output_raw": content,
            "judge_output_parsed": parsed_json,
            "rate_limit_headers": r_headers,
            "timestamp": time.time()
        }
        results.append(record)
        print(f"    Done in {dur:.2f}s | Prompt tokens: {usage.get('prompt_tokens')}, Completion tokens: {usage.get('completion_tokens')}")
        print(f"    Winner: {parsed_json.get('winner')} | SLM: {parsed_json.get('answer_1', {}).get('holistic')}/10 | 120B: {parsed_json.get('answer_2', {}).get('holistic')}/10")

        # Sleep slightly to stay well under rate limits
        if idx < len(selected_ids):
            time.sleep(1.0)

    # 4. Save to append-only JSONL
    with open(OUT_FILE, "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"\nSaved 5 limit check records to: {OUT_FILE}")

    # 5. Compute summary statistics
    prompt_tokens = [u.get("prompt_tokens", 0) for u in token_usages]
    comp_tokens = [u.get("completion_tokens", 0) for u in token_usages]
    total_tokens = [u.get("total_tokens", 0) for u in token_usages]

    mean_p = sum(prompt_tokens) / len(prompt_tokens)
    mean_c = sum(comp_tokens) / len(comp_tokens)
    mean_tot = sum(total_tokens) / len(total_tokens)
    mean_dur = sum(durations) / len(durations)

    req_limit = last_headers.get("x-ratelimit-limit-requests", "N/A")
    tpm_limit = last_headers.get("x-ratelimit-limit-tokens", "N/A")
    rem_req = last_headers.get("x-ratelimit-remaining-requests", "N/A")
    rem_tok = last_headers.get("x-ratelimit-remaining-tokens", "N/A")

    # Time estimate for 600 calls:
    # Under TPM limit:
    tpm_val = float(tpm_limit) if tpm_limit != "N/A" else 6000.0
    # Calls per minute allowed by TPM = tpm_val / mean_tot
    calls_per_min = tpm_val / mean_tot
    min_est_minutes = 600 / calls_per_min
    # Add safety buffer of 20%
    safe_est_minutes = min_est_minutes * 1.2
    safe_delay_per_call = (safe_est_minutes * 60) / 600

    print("\n" + "=" * 80)
    print("PHASE 2 LIMIT CHECK SUMMARY")
    print("=" * 80)
    print(f"Judge Model ID:             {JUDGE_MODEL}")
    print(f"Groq Rate Limits (Headers):")
    print(f"  Requests Limit:           {req_limit} requests/day (Remaining: {rem_req})")
    print(f"  Tokens Limit (TPM):       {tpm_limit} tokens/minute (Remaining: {rem_tok})")
    print(f"Tokens Per Call (Mean):")
    print(f"  Prompt Tokens:            {mean_p:.1f}")
    print(f"  Completion Tokens:        {mean_c:.1f}")
    print(f"  Total Tokens:             {mean_tot:.1f}")
    print(f"  Mean Request Latency:     {mean_dur:.2f}s")
    print(f"Execution Strategy for 600 Calls:")
    print(f"  Throughput Ceiling:       {calls_per_min:.2f} calls/minute (limited by {tpm_val:.0f} TPM)")
    print(f"  Recommended Delay/Call:   {safe_delay_per_call:.2f} seconds")
    print(f"  Estimated Total Time:     {safe_est_minutes:.1f} minutes (~{safe_est_minutes/60:.2f} hours)")
    print("=" * 80)


if __name__ == "__main__":
    main()