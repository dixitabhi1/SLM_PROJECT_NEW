"""
scripts/run_judge_prometheus.py

Secondary Evaluation Layer: LLM-as-a-Judge using Local Prometheus-2 7B.
Model: prometheus-eval/prometheus-7b-v2.0 (GGUF Q4_K_M, SHA-256 5bb7b0fa...)
Server: tools/llama_bin/llama-server.exe on port 8081 (temperature=0.0, context 4096)

Zero spend, 100% local GPU execution, strictly reference-free (no gold labels or answer keys).
Resumable execution writing to results/judge/judge_trials_raw_prometheus7b.jsonl.
"""

import os
import sys
import json
import time
import requests
import re
import hashlib
import numpy as np
from typing import Dict, Any, List, Tuple, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.run_heldout_evaluation import format_eval_prompt
from scripts.run_judge_phase3 import get_user_facing_response, compute_bootstrap_ci

LLAMA_SERVER_URL = "http://127.0.0.1:8081"
JUDGE_MODEL = "prometheus-eval/prometheus-7b-v2.0"
GGUF_SHA256 = "5bb7b0fa6b244a8cad8d2bb29d0f96422c43d3497fe1ab9ced7fd1ead03cc976"

TRACK_A_PATH = os.path.join(REPO_ROOT, "data", "track_a_heldout_split.json")
TRACK_B_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_heldout_split.json")
EXPECTED_TRACK_A_HASH = "2314fca186a064ffcface62f42dc346bda9fdc73c5221852e8ecf5b19aafd629"
EXPECTED_TRACK_B_HASH = "075bf20d1daafdb89e3eef1e35271113766b9845cfb9d52e88301faa2919c0e1"

SLM_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "heldout_e3_v2_pipeline_records.jsonl")
GPT120B_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "b1_gpt120b_heldout_records.jsonl")
QWEN27B_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "b1_qwen27b_heldout_records.jsonl")

OUT_DIR = os.path.join(REPO_ROOT, "results", "judge")
OUT_RAW_FILE = os.path.join(OUT_DIR, "judge_trials_raw_prometheus7b.jsonl")
OUT_SUMMARY_FILE = os.path.join(OUT_DIR, "judge_summary_metrics.json")
OUT_REPORTS_DIR = os.path.join(REPO_ROOT, "docs", "reports")

RUBRIC_TEMPLATE = """###Task Description:
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
[{criterion_name}]
Score 1: {s1}
Score 2: {s2}
Score 3: {s3}
Score 4: {s4}
Score 5: {s5}

###Feedback:
"""

CRITERIA = {
    "holistic": {
        "name": "Overall Quality and Usefulness",
        "s1": "Completely incorrect, broken, incomplete, or fails to answer the question.",
        "s2": "Partially correct but contains major errors, missing key components, or faulty logic.",
        "s3": "Acceptable response, answers the core question with minor errors or formatting issues.",
        "s4": "Very good response, correct, complete, logically sound, and well-structured.",
        "s5": "Exceptional, flawless, fully accurate, comprehensive, and clearly formatted response."
    },
    "correctness": {
        "name": "Factual and Computational Correctness",
        "s1": "Entirely incorrect or factual errors throughout.",
        "s2": "Major factual or logical errors affecting the core conclusion.",
        "s3": "Core facts/calculations mostly correct, but minor errors or unverified assertions present.",
        "s4": "Accurate with only trivial or cosmetic inaccuracies that do not affect the result.",
        "s5": "Fully correct, mathematically and factually sound throughout."
    },
    "completeness": {
        "name": "Completeness",
        "s1": "Severely incomplete, empty, or truncated before providing any substantive answer.",
        "s2": "Addresses only a small fraction of the requirements; major missing parts.",
        "s3": "Addresses the main question but omits secondary parts, constraints, or steps.",
        "s4": "Substantially complete; all key requirements and questions addressed.",
        "s5": "Exhaustively complete; addresses every requirement, edge case, and constraint."
    },
    "reasoning_quality": {
        "name": "Reasoning Quality",
        "s1": "Incoherent, nonsensical, or completely absent reasoning.",
        "s2": "Flawed reasoning with severe logical leaps, non-sequiturs, or fallacies.",
        "s3": "Basic reasoning present; steps follow but lack depth, clarity, or rigour.",
        "s4": "Clear, coherent, step-by-step reasoning that directly supports the conclusion.",
        "s5": "Rigorous, transparent, elegant, and logically impeccable reasoning throughout."
    },
    "formatting": {
        "name": "Format and Instruction Following",
        "s1": "Ignores all formatting requirements and instructions.",
        "s2": "Violates major formatting instructions (e.g. wrong output type, missed required tags).",
        "s3": "Follows some instructions but misses minor formatting details or style constraints.",
        "s4": "Follows almost all instructions and formatting requirements accurately.",
        "s5": "Flawlessly adheres to all instructions, output formats, schemas, and constraints."
    }
}

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

class ContextOverflowError(Exception):
    pass

class JudgeParseError(Exception):
    pass

def call_prometheus(prompt: str, max_tokens: int = 500) -> Tuple[str, Dict[str, Any], float]:
    url = f"{LLAMA_SERVER_URL}/completion"
    payload = {
        "prompt": f"[INST] {prompt} [/INST]",
        "temperature": 0.0,
        "n_predict": max_tokens,
        "stop": ["</s>", "[INST]", "[/INST]"]
    }
    t0 = time.time()
    resp = requests.post(url, json=payload, timeout=180)
    dur = time.time() - t0
    if resp.status_code != 200:
        if "exceed" in resp.text.lower() or "context size" in resp.text.lower():
            raise ContextOverflowError(f"context_overflow: {resp.text}")
        raise RuntimeError(f"llama-server error ({resp.status_code}): {resp.text}")
    data = resp.json()
    return data.get("content", ""), data, dur

def evaluate_single_criterion(instruction: str, response: str, crit_key: str, max_tokens: int = 500) -> Tuple[int, str, float, Dict[str, Any]]:
    crit_info = CRITERIA[crit_key]
    prompt = RUBRIC_TEMPLATE.format(
        instruction=instruction,
        response=response,
        criterion_name=crit_info["name"],
        s1=crit_info["s1"], s2=crit_info["s2"], s3=crit_info["s3"], s4=crit_info["s4"], s5=crit_info["s5"]
    )
    # Retry once on failure
    for attempt in range(2):
        content, data, dur = call_prometheus(prompt, max_tokens=max_tokens)
        m = re.search(r"\[RESULT\]\s*\(?([1-5])\)?", content)
        if m:
            return int(m.group(1)), content, dur, data
        time.sleep(0.5)
    raise JudgeParseError(f"Failed to parse [RESULT] integer score for criterion '{crit_key}': {content[-100:]}")

def evaluate_pairwise(instruction: str, resp_a: str, resp_b: str, max_tokens: int = 500) -> Tuple[str, str, float, Dict[str, Any]]:
    prompt = PROMETHEUS_PAIRWISE_PROMPT.format(
        instruction=instruction,
        response_a=resp_a,
        response_b=resp_b
    )
    for attempt in range(2):
        content, data, dur = call_prometheus(prompt, max_tokens=max_tokens)
        m = re.search(r"\[RESULT\]\s*\(?([AB]|Tie)\)?", content, re.IGNORECASE)
        if m:
            return m.group(1).upper(), content, dur, data
        time.sleep(0.5)
    raise JudgeParseError(f"Failed to parse [RESULT] pairwise winner: {content[-100:]}")

def evaluate_full_answer_profile(instruction: str, response: str, max_tokens: int = 500) -> Dict[str, Any]:
    scores = {}
    feedbacks = {}
    total_dur = 0.0
    prompt_tok = 0
    gen_tok = 0

    for crit_key in ("holistic", "correctness", "completeness", "reasoning_quality", "formatting"):
        score, fb, dur, data = evaluate_single_criterion(instruction, response, crit_key, max_tokens=max_tokens)
        scores[crit_key] = score
        feedbacks[crit_key] = fb
        total_dur += dur
        prompt_tok += data.get("tokens_evaluated", 0)
        gen_tok += data.get("tokens_predicted", 0)

    cqs = (scores["correctness"] + scores["completeness"] + scores["reasoning_quality"] + scores["formatting"]) / 4.0
    return {
        "holistic": scores["holistic"],
        "correctness": scores["correctness"],
        "completeness": scores["completeness"],
        "reasoning_quality": scores["reasoning_quality"],
        "formatting": scores["formatting"],
        "cqs": cqs,
        "feedbacks": feedbacks,
        "duration": total_dur,
        "prompt_tokens": prompt_tok,
        "completion_tokens": gen_tok,
        "parse_failed": False
    }


def verify_heldout_hashes():
    ha = hashlib.sha256(open(TRACK_A_PATH, "rb").read()).hexdigest()
    hb = hashlib.sha256(open(TRACK_B_PATH, "rb").read()).hexdigest()
    assert ha == EXPECTED_TRACK_A_HASH, f"Track A hash mismatch: {ha}"
    assert hb == EXPECTED_TRACK_B_HASH, f"Track B hash mismatch: {hb}"
    print(f"[VERIFIED] Track A Held-Out Hash: {ha}")
    print(f"[VERIFIED] Track B Held-Out Hash: {hb}")


def evaluate_summary_metrics(
    eval_items: List[Tuple[str, str, str, dict]],
    completed_records: Dict[Tuple[str, str], dict],
    baselines: List[Tuple[str, dict, str]],
    slm_recs: Dict[str, dict]
) -> Dict[str, Any]:
    n_items = len(eval_items)
    print("\n" + "=" * 80)
    print(f"EVALUATION SUMMARY METRICS (N={n_items} items)")
    print("=" * 80)

    summary: Dict[str, Any] = {
        "title": "Prometheus-2 7B Held-Out Evaluation Summary",
        "judge_model": JUDGE_MODEL,
        "gguf_sha256": GGUF_SHA256,
        "n_items": n_items,
        "comparisons": {},
        "lengths_and_correlations": {}
    }

    length_score_data: Dict[str, list] = {
        "slm_lens": [], "slm_scores": [],
        "gpt_lens": [], "gpt_scores": [],
        "qwen_lens": [], "qwen_scores": []
    }

    for b_name, b_dict, b_label in baselines:
        slm_wins, llm_wins, draws = 0, 0, 0
        pw_slm_wins, pw_llm_wins, pw_draws = 0, 0, 0
        swap_agreements = 0
        disagreements = []
        wrong_answers = []
        qps = []
        delta_qs = []
        slm_cqs_list = []
        llm_cqs_list = []
        exclusions_count = 0

        cat_data: Dict[str, Dict[str, list]] = {}

        for iid, track, cat, it in eval_items:
            rec = completed_records.get((iid, b_name))
            if not rec:
                continue

            if rec.get("parse_failed"):
                exclusions_count += 1
                continue

            q_s = float(rec["slm_profile"]["holistic"])
            q_l = float(rec["llm_profile"]["holistic"])
            cqs_s = float(rec["slm_profile"]["cqs"])
            cqs_l = float(rec["llm_profile"]["cqs"])

            slm_cqs_list.append(cqs_s)
            llm_cqs_list.append(cqs_l)

            # Native 1-5 scale QP: QP = 1 - |Q_S - Q_L| / 4
            qp = 1.0 - (abs(q_s - q_l) / 4.0)
            dq = q_s - q_l
            qps.append(qp)
            delta_qs.append(dq)

            # Length correlation tracking
            s_len = rec.get("slm_len", 0)
            l_len = rec.get("llm_len", 0)
            length_score_data["slm_lens"].append(s_len)
            length_score_data["slm_scores"].append(q_s)
            if "gpt" in b_name.lower():
                length_score_data["gpt_lens"].append(l_len)
                length_score_data["gpt_scores"].append(q_l)
            else:
                length_score_data["qwen_lens"].append(l_len)
                length_score_data["qwen_scores"].append(q_l)

            if cat not in cat_data:
                cat_data[cat] = {
                    "qps": [], "dqs": [], "slm_w": 0, "llm_w": 0, "draw": 0,
                    "slm_cqs": [], "llm_cqs": []
                }
            cat_data[cat]["qps"].append(qp)
            cat_data[cat]["dqs"].append(dq)
            cat_data[cat]["slm_cqs"].append(cqs_s)
            cat_data[cat]["llm_cqs"].append(cqs_l)

            # Primary outcomes: Win / Draw / Loss from holistic scores
            if q_s > q_l:
                slm_wins += 1
                cat_data[cat]["slm_w"] += 1
            elif q_l > q_s:
                llm_wins += 1
                cat_data[cat]["llm_w"] += 1
            else:
                draws += 1
                cat_data[cat]["draw"] += 1

            # Secondary Pairwise Outcomes & Swap Consistency
            pw_A = rec.get("pairwise_A", {}).get("winner", "")
            pw_B = rec.get("pairwise_B", {}).get("winner", "")
            # Pass A: Answer 1 = SLM, Answer 2 = LLM -> 'A' is SLM, 'B' is LLM
            # Pass B: Answer 1 = LLM, Answer 2 = SLM -> 'B' is SLM, 'A' is LLM
            pw_A_sys = "SLM" if pw_A == "A" else ("LLM" if pw_A == "B" else "Draw")
            pw_B_sys = "SLM" if pw_B == "B" else ("LLM" if pw_B == "A" else "Draw")

            if pw_A_sys == pw_B_sys:
                swap_agreements += 1
                if pw_A_sys == "SLM":
                    pw_slm_wins += 1
                elif pw_A_sys == "LLM":
                    pw_llm_wins += 1
                else:
                    pw_draws += 1
            else:
                pw_draws += 1  # Inconsistent swap counts as draw / inconclusive

            # Validity check (a): concordance on answer-key disagreements
            s_rec = slm_recs.get(iid, {})
            b_rec = b_dict.get(iid, {})
            s_pass = bool(s_rec.get("passed", False))
            l_pass = bool(b_rec.get("passed", False))

            if s_pass != l_pass:
                ak_winner = "SLM" if s_pass else "LLM"
                j_winner = "SLM" if q_s > q_l else ("LLM" if q_l > q_s else "Draw")
                concordant = (ak_winner == j_winner)
                disagreements.append({"item_id": iid, "ak_winner": ak_winner, "j_winner": j_winner, "concordant": concordant})

            # Validity check (b): false high scores on wrong answers
            if not s_pass:
                wrong_answers.append(("SLM", iid, q_s))
            if not l_pass:
                wrong_answers.append(("LLM", iid, q_l))

        evaluated_count = len(qps)
        if evaluated_count == 0:
            print(f"No completed items for {b_label}")
            continue

        qp_mean, qp_low, qp_high = compute_bootstrap_ci(np.array(qps))
        dq_mean, dq_low, dq_high = compute_bootstrap_ci(np.array(delta_qs))
        mean_cqs_s = float(np.mean(slm_cqs_list))
        mean_cqs_l = float(np.mean(llm_cqs_list))

        eff_win_rate = ((slm_wins + draws) / evaluated_count) * 100.0
        swap_consist_pct = (swap_agreements / evaluated_count) * 100.0

        if disagreements:
            conc_count = sum(1 for d in disagreements if d["concordant"])
            conc_rate = (conc_count / len(disagreements)) * 100.0
            conc_rate_str = f"{conc_rate:.1f}%"
            passed_gate = (conc_rate >= 80.0)
        else:
            conc_count = 0
            conc_rate = None
            conc_rate_str = "n/a"
            passed_gate = "n/a"

        if wrong_answers:
            false_high = sum(1 for _, _, q in wrong_answers if q >= 4.0)  # >= 4 on 1-5 scale is false high
            false_high_rate = (false_high / len(wrong_answers)) * 100.0
        else:
            false_high = 0
            false_high_rate = 0.0

        per_cat_summary = {}
        for c, cvals in cat_data.items():
            c_qp_m, c_qp_l, c_qp_h = compute_bootstrap_ci(np.array(cvals["qps"]))
            c_dq_m, c_dq_l, c_dq_h = compute_bootstrap_ci(np.array(cvals["dqs"]))
            per_cat_summary[c] = {
                "n": len(cvals["qps"]),
                "slm_wins": cvals["slm_w"],
                "llm_wins": cvals["llm_w"],
                "draws": cvals["draw"],
                "qp": {"mean": c_qp_m, "ci_low": c_qp_l, "ci_high": c_qp_h},
                "delta_q": {"mean": c_dq_m, "ci_low": c_dq_l, "ci_high": c_dq_h},
                "slm_cqs": float(np.mean(cvals["slm_cqs"])) if cvals["slm_cqs"] else 0.0,
                "llm_cqs": float(np.mean(cvals["llm_cqs"])) if cvals["llm_cqs"] else 0.0
            }

        b_summary = {
            "baseline": b_name,
            "baseline_label": b_label,
            "evaluated_items": evaluated_count,
            "exclusions_count": exclusions_count,
            "slm_wins": slm_wins,
            "llm_wins": llm_wins,
            "draws": draws,
            "effective_win_rate": eff_win_rate,
            "qp": {"mean": qp_mean, "ci_low": qp_low, "ci_high": qp_high},
            "delta_q": {"mean": dq_mean, "ci_low": dq_low, "ci_high": dq_high},
            "mean_slm_cqs": mean_cqs_s,
            "mean_llm_cqs": mean_cqs_l,
            "pairwise_outcomes": {
                "slm_wins": pw_slm_wins,
                "llm_wins": pw_llm_wins,
                "draws": pw_draws,
                "swap_consistency": swap_consist_pct
            },
            "check_a_concordance": {
                "total_disagreements": len(disagreements),
                "concordant_items": conc_count,
                "concordance_rate": conc_rate_str,
                "passed_gate": passed_gate
            },
            "check_b_false_high_score": {
                "total_wrong_answers": len(wrong_answers),
                "false_high_scores": false_high,
                "false_high_rate": false_high_rate
            },
            "per_category": per_cat_summary
        }
        summary["comparisons"][b_name] = b_summary

        print(f"\n>>> Specialist SLM v1.3 vs {b_label} <<<")
        print(f"  Evaluated Items: {evaluated_count} (Exclusions: {exclusions_count})")
        print(f"  Holistic Outcomes: SLM Wins: {slm_wins} ({slm_wins/evaluated_count*100:.1f}%) | Draws: {draws} ({draws/evaluated_count*100:.1f}%) | LLM Wins: {llm_wins} ({llm_wins/evaluated_count*100:.1f}%) | Eff. Win Rate: {eff_win_rate:.1f}%")
        print(f"  Quality Proximity (QP): {qp_mean:.4f} [95% CI: {qp_low:.4f}, {qp_high:.4f}]")
        print(f"  Quality Difference (Delta Q): {dq_mean:+.4f} [95% CI: {dq_low:+.4f}, {dq_high:+.4f}]")
        print(f"  CQS (1-5): SLM {mean_cqs_s:.2f} vs LLM {mean_cqs_l:.2f}")
        print(f"  Pairwise Signal: SLM Wins: {pw_slm_wins} | Draws: {pw_draws} | LLM Wins: {pw_llm_wins} | Swap Consistency: {swap_consist_pct:.1f}%")
        gate_str = ("PASSED (>=80%)" if passed_gate is True else "FAILED (<80%)") if passed_gate != "n/a" else "n/a (no disagreements)"
        print(f"  Check (a) Concordance: {conc_rate_str} ({conc_count}/{len(disagreements)}) -> {gate_str}")
        print(f"  Check (b) False High Score (>=4/5 on Wrong): {false_high_rate:.1f}% ({false_high}/{len(wrong_answers)})")
        print("  Per-Category Breakdown (SLM Wins / Draws / LLM Wins | Delta Q [95% CI]):")
        for c, cdata in per_cat_summary.items():
            print(f"    - {c:32s}: {cdata['slm_wins']:2d} / {cdata['draws']:2d} / {cdata['llm_wins']:2d} | Delta Q: {cdata['delta_q']['mean']:+.3f} [{cdata['delta_q']['ci_low']:+.3f}, {cdata['delta_q']['ci_high']:+.3f}] | CQS: SLM {cdata['slm_cqs']:.2f} vs LLM {cdata['llm_cqs']:.2f}")

    def calc_corr(lens: list, scores: list) -> float:
        if len(lens) < 2:
            return 0.0
        return float(np.corrcoef(lens, scores)[0, 1])

    mean_slm_len = float(np.mean(length_score_data["slm_lens"])) if length_score_data["slm_lens"] else 0.0
    mean_gpt_len = float(np.mean(length_score_data["gpt_lens"])) if length_score_data["gpt_lens"] else 0.0
    mean_qwen_len = float(np.mean(length_score_data["qwen_lens"])) if length_score_data["qwen_lens"] else 0.0

    r_slm = calc_corr(length_score_data["slm_lens"], length_score_data["slm_scores"])
    r_gpt = calc_corr(length_score_data["gpt_lens"], length_score_data["gpt_scores"])
    r_qwen = calc_corr(length_score_data["qwen_lens"], length_score_data["qwen_scores"])

    summary["lengths_and_correlations"] = {
        "mean_response_length_chars": {
            "Specialist_SLM_v1.3": mean_slm_len,
            "GPT-OSS-120B_B1": mean_gpt_len,
            "qwen/qwen3.8-27b_B1": mean_qwen_len
        },
        "length_score_pearson_r": {
            "Specialist_SLM_v1.3": r_slm,
            "GPT-OSS-120B_B1": r_gpt,
            "qwen/qwen3.8-27b_B1": r_qwen
        }
    }

    print("\n>>> Response Length & Correlation Analysis <<<")
    print(f"  Specialist SLM v1.3 : Mean Length {mean_slm_len:6.1f} chars | r(Length, Score) = {r_slm:+.3f}")
    print(f"  GPT-OSS-120B B1     : Mean Length {mean_gpt_len:6.1f} chars | r(Length, Score) = {r_gpt:+.3f}")
    print(f"  qwen/qwen3.8-27b B1 : Mean Length {mean_qwen_len:6.1f} chars | r(Length, Score) = {r_qwen:+.3f}")

    return summary


def write_mentor_tables(summary: Dict[str, Any]):
    os.makedirs(OUT_REPORTS_DIR, exist_ok=True)
    c_120 = summary["comparisons"].get("openai/gpt-oss-120b", {})
    c_27 = summary["comparisons"].get("qwen/qwen3.8-27b", {})

    def format_row_md(exp, slm_ft, skill_m, llm_ft, c):
        if not c or "slm_wins" not in c:
            return f"| {exp} | {slm_ft} | {skill_m} | {llm_ft} | — | — | — | Not run | — | — |\n"
        n = c["evaluated_items"]
        lw = f"{c['llm_wins']} ({c['llm_wins']/n*100:.1f}%)"
        sw = f"{c['slm_wins']} ({c['slm_wins']/n*100:.1f}%)"
        dr = f"{c['draws']} ({c['draws']/n*100:.1f}%)"
        qp = f"{c['qp']['mean']:.4f} [{c['qp']['ci_low']:.4f}, {c['qp']['ci_high']:.4f}]"
        scqs = f"{c['mean_slm_cqs']:.2f}"
        lcqs = f"{c['mean_llm_cqs']:.2f}"
        return f"| {exp} | {slm_ft} | {skill_m} | {llm_ft} | {lw} | {sw} | {dr} | {qp} | {scqs} | {lcqs} |\n"

    md_content = """# Mentor Protocol Table: Secondary Evaluation Layer (LLM-as-a-Judge)

**Judge Evaluation Scope:** Held-Out Split ($N=150$: Track A $N=100$, Track B $N=50$).  
**Judge Model:** `prometheus-eval/prometheus-7b-v2.0` (GGUF Q4_K_M, SHA-256 `5bb7b0fa...`, local execution on port 8081).  
**Protocol Invariants:** Temperature 0.0, reference-free (no answer key), native 1–5 rubrics. Quality Proximity computed on native scale ($QP = 1 - |Q_S - Q_L|/4$).  

| Experiment | SLM Fine-Tuning Configuration | Skill-Matching SLM | LLM Fine-Tuning | LLM Wins | SLM Wins | Draws | Quality Proximity | SLM CQS | LLM CQS |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
"""
    md_content += format_row_md("E1 (vs GPT-OSS-120B B1)", "None (Base Phi-4-mini 3.82B, prompt/tool-only)", "Single-model pool (no router)", "None (Frozen API B1)", c_120)
    md_content += format_row_md("E1 (vs qwen/qwen3.8-27b B1)", "None (Base Phi-4-mini 3.82B, prompt/tool-only)", "Single-model pool (no router)", "None (Frozen API B1)", c_27)
    md_content += """| E2 | Query-dependent LoRA adapters (SQL specialist) | Single-model pool | None | — | — | — | Not run (training pipeline prepared, run pending owner sign-off) | — | — |
| E3 | All specialist SLMs fine-tuned | Multi-SLM pool | None | — | — | — | Not run (mentor multi-model pool not configured; repo E3 was compute-in-code) | — | — |
| E4-A | None | Skill-matching SLM (router) | None | — | — | — | Not run as specified (repo E4 learned router rejected on dev headroom gate) | — | — |
| E4-B | Fine-tuned skill matcher | Fine-tuned router | None | — | — | — | Not run (repo E4b retry failed dev regression gate) | — | — |

**Footnote:** Mapping to repo experiments: Our frozen pipeline v1.3 corresponds to mentor E1 (no fine-tuning, autonomous tool execution). Our repo "E3" designates compute-in-code routing (accepted into v1.3), not all-SLM fine-tuning. Our repo "E4" designates learned router experiments (E4 and E4b, both rejected at dev gates). The active specialist pool is a single 3.82B parameter model (Phi-4-mini) with specialized execution tools, not a 5–8B multi-model pool.
"""

    with open(os.path.join(OUT_REPORTS_DIR, "mentor_protocol_table.md"), "w", encoding="utf-8") as f:
        f.write(md_content)
    with open(os.path.join(REPO_ROOT, "docs", "judge_mentor_table.md"), "w", encoding="utf-8") as f:
        f.write(md_content)

    def format_row_tex(exp, slm_ft, skill_m, llm_ft, c):
        if not c or "slm_wins" not in c:
            return f"{exp} & {slm_ft} & {skill_m} & {llm_ft} & — & — & — & Not run & — & — \\\\\n"
        n = c["evaluated_items"]
        lw = f"{c['llm_wins']} ({c['llm_wins']/n*100:.1f}\\%)"
        sw = f"{c['slm_wins']} ({c['slm_wins']/n*100:.1f}\\%)"
        dr = f"{c['draws']} ({c['draws']/n*100:.1f}\\%)"
        qp = f"{c['qp']['mean']:.4f} [{c['qp']['ci_low']:.4f}, {c['qp']['ci_high']:.4f}]"
        scqs = f"{c['mean_slm_cqs']:.2f}"
        lcqs = f"{c['mean_llm_cqs']:.2f}"
        return f"{exp} & {slm_ft} & {skill_m} & {llm_ft} & {lw} & {sw} & {dr} & {qp} & {scqs} & {lcqs} \\\\\n"

    tex_content = """% Mentor Protocol Table: Secondary Evaluation Layer (LLM-as-a-Judge)
\\begin{table*}[t]
\\centering
\\small
\\caption{\\textbf{Mentor Protocol Evaluation Matrix: LLM-as-a-Judge Secondary Layer} ($N=150$, Held-Out Split). Evaluated using local Prometheus-2 7B (GGUF Q4\\_K\\_M, temperature 0.0) with native 1–5 rubrics. Quality Proximity is defined as $QP = 1 - |Q_S - Q_L|/4$; brackets denote empirical 95\\% bootstrap percentile confidence intervals ($B=10000$). Primary answer-key correctness remains the definitive metric.}
\\label{tab:mentor_protocol_results}
\\begin{tabular}{llcccccccc}
\\toprule
\\textbf{Experiment} & \\textbf{SLM Fine-Tuning} & \\textbf{Skill-Match} & \\textbf{LLM FT} & \\textbf{LLM Win} & \\textbf{SLM Win} & \\textbf{Draw} & \\textbf{Quality Proximity} & \\textbf{SLM CQS} & \\textbf{LLM CQS} \\\\
\\midrule
"""
    tex_content += format_row_tex("E1 (vs 120B B1)", "None (Phi-4-mini base)", "Single SLM", "None", c_120)
    tex_content += format_row_tex("E1 (vs 27B B1)", "None (Phi-4-mini base)", "Single SLM", "None", c_27)
    tex_content += """E2 & Query-dep. LoRA (SQL) & Single SLM & None & — & — & — & Not run & — & — \\\\
E3 & All specialists FT & Multi-SLM & None & — & — & — & Not run & — & — \\\\
E4-A & None & Skill-matching & None & — & — & — & Not run & — & — \\\\
E4-B & FT skill matcher & FT router & None & — & — & — & Not run & — & — \\\\
\\bottomrule
\\end{tabular}
\\begin{tablenotes}
\\small
\\item \\textbf{Note on Experiment Mapping:} Frozen pipeline v1.3 corresponds to mentor E1 (no fine-tuning, autonomous tool execution). Repo E3 designates compute-in-code routing (accepted into v1.3), not all-SLM fine-tuning. Repo E4 designates learned router experiments (rejected at dev gates). The specialist pool is a single 3.82B model with tools, not a 5–8B multi-model pool.
\\end{tablenotes}
\\end{table*}
"""
    with open(os.path.join(OUT_REPORTS_DIR, "mentor_protocol_table.tex"), "w", encoding="utf-8") as f:
        f.write(tex_content)
    with open(os.path.join(REPO_ROOT, "docs", "judge_mentor_table.tex"), "w", encoding="utf-8") as f:
        f.write(tex_content)

    print(f"\n[SAVED] Mentor protocol tables written to:")
    print(f"  - docs/reports/mentor_protocol_table.md & .tex")
    print(f"  - docs/judge_mentor_table.md & .tex")


def main():
    print("=" * 80)
    print("STARTING HELD-OUT EVALUATION WITH LOCAL PROMETHEUS-2 7B JUDGE")
    print("=" * 80)

    # 1. Verify Hashes
    verify_heldout_hashes()

    os.makedirs(OUT_DIR, exist_ok=True)

    # 2. Load Held-Out Items (Track A first, then Track B)
    with open(TRACK_A_PATH, "r", encoding="utf-8") as f:
        track_a_items = json.load(f)
    with open(TRACK_B_PATH, "r", encoding="utf-8") as f:
        track_b_items = json.load(f)

    eval_items: List[Tuple[str, str, str, dict]] = []
    for it in track_a_items:
        iid = it.get("item_id") or it.get("original_id")
        cat = it.get("task_type") or it.get("category", "track_a")
        eval_items.append((iid, "track_a", cat, it))

    for it in track_b_items:
        iid = it.get("item_id") or it.get("question_id") or it.get("original_id")
        cat = "track_b_fact_checklist"
        eval_items.append((iid, "track_b", cat, it))

    print(f"Loaded {len(eval_items)} Held-Out Items (Track A: {len(track_a_items)}, Track B: {len(track_b_items)})")

    # 3. Load Model Responses
    slm_recs = {}
    with open(SLM_RECORDS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                slm_recs[d["item_id"]] = d

    gpt_recs = {}
    with open(GPT120B_RECORDS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                gpt_recs[d["item_id"]] = d

    qwen_recs = {}
    with open(QWEN27B_RECORDS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                qwen_recs[d["item_id"]] = d

    baselines = [
        ("openai/gpt-oss-120b", gpt_recs, "GPT-OSS-120B B1"),
        ("qwen/qwen3.8-27b", qwen_recs, "qwen/qwen3.8-27b B1")
    ]

    # 4. Load Completed Records from OUT_RAW_FILE (Resumable & Auditable)
    # Maintain latest record per (item_id, baseline)
    latest_records: Dict[Tuple[str, str], dict] = {}
    slm_profiles_cache: Dict[str, dict] = {}

    if os.path.exists(OUT_RAW_FILE):
        with open(OUT_RAW_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        d = json.loads(line)
                        k = (d["item_id"], d["baseline"])
                        latest_records[k] = d
                        if "slm_profile" in d and not d["slm_profile"].get("parse_failed"):
                            slm_profiles_cache[d["item_id"]] = d["slm_profile"]
                    except Exception:
                        pass
        print(f"Resuming execution: loaded {len(latest_records)} unique comparison records ({len(slm_profiles_cache)} SLM profiles cached)")

    # 5. Open output file for appending (Never overwrite or delete)
    f_out = open(OUT_RAW_FILE, "a", encoding="utf-8")

    # Step 5A: Repair Pass for Track A Failed Items (attempt=2, repair_of=...)
    track_a_repairs = []
    for iid, track, cat, it in eval_items:
        if track != "track_a":
            continue
        for b_name, b_dict, b_label in baselines:
            comp_key = (iid, b_name)
            old_rec = latest_records.get(comp_key)
            if old_rec and old_rec.get("parse_failed"):
                track_a_repairs.append((iid, track, cat, it, b_name, b_dict, b_label, old_rec))

    print(f"\n" + "=" * 80)
    print(f"[REPAIR PASS] Found {len(track_a_repairs)} parse_failed Track A trials to repair with n_predict=500, ctx=8192")
    print("=" * 80)

    for rep_idx, (iid, track, cat, it, b_name, b_dict, b_label, old_rec) in enumerate(track_a_repairs, 1):
        prompt_text = format_eval_prompt(it)
        s_rec = slm_recs[iid]
        s_text, s_field = get_user_facing_response(s_rec, "Specialist SLM v1.3")
        b_rec = b_dict[iid]
        b_text, b_field = get_user_facing_response(b_rec, b_label)

        # SLM profile: reuse cache if valid, otherwise re-evaluate
        if iid in slm_profiles_cache:
            slm_profile = slm_profiles_cache[iid]
        else:
            try:
                slm_profile = evaluate_full_answer_profile(prompt_text, s_text, max_tokens=500)
                if not slm_profile.get("parse_failed"):
                    slm_profiles_cache[iid] = slm_profile
            except ContextOverflowError as coe:
                print(f"  [OVERFLOW] SLM Profile context overflow for {iid}: {coe}")
                slm_profile = {"parse_failed": True, "context_overflow": True, "error": str(coe)}
            except Exception as pe:
                print(f"  [ERROR] SLM Profile evaluation failed during repair for {iid}: {pe}")
                slm_profile = {"parse_failed": True, "error": str(pe)}

        # LLM profile: reuse previous if it was already valid, otherwise re-evaluate
        old_llm = old_rec.get("llm_profile", {})
        if not old_llm.get("parse_failed") and "holistic" in old_llm:
            llm_profile = old_llm
        else:
            try:
                llm_profile = evaluate_full_answer_profile(prompt_text, b_text, max_tokens=500)
            except ContextOverflowError as coe:
                print(f"  [OVERFLOW] LLM Profile context overflow for {iid} vs {b_label}: {coe}")
                llm_profile = {"parse_failed": True, "context_overflow": True, "error": str(coe)}
            except Exception as pe:
                print(f"  [ERROR] LLM Profile evaluation failed during repair for {iid} vs {b_label}: {pe}")
                llm_profile = {"parse_failed": True, "error": str(pe)}

        # Pairwise Evaluations: with max_tokens=500
        try:
            pw_A_win, pw_A_fb, pw_A_dur, pw_A_data = evaluate_pairwise(prompt_text, s_text, b_text, max_tokens=500)
            pw_A = {"winner": pw_A_win, "feedback": pw_A_fb, "duration": pw_A_dur}
        except ContextOverflowError as coe:
            pw_A = {"winner": "UNKNOWN", "error": str(coe), "context_overflow": True, "parse_failed": True}
        except Exception as pe:
            pw_A = {"winner": "UNKNOWN", "error": str(pe), "parse_failed": True}

        try:
            pw_B_win, pw_B_fb, pw_B_dur, pw_B_data = evaluate_pairwise(prompt_text, b_text, s_text, max_tokens=500)
            pw_B = {"winner": pw_B_win, "feedback": pw_B_fb, "duration": pw_B_dur}
        except ContextOverflowError as coe:
            pw_B = {"winner": "UNKNOWN", "error": str(coe), "context_overflow": True, "parse_failed": True}
        except Exception as pe:
            pw_B = {"winner": "UNKNOWN", "error": str(pe), "parse_failed": True}

        parse_failed = bool(slm_profile.get("parse_failed") or llm_profile.get("parse_failed") or pw_A.get("parse_failed") or pw_B.get("parse_failed"))

        repaired_rec = {
            "item_id": iid,
            "split": "heldout",
            "track": track,
            "category": cat,
            "baseline": b_name,
            "baseline_label": b_label,
            "slm_field": s_field,
            "llm_field": b_field,
            "slm_len": len(s_text),
            "llm_len": len(b_text),
            "judge_model": JUDGE_MODEL,
            "gguf_sha256": GGUF_SHA256,
            "slm_profile": slm_profile,
            "llm_profile": llm_profile,
            "pairwise_A": pw_A,
            "pairwise_B": pw_B,
            "parse_failed": parse_failed,
            "timestamp": time.time(),
            "repair_of": f"{iid}::{b_name}",
            "attempt": 2
        }

        f_out.write(json.dumps(repaired_rec) + "\n")
        f_out.flush()
        latest_records[(iid, b_name)] = repaired_rec

        q_s = slm_profile.get("holistic", "?")
        q_l = llm_profile.get("holistic", "?")
        print(f"[REPAIR {rep_idx}/{len(track_a_repairs)}] {iid} ({cat}) vs {b_label} -> SLM: {q_s}/5 | LLM: {q_l}/5 | PW: A={pw_A.get('winner')}, B={pw_B.get('winner')} | Failed={parse_failed}")

    # Step 5B: Track B Pass (50 items x 2 baselines = 100 trials, max_tokens=500)
    track_b_items_list = [(iid, track, cat, it) for (iid, track, cat, it) in eval_items if track == "track_b"]
    print(f"\n" + "=" * 80)
    print(f"[TRACK B PASS] Starting Track B evaluation ({len(track_b_items_list)} items, {len(track_b_items_list)*2} comparisons)")
    print("=" * 80)

    for item_idx, (iid, track, cat, it) in enumerate(track_b_items_list, 1):
        prompt_text = format_eval_prompt(it)
        s_rec = slm_recs[iid]
        s_text, s_field = get_user_facing_response(s_rec, "Specialist SLM v1.3")

        # SLM profile: evaluate once per Track B item
        if iid in slm_profiles_cache:
            slm_profile = slm_profiles_cache[iid]
        else:
            try:
                slm_profile = evaluate_full_answer_profile(prompt_text, s_text, max_tokens=500)
                if not slm_profile.get("parse_failed"):
                    slm_profiles_cache[iid] = slm_profile
            except ContextOverflowError as coe:
                print(f"  [OVERFLOW] SLM Profile context overflow for {iid}: {coe}")
                slm_profile = {"parse_failed": True, "context_overflow": True, "error": str(coe)}
            except Exception as pe:
                print(f"  [ERROR] SLM Profile evaluation failed for {iid}: {pe}")
                slm_profile = {"parse_failed": True, "error": str(pe)}

        for b_name, b_dict, b_label in baselines:
            comp_key = (iid, b_name)
            if comp_key in latest_records and not latest_records[comp_key].get("parse_failed"):
                continue

            b_rec = b_dict[iid]
            b_text, b_field = get_user_facing_response(b_rec, b_label)

            try:
                llm_profile = evaluate_full_answer_profile(prompt_text, b_text, max_tokens=500)
            except ContextOverflowError as coe:
                print(f"  [OVERFLOW] LLM Profile context overflow for {iid} vs {b_label}: {coe}")
                llm_profile = {"parse_failed": True, "context_overflow": True, "error": str(coe)}
            except Exception as pe:
                print(f"  [ERROR] LLM Profile evaluation failed for {iid} vs {b_label}: {pe}")
                llm_profile = {"parse_failed": True, "error": str(pe)}

            try:
                pw_A_win, pw_A_fb, pw_A_dur, pw_A_data = evaluate_pairwise(prompt_text, s_text, b_text, max_tokens=500)
                pw_A = {"winner": pw_A_win, "feedback": pw_A_fb, "duration": pw_A_dur}
            except ContextOverflowError as coe:
                pw_A = {"winner": "UNKNOWN", "error": str(coe), "context_overflow": True, "parse_failed": True}
            except Exception as pe:
                pw_A = {"winner": "UNKNOWN", "error": str(pe), "parse_failed": True}

            try:
                pw_B_win, pw_B_fb, pw_B_dur, pw_B_data = evaluate_pairwise(prompt_text, b_text, s_text, max_tokens=500)
                pw_B = {"winner": pw_B_win, "feedback": pw_B_fb, "duration": pw_B_dur}
            except ContextOverflowError as coe:
                pw_B = {"winner": "UNKNOWN", "error": str(coe), "context_overflow": True, "parse_failed": True}
            except Exception as pe:
                pw_B = {"winner": "UNKNOWN", "error": str(pe), "parse_failed": True}

            parse_failed = bool(slm_profile.get("parse_failed") or llm_profile.get("parse_failed") or pw_A.get("parse_failed") or pw_B.get("parse_failed"))

            rec = {
                "item_id": iid,
                "split": "heldout",
                "track": track,
                "category": cat,
                "baseline": b_name,
                "baseline_label": b_label,
                "slm_field": s_field,
                "llm_field": b_field,
                "slm_len": len(s_text),
                "llm_len": len(b_text),
                "judge_model": JUDGE_MODEL,
                "gguf_sha256": GGUF_SHA256,
                "slm_profile": slm_profile,
                "llm_profile": llm_profile,
                "pairwise_A": pw_A,
                "pairwise_B": pw_B,
                "parse_failed": parse_failed,
                "timestamp": time.time(),
                "attempt": 1
            }

            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            latest_records[comp_key] = rec

            q_s = slm_profile.get("holistic", "?")
            q_l = llm_profile.get("holistic", "?")
            print(f"[TRACK B {item_idx}/{len(track_b_items_list)}] {iid} ({cat}) vs {b_label} -> SLM: {q_s}/5 | LLM: {q_l}/5 | PW: A={pw_A.get('winner')}, B={pw_B.get('winner')} | Failed={parse_failed}")

    f_out.close()

    # Step 6: Validity Audit & Publication Gate Verification
    print("\n" + "=" * 80)
    print("VALIDITY AUDIT & PUBLICATION GATE VERIFICATION (N=150 items per baseline)")
    print("=" * 80)

    from collections import Counter
    gate_passed = True
    audit_results = {}

    for b_name, b_dict, b_label in baselines:
        valid_items = 0
        failures_by_cause = Counter()
        unknown_pw_count = 0
        overflow_ids = []

        for iid, track, cat, it in eval_items:
            rec = latest_records.get((iid, b_name))
            if not rec:
                failures_by_cause["missing_record"] += 1
                continue

            pw_a_win = rec.get("pairwise_A", {}).get("winner")
            pw_b_win = rec.get("pairwise_B", {}).get("winner")
            if pw_a_win == "UNKNOWN" or pw_b_win == "UNKNOWN":
                unknown_pw_count += 1

            if rec.get("parse_failed"):
                sp = rec.get("slm_profile", {})
                lp = rec.get("llm_profile", {})
                pwa = rec.get("pairwise_A", {})
                pwb = rec.get("pairwise_B", {})
                err_str = sp.get("error", "") or lp.get("error", "") or pwa.get("error", "") or pwb.get("error", "")
                is_overflow = bool(sp.get("context_overflow") or lp.get("context_overflow") or pwa.get("context_overflow") or pwb.get("context_overflow") or "context_overflow" in err_str or "context size" in err_str)
                if is_overflow:
                    failures_by_cause["context_overflow"] += 1
                    overflow_ids.append(iid)
                elif "integer score" in err_str:
                    failures_by_cause["rubric_parse_error"] += 1
                elif "pairwise winner" in err_str:
                    failures_by_cause["pairwise_parse_error"] += 1
                else:
                    failures_by_cause["other_parse_error"] += 1
            else:
                valid_items += 1

        valid_pct = (valid_items / len(eval_items)) * 100.0
        audit_results[b_name] = {
            "valid_items": valid_items,
            "total_items": len(eval_items),
            "valid_pct": valid_pct,
            "failures": dict(failures_by_cause),
            "unknown_pw_count": unknown_pw_count,
            "overflow_ids": overflow_ids
        }

        print(f"\nBaseline: {b_label}")
        print(f"  Valid Items: {valid_items}/{len(eval_items)} ({valid_pct:.1f}%)")
        print(f"  Remaining Failures: {len(eval_items) - valid_items}")
        for cause, count in failures_by_cause.items():
            print(f"    - {cause}: {count}")
        if overflow_ids:
            print(f"    - Overflow IDs: {overflow_ids}")
        print(f"  Pairwise UNKNOWN count: {unknown_pw_count}/{len(eval_items)}")

        if valid_pct < 95.0:
            gate_passed = False
            print(f"  [GATE FAILED] {b_label} valid % ({valid_pct:.1f}%) is below required 95.0% threshold ($N \\ge 143/150$)!")
        else:
            print(f"  [GATE PASSED] {b_label} valid % ({valid_pct:.1f}%) meets >=95.0% requirement ($N \\ge 143/150$).")

    if not gate_passed:
        print("\n" + "!" * 80)
        print("PUBLICATION GATE ABORTED: At least one baseline did not meet >= 95% valid items.")
        print("Judge metrics will NOT be written to summary or published to reports.")
        print("!" * 80)
        return False

    # 7. Compute Final Metrics from latest valid records
    summary = evaluate_summary_metrics(eval_items, latest_records, baselines, slm_recs)

    # 8. Save Summary JSON
    with open(OUT_SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[SAVED] Summary metrics saved to {OUT_SUMMARY_FILE}")

    # 9. Write Mentor Tables
    write_mentor_tables(summary)

    print("\n" + "=" * 80)
    print("EVALUATION EXECUTION COMPLETE AND ALL GATES PASSED")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

