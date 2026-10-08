"""
Benchmark Qwen3-4B in both modes on 50 hard subtasks under Configuration (f):
- Mode 1: Thinking Off (think=False, max_tokens=512)
- Mode 2: Thinking On (think=True, max_tokens=4096)

Reports:
- Overall accuracy (50 items)
- Downloaded items accuracy (30 items: HumanEval + GSM8K)
- Agent-written items accuracy (20 items: Spider + ARC)
- Wall clock time and throughput
- Exact count of items hitting token limit in thinking mode
- Measured concurrency and peak VRAM

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

MODEL_ID = "qwen3:4b"
CONTEXT_LENGTH = 4096
NUM_WORKERS = 2  # Approved Configuration (f)


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


def run_single_qwen3_subtask(
    subtask: Dict[str, Any],
    think_mode: bool,
    max_tokens: int,
    host: str = "http://127.0.0.1:11434",
    seed: int = 42,
) -> Dict[str, Any]:
    """Generates response for a single subtask and evaluates correctness."""
    payload = {
        "model": MODEL_ID,
        "prompt": subtask["prompt"],
        "stream": False,
        "think": think_mode,
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
    thinking_text = data.get("thinking", "") or ""
    response_text = data.get("response", "") or ""

    # Check if item hit token limit
    hit_limit = (done_reason == "length") or (completion_tokens >= max_tokens)

    # For evaluation, prefer response text; if empty and thinking exists, fall back to thinking
    content_for_eval = response_text.strip()
    if not content_for_eval and thinking_text.strip():
        content_for_eval = thinking_text.strip()

    status = "COMPLETE" if (completion_tokens > 0 and not error_msg) else "FAILED"
    is_correct = False
    checker_name = ""
    check_reason = ""

    if status == "COMPLETE" and content_for_eval:
        is_correct, checker_name, check_reason = evaluate_subtask(subtask, content_for_eval)
    else:
        check_reason = f"Empty generation or error: {error_msg or '0 tokens'}"

    # Determine provenance category
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
        "hit_limit": hit_limit,
        "thinking_tokens_len": len(thinking_text),
        "response_len": len(response_text),
        "is_correct": is_correct,
        "checker": checker_name,
        "reason": check_reason,
        "error": error_msg,
    }


def execute_mode_benchmark(
    mode_id: str,
    mode_label: str,
    think_mode: bool,
    max_tokens: int,
    subtasks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    print(f"\n=================================================================")
    print(f"[{mode_id}] Starting: {mode_label} (max_tokens={max_tokens})")
    print(f"=================================================================")

    clean_gpu_state()
    baseline_gpu = get_gpu_status()
    baseline_vram = baseline_gpu.used_vram_mb
    baseline_temp = baseline_gpu.temperature_c
    print(f"  Baseline Idle VRAM: {baseline_vram} MiB, Temp: {baseline_temp}°C")

    # Warmup
    warmup_req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps({"model": MODEL_ID, "prompt": "Hi", "stream": False, "think": think_mode, "options": {"num_predict": 2}}).encode("utf-8"),
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

    print(f"  Executing {len(subtasks)} subtasks with W={NUM_WORKERS} parallel slots...")
    wall_start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        future_to_item = {
            executor.submit(run_single_qwen3_subtask, item, think_mode, max_tokens): item["id"]
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
            limit_str = " [HIT LIMIT]" if res["hit_limit"] else ""
            print(f"    [{completed_count:02d}/{len(subtasks)}] {res['subtask_id']} ({res['benchmark']}|{res['provenance']}): {verdict_str} ({res['duration_seconds']}s, {res['completion_tokens']} tok){limit_str}")

    wall_end = time.perf_counter()
    wall_elapsed = wall_end - wall_start

    # Concurrency calculation
    t_min = min(r["start_timestamp"] for r in results)
    t_max = max(r["end_timestamp"] for r in results)
    active_window = t_max - t_min
    total_duration = sum(r["duration_seconds"] for r in results)
    mean_concurrency = round(total_duration / active_window, 2) if active_window > 0 else 1.0

    total_count = len(subtasks)
    correct_total = sum(1 for r in results if r["is_correct"])
    acc_total = round((correct_total / total_count) * 100, 1)

    # Stratified Accuracy: Downloaded (30 items) vs Agent-Written (20 items)
    downloaded_results = [r for r in results if r["provenance"] == "downloaded"]
    agent_written_results = [r for r in results if r["provenance"] == "agent-written"]

    correct_downloaded = sum(1 for r in downloaded_results if r["is_correct"])
    acc_downloaded = round((correct_downloaded / len(downloaded_results)) * 100, 1) if downloaded_results else 0.0

    correct_agent = sum(1 for r in agent_written_results if r["is_correct"])
    acc_agent = round((correct_agent / len(agent_written_results)) * 100, 1) if agent_written_results else 0.0

    # Limit hit count
    items_hit_limit = sum(1 for r in results if r["hit_limit"])

    clean_gpu_state()

    print("\n" + "=" * 65)
    print(f"  Summary for {mode_label}:")
    print(f"  Elapsed Time: {round(wall_elapsed, 2)} s (Avg: {round(wall_elapsed/total_count, 2)} s/item)")
    print(f"  Overall Accuracy: {correct_total}/{total_count} ({acc_total}%)")
    print(f"  - Downloaded Items (30): {correct_downloaded}/{len(downloaded_results)} ({acc_downloaded}%)")
    print(f"  - Agent-Written Items (20): {correct_agent}/{len(agent_written_results)} ({acc_agent}%)")
    print(f"  Items Hitting Token Limit: {items_hit_limit}/{total_count}")
    print(f"  Mean Concurrency: {mean_concurrency} | Peak VRAM: {peak_vram} MiB")
    print("=" * 65)

    return {
        "mode_id": mode_id,
        "mode_label": mode_label,
        "think_mode": think_mode,
        "max_tokens": max_tokens,
        "model_id": MODEL_ID,
        "total_subtasks": total_count,
        "wall_elapsed_seconds": round(wall_elapsed, 2),
        "mean_concurrency": mean_concurrency,
        "peak_vram_mb": peak_vram,
        "delta_vram_mb": peak_vram - baseline_vram,
        "ollama_ps_output": ps_output,
        "overall_correct": correct_total,
        "overall_accuracy_pct": acc_total,
        "downloaded_total": len(downloaded_results),
        "downloaded_correct": correct_downloaded,
        "downloaded_accuracy_pct": acc_downloaded,
        "agent_written_total": len(agent_written_results),
        "agent_written_correct": correct_agent,
        "agent_written_accuracy_pct": acc_agent,
        "items_hit_limit": items_hit_limit,
        "subtask_results": results,
    }


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    subtasks_path = os.path.join(repo_root, "data", "benchmark_50_hard_subtasks.json")
    with open(subtasks_path, "r", encoding="utf-8") as f:
        subtasks = json.load(f)

    # 1. Mode 1: Thinking Off
    mode1_res = execute_mode_benchmark(
        mode_id="qwen3_4b_thinking_off",
        mode_label="Qwen3-4B (Thinking Off)",
        think_mode=False,
        max_tokens=768,
        subtasks=subtasks,
    )
    out1 = os.path.join(repo_root, "results", "benchmarks", "qwen3_4b_thinking_off_50.json")
    with open(out1, "w", encoding="utf-8") as f:
        json.dump(mode1_res, f, indent=2)

    # 2. Mode 2: Thinking On
    mode2_res = execute_mode_benchmark(
        mode_id="qwen3_4b_thinking_on",
        mode_label="Qwen3-4B (Thinking On)",
        think_mode=True,
        max_tokens=4096,
        subtasks=subtasks,
    )
    out2 = os.path.join(repo_root, "results", "benchmarks", "qwen3_4b_thinking_on_50.json")
    with open(out2, "w", encoding="utf-8") as f:
        json.dump(mode2_res, f, indent=2)

    print("\nAll Qwen3-4B mode benchmarks completed and saved successfully.")


if __name__ == "__main__":
    main()

