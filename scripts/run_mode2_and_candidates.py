"""
Automated benchmark runner for:
1. Qwen3-4B (Thinking On) with context-safe budget:
   - Evaluates on 50 hard subtasks
   - Explicitly records truncated items and excludes them from valid accuracy
   - Stratified reporting: Downloaded (30) vs Agent-Written (20)
2. Phi-4-mini (Configuration f, W=2 parallel, c=4096, 50 subtasks)
3. SmolLM3-3B (Configuration f, W=2 parallel, c=4096, 50 subtasks)

Zero fabricated numbers. Direct recording from disk and hardware APIs.
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
import concurrent.futures
from typing import List, Dict, Any, Tuple

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.serving.hardware import get_gpu_status
from src.eval.subtask_checkers import evaluate_subtask

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def clean_gpu_state():
    """Stops all loaded Ollama models to ensure clean idle VRAM state."""
    for _ in range(5):
        try:
            proc = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10)
            lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
            if len(lines) <= 1:
                break
            for line in lines[1:]:
                parts = line.split()
                if parts:
                    model_name = parts[0]
                    subprocess.run(["ollama", "stop", model_name], capture_output=True, text=True, timeout=10)
            time.sleep(1.5)
        except Exception as e:
            print(f"Warning during clean_gpu_state: {e}")
            break
    time.sleep(2.0)


def capture_ollama_ps() -> str:
    """Captures and returns raw output of `ollama ps`."""
    try:
        proc = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10)
        return proc.stdout.strip()
    except Exception as e:
        return f"Error running ollama ps: {e}"


def run_qwen3_thinking_on_subtask(
    subtask: Dict[str, Any],
    num_ctx: int,
    max_output_tokens: int,
    host: str = "http://127.0.0.1:11434",
    seed: int = 42,
) -> Dict[str, Any]:
    """Runs a single subtask with thinking enabled and context-safe token budgeting."""
    payload = {
        "model": "qwen3:4b",
        "prompt": subtask["prompt"],
        "stream": False,
        "think": True,
        "options": {
            "seed": seed,
            "temperature": 0.0,
            "num_ctx": num_ctx,
            "num_predict": max_output_tokens,
        },
    }

    req = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "SLM-Engine/1.0"},
    )

    t_start = time.perf_counter()
    error_msg = None
    try:
        with urllib.request.urlopen(req, timeout=600.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        data = {}
        error_msg = str(e)
    t_end = time.perf_counter()

    prompt_tokens = data.get("prompt_eval_count", 0)
    completion_tokens = data.get("eval_count", 0)
    done_reason = data.get("done_reason", "error" if error_msg else "stop")
    thinking_text = data.get("thinking", "") or ""
    response_text = data.get("response", "") or ""

    # An item is truncated if done_reason is length or completion reached limit
    is_truncated = (done_reason == "length") or (completion_tokens >= max_output_tokens)

    # For evaluation, take response text if present; if empty and thinking exists, use thinking
    content_for_eval = response_text.strip()
    if not content_for_eval and thinking_text.strip():
        content_for_eval = thinking_text.strip()

    status = "COMPLETE" if (completion_tokens > 0 and not error_msg) else "FAILED"
    is_correct = False
    checker_name = ""
    check_reason = ""

    if status == "COMPLETE" and content_for_eval and not is_truncated:
        is_correct, checker_name, check_reason = evaluate_subtask(subtask, content_for_eval)
    elif is_truncated:
        # Per Hard Rule 3: truncated generation is FAILED and excluded from valid scoring
        status = "TRUNCATED"
        check_reason = f"Generation truncated at {completion_tokens} tokens (done_reason={done_reason})"
    else:
        check_reason = f"Generation failed: {error_msg or '0 completion tokens'}"

    provenance = subtask.get("provenance", "")
    if not provenance:
        provenance = "agent-written" if subtask.get("benchmark") in ["Spider", "ARC-Challenge"] else "downloaded"

    return {
        "subtask_id": subtask["id"],
        "type": subtask["type"],
        "benchmark": subtask.get("benchmark", ""),
        "provenance": provenance,
        "original_id": subtask.get("original_id", ""),
        "start_timestamp": t_start,
        "end_timestamp": t_end,
        "duration_seconds": round(t_end - t_start, 4),
        "status": status,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "done_reason": done_reason,
        "is_truncated": is_truncated,
        "thinking_tokens_len": len(thinking_text),
        "response_len": len(response_text),
        "is_correct": is_correct,
        "checker": checker_name,
        "reason": check_reason,
        "error": error_msg,
    }


def run_standard_subtask(
    model_id: str,
    subtask: Dict[str, Any],
    max_tokens: int = 512,
    host: str = "http://127.0.0.1:11434",
    seed: int = 42,
) -> Dict[str, Any]:
    """Runs a standard non-thinking or instruction subtask."""
    payload = {
        "model": model_id,
        "prompt": subtask["prompt"],
        "stream": False,
        "think": False,
        "options": {
            "seed": seed,
            "temperature": 0.0,
            "num_predict": max_tokens,
        },
    }

    req = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "SLM-Engine/1.0"},
    )

    t_start = time.perf_counter()
    error_msg = None
    try:
        with urllib.request.urlopen(req, timeout=600.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        data = {}
        error_msg = str(e)
    t_end = time.perf_counter()

    prompt_tokens = data.get("prompt_eval_count", 0)
    completion_tokens = data.get("eval_count", 0)
    done_reason = data.get("done_reason", "error" if error_msg else "stop")
    response_text = data.get("response", "") or ""

    status = "COMPLETE" if (completion_tokens > 0 and not error_msg) else "FAILED"
    is_correct = False
    checker_name = ""
    check_reason = ""

    if status == "COMPLETE" and response_text:
        is_correct, checker_name, check_reason = evaluate_subtask(subtask, response_text.strip())
    else:
        check_reason = f"Generation failed: {error_msg or '0 tokens'}"

    provenance = subtask.get("provenance", "")
    if not provenance:
        provenance = "agent-written" if subtask.get("benchmark") in ["Spider", "ARC-Challenge"] else "downloaded"

    return {
        "subtask_id": subtask["id"],
        "type": subtask["type"],
        "benchmark": subtask.get("benchmark", ""),
        "provenance": provenance,
        "original_id": subtask.get("original_id", ""),
        "start_timestamp": t_start,
        "end_timestamp": t_end,
        "duration_seconds": round(t_end - t_start, 4),
        "status": status,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "done_reason": done_reason,
        "is_truncated": (done_reason == "length"),
        "response_len": len(response_text),
        "is_correct": is_correct,
        "checker": checker_name,
        "reason": check_reason,
        "error": error_msg,
    }


def execute_qwen3_thinking_on_benchmark(subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    print("\n" + "=" * 65)
    print("[Qwen3-4B Thinking On] Starting with context-safe token budget")
    print("=" * 65)

    clean_gpu_state()
    baseline_gpu = get_gpu_status()
    baseline_vram = baseline_gpu.used_vram_mb
    baseline_temp = baseline_gpu.temperature_c
    print(f"  Baseline Idle VRAM: {baseline_vram} MiB, Temp: {baseline_temp}°C")

    # Warmup with num_ctx=6144
    warmup_req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps({"model": "qwen3:4b", "prompt": "Hi", "stream": False, "think": True, "options": {"num_ctx": 6144, "num_predict": 2}}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(warmup_req, timeout=30.0) as _:
            pass
    except Exception as e:
        print(f"  Warmup error: {e}")
    time.sleep(1.0)

    ps_output = capture_ollama_ps()
    print(f"  [ollama ps Output]:\n{ps_output}")

    peak_vram = baseline_vram
    peak_temp = baseline_temp
    results = []

    print(f"  Executing {len(subtasks)} subtasks (num_ctx=6144, max_output=4096, W=1 serial)...")
    wall_start = time.perf_counter()

    # Execute serially to prevent any VRAM spill at 6144 context on 6GB GPU
    for idx, item in enumerate(subtasks, start=1):
        res = run_qwen3_thinking_on_subtask(item, num_ctx=6144, max_output_tokens=4096)
        results.append(res)
        gpu = get_gpu_status()
        if gpu.used_vram_mb > peak_vram:
            peak_vram = gpu.used_vram_mb
        if gpu.temperature_c > peak_temp:
            peak_temp = gpu.temperature_c

        status_str = "PASS" if res["is_correct"] else ("TRUNCATED" if res["is_truncated"] else "FAIL")
        print(f"    [{idx:02d}/{len(subtasks)}] {res['subtask_id']} ({res['benchmark']}|{res['provenance']}): {status_str} ({res['duration_seconds']}s, {res['completion_tokens']} tok)")

    wall_end = time.perf_counter()
    wall_elapsed = wall_end - wall_start

    total_count = len(subtasks)
    truncated_count = sum(1 for r in results if r["is_truncated"])
    valid_count = total_count - truncated_count

    valid_correct = sum(1 for r in results if r["is_correct"] and not r["is_truncated"])
    valid_acc_pct = round((valid_correct / valid_count) * 100, 1) if valid_count > 0 else 0.0

    # Stratified: Downloaded vs Agent-Written
    down_results = [r for r in results if r["provenance"] == "downloaded"]
    agent_results = [r for r in results if r["provenance"] == "agent-written"]

    down_trunc = sum(1 for r in down_results if r["is_truncated"])
    down_valid = len(down_results) - down_trunc
    down_correct = sum(1 for r in down_results if r["is_correct"] and not r["is_truncated"])
    down_acc_pct = round((down_correct / down_valid) * 100, 1) if down_valid > 0 else 0.0

    agent_trunc = sum(1 for r in agent_results if r["is_truncated"])
    agent_valid = len(agent_results) - agent_trunc
    agent_correct = sum(1 for r in agent_results if r["is_correct"] and not r["is_truncated"])
    agent_acc_pct = round((agent_correct / agent_valid) * 100, 1) if agent_valid > 0 else 0.0

    clean_gpu_state()

    print("\n" + "=" * 65)
    print("  Qwen3-4B (Thinking On) Summary:")
    print(f"  Wall Time: {round(wall_elapsed, 2)} s")
    print(f"  Truncated Items (Excluded): {truncated_count}/{total_count}")
    print(f"  Valid Scored Items: {valid_count}/{total_count}")
    print(f"  Valid Accuracy: {valid_correct}/{valid_count} ({valid_acc_pct}%)")
    print(f"  - Downloaded Items: {down_correct}/{down_valid} ({down_acc_pct}%) [Truncated: {down_trunc}]")
    print(f"  - Agent-Written Items: {agent_correct}/{agent_valid} ({agent_acc_pct}%) [Truncated: {agent_trunc}]")
    print(f"  Peak VRAM: {peak_vram} MiB")
    print("=" * 65)

    return {
        "model_id": "qwen3:4b",
        "mode": "thinking_on",
        "num_ctx": 6144,
        "max_output_tokens": 4096,
        "total_subtasks": total_count,
        "truncated_items": truncated_count,
        "valid_items": valid_count,
        "valid_correct": valid_correct,
        "valid_accuracy_pct": valid_acc_pct,
        "downloaded_total": len(down_results),
        "downloaded_truncated": down_trunc,
        "downloaded_valid": down_valid,
        "downloaded_correct": down_correct,
        "downloaded_accuracy_pct": down_acc_pct,
        "agent_written_total": len(agent_results),
        "agent_written_truncated": agent_trunc,
        "agent_written_valid": agent_valid,
        "agent_written_correct": agent_correct,
        "agent_written_accuracy_pct": agent_acc_pct,
        "wall_elapsed_seconds": round(wall_elapsed, 2),
        "peak_vram_mb": peak_vram,
        "ollama_ps_output": ps_output,
        "subtask_results": results,
    }


def execute_reference_model_benchmark(model_id: str, model_label: str, subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    print("\n" + "=" * 65)
    print(f"[{model_id}] Starting Reference Benchmark: {model_label}")
    print("=" * 65)

    clean_gpu_state()
    baseline_gpu = get_gpu_status()
    baseline_vram = baseline_gpu.used_vram_mb
    baseline_temp = baseline_gpu.temperature_c
    print(f"  Baseline Idle VRAM: {baseline_vram} MiB, Temp: {baseline_temp}°C")

    # Warmup
    warmup_req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps({"model": model_id, "prompt": "Hi", "stream": False, "options": {"num_predict": 2}}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(warmup_req, timeout=30.0) as _:
            pass
    except Exception:
        pass
    time.sleep(1.0)

    ps_output = capture_ollama_ps()
    print(f"  [ollama ps Output]:\n{ps_output}")

    peak_vram = baseline_vram
    peak_temp = baseline_temp
    results = []

    print(f"  Executing {len(subtasks)} subtasks with W=2 parallel slots (c=4096)...")
    wall_start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_to_item = {
            executor.submit(run_standard_subtask, model_id, item, 512): item["id"]
            for item in subtasks
        }
        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_item):
            completed_count += 1
            res = future.result()
            results.append(res)
            gpu = get_gpu_status()
            if gpu.used_vram_mb > peak_vram:
                peak_vram = gpu.used_vram_mb
            if gpu.temperature_c > peak_temp:
                peak_temp = gpu.temperature_c
            verdict_str = "PASS" if res["is_correct"] else "FAIL"
            print(f"    [{completed_count:02d}/{len(subtasks)}] {res['subtask_id']} ({res['benchmark']}|{res['provenance']}): {verdict_str} ({res['duration_seconds']}s, {res['completion_tokens']} tok)")

    wall_end = time.perf_counter()
    wall_elapsed = wall_end - wall_start

    t_min = min(r["start_timestamp"] for r in results)
    t_max = max(r["end_timestamp"] for r in results)
    active_window = t_max - t_min
    total_duration = sum(r["duration_seconds"] for r in results)
    mean_concurrency = round(total_duration / active_window, 2) if active_window > 0 else 1.0

    total_count = len(subtasks)
    correct_total = sum(1 for r in results if r["is_correct"])
    acc_total = round((correct_total / total_count) * 100, 1)

    down_results = [r for r in results if r["provenance"] == "downloaded"]
    agent_results = [r for r in results if r["provenance"] == "agent-written"]

    down_correct = sum(1 for r in down_results if r["is_correct"])
    down_acc = round((down_correct / len(down_results)) * 100, 1) if down_results else 0.0

    agent_correct = sum(1 for r in agent_results if r["is_correct"])
    agent_acc = round((agent_correct / len(agent_results)) * 100, 1) if agent_results else 0.0

    clean_gpu_state()

    print("\n" + "=" * 65)
    print(f"  Summary for {model_label}:")
    print(f"  Wall Time: {round(wall_elapsed, 2)} s")
    print(f"  Overall Accuracy: {correct_total}/{total_count} ({acc_total}%)")
    print(f"  - Downloaded Items: {down_correct}/{len(down_results)} ({down_acc}%)")
    print(f"  - Agent-Written Items: {agent_correct}/{len(agent_results)} ({agent_acc}%)")
    print(f"  Mean Concurrency: {mean_concurrency} | Peak VRAM: {peak_vram} MiB")
    print("=" * 65)

    return {
        "model_id": model_id,
        "model_label": model_label,
        "total_subtasks": total_count,
        "correct_subtasks": correct_total,
        "accuracy_pct": acc_total,
        "downloaded_total": len(down_results),
        "downloaded_correct": down_correct,
        "downloaded_accuracy_pct": down_acc,
        "agent_written_total": len(agent_results),
        "agent_written_correct": agent_correct,
        "agent_written_accuracy_pct": agent_acc,
        "wall_elapsed_seconds": round(wall_elapsed, 2),
        "mean_concurrency": mean_concurrency,
        "peak_vram_mb": peak_vram,
        "ollama_ps_output": ps_output,
        "subtask_results": results,
    }


def main():
    subtasks_path = os.path.join(REPO_ROOT, "data", "benchmark_50_hard_subtasks.json")
    with open(subtasks_path, "r", encoding="utf-8") as f:
        subtasks = json.load(f)

    # 1. Qwen3-4B Thinking On
    qwen3_thinking_res = execute_qwen3_thinking_on_benchmark(subtasks)
    with open(os.path.join(REPO_ROOT, "results", "benchmarks", "qwen3_4b_thinking_on_50.json"), "w", encoding="utf-8") as f:
        json.dump(qwen3_thinking_res, f, indent=2)

    # 2. Phi-4-mini Full Rerun
    phi4_res = execute_reference_model_benchmark("phi4-mini:latest", "Phi-4-mini (Configuration f, W=2, c=4096)", subtasks)
    with open(os.path.join(REPO_ROOT, "results", "benchmarks", "phi4_mini_50.json"), "w", encoding="utf-8") as f:
        json.dump(phi4_res, f, indent=2)

    # 3. SmolLM3 Full Rerun
    smollm3_res = execute_reference_model_benchmark("pedrolucas/smollm3:3b-q4_k_m", "SmolLM3-3B (Configuration f, W=2, c=4096)", subtasks)
    with open(os.path.join(REPO_ROOT, "results", "benchmarks", "smollm3_3b_50.json"), "w", encoding="utf-8") as f:
        json.dump(smollm3_res, f, indent=2)

    print("\nAll benchmark runs completed successfully.")


if __name__ == "__main__":
    main()
