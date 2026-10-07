"""
Benchmark script for laptop concurrency configurations on 20 public benchmark dev subtasks.
Context length: >= 4,096 tokens per request across all configurations.

Evaluates 8 configurations:
- (a) Two bases <= 4B co-loaded (Phi-3.5 + Llama-3.2-3B, W=2, c=4096)
- (b) Three bases <= 3B co-loaded (Qwen-1.5B + Llama-3.2-3B + Qwen-Coder-3B, W=3, c=4096)
- (b-serial) Serial run of (b) (Qwen-1.5B + Llama-3.2-3B + Qwen-Coder-3B, W=1, c=4096)
- (c) One 8B base with 2 parallel request slots (Llama-3.1-8B, W=2, c=4096)
- (d) Fully serial reference (Llama-3.1-8B, W=1, c=4096)
- (e) Same two models as (a), serial (Phi-3.5 + Llama-3.2-3B, W=1, c=4096)
- (f) One <= 4B base with 2 parallel slots (Llama-3.2-3B, W=2, c=4096)
- (g) Two <= 4B bases loaded one at a time, swapping between waves (Phi-3.5 wave 1 -> Llama-3.2 wave 2, W=1, c=4096)

Zero fabricated numbers.
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

    # 1. Reset GPU state
    clean_gpu_state()
    baseline_gpu = get_gpu_status()
    baseline_vram = baseline_gpu.used_vram_mb
    baseline_temp = baseline_gpu.temperature_c
    print(f"  Baseline Idle VRAM: {baseline_vram} MiB, Temp: {baseline_temp}°C")

    # 2. Warm up models
    print(f"  Warming up {len(models)} model(s) to verify GPU allocation...")
    for m in models:
        client.generate(model_id=m, prompt="Hello", seed=42, max_tokens=2)
    time.sleep(1.0)

    ps_output = capture_ollama_ps()
    print(f"  [ollama ps Output]:\n{ps_output}")
    gpu_verified, gpu_reason = verify_100_percent_gpu(ps_output, models)
    if not gpu_verified:
        print(f"  WARNING: GPU offload verification issue: {gpu_reason}")

    # Map subtasks to models round-robin
    task_model_pairs = []
    for idx, item in enumerate(subtasks):
        model = models[idx % len(models)]
        task_model_pairs.append((item, model))

    peak_vram = baseline_vram
    peak_temp = baseline_temp
    results = []

    print(f"  Executing {len(subtasks)} subtasks with max_workers={max_workers} (context={CONTEXT_LENGTH})...")
    wall_start = time.perf_counter()

    if max_workers == 1:
        # Serial execution
        for item, model in task_model_pairs:
            res = run_single_subtask(client, model, item, seed=42)
            results.append(res)
            gpu = get_gpu_status()
            if gpu.used_vram_mb > peak_vram:
                peak_vram = gpu.used_vram_mb
            if gpu.temperature_c > peak_temp:
                peak_temp = gpu.temperature_c
            verdict_str = "PASS" if res["is_correct"] else "FAIL"
            print(f"    - [{res['subtask_id']}] ({res['benchmark']}) {model}: {verdict_str} ({res['duration_seconds']}s, {res['checker']})")
    else:
        # Parallel execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(run_single_subtask, client, model, item, seed=42): item["id"]
                for item, model in task_model_pairs
            }
            for future in concurrent.futures.as_completed(future_to_item):
                res = future.result()
                results.append(res)
                gpu = get_gpu_status()
                if gpu.used_vram_mb > peak_vram:
                    peak_vram = gpu.used_vram_mb
                if gpu.temperature_c > peak_temp:
                    peak_temp = gpu.temperature_c
                verdict_str = "PASS" if res["is_correct"] else "FAIL"
                print(f"    - [{res['subtask_id']}] ({res['benchmark']}) {res['model']}: {verdict_str} ({res['duration_seconds']}s, {res['checker']})")

    wall_end = time.perf_counter()
    wall_elapsed = wall_end - wall_start

    # Concurrency calculation
    if max_workers == 1:
        # Strictly serial concurrency from timestamps is 1.0
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

    print(f"  Results: Elapsed={round(wall_elapsed, 2)}s, Throughput={throughput} subtasks/s")
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


def execute_wave_swapping_benchmark(
    config_id: str,
    config_name: str,
    wave_specs: List[Tuple[str, List[int]]],  # [(model_id, [subtask_indices])]
    subtasks: List[Dict[str, Any]],
    client: OllamaClient,
) -> Dict[str, Any]:
    """
    Executes Configuration (g): Two <=4B bases loaded one at a time, swapping between waves.
    Measures per-wave execution time, model swap latency, peak VRAM per wave, and overall concurrency.
    """
    print(f"\n=======================================================")
    print(f"[{config_id}] Preparing Wave-Swapping: {config_name}")
    print(f"=======================================================")

    clean_gpu_state()
    baseline_gpu = get_gpu_status()
    baseline_vram = baseline_gpu.used_vram_mb
    baseline_temp = baseline_gpu.temperature_c
    print(f"  Baseline Idle VRAM: {baseline_vram} MiB, Temp: {baseline_temp}°C")

    all_results = []
    peak_vram = baseline_vram
    peak_temp = baseline_temp
    ps_outputs = []
    swap_latencies = []

    wall_start = time.perf_counter()

    for wave_idx, (model_id, indices) in enumerate(wave_specs, start=1):
        print(f"\n  --- Wave {wave_idx}: Loading model '{model_id}' ({len(indices)} subtasks) ---")
        t_load_start = time.perf_counter()
        client.generate(model_id=model_id, prompt="Hello", seed=42, max_tokens=2)
        load_duration = time.perf_counter() - t_load_start
        swap_latencies.append(round(load_duration, 2))
        print(f"  Loaded in {round(load_duration, 2)} s")

        ps_wave = capture_ollama_ps()
        ps_outputs.append(f"Wave {wave_idx} ({model_id}):\n{ps_wave}")
        gpu_ok, gpu_msg = verify_100_percent_gpu(ps_wave, [model_id])
        if not gpu_ok:
            print(f"  WARNING: GPU offload verification issue for {model_id}: {gpu_msg}")

        # Execute subtasks serially in this wave
        for idx in indices:
            item = subtasks[idx]
            res = run_single_subtask(client, model_id, item, seed=42)
            all_results.append(res)
            gpu = get_gpu_status()
            if gpu.used_vram_mb > peak_vram:
                peak_vram = gpu.used_vram_mb
            if gpu.temperature_c > peak_temp:
                peak_temp = gpu.temperature_c
            verdict_str = "PASS" if res["is_correct"] else "FAIL"
            print(f"    - [{res['subtask_id']}] ({res['benchmark']}) {model_id}: {verdict_str} ({res['duration_seconds']}s, {res['checker']})")

        # Unload model after wave if not last wave
        if wave_idx < len(wave_specs):
            print(f"  Unloading model '{model_id}' to clear VRAM for next wave...")
            subprocess.run(["ollama", "stop", model_id], capture_output=True, text=True)
            time.sleep(1.5)

    wall_end = time.perf_counter()
    wall_elapsed = wall_end - wall_start

    # Concurrency for serial wave-swapping is strictly 1.0
    mean_concurrency = 1.0
    successful_tasks = sum(1 for r in all_results if r["status"] == "COMPLETE")
    correct_tasks = sum(1 for r in all_results if r["is_correct"])
    accuracy_pct = round((correct_tasks / len(subtasks)) * 100, 1)
    throughput = round(len(subtasks) / wall_elapsed, 4) if wall_elapsed > 0 else 0.0

    disqualified = False
    disq_reason = ""
    if peak_vram >= 6000:
        disqualified = True
        disq_reason = f"Peak VRAM ({peak_vram} MiB) exceeded safe limit; spilled to CPU"
    elif successful_tasks < len(subtasks):
        disqualified = True
        disq_reason = f"{len(subtasks) - successful_tasks} requests failed"

    clean_gpu_state()

    print(f"\n  Wave-Swapping Results: Elapsed={round(wall_elapsed, 2)}s (inc. swaps={swap_latencies}), Throughput={throughput} subtasks/s")
    print(f"  Concurrency={mean_concurrency}, Peak VRAM={peak_vram} MiB, Accuracy={correct_tasks}/{len(subtasks)} ({accuracy_pct}%)")

    return {
        "config_id": config_id,
        "config_name": config_name,
        "context_length": CONTEXT_LENGTH,
        "models_used": [m for m, _ in wave_specs],
        "max_workers": 1,
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
        "swap_latencies_seconds": swap_latencies,
        "ollama_ps_output": "\n---\n".join(ps_outputs),
        "disqualified": disqualified,
        "disqualification_reason": disq_reason,
        "subtask_results": all_results,
    }


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    subtasks_path = os.path.join(repo_root, "data", "benchmark_20_hard_subtasks.json")
    with open(subtasks_path, "r", encoding="utf-8") as f:
        subtasks = json.load(f)

    client = OllamaClient()
    if not client.ensure_server_running():
        print("ERROR: Ollama server is not running and could not be started.")
        sys.exit(1)

    print(f"Loaded {len(subtasks)} public benchmark dev subtasks.")
    print(f"Context length requirement: {CONTEXT_LENGTH} tokens per request.")
    print(f"Beginning benchmark across all configurations...")

    # (a) Two bases <= 4B co-loaded (Phi-3.5 + Llama-3.2-3B, W=2, c=4096)
    cfg_a = execute_configuration_benchmark(
        config_id="config_a",
        config_name="(a) Two bases <= 4B co-loaded (Phi-3.5 + Llama-3.2-3B, parallel workers=2, c=4096)",
        models=["phi3.5:3.8b", "llama3.2:3b"],
        subtasks=subtasks,
        max_workers=2,
        client=client,
    )

    # (b) Three bases <= 3B co-loaded (Qwen-1.5B + Llama-3.2-3B + Qwen-Coder-3B, W=3, c=4096)
    cfg_b = execute_configuration_benchmark(
        config_id="config_b",
        config_name="(b) Three bases <= 3B co-loaded (Qwen-1.5B + Llama-3.2-3B + Qwen-Coder-3B, parallel workers=3, c=4096)",
        models=["qwen2.5:1.5b", "llama3.2:3b", "qwen2.5-coder:3b"],
        subtasks=subtasks,
        max_workers=3,
        client=client,
    )

    # (b-serial) Serial run of (b) (W=1, c=4096)
    cfg_b_serial = execute_configuration_benchmark(
        config_id="config_b_serial",
        config_name="(b-serial) Three bases <= 3B serial (Qwen-1.5B + Llama-3.2-3B + Qwen-Coder-3B, serial worker=1, c=4096)",
        models=["qwen2.5:1.5b", "llama3.2:3b", "qwen2.5-coder:3b"],
        subtasks=subtasks,
        max_workers=1,
        client=client,
    )

    # (c) One 8B base with 2 parallel slots (Llama-3.1-8B, W=2, c=4096)
    cfg_c = execute_configuration_benchmark(
        config_id="config_c",
        config_name="(c) One 8B base with 2 parallel slots (Llama-3.1-8B, parallel workers=2, c=4096)",
        models=["llama3.1:8b"],
        subtasks=subtasks,
        max_workers=2,
        client=client,
    )

    # (d) Fully serial reference (Llama-3.1-8B, W=1, c=4096)
    cfg_d = execute_configuration_benchmark(
        config_id="config_d",
        config_name="(d) Fully serial reference (Llama-3.1-8B, serial worker=1, c=4096)",
        models=["llama3.1:8b"],
        subtasks=subtasks,
        max_workers=1,
        client=client,
    )

    # (e) Same two models as (a) run serially (Phi-3.5 + Llama-3.2-3B, W=1, c=4096)
    cfg_e = execute_configuration_benchmark(
        config_id="config_e",
        config_name="(e) Same two models as (a) run serially (Phi-3.5 + Llama-3.2-3B, serial worker=1, c=4096)",
        models=["phi3.5:3.8b", "llama3.2:3b"],
        subtasks=subtasks,
        max_workers=1,
        client=client,
    )

    # (f) One <= 4B base with 2 parallel request slots (Llama-3.2-3B, W=2, c=4096)
    cfg_f = execute_configuration_benchmark(
        config_id="config_f",
        config_name="(f) One <= 4B base with 2 parallel request slots (Llama-3.2-3B, parallel workers=2, c=4096)",
        models=["llama3.2:3b"],
        subtasks=subtasks,
        max_workers=2,
        client=client,
    )

    # (g) Two <= 4B bases loaded one at a time, swapping between waves (c=4096)
    # Wave 1: phi3.5:3.8b (subtasks 0-9: code & math)
    # Wave 2: llama3.2:3b (subtasks 10-19: sql & qa)
    cfg_g = execute_wave_swapping_benchmark(
        config_id="config_g",
        config_name="(g) Two <= 4B bases loaded one at a time, swapping between waves (Phi-3.5 wave 1 -> Llama-3.2 wave 2, serial worker=1, c=4096)",
        wave_specs=[
            ("phi3.5:3.8b", list(range(0, 10))),
            ("llama3.2:3b", list(range(10, 20))),
        ],
        subtasks=subtasks,
        client=client,
    )

    all_results = [cfg_a, cfg_b, cfg_b_serial, cfg_c, cfg_d, cfg_e, cfg_f, cfg_g]

    out_dir = os.path.join(repo_root, "results", "benchmarks")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "parallelism_benchmark.json")

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n=======================================================")
    print(f"ALL 8 CONFIGURATIONS BENCHMARKED WITH CONTEXT={CONTEXT_LENGTH}!")
    print(f"Summary written to: {out_file}")
    print(f"=======================================================")


if __name__ == "__main__":
    main()
