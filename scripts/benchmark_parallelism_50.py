"""
Benchmark script for Config (f) and Serial (f) on 50 hard public benchmark subtasks.
Evaluates:
- llama3.2:3b (Config f: W=2 parallel, c=4096)
- llama3.2:3b (Config f-serial: W=1 serial, c=4096)
- qwen2.5:7b-instruct-q3_k_m (Config f: W=2 parallel, c=4096)
- qwen2.5:7b-instruct-q3_k_m (Config f-serial: W=1 serial, c=4096)

Zero fabricated numbers. Direct recording from disk and hardware APIs.
"""

import os
import sys
import json
import time
import subprocess
import concurrent.futures
from typing import List, Dict, Any, Tuple

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.serving.hardware import get_gpu_status
from src.serving.ollama_client import OllamaClient
from src.eval.subtask_checkers import evaluate_subtask

CONTEXT_LENGTH = 4096


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


def verify_100_percent_gpu(ps_output: str, models: List[str]) -> Tuple[bool, str]:
    """Verifies that all loaded models have 100% GPU in ollama ps output."""
    if not ps_output:
        return False, "ollama ps output is empty"

    for model in models:
        model_found = False
        for line in ps_output.splitlines():
            if model in line:
                model_found = True
                if "100% GPU" not in line and "100% gpu" not in line.lower():
                    return False, f"Model {model} does not show 100% GPU: {line}"
                break
        if not model_found:
            return False, f"Model {model} not found in ollama ps output"
    return True, "All models confirmed 100% GPU"


def run_single_subtask(
    client: OllamaClient,
    model_id: str,
    subtask: Dict[str, Any],
    seed: int = 42,
) -> Dict[str, Any]:
    """Executes a single subtask, logs exact start/end timestamps and evaluates accuracy."""
    t_start = time.perf_counter()
    resp = client.generate(
        model_id=model_id,
        prompt=subtask["prompt"],
        seed=seed,
        temperature=0.0,
        max_tokens=384,
    )
    t_end = time.perf_counter()

    is_correct, checker_name, check_reason = evaluate_subtask(subtask, resp.content)

    return {
        "subtask_id": subtask["id"],
        "type": subtask["type"],
        "benchmark": subtask.get("benchmark", ""),
        "original_id": subtask.get("original_id", ""),
        "model": model_id,
        "start_timestamp": t_start,
        "end_timestamp": t_end,
        "duration_seconds": round(t_end - t_start, 4),
        "status": resp.status,
        "tokens": resp.completion_tokens,
        "is_correct": is_correct,
        "checker": checker_name,
        "reason": check_reason,
        "error": resp.error_message,
    }


def execute_configuration_benchmark(
    config_id: str,
    config_name: str,
    models: List[str],
    subtasks: List[Dict[str, Any]],
    max_workers: int,
    client: OllamaClient,
) -> Dict[str, Any]:
    """Executes benchmark for a single configuration."""
    print(f"\n=======================================================")
    print(f"[{config_id}] Preparing: {config_name}")
    print(f"=======================================================")

    clean_gpu_state()
    baseline_gpu = get_gpu_status()
    baseline_vram = baseline_gpu.used_vram_mb
    baseline_temp = baseline_gpu.temperature_c
    print(f"  Baseline Idle VRAM: {baseline_vram} MiB, Temp: {baseline_temp}°C")

    # Warm up model
    for m in models:
        client.generate(model_id=m, prompt="Hello", seed=42, max_tokens=2)
    time.sleep(1.0)

    ps_output = capture_ollama_ps()
    print(f"  [ollama ps Output]:\n{ps_output}")
    gpu_verified, gpu_reason = verify_100_percent_gpu(ps_output, models)
    if not gpu_verified:
        print(f"  WARNING: GPU offload verification issue: {gpu_reason}")

    peak_vram = baseline_vram
    peak_temp = baseline_temp
    results = []

    print(f"  Executing {len(subtasks)} subtasks with max_workers={max_workers} (context={CONTEXT_LENGTH})...")
    wall_start = time.perf_counter()

    if max_workers == 1:
        for idx, item in enumerate(subtasks, start=1):
            m = models[0]
            res = run_single_subtask(client, m, item, seed=42)
            results.append(res)
            gpu = get_gpu_status()
            if gpu.used_vram_mb > peak_vram:
                peak_vram = gpu.used_vram_mb
            if gpu.temperature_c > peak_temp:
                peak_temp = gpu.temperature_c
            verdict_str = "PASS" if res["is_correct"] else "FAIL"
            print(f"    [{idx}/{len(subtasks)}] {res['subtask_id']} ({res['benchmark']}) {m}: {verdict_str} ({res['duration_seconds']}s)")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(run_single_subtask, client, models[0], item, seed=42): item["id"]
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
                print(f"    [{completed_count}/{len(subtasks)}] {res['subtask_id']} ({res['benchmark']}) {res['model']}: {verdict_str} ({res['duration_seconds']}s)")

    wall_end = time.perf_counter()
    wall_elapsed = wall_end - wall_start

    # Concurrency calculation
    if max_workers == 1:
        mean_concurrency = 1.0
    else:
        t_min = min(r["start_timestamp"] for r in results)
        t_max = max(r["end_timestamp"] for r in results)
        active_window = t_max - t_min
        total_duration = sum(r["duration_seconds"] for r in results)
        mean_concurrency = round(total_duration / active_window, 2) if active_window > 0 else 1.0

    successful_tasks = sum(1 for r in results if r["status"] == "COMPLETE")
    correct_tasks = sum(1 for r in results if r["is_correct"])
    accuracy_pct = round((correct_tasks / len(subtasks)) * 100, 1)
    throughput = round(len(subtasks) / wall_elapsed, 4) if wall_elapsed > 0 else 0.0

    disqualified = False
    disq_reason = ""
    if peak_vram >= 6000:
        disqualified = True
        disq_reason = f"Peak VRAM ({peak_vram} MiB) exceeded safe limit; spilled to CPU"
    elif not gpu_verified:
        disqualified = True
        disq_reason = f"GPU offload check failed: {gpu_reason}"
    elif successful_tasks < len(subtasks):
        disqualified = True
        disq_reason = f"{len(subtasks) - successful_tasks} requests failed"

    clean_gpu_state()

    print(f"\n  Summary: Elapsed={round(wall_elapsed, 2)}s, Throughput={throughput} subtasks/s")
    print(f"  Concurrency={mean_concurrency}, Peak VRAM={peak_vram} MiB, Accuracy={correct_tasks}/{len(subtasks)} ({accuracy_pct}%)")

    return {
        "config_id": config_id,
        "config_name": config_name,
        "context_length": CONTEXT_LENGTH,
        "models_used": models,
        "max_workers": max_workers,
        "total_subtasks": len(subtasks),
        "successful_subtasks": successful_tasks,
        "correct_subtasks": correct_tasks,
        "accuracy_percent": accuracy_pct,
        "elapsed_seconds": round(wall_elapsed, 2),
        "throughput_subtasks_per_sec": throughput,
        "mean_concurrency": mean_concurrency,
        "baseline_vram_mb": baseline_vram,
        "peak_vram_mb": peak_vram,
        "delta_vram_mb": peak_vram - baseline_vram,
        "start_temp_c": baseline_temp,
        "peak_temp_c": peak_temp,
        "ollama_ps_output": ps_output,
        "disqualified": disqualified,
        "disqualification_reason": disq_reason,
        "subtask_results": results,
    }


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    subtasks_path = os.path.join(repo_root, "data", "benchmark_50_hard_subtasks.json")
    with open(subtasks_path, "r", encoding="utf-8") as f:
        subtasks = json.load(f)

    client = OllamaClient()
    if not client.ensure_server_running():
        print("ERROR: Ollama server is not running.")
        sys.exit(1)

    print(f"Running benchmark on {len(subtasks)} hard subtasks...")

    # 1. Config (f) - Llama-3.2-3B parallel W=2
    f_llama_parallel = execute_configuration_benchmark(
        config_id="config_f_llama32_parallel",
        config_name="(f) Llama-3.2-3B (2 parallel slots, c=4096)",
        models=["llama3.2:3b"],
        subtasks=subtasks,
        max_workers=2,
        client=client,
    )

    # 2. Config (f-serial) - Llama-3.2-3B serial W=1
    f_llama_serial = execute_configuration_benchmark(
        config_id="config_f_llama32_serial",
        config_name="(f-serial) Llama-3.2-3B (1 serial slot, c=4096)",
        models=["llama3.2:3b"],
        subtasks=subtasks,
        max_workers=1,
        client=client,
    )

    # 3. Config (f) - Qwen2.5-7B-Instruct-Q3 parallel W=2
    f_qwen7b_parallel = execute_configuration_benchmark(
        config_id="config_f_qwen7b_q3_parallel",
        config_name="(f) Qwen2.5-7B-Instruct-Q3 (2 parallel slots, c=4096)",
        models=["qwen2.5:7b-instruct-q3_k_m"],
        subtasks=subtasks,
        max_workers=2,
        client=client,
    )

    # 4. Config (f-serial) - Qwen2.5-7B-Instruct-Q3 serial W=1
    f_qwen7b_serial = execute_configuration_benchmark(
        config_id="config_f_qwen7b_q3_serial",
        config_name="(f-serial) Qwen2.5-7B-Instruct-Q3 (1 serial slot, c=4096)",
        models=["qwen2.5:7b-instruct-q3_k_m"],
        subtasks=subtasks,
        max_workers=1,
        client=client,
    )

    out_file = os.path.join(repo_root, "results", "benchmarks", "parallelism_benchmark_50.json")
    results = [f_llama_parallel, f_llama_serial, f_qwen7b_parallel, f_qwen7b_serial]
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved all results to {out_file}")


if __name__ == "__main__":
    main()

