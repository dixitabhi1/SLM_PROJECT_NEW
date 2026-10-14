"""
evaluate_slm_fallbacks_dev.py — Evaluation of SLM-Only Fallback Strategies on Dev Track A.

Evaluates two SLM-only fallback mechanisms on the 32 triggered items from Dev Track A:
(a) Three parallel samples across the three slots (temperature=0.7) with majority voting.
(b) Re-decomposing once and answering again.

Strict prompt-only execution: zero item metadata / domain tags passed to fallback functions.
Reports:
- Dev Track A accuracy for v1.1 alone, Fallback (a), and Fallback (b)
- Fallback trigger rate on Track A (32 / 100 = 32.0%)
- Latency cost per item for each strategy
- Paired difference against Pipeline v1.1 with 95% bootstrap confidence intervals
- Fixed vs broken items

Strict Integrity Constraint: SLM-only execution using local llama-server (phi-4-mini).
Zero Groq / API calls.
"""

import os
import sys
import json
import time
import re
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Tuple, Optional
from collections import Counter

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import (
    call_phi,
    run_specialist_pipeline,
    task_asks_for_query,
    extract_sql_from_text,
    analyse_task_model_call,
    get_table_schema,
    KNOWN_DATABASES
)
from src.eval.versioned_scorer import score_record
from scripts.rerun_dev_phase4_fix import format_eval_prompt

DEV_A_PATH = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
V11_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_v11_pipeline_records.jsonl")
T5_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_self_check_eval.json")
ANALYSER_SOURCES_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_analyser_sources.json")
OUT_JSON_PATH = os.path.join(REPO_ROOT, "results", "phase4", "dev_slm_fallback_evaluation.json")


def load_dev_data():
    items = json.load(open(DEV_A_PATH, "r", encoding="utf-8"))
    with open(V11_PATH, "r", encoding="utf-8") as f:
        v11_recs = {json.loads(l)["item_id"]: json.loads(l) for l in f if l.strip()}
    t5_data = json.load(open(T5_PATH, "r", encoding="utf-8"))
    analyser_sources = json.load(open(ANALYSER_SOURCES_PATH, "r", encoding="utf-8"))
    return items, v11_recs, t5_data, analyser_sources


def detect_task_mode_from_prompt(prompt: str) -> str:
    """Infers execution mode strictly from prompt text (zero item metadata)."""
    p_lower = prompt.lower()
    if task_asks_for_query(prompt) or "[database schema:" in p_lower:
        return "sql"
    if "options:" in p_lower and "(a)" in p_lower:
        return "qa"
    if "####" in prompt or "conclude with: ####" in p_lower or "final answer: ####" in p_lower:
        return "math"
    if "```python" in prompt or "def " in prompt:
        return "code"
    return "general"


def extract_math_val(text: str) -> Optional[int]:
    m = re.search(r"####\s*(-?\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"\\boxed\{(-?\d+)\}", text)
    if m:
        return int(m.group(1))
    decl = re.findall(r"(?:answer\s+is\s+|total\s+is\s+|equal\s+to\s+|=\s*)(-?\d+)", text, re.I)
    if decl:
        try:
            return int(decl[-1])
        except Exception:
            pass
    nums = re.findall(r"\b(-?\d+)\b", text)
    if nums:
        try:
            return int(nums[-1])
        except Exception:
            pass
    return None


def extract_qa_letter(text: str) -> Optional[str]:
    m = re.findall(r"(?:answer\s*(?:is)?\s*[:\-]|\bfinal answer\s*[:\-]?\s*)\s*\(?([A-D])\)?", text, re.I)
    if m:
        return m[-1].upper()
    m = re.findall(r"\b([A-D])\b", text)
    if m:
        return m[-1].upper()
    return None


def extract_canonical_answer(task_mode: str, text: str) -> str:
    """Extracts a canonical normalized answer string for voting."""
    if task_mode == "math":
        ans = extract_math_val(text)
        return str(ans) if ans is not None else text.strip()
    elif task_mode == "qa":
        let = extract_qa_letter(text)
        return str(let) if let else text.strip()
    elif task_mode == "sql":
        return extract_sql_from_text(text).strip()
    else:
        # Compound, code, or general: look for Final Answer or last line
        m = re.search(r"(?:Final Answer|Answer|####):\s*([^\n\r]+)", text, re.I)
        if m:
            return m.group(1).strip()
        lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
        return lines[-1] if lines else text.strip()


# =========================================================================
# FALLBACK (a): 3 PARALLEL SAMPLES + MAJORITY VOTE
# =========================================================================

def sample_single(prompt: str, task_mode: str, temp: float = 0.7, seed: int = 42) -> str:
    """Dispatches a single stochastic sample to llama-server slot."""
    sys_prompt = "You are a helpful, precise assistant. Reason step-by-step and provide your final answer in the requested format."
    if task_mode == "sql":
        sys_prompt = "You are an expert SQLite assistant. Output ONLY the SQLite query enclosed in ```sql ... ```."
    elif task_mode == "qa":
        sys_prompt = "You are an expert QA assistant. Output your final option letter as Answer: (X)."
    elif task_mode == "code":
        sys_prompt = "You are an expert Python programmer. Output only valid Python code in ```python ... ```."
    elif task_mode == "math":
        sys_prompt = "Solve the math problem step by step. Conclude with: #### <number>."

    resp = call_phi([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt}
    ], temperature=temp, max_tokens=1024)
    return resp


def run_fallback_a_voting(prompt: str) -> Tuple[str, float]:
    """Runs 3 parallel stochastic samples on 3 slots and selects majority vote (prompt-only)."""
    t0 = time.time()
    task_mode = detect_task_mode_from_prompt(prompt)

    # Parallel dispatch across the 3 slots of llama-server
    seeds = [42, 101, 202]
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(sample_single, prompt, task_mode, 0.7, s) for s in seeds]
        samples = [f.result() for f in futures]

    dt = time.time() - t0

    # Extract canonical answers
    canonical_answers = [extract_canonical_answer(task_mode, s) for s in samples]

    # Majority vote
    counts = Counter(canonical_answers)
    most_common, freq = counts.most_common(1)[0]

    # If majority (2 or 3 agree), pick that sample
    if freq >= 2:
        for s, c in zip(samples, canonical_answers):
            if c == most_common:
                return s, dt
    # If tie / all different, return first sample
    return samples[0], dt


# =========================================================================
# FALLBACK (b): RE-DECOMPOSING ONCE AND ANSWERING AGAIN
# =========================================================================

def run_fallback_b_redecompose(prompt: str) -> Tuple[str, float]:
    """Re-decomposes once with refined instruction and answers again (prompt-only)."""
    t0 = time.time()
    task_mode = detect_task_mode_from_prompt(prompt)

    if task_mode == "sql":
        re_prompt = (
            f"{prompt}\n\n"
            f"Double-check table joins and column names. Write a clean, valid SQLite query in ```sql ... ```."
        )
        final_resp = call_phi([
            {"role": "system", "content": "You are an expert SQL assistant."},
            {"role": "user", "content": re_prompt}
        ], temperature=0.2, max_tokens=256)
        dt = time.time() - t0
        return final_resp, dt

    # Check if compound task (needs decomposition) via Stage 1 model call
    analysis, _ = analyse_task_model_call(prompt)
    if analysis.get("needs_outside_data") or "step" in prompt.lower() or "then" in prompt.lower():
        re_prompt = (
            f"Task:\n{prompt}\n\n"
            f"The previous decomposition failed verification. Please re-analyze the task carefully.\n"
            f"Decompose this task into exactly two clean, sequential subtasks (Subtask 1 and Subtask 2) such that:\n"
            f"- Subtask 1 retrieves the necessary data or executes the first calculation.\n"
            f"- Subtask 2 uses the exact result from Subtask 1 to produce the final answer.\n\n"
            f"Subtasks:"
        )
        decomp_resp = call_phi([
            {"role": "system", "content": "You are an expert task decomposer."},
            {"role": "user", "content": re_prompt}
        ], temperature=0.3, max_tokens=256)

        subtasks = [l.strip() for l in decomp_resp.split("\n") if l.strip() and ("Subtask" in l or l.startswith("1.") or l.startswith("2."))]
        if len(subtasks) < 2:
            subtasks = [f"Step 1: Fetch and compute initial values for: {prompt[:100]}", f"Step 2: Calculate final result."]

        reason_prompt = (
            f"Task: {prompt}\n\n"
            f"Plan:\n1. {subtasks[0]}\n2. {subtasks[1]}\n\n"
            f"Follow this plan step by step and provide the final answer concluding with 'Final Answer: <answer>' or '#### <answer>'."
        )
        final_resp = call_phi([
            {"role": "system", "content": "You are a precise reasoning specialist."},
            {"role": "user", "content": reason_prompt}
        ], temperature=0.0, max_tokens=1024)
        dt = time.time() - t0
        return final_resp, dt

    else:
        # Atomic reasoning
        re_prompt = (
            f"{prompt}\n\n"
            f"Carefully rethink and verify your solution step-by-step before stating the final answer."
        )
        final_resp = call_phi([
            {"role": "system", "content": "You are a precise reasoning specialist."},
            {"role": "user", "content": re_prompt}
        ], temperature=0.2, max_tokens=1024)
        dt = time.time() - t0
        return final_resp, dt


def bootstrap_diff_ci(diffs: List[float], n_boot: int = 10000, alpha: float = 0.05) -> Tuple[float, float]:
    rng = random.Random(42)
    n = len(diffs)
    means = []
    for _ in range(n_boot):
        sample = [rng.choice(diffs) for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lower_idx = int(n_boot * (alpha / 2))
    upper_idx = int(n_boot * (1 - alpha / 2))
    return (round(means[lower_idx] * 100, 2), round(means[upper_idx] * 100, 2))


def main():
    print("=" * 80)
    print("EVALUATION OF SLM-ONLY FALLBACK MECHANISMS ON DEV TRACK A (N=100)")
    print("=" * 80)

    items, v11_recs, t5_data, analyser_sources = load_dev_data()
    print(f"Loaded {len(items)} Dev Track A items.")

    # Identify triggered items
    triggered_iids = set()
    for item in items:
        iid = item.get("original_id") or item.get("subtask_id") or item.get("item_id")
        r = v11_recs.get(iid, {})
        clean = r.get("clean_execution", True)
        fallbacks = r.get("fallbacks", {})
        t1 = not clean
        t2 = bool(fallbacks.get("analyser", False))
        t3 = bool(fallbacks.get("database_identifier", False))
        final_ans = str(r.get("final_answer") or r.get("output", "")).strip()
        t4 = not bool(final_ans)
        t5 = bool(t5_data.get(iid, {}).get("flagged", False))
        is_corpus = (analyser_sources.get(iid, {}).get("source") == "CORPUS")

        if (t1 or t2 or t3 or t4 or t5) and not is_corpus:
            triggered_iids.add(iid)

    print(f"Triggered items: {len(triggered_iids)} / {len(items)} ({len(triggered_iids)/len(items)*100:.1f}%)")

    # Evaluate v1.1 Alone
    v11_scores = {}
    v11_latencies = {}
    for item in items:
        iid = item.get("original_id") or item.get("subtask_id") or item.get("item_id")
        r = v11_recs[iid]
        v11_scores[iid] = 1.0 if r.get("passed", False) else 0.0
        v11_latencies[iid] = float(r.get("duration", 0.0) or 0.0)

    v11_acc = sum(v11_scores.values()) / len(items) * 100
    v11_mean_lat = sum(v11_latencies.values()) / len(items)

    # -------------------------------------------------------------------------
    # RUN FALLBACK (a): 3 Parallel Samples + Majority Vote
    # -------------------------------------------------------------------------
    print("\n[Running Fallback (a): 3 Parallel Samples (temp=0.7) + Majority Vote on 32 items]...")
    fallback_a_scores = dict(v11_scores)
    fallback_a_latencies = dict(v11_latencies)
    fixed_a = []
    broke_a = []

    for idx, item in enumerate(items, 1):
        iid = item.get("original_id") or item.get("subtask_id") or item.get("item_id")
        if iid not in triggered_iids:
            continue

        prompt = format_eval_prompt(item)
        resp_a, dt_a = run_fallback_a_voting(prompt)
        sc_a = score_record(item, resp_a)
        is_pass_a = 1.0 if sc_a["passed"] else 0.0

        orig_pass = v11_scores[iid]
        if orig_pass == 0.0 and is_pass_a == 1.0:
            fixed_a.append(iid)
        elif orig_pass == 1.0 and is_pass_a == 0.0:
            broke_a.append(iid)

        fallback_a_scores[iid] = is_pass_a
        fallback_a_latencies[iid] = v11_latencies[iid] + dt_a
        print(f"  [Vote {len(fixed_a)+len(broke_a):02d}/32] {iid} -> Old: {bool(orig_pass)} | New: {bool(is_pass_a)} | Lat: +{dt_a:.2f}s")

    acc_a = sum(fallback_a_scores.values()) / len(items) * 100
    mean_lat_a = sum(fallback_a_latencies.values()) / len(items)
    diffs_a = [fallback_a_scores[iid] - v11_scores[iid] for iid in [it.get("original_id") or it.get("subtask_id") or it.get("item_id") for it in items]]
    paired_a = sum(diffs_a) / len(items) * 100
    ci_a = bootstrap_diff_ci(diffs_a)

    # -------------------------------------------------------------------------
    # RUN FALLBACK (b): Re-Decomposing Once and Answering Again
    # -------------------------------------------------------------------------
    print("\n[Running Fallback (b): Re-Decomposing Once and Answering Again on 32 items]...")
    fallback_b_scores = dict(v11_scores)
    fallback_b_latencies = dict(v11_latencies)
    fixed_b = []
    broke_b = []

    for idx, item in enumerate(items, 1):
        iid = item.get("original_id") or item.get("subtask_id") or item.get("item_id")
        if iid not in triggered_iids:
            continue

        prompt = format_eval_prompt(item)
        resp_b, dt_b = run_fallback_b_redecompose(prompt)
        sc_b = score_record(item, resp_b)
        is_pass_b = 1.0 if sc_b["passed"] else 0.0

        orig_pass = v11_scores[iid]
        if orig_pass == 0.0 and is_pass_b == 1.0:
            fixed_b.append(iid)
        elif orig_pass == 1.0 and is_pass_b == 0.0:
            broke_b.append(iid)

        fallback_b_scores[iid] = is_pass_b
        fallback_b_latencies[iid] = v11_latencies[iid] + dt_b
        print(f"  [ReDecomp {len(fixed_b)+len(broke_b):02d}/32] {iid} -> Old: {bool(orig_pass)} | New: {bool(is_pass_b)} | Lat: +{dt_b:.2f}s")

    acc_b = sum(fallback_b_scores.values()) / len(items) * 100
    mean_lat_b = sum(fallback_b_latencies.values()) / len(items)
    diffs_b = [fallback_b_scores[iid] - v11_scores[iid] for iid in [it.get("original_id") or it.get("subtask_id") or it.get("item_id") for it in items]]
    paired_b = sum(diffs_b) / len(items) * 100
    ci_b = bootstrap_diff_ci(diffs_b)

    # -------------------------------------------------------------------------
    # Save Results Summary
    # -------------------------------------------------------------------------
    summary = {
        "dataset": "Dev Track A (N=100)",
        "model": "phi-4-mini (SLM-only)",
        "fallback_rate_pct": round(len(triggered_iids) / len(items) * 100, 2),
        "triggered_count": len(triggered_iids),
        "v11_alone": {
            "accuracy": round(v11_acc, 2),
            "correct": int(sum(v11_scores.values())),
            "mean_latency_s": round(v11_mean_lat, 2)
        },
        "fallback_a_voting": {
            "accuracy": round(acc_a, 2),
            "correct": int(sum(fallback_a_scores.values())),
            "mean_latency_s": round(mean_lat_a, 2),
            "paired_diff_vs_v11": round(paired_a, 2),
            "paired_diff_95_ci": list(ci_a),
            "fixed_count": len(fixed_a),
            "broke_count": len(broke_a),
            "net_gain": len(fixed_a) - len(broke_a),
            "fixed_items": fixed_a,
            "broke_items": broke_a
        },
        "fallback_b_redecompose": {
            "accuracy": round(acc_b, 2),
            "correct": int(sum(fallback_b_scores.values())),
            "mean_latency_s": round(mean_lat_b, 2),
            "paired_diff_vs_v11": round(paired_b, 2),
            "paired_diff_95_ci": list(ci_b),
            "fixed_count": len(fixed_b),
            "broke_count": len(broke_b),
            "net_gain": len(fixed_b) - len(broke_b),
            "fixed_items": fixed_b,
            "broke_items": broke_b
        }
    }

    with open(OUT_JSON_PATH, "w", encoding="utf-8") as f_out:
        json.dump(summary, f_out, indent=2)

    # Print Comparison Table
    print("\n" + "=" * 105)
    print("SLM-ONLY FALLBACK COMPARISON TABLE ON DEV TRACK A (N=100)")
    print("=" * 105)
    print(f"{'System / Strategy':<35} | {'Acc (N=100)':<12} | {'Fallback Rate':<14} | {'Mean Latency':<13} | {'Paired Diff vs v1.1':<22} | {'Net'}")
    print("-" * 105)
    print(f"{'Pipeline v1.1 Alone':<35} | {v11_acc:>5.1f}% ({int(sum(v11_scores.values())):>2}/100) | {'0.0%':<14} | {v11_mean_lat:>10.2f}s   | {'—':<22} | +0")
    print(f"{'Fallback (a): 3-Slot Vote (T=0.7)':<35} | {acc_a:>5.1f}% ({int(sum(fallback_a_scores.values())):>2}/100) | {len(triggered_iids):>2.0f}% ({len(triggered_iids):>2}/100)  | {mean_lat_a:>10.2f}s   | {paired_a:>+5.2f} pp [{ci_a[0]:>+5.2f}, {ci_a[1]:>+5.2f}] | {len(fixed_a)-len(broke_a):>+2}")
    print(f"{'Fallback (b): Re-Decompose Once':<35} | {acc_b:>5.1f}% ({int(sum(fallback_b_scores.values())):>2}/100) | {len(triggered_iids):>2.0f}% ({len(triggered_iids):>2}/100)  | {mean_lat_b:>10.2f}s   | {paired_b:>+5.2f} pp [{ci_b[0]:>+5.2f}, {ci_b[1]:>+5.2f}] | {len(fixed_b)-len(broke_b):>+2}")
    print("=" * 105)


if __name__ == "__main__":
    main()

