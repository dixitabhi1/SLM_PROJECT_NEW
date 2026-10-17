"""
scripts/run_judge_phase3.py

Phase 3: LLM-as-a-Judge Secondary Evaluation on Held-Out Splits (N=150).
- Judge Model: 'gemini-3.8-flash' via Google Generative Language API
- Family Separation: Google DeepMind (Hard Rule 8 satisfied)
- Authentication: 'x-goog-api-key' request header (zero keys in URL, logs, or records)
- Pinned Settings: temperature=0.0, thinkingBudget=0, JSON response type
- Scope: 150 held-out items x 2 baselines x 2 swap passes = 600 judge calls
  * Baseline 1: openai/gpt-oss-120b (Tool-equipped B1)
  * Baseline 2: qwen/qwen3.8-27b (Tool-equipped B1)
- Appends immutably to results/judge/judge_trials_raw_gemini38.jsonl
- Rate Limit Pacing: strictly <= 15 requests/minute (~4.2s interval)
- Clean Stop: on any 429 quota error, stops cleanly without tight-loop retry
- Execution Order: Track A (400 calls) first, intermediate report printed, then Track B (200 calls)
- Computes: Win/Draw/Loss, Quality Proximity (QP), Quality Difference (ΔQ), CQS,
  Swap Consistency, Validity Check (a) Concordance, Validity Check (b) False-Positive Rate,
  and response length correlations.
- Builds mentor table: docs/reports/mentor_protocol_table.md + .tex
"""

import os
import sys
import json
import time
import hashlib
import requests
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.run_heldout_evaluation import format_eval_prompt

JUDGE_MODEL = "gemini-3.8-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"

TRACK_A_PATH = os.path.join(REPO_ROOT, "data", "track_a_heldout_split.json")
TRACK_B_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_heldout_split.json")
EXPECTED_TRACK_A_HASH = "2314fca186a064ffcface62f42dc346bda9fdc73c5221852e8ecf5b19aafd629"
EXPECTED_TRACK_B_HASH = "075bf20d1daafdb89e3eef1e35271113766b9845cfb9d52e88301faa2919c0e1"

SLM_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "heldout_e3_v2_pipeline_records.jsonl")
GPT120B_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "b1_gpt120b_heldout_records.jsonl")
QWEN27B_RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "b1_qwen27b_heldout_records.jsonl")

OUT_DIR = os.path.join(REPO_ROOT, "results", "judge")
OUT_RAW_TRIALS = os.path.join(OUT_DIR, "judge_trials_raw_gemini38.jsonl")
OUT_SUMMARY_JSON = os.path.join(OUT_DIR, "judge_summary_metrics.json")
OUT_REPORTS_DIR = os.path.join(REPO_ROOT, "docs", "reports")
OUT_MENTOR_MD = os.path.join(OUT_REPORTS_DIR, "mentor_protocol_table.md")
OUT_MENTOR_TEX = os.path.join(OUT_REPORTS_DIR, "mentor_protocol_table.tex")
OUT_DOCS_MENTOR_MD = os.path.join(REPO_ROOT, "docs", "judge_mentor_table.md")
OUT_DOCS_MENTOR_TEX = os.path.join(REPO_ROOT, "docs", "judge_mentor_table.tex")

JUDGE_SYS_PROMPT = """You are an expert impartial judge evaluating two competing AI model answers to a user query.
Evaluate both answers on their merits without knowing which model produced which.
Rate each answer:
1. Holistic score: 1 to 10 (overall quality, usefulness, correctness)
2. Four criteria (each 1 to 5):
   - correctness (1-5)
   - completeness (1-5)
   - reasoning_quality (1-5)
   - formatting (1-5)

Output STRICT valid JSON object (must be a JSON dictionary, NOT a list) matching this schema:
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


class QuotaExceededError(Exception):
    def __init__(self, message: str, status_code: int = 429, response_text: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


def verify_heldout_hashes():
    ha = hashlib.sha256(open(TRACK_A_PATH, "rb").read()).hexdigest()
    hb = hashlib.sha256(open(TRACK_B_PATH, "rb").read()).hexdigest()
    assert ha == EXPECTED_TRACK_A_HASH, f"Track A hash mismatch: {ha}"
    assert hb == EXPECTED_TRACK_B_HASH, f"Track B hash mismatch: {hb}"
    print(f"[VERIFIED] Track A Held-Out Hash: {ha}")
    print(f"[VERIFIED] Track B Held-Out Hash: {hb}")


def get_user_facing_response(rec: dict, system: str) -> Tuple[str, str]:
    if "GPT" in system or "qwen" in system:
        if rec.get("full_output"):
            return str(rec["full_output"]), "full_output"
        return str(rec.get("output", "")), "output"
    else:
        if rec.get("full_output"):
            return str(rec["full_output"]), "full_output"
        fa = str(rec.get("final_answer", "")).strip()
        out = str(rec.get("output", "")).strip()
        if len(fa) < 50 and len(out) > len(fa):
            if fa in out:
                return out, "output"
            return f"{out}\n\n{fa}", "output + final_answer"
        if len(fa) >= len(out) and fa:
            return fa, "final_answer"
        return out or fa, "output"


def call_gemini_judge(prompt_text: str, ans1_text: str, ans2_text: str, api_key: str, max_retries: int = 3) -> Tuple[Dict[str, Any], float]:
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }
    user_content = f"User Query:\n{prompt_text}\n\nAnswer 1:\n{ans1_text}\n\nAnswer 2:\n{ans2_text}\n\nRespond with a single JSON object:"
    payload = {
        "system_instruction": {"parts": [{"text": JUDGE_SYS_PROMPT}]},
        "contents": [{"parts": [{"text": user_content}]}],
        "generationConfig": {
            "temperature": 0.0,
            "response_mime_type": "application/json",
            "thinkingConfig": {"thinkingBudget": 0}
        }
    }

    for attempt in range(max_retries):
        t0 = time.time()
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=35)
            dur = time.time() - t0
            if resp.status_code == 200:
                data = resp.json()
                data["_request_duration"] = dur
                return data, dur
            elif resp.status_code == 429:
                raise QuotaExceededError(f"HTTP 429 Quota Exceeded / Rate Limit: {resp.text[:300]}", status_code=429, response_text=resp.text)
            elif resp.status_code in (500, 503):
                wait_time = (attempt + 1) * 6.0
                print(f"    [HTTP {resp.status_code}] Transient server error, backing off {wait_time:.1f}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise RuntimeError(f"Gemini API returned status {resp.status_code}: {resp.text[:200]}")
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Gemini API request failed after {max_retries} attempts: {type(e).__name__}")
            time.sleep((attempt + 1) * 4.0)

    raise RuntimeError("Gemini API call exhausted retries.")


def parse_judge_output(content_str: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(content_str)
        if isinstance(parsed, dict):
            return parsed
        elif isinstance(parsed, list):
            merged = {}
            for elem in parsed:
                if isinstance(elem, dict):
                    merged.update(elem)
            return merged
    except Exception:
        pass
    return {"raw": content_str}


def extract_trial_metrics(parsed: Dict[str, Any], pass_label: str) -> Dict[str, Any]:
    ans1_dict = parsed.get("answer_1", {}) if isinstance(parsed.get("answer_1"), dict) else {}
    ans2_dict = parsed.get("answer_2", {}) if isinstance(parsed.get("answer_2"), dict) else {}

    h1 = float(ans1_dict.get("holistic", 5))
    h2 = float(ans2_dict.get("holistic", 5))

    def get_cqs(d: dict) -> float:
        crit = [float(d.get(k, 3)) for k in ("correctness", "completeness", "reasoning_quality", "formatting")]
        return sum(crit) / len(crit)

    cqs1 = get_cqs(ans1_dict)
    cqs2 = get_cqs(ans2_dict)

    raw_winner = str(parsed.get("winner", "Draw")).strip().lower()

    if pass_label == "A":
        slm_h, llm_h = h1, h2
        slm_cqs, llm_cqs = cqs1, cqs2
        if "answer 1" in raw_winner or raw_winner == "answer 1":
            winner_sys = "SLM"
        elif "answer 2" in raw_winner or raw_winner == "answer 2":
            winner_sys = "LLM"
        else:
            winner_sys = "Draw"
    else:
        slm_h, llm_h = h2, h1
        slm_cqs, llm_cqs = cqs2, cqs1
        if "answer 1" in raw_winner or raw_winner == "answer 1":
            winner_sys = "LLM"
        elif "answer 2" in raw_winner or raw_winner == "answer 2":
            winner_sys = "SLM"
        else:
            winner_sys = "Draw"

    return {
        "h1": h1, "h2": h2,
        "cqs1": cqs1, "cqs2": cqs2,
        "slm_h": slm_h, "llm_h": llm_h,
        "slm_cqs": slm_cqs, "llm_cqs": llm_cqs,
        "winner_sys": winner_sys,
        "raw_winner": parsed.get("winner", "Draw"),
        "explanation": parsed.get("explanation", "")
    }


def compute_bootstrap_ci(data_arr: np.ndarray, num_resamples: int = 10000, seed: int = 42) -> Tuple[float, float, float]:
    if len(data_arr) == 0:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(seed)
    mean_val = float(np.mean(data_arr))
    boot_means = rng.choice(data_arr, size=(num_resamples, len(data_arr)), replace=True).mean(axis=1)
    ci_low = float(np.percentile(boot_means, 2.5))
    ci_high = float(np.percentile(boot_means, 97.5))
    return mean_val, ci_low, ci_high


def evaluate_metrics(
    eval_items: List[Tuple[str, str, str, dict]],
    index_trials: Dict[Tuple[str, str, str], dict],
    baselines: List[Tuple[str, dict, str]],
    slm_recs: Dict[str, dict],
    title: str = "Evaluation Summary"
) -> Dict[str, Any]:
    n_items = len(eval_items)
    print("\n" + "=" * 80)
    print(f"{title} (N={n_items} items, {n_items * 4} judge trials)")
    print("=" * 80)

    summary: Dict[str, Any] = {
        "title": title,
        "judge_model": JUDGE_MODEL,
        "n_items": n_items,
        "comparisons": {}
    }

    length_score_data: Dict[str, list] = {
        "slm_lens": [], "slm_scores": [],
        "gpt_lens": [], "gpt_scores": [],
        "qwen_lens": [], "qwen_scores": []
    }

    for b_name, b_dict, b_label in baselines:
        slm_wins, llm_wins, draws = 0, 0, 0
        swap_agreements = 0
        disagreements = []
        wrong_answers = []
        qps = []
        delta_qs = []
        slm_cqs_list = []
        llm_cqs_list = []

        cat_data: Dict[str, Dict[str, list]] = {}

        for iid, track, cat, it in eval_items:
            rec_A = index_trials.get((iid, b_name, "A"))
            rec_B = index_trials.get((iid, b_name, "B"))
            if not rec_A or not rec_B:
                continue

            mA = rec_A["trial_metrics"]
            mB = rec_B["trial_metrics"]

            q_s = (mA["slm_h"] + mB["slm_h"]) / 2.0
            q_l = (mA["llm_h"] + mB["llm_h"]) / 2.0

            cqs_s = (mA["slm_cqs"] + mB["slm_cqs"]) / 2.0
            cqs_l = (mA["llm_cqs"] + mB["llm_cqs"]) / 2.0

            slm_cqs_list.append(cqs_s)
            llm_cqs_list.append(cqs_l)

            qp = 1.0 - (abs(q_s - q_l) / 9.0)
            dq = q_s - q_l
            qps.append(qp)
            delta_qs.append(dq)

            if cat not in cat_data:
                cat_data[cat] = {"qps": [], "dqs": [], "slm_w": 0, "llm_w": 0, "draw": 0}
            cat_data[cat]["qps"].append(qp)
            cat_data[cat]["dqs"].append(dq)

            if q_s > q_l:
                slm_wins += 1
                cat_data[cat]["slm_w"] += 1
            elif q_l > q_s:
                llm_wins += 1
                cat_data[cat]["llm_w"] += 1
            else:
                draws += 1
                cat_data[cat]["draw"] += 1

            if mA["winner_sys"] == mB["winner_sys"]:
                swap_agreements += 1

            s_len = rec_A["answer_1_len"]
            l_len = rec_A["answer_2_len"]
            length_score_data["slm_lens"].append(s_len)
            length_score_data["slm_scores"].append(q_s)
            if "120b" in b_name:
                length_score_data["gpt_lens"].append(l_len)
                length_score_data["gpt_scores"].append(q_l)
            else:
                length_score_data["qwen_lens"].append(l_len)
                length_score_data["qwen_scores"].append(q_l)

            s_pass = bool(slm_recs.get(iid, {}).get("passed", False))
            l_pass = bool(b_dict.get(iid, {}).get("passed", False))

            if s_pass != l_pass:
                ak_winner = "SLM" if s_pass else "LLM"
                j_winner = "SLM" if q_s > q_l else ("LLM" if q_l > q_s else "Draw")
                concordant = (ak_winner == j_winner)
                disagreements.append({"item_id": iid, "ak_winner": ak_winner, "j_winner": j_winner, "concordant": concordant})

            if not s_pass:
                wrong_answers.append(("SLM", iid, q_s))
            if not l_pass:
                wrong_answers.append(("LLM", iid, q_l))

        evaluated_count = len(qps)
        if evaluated_count == 0:
            print(f"No completed trials for {b_label}")
            continue

        qp_mean, qp_low, qp_high = compute_bootstrap_ci(np.array(qps))
        dq_mean, dq_low, dq_high = compute_bootstrap_ci(np.array(delta_qs))
        mean_cqs_s = float(np.mean(slm_cqs_list))
        mean_cqs_l = float(np.mean(llm_cqs_list))

        swap_consist_pct = (swap_agreements / evaluated_count) * 100.0
        eff_win_rate = ((slm_wins + draws) / evaluated_count) * 100.0

        if disagreements:
            conc_count = sum(1 for d in disagreements if d["concordant"])
            conc_rate = (conc_count / len(disagreements)) * 100.0
        else:
            conc_count = 0
            conc_rate = 100.0

        if wrong_answers:
            false_high = sum(1 for _, _, q in wrong_answers if q >= 8.0)
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
                "delta_q": {"mean": c_dq_m, "ci_low": c_dq_l, "ci_high": c_dq_h}
            }

        b_summary = {
            "baseline": b_name,
            "baseline_label": b_label,
            "evaluated_items": evaluated_count,
            "slm_wins": slm_wins,
            "llm_wins": llm_wins,
            "draws": draws,
            "effective_win_rate": eff_win_rate,
            "qp": {"mean": qp_mean, "ci_low": qp_low, "ci_high": qp_high},
            "delta_q": {"mean": dq_mean, "ci_low": dq_low, "ci_high": dq_high},
            "mean_slm_cqs": mean_cqs_s,
            "mean_llm_cqs": mean_cqs_l,
            "swap_consistency": swap_consist_pct,
            "check_a_concordance": {
                "total_disagreements": len(disagreements),
                "concordant_items": conc_count,
                "concordance_rate": conc_rate,
                "passed_gate": conc_rate >= 80.0
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
        print(f"  Outcome: SLM Wins: {slm_wins} ({slm_wins/evaluated_count*100:.1f}%) | Draws: {draws} ({draws/evaluated_count*100:.1f}%) | LLM Wins: {llm_wins} ({llm_wins/evaluated_count*100:.1f}%) | Eff. Win Rate: {eff_win_rate:.1f}%")
        print(f"  Quality Proximity (QP): {qp_mean:.4f} [95% CI: {qp_low:.4f}, {qp_high:.4f}]")
        print(f"  Quality Difference (Delta Q): {dq_mean:+.4f} [95% CI: {dq_low:+.4f}, {dq_high:+.4f}]")
        print(f"  CQS: SLM {mean_cqs_s:.2f} vs LLM {mean_cqs_l:.2f}")
        print(f"  Swap Consistency: {swap_consist_pct:.1f}% ({swap_agreements}/{evaluated_count})")
        print(f"  Check (a) Concordance: {conc_rate:.1f}% ({conc_count}/{len(disagreements)}) -> {'PASSED (>=80%)' if conc_rate >= 80.0 else 'FAILED (<80%)'}")
        print(f"  Check (b) False High Score (>=8.0 on Wrong): {false_high_rate:.1f}% ({false_high}/{len(wrong_answers)})")
        print("  Per-Category Breakdown (SLM Wins / Draws / LLM Wins | Delta Q [95% CI]):")
        for c, cdata in per_cat_summary.items():
            print(f"    - {c:32s}: {cdata['slm_wins']:2d} / {cdata['draws']:2d} / {cdata['llm_wins']:2d} | Delta Q: {cdata['delta_q']['mean']:+.3f} [{cdata['delta_q']['ci_low']:+.3f}, {cdata['delta_q']['ci_high']:+.3f}]")

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
        qp = f"{c['qp']['mean']:.3f} [{c['qp']['ci_low']:.3f}, {c['qp']['ci_high']:.3f}]"
        s_cqs = f"{c['mean_slm_cqs']:.2f}"
        l_cqs = f"{c['mean_llm_cqs']:.2f}"
        return f"| {exp} | {slm_ft} | {skill_m} | {llm_ft} | {lw} | {sw} | {dr} | {qp} | {s_cqs} | {l_cqs} |\n"

    md = """# Mentor Protocol Table: Secondary Evaluation Layer (LLM-as-a-Judge)

**Judge Model:** `gemini-3.8-flash` (Google DeepMind, Hard Rule 8 satisfied)  
**Evaluation Scope:** Held-Out Split ($N=150$: Track A $N=100$, Track B $N=50$), position-swap testing ($2 \\times 150 = 300$ calls per baseline).  
**Protocol Invariants:** Temperature 0.0, zero thinking tokens (`thinkingBudget: 0`), strict JSON response schema. Key transmitted exclusively via `x-goog-api-key` header.

| Experiment | SLM Fine-Tuning Configuration | Skill-Matching SLM | LLM Fine-Tuning | LLM Wins | SLM Wins | Draws | Quality Proximity | SLM CQS | LLM CQS |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
"""
    md += format_row_md("E1 (vs GPT-OSS-120B B1)", "None (Base Phi-4-mini 3.82B, prompt/tool-only)", "Single-model pool (no router)", "None (Frozen API B1)", c_120)
    md += format_row_md("E1 (vs qwen/qwen3.8-27b B1)", "None (Base Phi-4-mini 3.82B, prompt/tool-only)", "Single-model pool (no router)", "None (Frozen API B1)", c_27)
    md += "| E2 | Query-dependent LoRA adapters (SQL specialist) | Single-model pool | None | — | — | — | Not run (training pipeline prepared, run pending owner sign-off) | — | — |\n"
    md += "| E3 | All specialist SLMs fine-tuned | Multi-SLM pool | None | — | — | — | Not run (mentor multi-model pool not configured; repo E3 was compute-in-code) | — | — |\n"
    md += "| E4-A | None | Skill-matching SLM (router) | None | — | — | — | Not run as specified (repo E4 learned router rejected on dev headroom gate) | — | — |\n"
    md += "| E4-B | Fine-tuned skill matcher | Fine-tuned router | None | — | — | — | Not run (repo E4b retry failed dev regression gate) | — | — |\n"

    md += """
\\*\\*Footnote:\\*\\* Mapping to repo experiments: Our frozen pipeline v1.3 corresponds to mentor E1 (no fine-tuning, autonomous tool execution). Our repo "E3" designates compute-in-code routing (accepted into v1.3), not all-SLM fine-tuning. Our repo "E4" designates learned router experiments (E4 and E4b, both rejected at dev gates). The active specialist pool is a single 3.82B parameter model (Phi-4-mini) with specialized execution tools, not a 5–8B multi-model pool.
"""

    with open(OUT_MENTOR_MD, "w", encoding="utf-8") as f:
        f.write(md)
    with open(OUT_DOCS_MENTOR_MD, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Saved Mentor Table Markdown to: {OUT_MENTOR_MD} and {OUT_DOCS_MENTOR_MD}")

    def format_row_tex(exp, slm_ft, skill_m, llm_ft, c):
        if not c or "slm_wins" not in c:
            return f"{exp} & {slm_ft} & {skill_m} & {llm_ft} & — & — & — & Not run & — & — \\\\\n"
        n = c["evaluated_items"]
        lw = f"{c['llm_wins']}"
        sw = f"{c['slm_wins']}"
        dr = f"{c['draws']}"
        qp = f"{c['qp']['mean']:.3f} [{c['qp']['ci_low']:.3f}, {c['qp']['ci_high']:.3f}]".replace('[', '$[').replace(']', ']$')
        s_cqs = f"{c['mean_slm_cqs']:.2f}"
        l_cqs = f"{c['mean_llm_cqs']:.2f}"
        return f"{exp} & {slm_ft} & {skill_m} & {llm_ft} & {lw} & {sw} & {dr} & {qp} & {s_cqs} & {l_cqs} \\\\\n"

    tex = """% Mentor Protocol Table: Secondary Evaluation Layer (LLM-as-a-Judge)
% Generated from results/judge/judge_trials_raw_gemini38.jsonl (immutable raw records)
\\begin{table*}[t]
\\centering
\\small
\\caption{\\textbf{Mentor Protocol Evaluation Matrix: LLM-as-a-Judge Secondary Layer} ($N=150$, Held-Out Split). Pairwise comparisons conducted with order-swapped consistency testing ($2 \\times 150 = 300$ calls per baseline) using \\texttt{gemini-3.8-flash} ($T=0.0$, zero thinking tokens). Quality Proximity is defined as $QP = 1 - |Q_S - Q_L|/9$; brackets denote empirical 95\\% bootstrap percentile confidence intervals ($B=10000$). Primary answer-key correctness remains the definitive metric.}
\\label{tab:mentor_protocol_results}
\\begin{tabular}{llcccccccc}
\\toprule
\\textbf{Experiment} & \\textbf{SLM Fine-Tuning} & \\textbf{Skill-Match} & \\textbf{LLM FT} & \\textbf{LLM Win} & \\textbf{SLM Win} & \\textbf{Draw} & \\textbf{Quality Proximity} & \\textbf{SLM CQS} & \\textbf{LLM CQS} \\\\
\\midrule
"""
    tex += format_row_tex("E1 (vs 120B B1)", "None (Phi-4-mini base)", "Single SLM", "None", c_120)
    tex += format_row_tex("E1 (vs 27B B1)", "None (Phi-4-mini base)", "Single SLM", "None", c_27)
    tex += "E2 & Query-dep. LoRA (SQL) & Single SLM & None & — & — & — & Not run & — & — \\\\\n"
    tex += "E3 & All specialists FT & Multi-SLM & None & — & — & — & Not run & — & — \\\\\n"
    tex += "E4-A & None & Skill-matching & None & — & — & — & Not run & — & — \\\\\n"
    tex += "E4-B & FT skill matcher & FT router & None & — & — & — & Not run & — & — \\\\\n"
    tex += """\\bottomrule
\\end{tabular}
\\begin{tablenotes}
\\small
\\item \\textbf{Note on Experiment Mapping:} Frozen pipeline v1.3 corresponds to mentor E1 (no fine-tuning, autonomous tool execution). Repo E3 designates compute-in-code routing (accepted into v1.3), not all-SLM fine-tuning. Repo E4 designates learned router experiments (rejected at dev gates). The specialist pool is a single 3.82B model with tools, not a 5–8B multi-model pool.
\\end{tablenotes}
\\end{table*}
"""

    with open(OUT_MENTOR_TEX, "w", encoding="utf-8") as f:
        f.write(tex)
    with open(OUT_DOCS_MENTOR_TEX, "w", encoding="utf-8") as f:
        f.write(tex)
    print(f"Saved Mentor Table LaTeX to: {OUT_MENTOR_TEX} and {OUT_DOCS_MENTOR_TEX}")


def main():
    load_dotenv()
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("[ERROR] GEMINI_API_KEY not found in environment.", file=sys.stderr)
        sys.exit(1)

    verify_heldout_hashes()
    os.makedirs(OUT_DIR, exist_ok=True)

    ta_items = json.load(open(TRACK_A_PATH, "r", encoding="utf-8"))
    tb_items = json.load(open(TRACK_B_PATH, "r", encoding="utf-8"))

    ta_items_list = []
    for it in ta_items:
        iid = it.get("item_id") or it.get("original_id")
        st = it.get("stratum")
        tt = it.get("task_type")
        solv = it.get("solvability")
        cat = tt if st == "atomic" else f"compound_{solv}"
        ta_items_list.append((iid, "Track A", cat, it))

    tb_items_list = []
    for it in tb_items:
        iid = it.get("question_id") or it.get("item_id")
        tb_items_list.append((iid, "Track B", "hypergrid", it))

    all_items = ta_items_list + tb_items_list
    assert len(all_items) == 150, f"Expected 150 heldout items, got {len(all_items)}"
    print(f"Loaded {len(ta_items_list)} Track A items and {len(tb_items_list)} Track B items.")

    slm_recs = {json.loads(l)["item_id"]: json.loads(l) for l in open(SLM_RECORDS_PATH, "r", encoding="utf-8")}
    gpt_recs = {json.loads(l)["item_id"]: json.loads(l) for l in open(GPT120B_RECORDS_PATH, "r", encoding="utf-8")}
    qwen_recs = {json.loads(l)["item_id"]: json.loads(l) for l in open(QWEN27B_RECORDS_PATH, "r", encoding="utf-8")}

    completed_trials = set()
    index_trials: Dict[Tuple[str, str, str], dict] = {}
    if os.path.exists(OUT_RAW_TRIALS):
        with open(OUT_RAW_TRIALS, "r", encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    try:
                        d = json.loads(l)
                        key = (d["item_id"], d["baseline"], d["pass"])
                        completed_trials.add(key)
                        index_trials[key] = d
                    except Exception:
                        pass
    print(f"Existing completed trials in {OUT_RAW_TRIALS}: {len(completed_trials)} / 600")

    baselines = [
        ("openai/gpt-oss-120b", gpt_recs, "GPT-OSS-120B B1"),
        ("qwen/qwen3.8-27b", qwen_recs, "qwen/qwen3.8-27b B1")
    ]
    passes = ["A", "B"]

    ta_planned = []
    for iid, track, cat, it in ta_items_list:
        for b_name, b_dict, b_label in baselines:
            for p in passes:
                ta_planned.append((iid, track, cat, it, b_name, b_dict, b_label, p))

    tb_planned = []
    for iid, track, cat, it in tb_items_list:
        for b_name, b_dict, b_label in baselines:
            for p in passes:
                tb_planned.append((iid, track, cat, it, b_name, b_dict, b_label, p))

    assert len(ta_planned) == 400, f"Expected 400 Track A planned trials, got {len(ta_planned)}"
    assert len(tb_planned) == 200, f"Expected 200 Track B planned trials, got {len(tb_planned)}"

    print(f"\n{'='*80}")
    print(f"STARTING EXECUTION: Track A First (400 Calls), then Track B (200 Calls)")
    print(f"Judge Model: {JUDGE_MODEL} | Target File: {OUT_RAW_TRIALS}")
    print(f"Rate Pacing: >= 4.20s per call (<= 14.3 requests/minute)")
    print(f"{'='*80}")

    t_start = time.time()
    calls_made_this_run = 0

    def run_trial_batch(batch, batch_name):
        nonlocal calls_made_this_run
        print(f"\n--- Running {batch_name} ({len(batch)} trials) ---")
        with open(OUT_RAW_TRIALS, "a", encoding="utf-8") as f_out:
            for idx, (iid, track, cat, it, b_name, b_dict, b_label, p) in enumerate(batch, 1):
                key = (iid, b_name, p)
                if key in completed_trials:
                    continue

                calls_made_this_run += 1
                prompt_text = format_eval_prompt(it)
                s_rec = slm_recs[iid]
                b_rec = b_dict[iid]

                s_text, s_field = get_user_facing_response(s_rec, "Specialist SLM v1.3")
                b_text, b_field = get_user_facing_response(b_rec, b_label)

                if p == "A":
                    ans1_text, ans1_sys, ans1_field, ans1_len = s_text, "Specialist SLM v1.3", s_field, len(s_text)
                    ans2_text, ans2_sys, ans2_field, ans2_len = b_text, b_label, b_field, len(b_text)
                else:
                    ans1_text, ans1_sys, ans1_field, ans1_len = b_text, b_label, b_field, len(b_text)
                    ans2_text, ans2_sys, ans2_field, ans2_len = s_text, "Specialist SLM v1.3", s_field, len(s_text)

                t0 = time.time()
                res_data, dur = call_gemini_judge(prompt_text, ans1_text, ans2_text, gemini_key)
                model_ver = res_data.get("modelVersion", JUDGE_MODEL)
                content_str = res_data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = parse_judge_output(content_str)
                t_metrics = extract_trial_metrics(parsed, p)

                u_meta = res_data.get("usageMetadata", {})
                tokens = {
                    "prompt_tokens": u_meta.get("promptTokenCount", 0),
                    "completion_tokens": u_meta.get("candidatesTokenCount", 0),
                    "total_tokens": u_meta.get("totalTokenCount", 0)
                }

                record = {
                    "item_id": iid,
                    "split": "heldout",
                    "track": track,
                    "category": cat,
                    "baseline": b_name,
                    "baseline_label": b_label,
                    "pass": p,
                    "answer_1_system": ans1_sys,
                    "answer_2_system": ans2_sys,
                    "answer_1_field": ans1_field,
                    "answer_2_field": ans2_field,
                    "answer_1_len": ans1_len,
                    "answer_2_len": ans2_len,
                    "judge_model": JUDGE_MODEL,
                    "model_version": model_ver,
                    "tokens": tokens,
                    "duration": dur,
                    "judge_output_raw": content_str,
                    "judge_output_parsed": parsed,
                    "trial_metrics": t_metrics,
                    "timestamp": time.time()
                }

                f_out.write(json.dumps(record) + "\n")
                f_out.flush()
                completed_trials.add(key)
                index_trials[key] = record

                elapsed = time.time() - t_start
                pace = elapsed / calls_made_this_run
                rem_trials = 600 - len(completed_trials)
                est_rem = rem_trials * pace

                if calls_made_this_run % 5 == 0 or calls_made_this_run == 1 or len(completed_trials) == 600:
                    print(f"[{len(completed_trials)}/600] ({len(completed_trials)/6.0:.1f}%) | {iid} vs {b_label.split()[0]} Pass {p} | Win: {t_metrics['winner_sys']} | S: {t_metrics['slm_h']:.0f} L: {t_metrics['llm_h']:.0f} | Pace: {pace:.2f}s | Est Rem: {est_rem/60:.1f}m")

                # Strict Pacing: maintain <= 14.3 requests/minute (>= 4.2s interval)
                time_to_sleep = max(0.2, 4.2 - dur)
                time.sleep(time_to_sleep)

    try:
        # Step 1: Track A
        run_trial_batch(ta_planned, "Track A (400 Trials)")
        print("\n" + "*" * 80)
        print("TRACK A COMPLETE: Computing Intermediate Track A Metrics...")
        print("*" * 80)
        ta_summary = evaluate_metrics(ta_items_list, index_trials, baselines, slm_recs, title="Track A Intermediate Evaluation (N=100)")

        # Step 2: Track B
        run_trial_batch(tb_planned, "Track B (200 Trials)")
        print("\n" + "*" * 80)
        print("TRACK B COMPLETE: All 600 Trials Finished!")
        print("*" * 80)

    except QuotaExceededError as qe:
        print("\n" + "!" * 80)
        print(f"[QUOTA LIMIT HIT] STOPPING CLEANLY PER INSTRUCTIONS: {qe}")
        print(f"Calls completed this run: {calls_made_this_run}")
        print(f"Total trials saved in {OUT_RAW_TRIALS}: {len(completed_trials)} / 600")
        print("!" * 80)

    # Full Evaluation & Mentor Tables
    print("\nComputing Complete Held-Out Evaluation Metrics across all available items...")
    final_summary = evaluate_metrics(all_items, index_trials, baselines, slm_recs, title="Held-Out Secondary Evaluation (N=150)")

    with open(OUT_SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, indent=2)
    print(f"Saved final summary metrics to: {OUT_SUMMARY_JSON}")

    write_mentor_tables(final_summary)

    print("\n" + "=" * 80)
    print("PHASE 3 EXECUTION FINISHED")
    print(f"Total calls made this execution: {calls_made_this_run}")
    print(f"Total completed trials in {OUT_RAW_TRIALS}: {len(completed_trials)} / 600")
    print("=" * 80)


if __name__ == "__main__":
    main()
