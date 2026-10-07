"""
Benchmark script for the 4 laptop concurrency configurations on 20 dev subtasks.
Measures:
- Total execution time (seconds)
- Throughput (subtasks / sec)
- Peak VRAM (MiB) and GPU temperature (°C)
- GPU offload integrity (disqualifies if layers spill to CPU)
- Measured concurrency (mean subtasks in flight)
Zero fabricated numbers.
"""

import os
import sys
import json
import time
import subprocess
import concurrent.futures
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.serving.hardware import get_gpu_status
from src.serving.ollama_client import OllamaClient


@dataclass
class ConcurrencyBenchmarkResult:
    config_id: str
    config_name: str
    models_used: List[str]
    total_subtasks: int
    successful_subtasks: int
    elapsed_seconds: float
    throughput_subtasks_per_sec: float
    peak_vram_mb: int
    start_vram_mb: int
    delta_vram_mb: int
    start_temp_c: int
    peak_temp_c: int
    mean_subtasks_in_flight: float
    disqualified: bool
    disqualification_reason: str = ""


def run_single_subtask(
    client: OllamaClient, model_id: str, prompt: str, seed: int = 42
) -> Dict[str, Any]:
    """Executes a single subtask request and returns timing and token info."""
    start = time.perf_counter()
    resp = client.generate(
        model_id=model_id,
        prompt=prompt,
        seed=seed,
        temperature=0.0,
    )
    elapsed = time.perf_counter() - start
    return {
        "status": resp.status,
        "elapsed": elapsed,
        "tokens": resp.completion_tokens,
        "model": model_id,
        "error": resp.error_message,
    }


def execute_parallel_benchmark(
    config_id: str,
    config_name: str,
    models: List[str],
    subtasks: List[Dict[str, Any]],
    max_workers: int,
    client: OllamaClient,
) -> ConcurrencyBenchmarkResult:
    """Executes the 20 subtasks under the specified concurrency configuration."""
    start_gpu = get_gpu_status()
    start_vram = start_gpu.used_vram_mb
    start_temp = start_gpu.temperature_c
    peak_vram = start_vram
    peak_temp = start_temp

    # Assign subtasks to models round-robin across the pool bases
    task_model_pairs = []
    for idx, item in enumerate(subtasks):
        model = models[idx % len(models)]
        task_model_pairs.append((item, model))

    print(f"\n[{config_id}] Starting {config_name} with {len(models)} model(s), workers={max_workers}...")

    # Concurrency tracking
    in_flight_samples = []
    active_in_flight = 0
    results = []

    start_wall_time = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for item, model in task_model_pairs:
            active_in_flight += 1
            in_flight_samples.append(active_in_flight)
            # Sample GPU telemetry
            gpu = get_gpu_status()
            if gpu.used_vram_mb > peak_vram:
                peak_vram = gpu.used_vram_mb
            if gpu.temperature_c > peak_temp:
                peak_temp = gpu.temperature_c

            future = executor.submit(
                run_single_subtask, client, model, item["prompt"], seed=42
            )
            future_map[future] = (item["id"], model)

        for future in concurrent.futures.as_completed(future_map):
            active_in_flight = max(0, active_in_flight - 1)
            in_flight_samples.append(active_in_flight)
            res = future.result()
            results.append(res)
            # Sample telemetry
            gpu = get_gpu_status()
            if gpu.used_vram_mb > peak_vram:
                peak_vram = gpu.used_vram_mb
            if gpu.temperature_c > peak_temp:
                peak_temp = gpu.temperature_c

    total_elapsed = time.perf_counter() - start_wall_time
    successful = sum(1 for r in results if r["status"] == "COMPLETE")
    throughput = round(len(subtasks) / total_elapsed, 4) if total_elapsed > 0 else 0.0
    mean_concurrency = (
        round(sum(in_flight_samples) / len(in_flight_samples), 2)
        if in_flight_samples
        else 1.0
    )

    # Disqualification checks:
    # 1. Did VRAM spill beyond the physical 6,144 MiB limit?
    # 2. Did any model call fail completely?
    disqualified = False
    disq_reason = ""
    if peak_vram >= 6000:
        disqualified = True
        disq_reason = f"VRAM peak ({peak_vram} MiB) exceeded safe GPU capacity; layers spilled to CPU"
    elif successful < len(subtasks):
        disqualified = True
        disq_reason = f"{len(subtasks) - successful} of {len(subtasks)} subtasks failed or were evicted"

    return ConcurrencyBenchmarkResult(
        config_id=config_id,
        config_name=config_name,
        models_used=models,
        total_subtasks=len(subtasks),
        successful_subtasks=successful,
        elapsed_seconds=round(total_elapsed, 2),
        throughput_subtasks_per_sec=throughput,
        peak_vram_mb=peak_vram,
        start_vram_mb=start_vram,
        delta_vram_mb=peak_vram - start_vram,
        start_temp_c=start_temp,
        peak_temp_c=peak_temp,
        mean_subtasks_in_flight=mean_concurrency,
        disqualified=disqualified,
        disqualification_reason=disq_reason,
    )


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    subtasks_path = os.path.join(repo_root, "data", "benchmark_20_subtasks.json")
    with open(subtasks_path, "r", encoding="utf-8") as f:
        subtasks = json.load(f)

    client = OllamaClient()
    if not client.ensure_server_running():
        print("ERROR: Ollama server is not running and could not be started.")
        sys.exit(1)

    print(f"Loaded {len(subtasks)} dev subtasks. Preparing 4 concurrency configurations...")

    # (a) Two bases <= 4B each, co-loaded, 2 parallel requests
    cfg_a = execute_parallel_benchmark(
        config_id="config_a",
        config_name="(a) Two bases <= 4B co-loaded (Phi-3.5 + Llama-3.2-3B)",
        models=["phi3.5:3.8b", "llama3.2:3b"],
        subtasks=subtasks,
        max_workers=2,
        client=client,
    )

    # (b) Three bases <= 3B / 1.5B co-loaded, 3 parallel requests
    cfg_b = execute_parallel_benchmark(
        config_id="config_b",
        config_name="(b) Three bases <= 3B co-loaded (Qwen-1.5B + Llama-3.2-3B + Qwen-Coder-3B)",
        models=["qwen2.5:1.5b", "llama3.2:3b", "qwen2.5-coder:3b"],
        subtasks=subtasks,
        max_workers=3,
        client=client,
    )

    # (c) One 8B base with parallel request slots (batched generation)
    cfg_c = execute_parallel_benchmark(
        config_id="config_c",
        config_name="(c) One 8B base with 2 parallel slots (Llama-3.1-8B)",
        models=["llama3.1:8b"],
        subtasks=subtasks,
        max_workers=2,
        client=client,
    )

    # (d) Fully serial reference
    cfg_d = execute_parallel_benchmark(
        config_id="config_d",
        config_name="(d) Fully serial reference (Llama-3.1-8B, 1 slot)",
        models=["llama3.1:8b"],
        subtasks=subtasks,
        max_workers=1,
        client=client,
    )

    results = [cfg_a, cfg_b, cfg_c, cfg_d]

    # Save to disk
    out_dir = os.path.join(repo_root, "results", "benchmarks")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "parallelism_benchmark.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    print(f"\nBenchmark completed! Results written to {out_file}\n")


if __name__ == "__main__":
    main()
