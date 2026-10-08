"""
Benchmark Phi-4-mini with 3 parallel request slots (W=3, c=4096) on the 50 hard subtasks.
Zero fabricated numbers. Direct recording from disk and hardware APIs.
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
import concurrent.futures
from typing import List, Dict, Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
from src.serving.hardware import get_gpu_status
from src.eval.subtask_checkers import evaluate_subtask

MODEL_ID = "phi4-mini:latest"
CONTEXT_LENGTH = 4096
WORKERS = 3


def clean_gpu_state():
    for _ in range(5):
        try:
            proc = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10)
            lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
            if len(lines) <= 1:
                break
            for line in lines[1:]:
                parts = line.split()
                if parts:
                    subprocess.run(["ollama", "stop", parts[0]], capture_output=True, text=True, timeout=10)
            time.sleep(1.5)
        except Exception:
            break
    time.sleep(2.0)


def capture_ollama_ps() -> str:
    try:
        proc = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10)
        return proc.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def run_single_subtask(subtask: Dict[str, Any], host: str = "http://127.0.0.1:11434") -> Dict[str, Any]:
    payload = {
        "model": MODEL_ID,
        "prompt": subtask["prompt"],
        "stream": False,
        "options": {
            "seed": 42,
            "temperature": 0.0,
            "num_ctx": CONTEXT_LENGTH,
            "num_predict": 512,
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
        with urllib.request.urlopen(req, timeout=300.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        data = {}
        error_msg = str(e)
    t_end = time.perf_counter()

    prompt_tokens = data.get("prompt_eval_count", 0)
    completion_tokens = data.get("eval_count", 0)
    done_reason = data.get("done_reason", "error" if error_msg else "stop")
    response_text = (data.get("response", "") or "").strip()

    status = "COMPLETE" if (completion_tokens > 0 and not error_msg) else "FAILED"
    is_truncated = (done_reason == "length")
    is_correct = False
    checker_name = ""
    check_reason = ""

    if status == "COMPLETE" and response_text:
        is_correct, checker_name, check_reason = evaluate_subtask(subtask, response_text)
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
        "is_truncated": is_truncated,
        "response_len": len(response_text),
        "is_correct": is_correct,
        "checker": checker_name,
        "reason": check_reason,
        "error": error_msg,
    }


def main():
    subtasks_path = os.path.join(REPO_ROOT, "data", "benchmark_50_hard_subtasks.json")
    with open(subtasks_path, "r", encoding="utf-8") as f:
        subtasks = json.load(f)

    print("=" * 65)
    print(f"Phi-4-mini Parallel Benchmark (W={WORKERS} slots, c={CONTEXT_LENGTH})")
    print("=" * 65)

    clean_gpu_state()
    baseline_gpu = get_gpu_status()
    baseline_vram = baseline_gpu.used_vram_mb
    baseline_temp = baseline_gpu.temperature_c
    print(f"  Baseline Idle VRAM: {baseline_vram} MiB, Temp: {baseline_temp}°C")

    # Warmup
    warmup_req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps({"model": MODEL_ID, "prompt": "Hi", "stream": False, "options": {"num_ctx": CONTEXT_LENGTH, "num_predict": 2}}).encode("utf-8"),
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
    results = [None] * len(subtasks)

    print(f"  Executing {len(subtasks)} subtasks with {WORKERS} parallel workers...")
    wall_start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        future_to_idx = {executor.submit(run_single_subtask, item): i for i, item in enumerate(subtasks)}
        done_count = 0
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            res = future.result()
            results[idx] = res
            done_count += 1

            gpu = get_gpu_status()
            if gpu.used_vram_mb > peak_vram:
                peak_vram = gpu.used_vram_mb
            if gpu.temperature_c > peak_temp:
                peak_temp = gpu.temperature_c

            status_str = "PASS" if res["is_correct"] else "FAIL"
            trunc_str = " [TRUNCATED]" if res["is_truncated"] else ""
            print(f"    [{done_count:02d}/{len(subtasks)}] {res['subtask_id']} ({res['benchmark']}|{res['provenance']}): {status_str} ({res['duration_seconds']}s, {res['completion_tokens']} tok){trunc_str}")

    wall_end = time.perf_counter()
    wall_elapsed = wall_end - wall_start

    t_min = min(r["start_timestamp"] for r in results)
    t_max = max(r["end_timestamp"] for r in results)
    active_window = t_max - t_min
    total_duration = sum(r["duration_seconds"] for r in results)
    mean_concurrency = round(total_duration / active_window, 2) if active_window > 0 else 1.0

    total_count = len(subtasks)
    truncated_count = sum(1 for r in results if r["is_truncated"])
    valid_count = total_count - truncated_count

    # Metric A: Truncated excluded
    valid_correct = sum(1 for r in results if r["is_correct"] and not r["is_truncated"])
    valid_acc_pct = round(valid_correct / valid_count * 100, 1) if valid_count > 0 else 0.0

    # Metric B: Truncated counted as failures
    total_correct = sum(1 for r in results if r["is_correct"])
    total_acc_pct = round(total_correct / total_count * 100, 1) if total_count > 0 else 0.0

    down_results = [r for r in results if r["provenance"] == "downloaded"]
    agent_results = [r for r in results if r["provenance"] == "agent-written"]

    down_trunc = sum(1 for r in down_results if r["is_truncated"])
    down_valid = len(down_results) - down_trunc
    down_correct = sum(1 for r in down_results if r["is_correct"])
    down_acc_valid = round(down_correct / down_valid * 100, 1) if down_valid > 0 else 0.0
    down_acc_total = round(down_correct / len(down_results) * 100, 1) if down_results else 0.0

    agent_trunc = sum(1 for r in agent_results if r["is_truncated"])
    agent_valid = len(agent_results) - agent_trunc
    agent_correct = sum(1 for r in agent_results if r["is_correct"])
    agent_acc_valid = round(agent_correct / agent_valid * 100, 1) if agent_valid > 0 else 0.0
    agent_acc_total = round(agent_correct / len(agent_results) * 100, 1) if agent_results else 0.0

    throughput = round(total_count / wall_elapsed, 4)

    print("\n" + "=" * 65)
    print("BENCHMARK RESULTS SUMMARY:")
    print(f"  Configuration: Phi-4-mini (W={WORKERS} slots, c={CONTEXT_LENGTH})")
    print(f"  Wall Time: {wall_elapsed:.2f} s")
    print(f"  Throughput: {throughput} subtasks/s")
    print(f"  Active Execution Window: {active_window:.2f} s")
    print(f"  Measured Concurrency: {mean_concurrency:.2f} (Target: ~{WORKERS}.0)")
    print(f"  Peak Hardware VRAM: {peak_vram} MiB (Baseline: {baseline_vram} MiB)")
    print(f"  Truncated Items: {truncated_count}/{total_count}")
    print(f"  Acc (Valid, truncated excluded): {valid_correct}/{valid_count} ({valid_acc_pct}%)")
    print(f"  Acc (Total, truncated as fail):  {total_correct}/{total_count} ({total_acc_pct}%)")
    print(f"  Downloaded Subtasks: Valid={down_correct}/{down_valid} ({down_acc_valid}%) | Total={down_correct}/{len(down_results)} ({down_acc_total}%)")
    print(f"  Agent-Written Subtasks: Valid={agent_correct}/{agent_valid} ({agent_acc_valid}%) | Total={agent_correct}/{len(agent_results)} ({agent_acc_total}%)")
    print("=" * 65)

    final_record = {
        "model_id": MODEL_ID,
        "model_label": f"Phi-4-mini (Configuration f, W={WORKERS}, c={CONTEXT_LENGTH})",
        "context_length": CONTEXT_LENGTH,
        "workers": WORKERS,
        "baseline_vram_mb": baseline_vram,
        "peak_vram_mb": peak_vram,
        "wall_elapsed_seconds": round(wall_elapsed, 2),
        "active_window_seconds": round(active_window, 2),
        "total_task_duration_seconds": round(total_duration, 2),
        "throughput_subtasks_per_sec": throughput,
        "mean_concurrency": mean_concurrency,
        "ollama_ps_output": ps_output,
        "total_items": total_count,
        "truncated_items": truncated_count,
        "valid_items": valid_count,
        "valid_correct": valid_correct,
        "valid_accuracy_pct": valid_acc_pct,
        "total_correct": total_correct,
        "total_accuracy_pct": total_acc_pct,
        "downloaded_total": len(down_results),
        "downloaded_truncated": down_trunc,
        "downloaded_correct_valid": down_correct,
        "downloaded_acc_valid_pct": down_acc_valid,
        "downloaded_correct_total": down_correct,
        "downloaded_acc_total_pct": down_acc_total,
        "agent_total": len(agent_results),
        "agent_truncated": agent_trunc,
        "agent_correct_valid": agent_correct,
        "agent_acc_valid_pct": agent_acc_valid,
        "agent_correct_total": agent_correct,
        "agent_acc_total_pct": agent_acc_total,
        "subtask_results": results,
    }

    out_file = os.path.join(REPO_ROOT, "results", "benchmarks", "phi4_mini_w3_50.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_record, f, indent=2)
    print(f"\nSaved raw benchmark record to: {out_file}")


if __name__ == "__main__":
    main()

