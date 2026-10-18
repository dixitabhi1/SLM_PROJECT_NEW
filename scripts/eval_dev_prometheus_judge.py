"""
scripts/eval_dev_prometheus_judge.py

Runs the 5-item dev calibration check using local Prometheus-2 7B on port 8081.
Evaluates:
1. Schema adherence (strict JSON or Prometheus format)
2. Internal consistency (winner matches higher score)
3. Low scores (<= 4) for broken/incomplete answers (HumanEval/2, gsm8k_test_0530)
4. Latency and token throughput

Zero benchmark leakage: prompts and answers only, no answer keys.
"""

import os
import sys
import json
import time
import requests
import re
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.rerun_dev_phase4_fix import format_eval_prompt
from scripts.run_judge_phase3 import get_user_facing_response

LLAMA_SERVER_URL = "http://127.0.0.1:8081"
DEV_SPLIT_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
DEV_SLM_RECORDS = os.path.join(REPO_ROOT, "results", "phase4", "dev_e3_v2_pipeline_records.jsonl")
DEV_120B_RECORDS = os.path.join(REPO_ROOT, "results", "phase4", "dev_b1_gpt120b_records.jsonl")

# Standard JSON schema prompt (same as docs/judge_protocol.md)
JUDGE_SYS_PROMPT_JSON = """You are an impartial expert judge evaluating two competing AI model answers to a user query.
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

# Prometheus-2 Native Pairwise Prompt Format
PROMETHEUS_PAIRWISE_PROMPT = """###Task Description:
An instruction (might include an Input inside it), a response to evaluate, and a score rubric representing a evaluation criteria are given.
1. Write a detailed feedback that assess the quality of two responses strictly based on the given score rubric, not evaluating in general.
2. After writing a feedback, write a score that is either "A" or "B" or "Tie".
3. The output format should look as follows: "Feedback: (write a feedback for criteria) [RESULT] (either "A" or "B" or "Tie")"
4. Please do not generate any other opening, closing, and explanations.

###The instruction to evaluate:
{instruction}

###Response A:
{response_a}

###Response B:
{response_b}

###Score Rubrics:
Which response provides a more accurate, logically complete, correct, and well-reasoned answer to the instruction?

###Feedback:
"""

# Prometheus-2 Native Absolute Grading Prompt Format (Direct Assessment 1-5)
PROMETHEUS_ABSOLUTE_PROMPT = """###Task Description:
An instruction (might include an Input inside it), a response to evaluate, and a score rubric representing a evaluation criteria are given.
1. Write a detailed feedback that assess the quality of the response strictly based on the given score rubric, not evaluating in general.
2. After writing a feedback, write a score that is an integer between 1 and 5. You should refer to the score rubric.
3. The output format should look as follows: "Feedback: (write a feedback for criteria) [RESULT] (an integer number between 1 and 5)"
4. Please do not generate any other opening, closing, and explanations.

###The instruction to evaluate:
{instruction}

###Response to evaluate:
{response}

###Score Rubrics:
Score 1: Completely incorrect, broken, incomplete, or fails to answer the question.
Score 2: Partially correct but contains major errors or missing key components.
Score 3: Acceptable response, answers the core question with minor errors or formatting issues.
Score 4: Very good response, correct, complete, and well-structured.
Score 5: Exceptional, flawless, fully accurate, and clearly formatted response.

###Feedback:
"""

def call_llama_chat(messages: List[Dict[str, str]], max_tokens: int = 512, json_mode: bool = True) -> Tuple[Dict[str, Any], float]:
    url = f"{LLAMA_SERVER_URL}/v1/chat/completions"
    payload = {
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    
    t0 = time.time()
    resp = requests.post(url, json=payload, timeout=120)
    dur = time.time() - t0
    
    if resp.status_code != 200:
        raise RuntimeError(f"llama-server error ({resp.status_code}): {resp.text}")
    return resp.json(), dur

def call_llama_completion(prompt: str, max_tokens: int = 512) -> Tuple[str, Dict[str, Any], float]:
    url = f"{LLAMA_SERVER_URL}/completion"
    payload = {
        "prompt": prompt,
        "temperature": 0.0,
        "n_predict": max_tokens,
        "stop": ["</s>", "[INST]", "[/INST]"]
    }
    t0 = time.time()
    resp = requests.post(url, json=payload, timeout=120)
    dur = time.time() - t0
    if resp.status_code != 200:
        raise RuntimeError(f"llama-server error ({resp.status_code}): {resp.text}")
    data = resp.json()
    return data.get("content", ""), data, dur


def run_5_item_check(use_native_format: bool = False):
    print("=" * 80)
    fmt_name = "Prometheus Native Rubric Format" if use_native_format else "Standard JSON Schema Prompt"
    print(f"RUNNING 5-ITEM DEV CALIBRATION CHECK: {fmt_name}")
    print("=" * 80)

    # 1. Load dev items
    with open(DEV_SPLIT_PATH, "r", encoding="utf-8") as f:
        dev_items_list = json.load(f)
    dev_items = {it.get("item_id") or it.get("original_id"): it for it in dev_items_list}

    # 2. Load responses
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

    # 3. Stratified 5 dev items
    target_types = ["sql", "qa", "code", "math", "compound"]
    selected_ids = []
    for t_type in target_types:
        for iid, it in dev_items.items():
            if it.get("task_type") == t_type and iid in slm_recs and iid in llm_recs:
                if iid not in selected_ids:
                    selected_ids.append(iid)
                    break

    print(f"Items: {selected_ids}\n")

    results = []
    total_prompt_tok = 0
    total_gen_tok = 0
    total_dur = 0.0

    for idx, item_id in enumerate(selected_ids, 1):
        item = dev_items[item_id]
        prompt_text = format_eval_prompt(item)
        task_type = item.get("task_type")

        s_rec = slm_recs[item_id]
        l_rec = llm_recs[item_id]

        # Use full responses via official get_user_facing_response
        s_ans, s_field = get_user_facing_response(s_rec, "Specialist SLM v1.3")
        l_ans, l_field = get_user_facing_response(l_rec, "GPT-OSS-120B B1")

        print(f"[{idx}/5] Evaluating {item_id} ({task_type})...")

        if not use_native_format:
            # JSON format
            user_msg = f"User Query:\n{prompt_text}\n\nAnswer 1:\n{s_ans}\n\nAnswer 2:\n{l_ans}"
            messages = [
                {"role": "system", "content": JUDGE_SYS_PROMPT_JSON},
                {"role": "user", "content": user_msg}
            ]
            try:
                res_data, dur = call_llama_chat(messages, max_tokens=512, json_mode=True)
                content = res_data["choices"][0]["message"]["content"]
                usage = res_data.get("usage", {})
                p_tok = usage.get("prompt_tokens", 0)
                c_tok = usage.get("completion_tokens", 0)
                
                # Check JSON validity
                parsed = json.loads(content)
                a1 = parsed.get("answer_1", {})
                a2 = parsed.get("answer_2", {})
                winner = parsed.get("winner", "Draw")
                h1 = a1.get("holistic")
                h2 = a2.get("holistic")
                
                # Internal consistency
                consistent = True
                if h1 is not None and h2 is not None:
                    if h1 > h2 and "answer 1" not in winner.lower():
                        consistent = False
                    elif h2 > h1 and "answer 2" not in winner.lower():
                        consistent = False
                
                # Penalize broken answers check (item 3 and 4 are broken)
                is_broken_test = item_id in ("HumanEval/2", "gsm8k_test_0530")
                low_score_ok = True
                if is_broken_test and (h1 is not None and h2 is not None):
                    low_score_ok = (h1 <= 4 and h2 <= 4)

                res_info = {
                    "item_id": item_id,
                    "task_type": task_type,
                    "format": "JSON",
                    "duration_sec": dur,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "raw_output": content,
                    "parsed": parsed,
                    "schema_valid": True,
                    "internal_consistent": consistent,
                    "h1": h1, "h2": h2,
                    "winner": winner,
                    "low_score_on_broken": low_score_ok if is_broken_test else None
                }
                print(f"   -> JSON OK: h1={h1}, h2={h2}, winner='{winner}', dur={dur:.2f}s, tok={p_tok}+{c_tok}")
            except Exception as e:
                print(f"   -> JSON FAILED: {e}")
                res_info = {
                    "item_id": item_id,
                    "task_type": task_type,
                    "format": "JSON",
                    "schema_valid": False,
                    "error": str(e)
                }
        else:
            # Native Prometheus format (Pairwise + Absolute)
            # 1. Absolute grading for A
            p_abs_a = f"[INST] {PROMETHEUS_ABSOLUTE_PROMPT.format(instruction=prompt_text, response=s_ans)} [/INST]"
            out_a, data_a, dur_a = call_llama_completion(p_abs_a, max_tokens=300)
            
            # 2. Absolute grading for B
            p_abs_b = f"[INST] {PROMETHEUS_ABSOLUTE_PROMPT.format(instruction=prompt_text, response=l_ans)} [/INST]"
            out_b, data_b, dur_b = call_llama_completion(p_abs_b, max_tokens=300)

            # 3. Pairwise
            p_pair = f"[INST] {PROMETHEUS_PAIRWISE_PROMPT.format(instruction=prompt_text, response_a=s_ans, response_b=l_ans)} [/INST]"
            out_pair, data_pair, dur_pair = call_llama_completion(p_pair, max_tokens=300)

            dur = dur_a + dur_b + dur_pair
            p_tok = data_a.get("tokens_evaluated", 0) + data_b.get("tokens_evaluated", 0) + data_pair.get("tokens_evaluated", 0)
            c_tok = data_a.get("tokens_predicted", 0) + data_b.get("tokens_predicted", 0) + data_pair.get("tokens_predicted", 0)

            # Parse score_a
            m_a = re.search(r"\[RESULT\]\s*\(?(\d)\)?", out_a)
            score_a = int(m_a.group(1)) if m_a else None

            # Parse score_b
            m_b = re.search(r"\[RESULT\]\s*\(?(\d)\)?", out_b)
            score_b = int(m_b.group(1)) if m_b else None

            # Parse pairwise winner
            m_p = re.search(r"\[RESULT\]\s*\(?([AB]|Tie)\)?", out_pair, re.IGNORECASE)
            winner = m_p.group(1).upper() if m_p else "UNKNOWN"

            # Check consistency
            consistent = True
            if score_a is not None and score_b is not None:
                if score_a > score_b and winner != "A":
                    consistent = False
                elif score_b > score_a and winner != "B":
                    consistent = False

            # Broken answer penalty check (HumanEval/2, gsm8k_test_0530)
            is_broken_test = item_id in ("HumanEval/2", "gsm8k_test_0530")
            low_score_ok = True
            if is_broken_test and (score_a is not None and score_b is not None):
                # On 1-5 scale, <= 2 corresponds to <= 4 on 1-10 scale
                low_score_ok = (score_a <= 2 and score_b <= 2)

            schema_ok = (score_a is not None and score_b is not None and winner in ("A", "B", "TIE"))

            res_info = {
                "item_id": item_id,
                "task_type": task_type,
                "format": "Prometheus Native",
                "duration_sec": dur,
                "prompt_tokens": p_tok,
                "completion_tokens": c_tok,
                "score_a": score_a,
                "score_b": score_b,
                "winner": winner,
                "internal_consistent": consistent,
                "schema_valid": schema_ok,
                "low_score_on_broken": low_score_ok if is_broken_test else None,
                "score_a_raw": out_a,
                "score_b_raw": out_b,
                "pairwise_raw": out_pair
            }
            print(f"   -> Score A (SLM): {score_a}/5 | Score B (LLM): {score_b}/5 | Winner: {winner}")
            print(f"      Schema OK: {schema_ok} | Consistent: {consistent} | Broken Penalty: {low_score_ok if is_broken_test else 'n/a'}")
            print(f"      Dur: {dur:.2f}s | Tokens: {p_tok} prompt, {c_tok} gen")

        results.append(res_info)
        total_dur += res_info.get("duration_sec", 0)
        total_prompt_tok += res_info.get("prompt_tokens", 0)
        total_gen_tok += res_info.get("completion_tokens", 0)

    print("\n" + "=" * 80)
    print("CALIBRATION SUMMARY:")
    print(f"Total Duration: {total_dur:.2f}s (Avg {total_dur/len(results):.2f}s/item)")
    print(f"Total Tokens: Prompt {total_prompt_tok}, Gen {total_gen_tok}")
    valid_count = sum(1 for r in results if r.get("schema_valid"))
    print(f"Schema Adherence: {valid_count}/{len(results)}")
    print("=" * 80)
    return results

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "json"
    if mode == "native":
        run_5_item_check(use_native_format=True)
    else:
        run_5_item_check(use_native_format=False)

