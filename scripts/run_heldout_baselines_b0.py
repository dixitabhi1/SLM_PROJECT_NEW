"""
Phase 4 Frozen Held-Out Evaluation Script: B0 Baselines (No Tools, Unclamped).

Evaluates both baselines on Locked Held-Out Splits:
- Track A Held-Out Split: 100 items (SHA-256: 2314fca186a064ffcface62f42dc346bda9fdc73c5221852e8ecf5b19aafd629)
- Track B Held-Out Split: 50 items (SHA-256: b021e2d0032d15a20f24315fb4538fe59ecd3ecb323f9a8ca295c2b421d7ed6d)
Total: 150 items per baseline model

Models:
1. qwen/qwen3.8-27b (Tier 1 Baseline, 27B)
2. openai/gpt-oss-120b (Tier 3 Ceiling Baseline, 120B)

Configuration:
- Condition: B0 (Direct unassisted reasoning, no tools, greedy temp=0.0, unclamped max_tokens=2048)
- Pacing: 2.0s between requests + adaptive HTTP 429 backoff
- Append-only records to results/phase4/b0_qwen27b_heldout_records.jsonl and b0_gpt120b_heldout_records.jsonl
"""

import os
import sys
import json
import time
import re
import random
import hashlib
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

from src.eval.versioned_scorer import score_record
from src.eval.fact_checklist_scorer import score_fact_checklist
from src.pipeline.specialist_pipeline import get_table_schema

TRACK_A_HELDOUT_PATH = os.path.join(REPO_ROOT, "data", "track_a_heldout_split.json")
TRACK_B_HELDOUT_PATH = os.path.join(REPO_ROOT, "data", "track_b", "track_b_heldout_split.json")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "phase4")
os.makedirs(RESULTS_DIR, exist_ok=True)

EXPECTED_TRACK_A_HASH = "2314fca186a064ffcface62f42dc346bda9fdc73c5221852e8ecf5b19aafd629"
EXPECTED_TRACK_B_HASH = "075bf20d1daafdb89e3eef1e35271113766b9845cfb9d52e88301faa2919c0e1"


def verify_split_hashes():
    h_a = hashlib.sha256(open(TRACK_A_HELDOUT_PATH, "rb").read()).hexdigest()
    h_b = hashlib.sha256(open(TRACK_B_HELDOUT_PATH, "rb").read()).hexdigest()
    assert h_a == EXPECTED_TRACK_A_HASH, f"Track A hash mismatch: got {h_a}, expected {EXPECTED_TRACK_A_HASH}"
    assert h_b == EXPECTED_TRACK_B_HASH, f"Track B hash mismatch: got {h_b}, expected {EXPECTED_TRACK_B_HASH}"
    print("Cryptographic Lock Verified:")
    print(f"  Track A Held-out SHA-256: {h_a} [LOCKED]")
    print(f"  Track B Held-out SHA-256: {h_b} [LOCKED]")


def format_eval_prompt(item: Dict[str, Any]) -> str:
    """Constructs prompt for evaluation identical to C0/pipeline without leaking internal metadata."""
    if "checklist" in item:
        word_cap = item.get("word_cap", 75)
        return (
            f"{item['prompt']}\n\n"
            f"Provide a concise answer in key-value pairs (max {word_cap} words). "
            f"Conclude with 'Final Answer: <key-value pairs>'."
        )

    task_type = item.get("task_type") or item.get("type")
    if task_type == "sql":
        db_id = item.get("db_id", "")
        schema = get_table_schema(db_id)
        return (
            f"[Database: {db_id}]\n"
            f"[Database Schema:\n{schema}\n]\n"
            f"Question: {item['question']}\n"
            f"Return only the requested column.\n"
            f"Write a valid SQLite query in ```sql ... ```."
        )
    elif task_type == "qa":
        choices = item.get("choices", {})
        opt_text = "\n".join(f"({k}) {v}" for k, v in sorted(choices.items()))
        return (
            f"Question: {item['question']}\n\n"
            f"Options:\n{opt_text}\n\n"
            f"Select the single correct option. State your final answer as: Answer: (X)"
        )
    elif task_type == "code":
        return f"{item['prompt']}\nComplete the implementation of the above Python function inside ```python ... ```."
    elif task_type == "math":
        return f"Solve this math problem step by step:\n{item['question']}\n\nConclude your final answer with: #### <number>"
    elif task_type == "compound" or item.get("stratum") == "composed":
        return f"{item['prompt']}\n\nSolve the problem step by step. Conclude your final answer with 'Final Answer: <answer>' or '#### <answer>'."

    return item.get("prompt") or item.get("question") or ""


def load_existing_records(path: str) -> Dict[str, Dict[str, Any]]:
    records = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        iid = rec.get("item_id")
                        if iid:
                            records[iid] = rec
                    except Exception:
                        pass
    return records


def call_groq_api(
    model_id: str,
    prompt: str,
    system_prompt: str = "You are a helpful, precise assistant. Reason step-by-step and provide your final answer in the requested format.",
    max_tokens: int = 2048,
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

    for attempt in range(10):
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
                status = "COMPLETE" if finish_reason in ["stop", "length"] and content else "FAILED"
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
                sleep_time = max(retry_after + 1.0, body_wait + 1.0, 3.0 * (attempt + 1), 5.0)
                print(f"    [Rate Limit 429] Backing off for {sleep_time:.1f}s (attempt {attempt+1}/10)...")
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
                time.sleep(2.0 * (attempt + 1))
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
        "error_message": "All 10 retries exhausted"
    }


def score_item_response(item: Dict[str, Any], output_text: str, final_answer: str = "") -> Tuple[bool, str]:
    if "checklist" in item:
        text_to_score = final_answer if final_answer else output_text
        sc = score_fact_checklist(text_to_score, item["checklist"], max_word_cap=item.get("word_cap", 75))
        passed = sc["binary_pass"]
        details = f"Recall: {sc['recall']:.2f}, Precision: {sc['precision']:.2f}"
        if sc.get("failed_facts"):
            details += f" | Failed: {sc['failed_facts'][0]}"
        return passed, details
    else:
        sc = score_record(item, output_text)
        return sc["passed"], sc["details"]


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


def evaluate_baseline_model(
    model_name: str,
    output_path: str,
    all_items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    print(f"\nEvaluating Baseline: {model_name} -> {output_path}")
    existing = load_existing_records(output_path)
    print(f"Existing records: {len(existing)} / {len(all_items)}")

    records = []
    total_tokens_used = 0

    with open(output_path, "a", encoding="utf-8") as f_out:
        for idx, item in enumerate(all_items, 1):
            iid = item.get("subtask_id") or item.get("original_id") or item.get("question_id") or item.get("item_id")
            if iid in existing:
                records.append(existing[iid])
                continue

            prompt_str = format_eval_prompt(item)
            resp = call_groq_api(model_name, prompt_str, max_tokens=2048)

            content = resp["content"]
            passed, details = score_item_response(item, content, final_answer=content)
            clean = bool(content.strip() and resp["status"] == "COMPLETE")

            total_tokens_used += resp["total_tokens"]

            rec = {
                "item_id": iid,
                "split": "heldout",
                "track": "B" if "checklist" in item else "A",
                "task_type": item.get("task_type", "track_b" if "checklist" in item else ""),
                "stratum": item.get("stratum", "atomic" if "checklist" in item else ""),
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
                "clean_execution": clean,
                "passed": passed,
                "details": details,
                "duration": resp["latency_seconds"]
            }
            records.append(rec)
            f_out.write(json.dumps(rec) + "\n")
            f_out.flush()

            status_str = "PASS" if passed else "FAIL"
            print(f"  [{idx:03d}/{len(all_items)}] {model_name} {iid}: {status_str} (tokens={resp['completion_tokens']}, {resp['latency_seconds']:.2f}s)")

            # Pace requests ~2 seconds between calls to respect 8,000 TPM limit
            time.sleep(2.0)

    print(f"Finished {model_name}. New tokens used: {total_tokens_used}")
    return records


def analyze_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    def compute_stratum_metrics(subset: List[Dict[str, Any]]) -> Dict[str, Any]:
        count = len(subset)
        if count == 0:
            return {"count": 0, "passes": 0, "acc": 0.0, "ci_95": [0.0, 0.0], "clean_share": 0.0, "mean_duration": 0.0, "failed_or_trunc": 0, "failed_trunc_pct": 0.0}
        passes = sum(1 for r in subset if r.get("passed"))
        acc = round(passes / count * 100, 2)
        ci = bootstrap_ci([1.0 if r.get("passed") else 0.0 for r in subset])
        clean_share = round(sum(1 for r in subset if r.get("clean_execution")) / count * 100, 2)
        durations = [r.get("duration", 0.0) for r in subset]
        mean_dur = round(sum(durations) / count, 2) if durations else 0.0
        failed_trunc = sum(1 for r in subset if r.get("finish_reason") == "length" or r.get("status") == "FAILED")
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

    return {
        "track_a_total": compute_stratum_metrics(tra_items),
        "track_b_total": compute_stratum_metrics(trb_items),
        "tra_atomic": compute_stratum_metrics(atomic),
        "tra_compound": compute_stratum_metrics(comp),
        "tra_comp_solv": compute_stratum_metrics(comp_solv),
        "tra_comp_treq": compute_stratum_metrics(comp_treq)
    }


def main():
    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY environment variable is missing.")
        sys.exit(1)

    verify_split_hashes()

    track_a = json.load(open(TRACK_A_HELDOUT_PATH, "r", encoding="utf-8"))
    track_b = json.load(open(TRACK_B_HELDOUT_PATH, "r", encoding="utf-8"))
    all_heldout_items = track_a + track_b
    print(f"Loaded {len(track_a)} Track A heldout items + {len(track_b)} Track B heldout items. Total: {len(all_heldout_items)} items.")

    # 1. Qwen-27B
    qwen_out = os.path.join(RESULTS_DIR, "b0_qwen27b_heldout_records.jsonl")
    qwen_recs = evaluate_baseline_model("qwen/qwen3.8-27b", qwen_out, all_heldout_items)

    # 2. GPT-OSS-120B
    gpt_out = os.path.join(RESULTS_DIR, "b0_gpt120b_heldout_records.jsonl")
    gpt_recs = evaluate_baseline_model("openai/gpt-oss-120b", gpt_out, all_heldout_items)

    # Compile report
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "split": "heldout",
        "condition": "B0",
        "hashes": {
            "track_a_heldout_sha256": EXPECTED_TRACK_A_HASH,
            "track_b_heldout_sha256": EXPECTED_TRACK_B_HASH
        },
        "results": {
            "qwen27b": analyze_records(qwen_recs),
            "gpt120b": analyze_records(gpt_recs)
        }
    }

    report_path = os.path.join(RESULTS_DIR, "phase4_b0_heldout_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()

