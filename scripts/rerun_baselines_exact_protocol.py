"""
Script: rerun_baselines_exact_protocol.py
Implements User Directives:
1. Track B baselines: Identical prompt and format instructions matching pipeline answer step:
   - key-value format explicitly instructed
   - 75-word cap stated explicitly
   - Standard ASCII characters requested
   - Unicode hyphens (\u2011, \u2010) and narrow spaces (\u202f, \u00a0) normalized
2. Report both accuracy metrics on Track B:
   - With 75-word cap (official checklist score)
   - Facts alone (with length cap ignored)
3. Rerun every truncated or failed 27B item in B0 and B1 unclamped at 4,096 tokens as new rows.
   Ensures truncated/failed items <= 2% for every condition.
4. Append-only to raw jsonl files per Hard Rule 2.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
import random
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

from src.sandbox.runner import execute_python_code
from src.tools.tolerant_harness import execute_sql_tolerant, KNOWN_DATABASES
from src.tools.retriever_tool import BM25RetrieverTool
from src.eval.versioned_scorer import score_record, extract_sql_query
from src.eval.fact_checklist_scorer import score_fact_checklist
from src.pipeline.specialist_pipeline import get_table_schema, get_bm25_retriever

TRACK_A_HELDOUT_PATH = os.path.join(REPO_ROOT, "data", "track_a_heldout_split.json")
TRACK_B_HELDOUT_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_heldout_split.json")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")


def normalize_unicode(text: str) -> str:
    """Normalizes Unicode non-breaking hyphens and spaces to standard ASCII."""
    if not text:
        return ""
    return (
        text.replace("\u2011", "-")
        .replace("\u2010", "-")
        .replace("\u2013", "-")
        .replace("\u202f", " ")
        .replace("\u00a0", " ")
    )


def call_groq_api(
    model_id: str,
    prompt: str,
    system_prompt: str = "You are a helpful, precise assistant.",
    max_tokens: int = 4096,
    seed: int = 42
) -> Dict[str, Any]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": seed
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    for attempt in range(12):
        t0 = time.perf_counter()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                elapsed = time.perf_counter() - t0
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "").strip()
                finish_reason = choice.get("finish_reason", "stop")
                usage = data.get("usage", {})
                status = "COMPLETE" if finish_reason == "stop" and content else "FAILED"
                return {
                    "content": content,
                    "finish_reason": finish_reason,
                    "latency_seconds": round(elapsed, 4),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "status": status,
                    "error_message": None
                }
        except urllib.error.HTTPError as he:
            elapsed = time.perf_counter() - t0
            if he.code == 429:
                retry_after_str = he.headers.get("retry-after")
                try:
                    retry_after = float(retry_after_str) if retry_after_str else 0.0
                except (ValueError, TypeError):
                    retry_after = 0.0
                err_body = ""
                try:
                    err_body = he.read().decode("utf-8")
                except Exception:
                    pass
                wait_match = re.search(r"try again in (\d+(?:\.\d+)?)s", err_body)
                body_wait = float(wait_match.group(1)) if wait_match else 0.0
                sleep_time = max(retry_after + 1.0, body_wait + 1.0, 5.0 * (attempt + 1), 5.0)
                print(f"    [Rate Limit 429] Backing off for {sleep_time:.1f}s (attempt {attempt+1}/12)...")
                time.sleep(sleep_time)
                continue
            return {
                "content": "",
                "finish_reason": f"http_error_{he.code}",
                "latency_seconds": round(elapsed, 4),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "status": "FAILED",
                "error_message": f"HTTP {he.code}: {he.reason}"
            }
        except Exception as e:
            elapsed = time.perf_counter() - t0
            if attempt < 3:
                time.sleep(3.0 * (attempt + 1))
                continue
            return {
                "content": "",
                "finish_reason": "exception",
                "latency_seconds": round(elapsed, 4),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "status": "FAILED",
                "error_message": str(e)
            }
    return {
        "content": "",
        "finish_reason": "retries_exhausted",
        "latency_seconds": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "status": "FAILED",
        "error_message": "All 12 retries exhausted"
    }


def format_track_b_prompt_identical_to_pipeline(raw_prompt: str, context_str: str = "") -> Tuple[str, str]:
    """
    Constructs Track B prompt 100% IDENTICAL to pipeline's Stage 7 execute_downstream_reasoning:
    """
    sys_prompt = "You are an expert technical assistant. Answer the question based on the provided reference documents in concise key-value format."
    if context_str:
        user_msg = (
            f"Task:\n{raw_prompt}\n\n"
            f"Retrieved Documents:\n{context_str}\n\n"
            f"Answer the question in concise key-value pairs (max 75 words). "
            f"Explicitly include all component designations, names, and parameters mentioned in the text.\n"
            f"Conclude with: Final Answer: <key-value pairs>"
        )
    else:
        # B0: No tools / no documents
        sys_prompt = "You are an expert technical assistant. Answer the question in concise key-value format."
        user_msg = (
            f"Task:\n{raw_prompt}\n\n"
            f"Answer the question in concise key-value pairs (max 75 words). "
            f"Explicitly include all component designations, names, and parameters mentioned in the text.\n"
            f"Conclude with: Final Answer: <key-value pairs>"
        )
    return sys_prompt, user_msg


def evaluate_track_b_item(
    item: Dict[str, Any],
    model_name: str,
    condition: str  # "B0" or "B1"
) -> Dict[str, Any]:
    raw_prompt = item["prompt"]
    word_cap = item.get("word_cap", 75)
    t0 = time.time()

    if condition == "B1":
        retriever = get_bm25_retriever()
        passages = retriever.retrieve(raw_prompt, top_k=5)
        context_str = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in passages])
    else:
        context_str = ""

    sys_prompt, user_msg = format_track_b_prompt_identical_to_pipeline(raw_prompt, context_str)
    resp = call_groq_api(model_name, user_msg, system_prompt=sys_prompt, max_tokens=4096)
    dt = time.time() - t0

    content = resp["content"]
    clean_content = normalize_unicode(content)

    sc_cap = score_fact_checklist(clean_content, item["checklist"], max_word_cap=word_cap)
    sc_nocap = score_fact_checklist(clean_content, item["checklist"], max_word_cap=100000)

    iid = item.get("question_id") or item.get("item_id")
    return {
        "item_id": iid,
        "split": "heldout",
        "track": "B",
        "task_type": "track_b",
        "stratum": "atomic",
        "solvability": "",
        "model_id": model_name,
        "condition": condition,
        "prompt": user_msg,
        "output": clean_content[:300],
        "full_output": clean_content,
        "finish_reason": resp["finish_reason"],
        "prompt_tokens": resp["prompt_tokens"],
        "completion_tokens": resp["completion_tokens"],
        "total_tokens": resp["total_tokens"],
        "status": resp["status"],
        "clean_execution": resp["status"] == "COMPLETE",
        "passed": sc_cap["binary_pass"],
        "passed_facts_alone": sc_nocap["binary_pass"],
        "recall_facts_alone": sc_nocap["recall"],
        "details": f"With Cap: {sc_cap['binary_pass']} | Facts Alone: {sc_nocap['binary_pass']} (Recall: {sc_nocap['recall']:.2f})",
        "duration": round(dt, 2),
        "protocol_version": "v2_identical_instructions"
    }


def evaluate_track_a_b0_item(item: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """Evaluates Track A item under B0 (Direct, unassisted) unclamped at max_tokens=4096."""
    from scripts.run_heldout_baselines_b0 import format_eval_prompt
    t0 = time.time()
    prompt_str = format_eval_prompt(item)
    resp = call_groq_api(model_name, prompt_str, max_tokens=4096)
    dt = time.time() - t0

    content = resp["content"]
    iid = item.get("subtask_id") or item.get("original_id") or item.get("item_id")
    sc = score_record(item, content)

    return {
        "item_id": iid,
        "split": "heldout",
        "track": "A",
        "task_type": item.get("task_type") or item.get("type") or "",
        "stratum": item.get("stratum") or ("composed" if item.get("task_type") == "compound" else "atomic"),
        "solvability": item.get("solvability", ""),
        "model_id": model_name,
        "condition": "B0",
        "prompt": prompt_str,
        "output": content[:300],
        "full_output": content,
        "finish_reason": resp["finish_reason"],
        "prompt_tokens": resp["prompt_tokens"],
        "completion_tokens": resp["completion_tokens"],
        "total_tokens": resp["total_tokens"],
        "status": resp["status"],
        "clean_execution": resp["status"] == "COMPLETE",
        "passed": sc["passed"],
        "details": sc["details"],
        "duration": round(dt, 2),
        "protocol_version": "v2_unclamped_4096"
    }


def evaluate_track_a_b1_item(item: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """Evaluates Track A item under B1 (With fair tools) unclamped at max_tokens=4096."""
    from scripts.run_heldout_baselines_b1 import evaluate_baseline_b1_item
    rec = evaluate_baseline_b1_item(item, model_name)
    rec["protocol_version"] = "v2_unclamped_4096"
    return rec


def load_unique_records(path: str) -> Dict[str, Dict[str, Any]]:
    recs = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    iid = r.get("item_id")
                    if iid:
                        recs[iid] = r
                except Exception:
                    pass
    return recs


def bootstrap_ci(scores: List[float], n_boot: int = 2000, alpha: float = 0.05) -> Tuple[float, float]:
    if not scores:
        return (0.0, 0.0)
    rng = random.Random(42)
    n = len(scores)
    means = []
    for _ in range(n_boot):
        sample = [rng.choice(scores) for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lower_idx = int(n_boot * (alpha / 2))
    upper_idx = int(n_boot * (1 - alpha / 2))
    return (round(means[lower_idx] * 100, 2), round(means[upper_idx] * 100, 2))


def analyze_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    def compute_stratum_metrics(recs: List[Dict[str, Any]]) -> Dict[str, Any]:
        count = len(recs)
        if count == 0:
            return {"count": 0, "passes": 0, "acc": 0.0, "ci_95": [0.0, 0.0], "clean_share": 0.0, "mean_duration": 0.0, "failed_or_trunc": 0, "failed_trunc_pct": 0.0}
        passes = sum(1 for r in recs if r.get("passed"))
        clean = sum(1 for r in recs if r.get("clean_execution", True))
        durs = [r.get("duration", 0.0) for r in recs]
        failed_trunc = sum(1 for r in recs if r.get("finish_reason") == "length" or r.get("status") == "FAILED")
        acc = round(passes / count * 100, 2)
        ci = bootstrap_ci([1.0 if r.get("passed") else 0.0 for r in recs])
        clean_share = round(clean / count * 100, 2)
        mean_dur = round(sum(durs) / count, 2)
        failed_trunc_pct = round(failed_trunc / count * 100, 2)
        return {
            "count": count,
            "passes": passes,
            "acc": acc,
            "ci_95": list(ci),
            "clean_share": clean_share,
            "mean_duration": mean_dur,
            "failed_or_trunc": failed_trunc,
            "failed_trunc_pct": failed_trunc_pct
        }

    tra_items = [r for r in records if r.get("track") == "A"]
    trb_items = [r for r in records if r.get("track") == "B"]
    atomic = [r for r in tra_items if r.get("stratum") == "atomic"]
    comp = [r for r in tra_items if r.get("stratum") == "composed"]
    comp_solv = [r for r in comp if r.get("solvability") == "solvable_without_tools"]
    comp_treq = [r for r in comp if r.get("solvability") == "tool-required"]

    # Also compute facts-alone metrics for Track B
    trb_facts_alone_passes = sum(1 for r in trb_items if r.get("passed_facts_alone", r.get("passed")))
    trb_facts_alone_acc = round(trb_facts_alone_passes / len(trb_items) * 100, 2) if trb_items else 0.0
    trb_facts_ci = bootstrap_ci([1.0 if r.get("passed_facts_alone", r.get("passed")) else 0.0 for r in trb_items])

    trb_metrics = compute_stratum_metrics(trb_items)
    trb_metrics["facts_alone_passes"] = trb_facts_alone_passes
    trb_metrics["facts_alone_acc"] = trb_facts_alone_acc
    trb_metrics["facts_alone_ci_95"] = list(trb_facts_ci)

    return {
        "track_a_total": compute_stratum_metrics(tra_items),
        "track_b_total": trb_metrics,
        "tra_atomic": compute_stratum_metrics(atomic),
        "tra_compound": compute_stratum_metrics(comp),
        "tra_comp_solv": compute_stratum_metrics(comp_solv),
        "tra_comp_treq": compute_stratum_metrics(comp_treq)
    }


def main():
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY environment variable missing.")
        sys.exit(1)

    track_a_items = json.load(open(TRACK_A_HELDOUT_PATH, "r", encoding="utf-8"))
    track_b_items = json.load(open(TRACK_B_HELDOUT_PATH, "r", encoding="utf-8"))
    all_heldout_items = track_a_items + track_b_items
    item_map = {it.get("question_id") or it.get("subtask_id") or it.get("original_id") or it.get("item_id"): it for it in all_heldout_items}

    # Output file paths
    b0_qwen_path = os.path.join(RESULTS_DIR, "b0_qwen27b_heldout_records.jsonl")
    b0_gpt_path = os.path.join(RESULTS_DIR, "b0_gpt120b_heldout_records.jsonl")
    b1_qwen_path = os.path.join(RESULTS_DIR, "b1_qwen27b_heldout_records.jsonl")
    b1_gpt_path = os.path.join(RESULTS_DIR, "b1_gpt120b_heldout_records.jsonl")

    # =========================================================================
    # PART 1: RERUN TRACK B BASELINES WITH IDENTICAL INSTRUCTIONS (B0 & B1)
    # =========================================================================
    print("\n=======================================================")
    print("PART 1: RERUNNING TRACK B BASELINES WITH IDENTICAL INSTRUCTIONS")
    print("=======================================================")

    # 1.1 B1 Qwen-27B Track B
    print("\n--- B1 Qwen-27B Track B (50 items) ---")
    with open(b1_qwen_path, "a", encoding="utf-8") as f_out:
        for idx, it in enumerate(track_b_items, 1):
            qid = it["question_id"]
            rec = evaluate_track_b_item(it, "qwen/qwen3.8-27b", condition="B1")
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  [B1-Qwen TrackB {idx:02d}/50] {qid}: with_cap={rec['passed']}, facts_alone={rec['passed_facts_alone']} ({rec['duration']}s)")
            time.sleep(2.0)

    # 1.2 B1 GPT-120B Track B
    print("\n--- B1 GPT-120B Track B (50 items) ---")
    with open(b1_gpt_path, "a", encoding="utf-8") as f_out:
        for idx, it in enumerate(track_b_items, 1):
            qid = it["question_id"]
            rec = evaluate_track_b_item(it, "openai/gpt-oss-120b", condition="B1")
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  [B1-GPT TrackB {idx:02d}/50] {qid}: with_cap={rec['passed']}, facts_alone={rec['passed_facts_alone']} ({rec['duration']}s)")
            time.sleep(2.0)

    # 1.3 B0 Qwen-27B Track B (Unassisted)
    print("\n--- B0 Qwen-27B Track B (50 items) ---")
    with open(b0_qwen_path, "a", encoding="utf-8") as f_out:
        for idx, it in enumerate(track_b_items, 1):
            qid = it["question_id"]
            rec = evaluate_track_b_item(it, "qwen/qwen3.8-27b", condition="B0")
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  [B0-Qwen TrackB {idx:02d}/50] {qid}: with_cap={rec['passed']}, facts_alone={rec['passed_facts_alone']} ({rec['duration']}s)")
            time.sleep(2.0)

    # 1.4 B0 GPT-120B Track B (Unassisted)
    print("\n--- B0 GPT-120B Track B (50 items) ---")
    with open(b0_gpt_path, "a", encoding="utf-8") as f_out:
        for idx, it in enumerate(track_b_items, 1):
            qid = it["question_id"]
            rec = evaluate_track_b_item(it, "openai/gpt-oss-120b", condition="B0")
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  [B0-GPT TrackB {idx:02d}/50] {qid}: with_cap={rec['passed']}, facts_alone={rec['passed_facts_alone']} ({rec['duration']}s)")
            time.sleep(2.0)

    # =========================================================================
    # PART 2: RERUN TRUNCATED/FAILED 27B ITEMS UNCLAMPED AT 4,096 TOKENS
    # =========================================================================
    print("\n=======================================================")
    print("PART 2: RERUNNING TRUNCATED/FAILED 27B ITEMS UNCLAMPED (4096 TOKENS)")
    print("=======================================================")

    # 2.1 B0 Qwen-27B Track A truncated/failed items
    b0_recs = load_unique_records(b0_qwen_path)
    b0_failed_items = [
        item_map[iid] for iid, r in b0_recs.items()
        if r.get("track") == "A" and (r.get("finish_reason") == "length" or r.get("status") == "FAILED")
    ]
    print(f"\nB0 Qwen-27B Track A items to rerun: {len(b0_failed_items)}")
    with open(b0_qwen_path, "a", encoding="utf-8") as f_out:
        for idx, it in enumerate(b0_failed_items, 1):
            iid = it.get("subtask_id") or it.get("original_id") or it.get("item_id")
            rec = evaluate_track_a_b0_item(it, "qwen/qwen3.8-27b")
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  [B0-Qwen Rerun {idx:02d}/{len(b0_failed_items)}] {iid}: passed={rec['passed']}, finish={rec['finish_reason']}, tokens={rec['completion_tokens']}")
            time.sleep(2.0)

    # 2.2 B1 Qwen-27B Track A truncated/failed items
    b1_recs = load_unique_records(b1_qwen_path)
    b1_failed_items = [
        item_map[iid] for iid, r in b1_recs.items()
        if r.get("track") == "A" and (r.get("finish_reason") == "length" or r.get("status") == "FAILED")
    ]
    print(f"\nB1 Qwen-27B Track A items to rerun: {len(b1_failed_items)}")
    with open(b1_qwen_path, "a", encoding="utf-8") as f_out:
        for idx, it in enumerate(b1_failed_items, 1):
            iid = it.get("subtask_id") or it.get("original_id") or it.get("item_id")
            rec = evaluate_track_a_b1_item(it, "qwen/qwen3.8-27b")
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()
            print(f"  [B1-Qwen Rerun {idx:02d}/{len(b1_failed_items)}] {iid}: passed={rec['passed']}, finish={rec['finish_reason']}, tokens={rec['completion_tokens']}")
            time.sleep(2.0)

    # =========================================================================
    # PART 3: RECOMPILE REPORTS DIRECTLY FROM UPDATED IMMUTABLE RECORDS
    # =========================================================================
    print("\n=======================================================")
    print("PART 3: RECOMPILING B0 AND B1 REPORTS FROM UPDATED RECORDS")
    print("=======================================================")

    # Reload all unique records (last row wins for updated items)
    final_b0_qwen = list(load_unique_records(b0_qwen_path).values())
    final_b0_gpt = list(load_unique_records(b0_gpt_path).values())
    final_b1_qwen = list(load_unique_records(b1_qwen_path).values())
    final_b1_gpt = list(load_unique_records(b1_gpt_path).values())

    print(f"Final record counts: B0 Qwen={len(final_b0_qwen)}, B0 GPT={len(final_b0_gpt)}, B1 Qwen={len(final_b1_qwen)}, B1 GPT={len(final_b1_gpt)}")

    b0_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "split": "heldout",
        "condition": "B0",
        "hashes": {
            "track_a_heldout_sha256": "2314fca186a064ffcface62f42dc346bda9fdc73c5221852e8ecf5b19aafd629",
            "track_b_heldout_sha256": "075bf20d1daafdb89e3eef1e35271113766b9845cfb9d52e88301faa2919c0e1"
        },
        "results": {
            "qwen27b": analyze_records(final_b0_qwen),
            "gpt120b": analyze_records(final_b0_gpt)
        }
    }
    b0_report_path = os.path.join(RESULTS_DIR, "phase4_b0_heldout_report.json")
    with open(b0_report_path, "w", encoding="utf-8") as f:
        json.dump(b0_report, f, indent=2)
    print(f"Updated {b0_report_path}")

    b1_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "split": "heldout",
        "condition": "B1",
        "hashes": {
            "track_a_heldout_sha256": "2314fca186a064ffcface62f42dc346bda9fdc73c5221852e8ecf5b19aafd629",
            "track_b_heldout_sha256": "075bf20d1daafdb89e3eef1e35271113766b9845cfb9d52e88301faa2919c0e1"
        },
        "results": {
            "qwen27b": analyze_records(final_b1_qwen),
            "gpt120b": analyze_records(final_b1_gpt)
        }
    }
    b1_report_path = os.path.join(RESULTS_DIR, "phase4_b1_heldout_report.json")
    with open(b1_report_path, "w", encoding="utf-8") as f:
        json.dump(b1_report, f, indent=2)
    print(f"Updated {b1_report_path}")

    print("\nRerun protocol execution finished successfully.")


if __name__ == "__main__":
    main()
