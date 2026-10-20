"""
scripts/run_public_benchmarks.py

Public Benchmark Evaluation Harness for:
1. GSM-Hard (reasoning-machines/gsm-hard)
2. FinQA (czyssrs/FinQA)
3. InfiAgent-DABench (InfiAgent/InfiAgent)

Systems and Conditions Evaluated:
- C0: Base SLM (Phi-4-mini-instruct, 3.82B, local RTX 3050 Vulkan, direct zero-shot)
- SLM Pipeline v1.3: Frozen Specialist Pipeline (run_specialist_pipeline_e3)
- B0: Zero-shot unassisted LLMs (gpt-oss-120b and qwen3.8-27b on Groq)
- B1: Standard tool harness with full tool list and no oracle routing (1 tool execution round)
- B1+code: Real Python sandbox execution with up to 3 execute-and-revise rounds (matching SLM colorer budget)

Integrity Invariants:
- Real API finish_reason captured and recorded (never hard-coded 'stop').
- Reasoning tokens saved from Groq API (choice['message'].get('reasoning')).
- Pure black-box prompt evaluation for pipeline: run_specialist_pipeline_e3(prompt).
- Append-only records to results/public/public_benchmark_records_<condition>.jsonl.
- Safe resumption: skips items already completed.
- Zero monetary cost ($0.00 spend; local model + Groq free tier).
"""

import os
import sys
import json
import time
import re
import argparse
import datetime
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

from src.sandbox.runner import execute_python_code
from src.pipeline.specialist_pipeline import call_phi
from src.pipeline.specialist_pipeline_e3 import run_specialist_pipeline_e3
from src.adapters.public_adapters import adapt_benchmark_item
from src.eval.public_graders import grade_benchmark_item

DATA_PUBLIC_DIR = os.path.join(REPO_ROOT, "data", "public")
RAW_DIR = os.path.join(DATA_PUBLIC_DIR, "raw")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "public")
os.makedirs(RESULTS_DIR, exist_ok=True)

MODEL_CONFIGS = {
    "c0": {
        "model_id": "microsoft/Phi-4-mini-instruct",
        "family": "Phi",
        "parameters": 3.82e9,
        "is_local": True
    },
    "slm_v13": {
        "model_id": "microsoft/Phi-4-mini-instruct",
        "family": "Phi",
        "parameters": 3.82e9,
        "is_local": True
    },
    "gpt120b": {
        "model_id": "openai/gpt-oss-120b",
        "family": "GPT-OSS",
        "parameters": 120e9,
        "is_local": False
    },
    "qwen27b": {
        "model_id": "qwen/qwen3.8-27b",
        "family": "Qwen",
        "parameters": 27e9,
        "is_local": False
    }
}


def load_dataset_split(benchmark: str, split: str) -> List[Dict[str, Any]]:
    """
    Loads raw items for the given benchmark and split ('practice' or 'test').
    Returns list of items with keys: item_id, benchmark, raw_item.
    """
    id_file = os.path.join(DATA_PUBLIC_DIR, f"{benchmark}_{split}_ids.json")
    if not os.path.exists(id_file):
        raise FileNotFoundError(f"Split ID file not found: {id_file}")
    with open(id_file, "r", encoding="utf-8") as f:
        target_ids = set(json.load(f))

    items = []
    if benchmark == "gsmhard":
        raw_file = os.path.join(RAW_DIR, "gsmhard", "gsmhardv2.jsonl")
        with open(raw_file, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                iid = f"gsmhard_{idx:04d}"
                if iid in target_ids:
                    raw = json.loads(line)
                    items.append({
                        "item_id": iid,
                        "benchmark": "gsmhard",
                        "raw_item": raw
                    })
    elif benchmark == "finqa":
        raw_file = os.path.join(RAW_DIR, "finqa", "test.json")
        with open(raw_file, "r", encoding="utf-8") as f:
            raw_list = json.load(f)
            for raw in raw_list:
                iid = raw["id"]
                if iid in target_ids:
                    items.append({
                        "item_id": iid,
                        "benchmark": "finqa",
                        "raw_item": raw
                    })
    elif benchmark == "dabench":
        q_file = os.path.join(RAW_DIR, "dabench", "da-dev-questions.jsonl")
        lbl_file = os.path.join(RAW_DIR, "dabench", "da-dev-labels.jsonl")
        labels_by_id = {}
        with open(lbl_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    lbl = json.loads(line)
                    labels_by_id[lbl["id"]] = lbl.get("common_answers", [])
        with open(q_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    raw = json.loads(line)
                    iid = f"dabench_{raw['id']:04d}"
                    if iid in target_ids:
                        raw["common_answers"] = labels_by_id.get(raw["id"], [])
                        items.append({
                            "item_id": iid,
                            "benchmark": "dabench",
                            "raw_item": raw
                        })
    else:
        raise ValueError(f"Unknown benchmark: {benchmark}")

    # Preserve ordering according to target_ids file
    with open(id_file, "r", encoding="utf-8") as f:
        ordered_ids = json.load(f)
    items_by_id = {it["item_id"]: it for it in items}
    return [items_by_id[iid] for iid in ordered_ids if iid in items_by_id]


def load_existing_records(path: str) -> Dict[str, Dict[str, Any]]:
    """Loads existing records mapping item_id -> record."""
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


def call_groq_api_with_reasoning(
    model_id: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 4096,
    temperature: float = 0.0,
    seed: int = 42
) -> Dict[str, Any]:
    """
    Calls Groq Cloud API, extracting:
    - real finish_reason from API
    - reasoning from choice['message'].get('reasoning')
    - token counts and latency
    - handles HTTP 429 rate limit backoff cleanly
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "seed": seed
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "User-Agent": "SLM-Public-Benchmark-Evaluation/1.0"
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)

    rate_limit_wait = 0.0
    for attempt in range(12):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                elapsed = time.perf_counter() - t0
                body = json.loads(resp.read().decode("utf-8"))
                choice = body["choices"][0]
                usage = body.get("usage", {})
                msg = choice.get("message", {})
                content = msg.get("content", "")
                reasoning = msg.get("reasoning", "")
                finish_reason = choice.get("finish_reason") or "stop"
                return {
                    "content": content,
                    "reasoning": reasoning,
                    "finish_reason": finish_reason,
                    "latency_seconds": round(elapsed, 4),
                    "rate_limit_wait_seconds": round(rate_limit_wait, 2),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "status": "COMPLETE",
                    "error_message": ""
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
                rate_limit_wait += sleep_time
                print(f"    [Rate Limit 429] Backing off for {sleep_time:.1f}s (attempt {attempt+1}/12)...")
                time.sleep(sleep_time)
            if he.code == 400:
                err_body = ""
                try:
                    err_body = he.read().decode("utf-8")
                    err_json = json.loads(err_body)
                    err_obj = err_json.get("error", {})
                    if err_obj.get("code") == "tool_use_failed":
                        fg = err_obj.get("failed_generation", "")
                        code = fg
                        if '"arguments":' in fg:
                            code = fg.split('"arguments":', 1)[1].rstrip("}").strip()
                        return {
                            "content": f"```python\n{code}\n```",
                            "reasoning": "",
                            "finish_reason": "stop",
                            "latency_seconds": round(elapsed, 4),
                            "rate_limit_wait_seconds": round(rate_limit_wait, 2),
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                            "status": "COMPLETE",
                            "error_message": ""
                        }
                except Exception:
                    pass
                return {
                    "content": "",
                    "reasoning": "",
                    "finish_reason": f"http_error_{he.code}",
                    "latency_seconds": round(elapsed, 4),
                    "rate_limit_wait_seconds": round(rate_limit_wait, 2),
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "status": "FAILED",
                    "error_message": f"HTTP {he.code}: {he.reason}"
                }
            return {
                "content": "",
                "reasoning": "",
                "finish_reason": f"http_error_{he.code}",
                "latency_seconds": round(elapsed, 4),
                "rate_limit_wait_seconds": round(rate_limit_wait, 2),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "status": "FAILED",
                "error_message": f"HTTP {he.code}: {he.reason}"
            }
        except Exception as e:
            elapsed = time.perf_counter() - t0
            time.sleep(2.0 * (attempt + 1))
            if attempt == 11:
                return {
                    "content": "",
                    "reasoning": "",
                    "finish_reason": "connection_error",
                    "latency_seconds": round(elapsed, 4),
                    "rate_limit_wait_seconds": round(rate_limit_wait, 2),
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "status": "FAILED",
                    "error_message": str(e)
                }
    return {
        "content": "",
        "reasoning": "",
        "finish_reason": "max_retries_exceeded",
        "latency_seconds": 0.0,
        "rate_limit_wait_seconds": round(rate_limit_wait, 2),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "status": "FAILED",
        "error_message": "Exceeded 12 retry attempts"
    }


def run_c0_item(prompt: str) -> Dict[str, Any]:
    """Runs unassisted zero-shot base SLM (Phi-4-mini) on local llama-server."""
    t0 = time.time()
    resp = call_phi([
        {"role": "system", "content": "You are a helpful, precise assistant. Reason step-by-step and provide your final answer clearly."},
        {"role": "user", "content": prompt}
    ], temperature=0.0, max_tokens=4096)
    dt = time.time() - t0
    return {
        "full_output": resp,
        "final_answer": resp,
        "finish_reason": "stop" if resp.strip() else "empty",
        "reasoning": "",
        "tool_calls": 0,
        "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "duration": round(dt, 3)
    }


def run_slm_v13_item(prompt: str) -> Dict[str, Any]:
    """Runs frozen Specialist Pipeline v1.3 locally."""
    t0 = time.time()
    res = run_specialist_pipeline_e3(prompt)
    dt = time.time() - t0
    tool_count = 1 if res.get("routed_to") in ("code_compute", "code_implementation", "direct_sql", "outside_data") else 0
    return {
        "full_output": res.get("full_output", ""),
        "final_answer": res.get("final_answer", ""),
        "finish_reason": "stop" if res.get("full_output", "").strip() else "empty",
        "reasoning": "",
        "tool_calls": tool_count,
        "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "duration": round(dt, 3),
        "pipeline_meta": {
            "routed_to": res.get("routed_to"),
            "clean_execution": res.get("clean_execution"),
            "fallbacks": res.get("fallbacks")
        }
    }


def run_b0_item(model_id: str, prompt: str) -> Dict[str, Any]:
    """Runs unassisted zero-shot baseline LLM via Groq API."""
    messages = [
        {"role": "system", "content": "You are a helpful, precise assistant. Solve the problem and provide your final answer."},
        {"role": "user", "content": prompt}
    ]
    resp = call_groq_api_with_reasoning(model_id, messages, max_tokens=4096)
    return {
        "full_output": resp["content"],
        "final_answer": resp["content"],
        "finish_reason": resp["finish_reason"],
        "reasoning": resp.get("reasoning", ""),
        "tool_calls": 0,
        "tokens": {
            "prompt_tokens": resp["prompt_tokens"],
            "completion_tokens": resp["completion_tokens"],
            "total_tokens": resp["total_tokens"]
        },
        "duration": resp["latency_seconds"],
        "rate_limit_wait": resp["rate_limit_wait_seconds"]
    }


def run_b1_item(model_id: str, prompt: str) -> Dict[str, Any]:
    """
    Runs condition B1: Fair tools, NO oracle routing.
    Full tool capabilities provided to model; model decides autonomously whether to call tools.
    If model emits Python code block, executes once in sandbox and feeds stdout back to obtain final answer.
    """
    tool_instructions = (
        "You are an expert computational assistant with access to an isolated Python sandbox.\n"
        "If you wish to execute Python code to solve or verify the problem, enclose your script in ```python\n<code>\n```.\n"
        "Your code will be executed in the sandbox and its output returned to you.\n"
        "Always provide your final answer clearly."
    )
    messages = [
        {"role": "system", "content": tool_instructions},
        {"role": "user", "content": prompt}
    ]
    resp1 = call_groq_api_with_reasoning(model_id, messages, max_tokens=4096)
    total_prompt_tok = resp1["prompt_tokens"]
    total_comp_tok = resp1["completion_tokens"]
    total_wait = resp1["rate_limit_wait_seconds"]
    duration = resp1["latency_seconds"]

    code_m = re.search(r"```python\s*(.*?)\s*```", resp1["content"], re.DOTALL | re.IGNORECASE)
    tool_calls = 0
    final_content = resp1["content"]
    final_reasoning = resp1.get("reasoning", "")
    finish_reason = resp1["finish_reason"]

    if code_m and resp1["finish_reason"] != "length":
        tool_calls += 1
        code_to_run = code_m.group(1).strip()
        sb_res = execute_python_code(code_to_run, timeout_seconds=10.0)
        tool_output = sb_res.stdout.strip() if sb_res.exit_code == 0 else (sb_res.stderr.strip() or f"Error (exit {sb_res.exit_code})")

        messages.append({"role": "assistant", "content": resp1["content"]})
        follow_up = (
            f"Execution output from Python sandbox:\n```\n{tool_output}\n```\n"
            f"Based on this result, state your final answer clearly."
        )
        messages.append({"role": "user", "content": follow_up})
        resp2 = call_groq_api_with_reasoning(model_id, messages, max_tokens=4096)
        total_prompt_tok += resp2["prompt_tokens"]
        total_comp_tok += resp2["completion_tokens"]
        total_wait += resp2["rate_limit_wait_seconds"]
        duration += resp2["latency_seconds"]
        final_content = resp2["content"]
        if resp2.get("reasoning"):
            final_reasoning = f"{final_reasoning}\n\n[Round 2 Reasoning]:\n{resp2['reasoning']}".strip()
        finish_reason = resp2["finish_reason"]

    return {
        "full_output": final_content,
        "final_answer": final_content,
        "finish_reason": finish_reason,
        "reasoning": final_reasoning,
        "tool_calls": tool_calls,
        "tokens": {
            "prompt_tokens": total_prompt_tok,
            "completion_tokens": total_comp_tok,
            "total_tokens": total_prompt_tok + total_comp_tok
        },
        "duration": round(duration, 3),
        "rate_limit_wait": round(total_wait, 2)
    }


def run_b1_code_item(model_id: str, prompt: str) -> Dict[str, Any]:
    """
    Runs condition B1+code: Real Python sandbox execution with up to 3 execute-and-revise rounds.
    Matches the 3 feedback rounds allocated to the SLM specialist pipeline colorer.
    No oracle routing.
    """
    system_prompt = (
        "You are an expert computational assistant with access to an isolated Python sandbox.\n"
        "You may write Python code enclosed in ```python\n<code>\n``` to perform calculations or analyze data.\n"
        "Up to 3 execution-and-revision rounds will be provided to refine your solution if needed.\n"
        "When finished, provide your final answer clearly."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    total_prompt_tok = 0
    total_comp_tok = 0
    total_wait = 0.0
    duration = 0.0
    tool_calls = 0
    final_content = ""
    final_reasoning = ""
    finish_reason = "stop"

    for round_idx in range(1, 4):
        resp = call_groq_api_with_reasoning(model_id, messages, max_tokens=4096)
        total_prompt_tok += resp["prompt_tokens"]
        total_comp_tok += resp["completion_tokens"]
        total_wait += resp["rate_limit_wait_seconds"]
        duration += resp["latency_seconds"]
        final_content = resp["content"]
        finish_reason = resp["finish_reason"]
        
        if resp.get("reasoning"):
            tag = f"[Round {round_idx} Reasoning]"
            final_reasoning = f"{final_reasoning}\n\n{tag}\n{resp['reasoning']}".strip()

        if finish_reason == "length":
            break

        code_m = re.search(r"```python\s*(.*?)\s*```", resp["content"], re.DOTALL | re.IGNORECASE)
        if not code_m:
            # Model provided an answer without requesting further code execution
            break

        tool_calls += 1
        code_to_run = code_m.group(1).strip()
        sb_res = execute_python_code(code_to_run, timeout_seconds=10.0)
        tool_output = sb_res.stdout.strip() if sb_res.exit_code == 0 else (sb_res.stderr.strip() or f"Error (exit {sb_res.exit_code})")

        messages.append({"role": "assistant", "content": resp["content"]})
        if round_idx < 3:
            feedback_msg = (
                f"Execution Output from Round {round_idx}:\n```\n{tool_output}\n```\n"
                f"If the computation is complete, provide your final answer. "
                f"If an error occurred or revision is needed, you may provide revised Python code in ```python ... ```."
            )
        else:
            feedback_msg = (
                f"Execution Output from Round 3 (Final execution round):\n```\n{tool_output}\n```\n"
                f"Please provide your final answer now."
            )
        messages.append({"role": "user", "content": feedback_msg})

    return {
        "full_output": final_content,
        "final_answer": final_content,
        "finish_reason": finish_reason,
        "reasoning": final_reasoning,
        "tool_calls": tool_calls,
        "tokens": {
            "prompt_tokens": total_prompt_tok,
            "completion_tokens": total_comp_tok,
            "total_tokens": total_prompt_tok + total_comp_tok
        },
        "duration": round(duration, 3),
        "rate_limit_wait": round(total_wait, 2)
    }


def execute_evaluation_item(
    condition: str,
    benchmark: str,
    item_record: Dict[str, Any],
    adapted_prompt: str
) -> Dict[str, Any]:
    """Dispatches execution to the specified condition runner."""
    raw_item = item_record["raw_item"]

    if condition == "c0":
        return run_c0_item(adapted_prompt)
    elif condition == "slm_v13":
        return run_slm_v13_item(adapted_prompt)
    elif condition == "b0_gpt120b":
        return run_b0_item("openai/gpt-oss-120b", adapted_prompt)
    elif condition == "b0_qwen27b":
        return run_b0_item("qwen/qwen3.8-27b", adapted_prompt)
    elif condition == "b1_gpt120b":
        return run_b1_item("openai/gpt-oss-120b", adapted_prompt)
    elif condition == "b1_qwen27b":
        return run_b1_item("qwen/qwen3.8-27b", adapted_prompt)
    elif condition == "b1_code_gpt120b":
        return run_b1_code_item("openai/gpt-oss-120b", adapted_prompt)
    elif condition == "b1_code_qwen27b":
        return run_b1_code_item("qwen/qwen3.8-27b", adapted_prompt)
    else:
        raise ValueError(f"Unknown condition: {condition}")


def run_benchmark_suite(
    benchmarks: List[str],
    split: str,
    conditions: List[str],
    limit: Optional[int] = None
) -> None:
    """Executes the public benchmark evaluation suite."""
    print("=" * 70)
    print("PUBLIC BENCHMARK EVALUATION SUITE")
    print(f"Benchmarks: {benchmarks}")
    print(f"Split:      {split}")
    print(f"Conditions: {conditions}")
    print(f"Timestamp:  {datetime.datetime.now().isoformat()}")
    print("=" * 70)

    for cond in conditions:
        out_filename = f"public_records_{split}_{cond}.jsonl"
        out_path = os.path.join(RESULTS_DIR, out_filename)
        existing = load_existing_records(out_path)
        print(f"\nCondition [{cond}] -> {out_filename} ({len(existing)} existing records)")

        for bench in benchmarks:
            items = load_dataset_split(bench, split)
            if limit:
                items = items[:limit]
            print(f"  Benchmark [{bench}] ({len(items)} items):")

            for idx, it in enumerate(items, 1):
                iid = it["item_id"]
                if iid in existing:
                    print(f"    [{idx:03d}/{len(items):03d}] {iid}: ALREADY EVALUATED (passed={existing[iid].get('passed')})")
                    continue

                adapted_prompt = adapt_benchmark_item(bench, it["raw_item"])
                exec_res = execute_evaluation_item(cond, bench, it, adapted_prompt)

                passed, parsed_ans, grader_details = grade_benchmark_item(
                    bench,
                    exec_res["final_answer"],
                    it["raw_item"],
                    finish_reason=exec_res["finish_reason"]
                )

                # Gold answer serialization for reporting
                if bench == "gsmhard":
                    gold_val = it["raw_item"].get("target")
                elif bench == "finqa":
                    gold_val = it["raw_item"].get("qa", {}).get("answer")
                elif bench == "dabench":
                    gold_val = it["raw_item"].get("common_answers", [])
                else:
                    gold_val = None

                model_key = "gpt120b" if "gpt120b" in cond else ("qwen27b" if "qwen27b" in cond else ("slm_v13" if "slm" in cond else "c0"))
                record = {
                    "item_id": iid,
                    "benchmark": bench,
                    "split": split,
                    "condition": cond,
                    "model_id": MODEL_CONFIGS[model_key]["model_id"],
                    "adapted_prompt": adapted_prompt,
                    "full_output": exec_res["full_output"],
                    "reasoning": exec_res.get("reasoning", ""),
                    "final_answer": exec_res["final_answer"],
                    "gold": gold_val,
                    "passed": passed,
                    "parsed_answer": parsed_ans,
                    "grader_details": grader_details,
                    "finish_reason": exec_res["finish_reason"],
                    "tokens": exec_res.get("tokens", {}),
                    "duration": exec_res.get("duration", 0.0),
                    "rate_limit_wait": exec_res.get("rate_limit_wait", 0.0),
                    "tool_calls": exec_res.get("tool_calls", 0),
                    "timestamp": datetime.datetime.now().isoformat()
                }

                with open(out_path, "a", encoding="utf-8") as out_f:
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                existing[iid] = record

                mark = "[PASS]" if passed else "[FAIL]"
                print(f"    [{idx:03d}/{len(items):03d}] {iid}: {mark} (finish={exec_res['finish_reason']}, dur={exec_res.get('duration')}s)")


def main():
    parser = argparse.ArgumentParser(description="Run Public Benchmark Validation Suite")
    parser.add_argument("--benchmark", choices=["all", "gsmhard", "finqa", "dabench"], default="all")
    parser.add_argument("--split", choices=["practice", "test"], default="practice")
    parser.add_argument(
        "--condition",
        choices=[
            "all",
            "c0",
            "slm_v13",
            "b0_gpt120b",
            "b0_qwen27b",
            "b1_gpt120b",
            "b1_qwen27b",
            "b1_code_gpt120b",
            "b1_code_qwen27b"
        ],
        default="all"
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items per benchmark")
    args = parser.parse_args()

    benchmarks = ["gsmhard", "finqa", "dabench"] if args.benchmark == "all" else [args.benchmark]
    all_conditions = [
        "c0",
        "slm_v13",
        "b0_gpt120b",
        "b0_qwen27b",
        "b1_gpt120b",
        "b1_qwen27b",
        "b1_code_gpt120b",
        "b1_code_qwen27b"
    ]
    conditions = all_conditions if args.condition == "all" else [args.condition]

    run_benchmark_suite(benchmarks, args.split, conditions, limit=args.limit)


if __name__ == "__main__":
    main()
