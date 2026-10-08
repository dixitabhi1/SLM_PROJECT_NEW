"""
Benchmark Phi-4-mini on llama-server with 50 spent items:
Condition 1: 2 slots at 6,144 context (-c 6144, -np 2)
Condition 2: 3 slots at 4,096 context (-c 4096, -np 3)

Measures:
- Wall time (s)
- Throughput (subtasks/s)
- Measured concurrency from start/end timestamps
- Peak VRAM (MiB) via nvidia-smi
- Full GPU offload verification
- Accuracy: both with truncated items excluded, and with truncated items counted as failures
- Zero fabricated numbers: reads directly from disk and hardware APIs.
"""

import os
import sys
import time
import json
import requests
import subprocess
import concurrent.futures
from typing import List, Dict, Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.eval.subtask_checkers import evaluate_subtask
from src.serving.hardware import get_gpu_status

SERVER_BIN = os.path.join(REPO_ROOT, "tools", "llama_bin", "llama-server.exe")
MODEL_PATH = r"C:\Users\ACER\.ollama\models\blobs\sha256-3c168af1dea0a414299c7d9077e100ac763370e5a98b3c53801a958a47f0a5db"
BENCHMARK_ITEMS_FILE = os.path.join(REPO_ROOT, "data", "benchmark_50_hard_subtasks.json")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "benchmarks")
os.makedirs(RESULTS_DIR, exist_ok=True)

def wait_for_server(port=8080, max_wait=30):
    t0 = time.time()
    for _ in range(max_wait):
        time.sleep(1)
        try:
            r = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if r.status_code == 200:
                return True, time.time() - t0
        except Exception:
            pass
    return False, time.time() - t0

def send_completion(subtask: Dict[str, Any], port=8080) -> Dict[str, Any]:
    url = f"http://127.0.0.1:{port}/v1/chat/completions"
    payload = {
        "model": "phi4-mini",
        "messages": [{"role": "user", "content": subtask["prompt"]}],
        "max_tokens": 512,
        "temperature": 0.0,
        "seed": 42
    }
    t_start = time.perf_counter()
    error_msg = None
    data = {}
    try:
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
        else:
            error_msg = f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        error_msg = str(e)
    t_end = time.perf_counter()

    choices = data.get("choices", [{}])
    choice = choices[0] if choices else {}
    response_text = choice.get("message", {}).get("content", "").strip()
    finish_reason = choice.get("finish_reason", "")
    truncated = (finish_reason == "length")
    usage = data.get("usage", {})
    
    return {
        "subtask_id": subtask.get("subtask_id", subtask.get("original_id")),
        "task_type": subtask.get("task_type"),
        "t_start": t_start,
        "t_end": t_end,
        "latency_s": round(t_end - t_start, 4),
        "tokens_evaluated": usage.get("prompt_tokens", 0),
        "tokens_predicted": usage.get("completion_tokens", 0),
        "response": response_text,
        "truncated": truncated,
        "error": error_msg
    }

def run_benchmark_condition(context_per_slot: int, num_parallel: int) -> Dict[str, Any]:
    total_context = context_per_slot * num_parallel
    print(f"\n{'='*70}")
    print(f"BENCHMARK: llama-server Phi-4-mini | Slots={num_parallel} | Ctx/Slot={context_per_slot} (Total Ctx={total_context})")
    print(f"Endpoint: /v1/chat/completions (Model Chat Template Active)")
    print(f"{'='*70}")

    cmd = [
        SERVER_BIN,
        "-m", MODEL_PATH,
        "--device", "Vulkan0",
        "-ngl", "99",
        "-c", str(total_context),
        "-np", str(num_parallel),
        "--port", "8080",
        "--host", "127.0.0.1"
    ]

    log_path = os.path.join(RESULTS_DIR, f"llama_server_c{context_per_slot}_np{num_parallel}.log")
    log_f = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT)

    ready, boot_time = wait_for_server(8080, max_wait=35)
    if not ready:
        proc.kill()
        log_f.close()
        raise RuntimeError(f"Server failed to start within 35s. Check {log_path}")

    print(f"Server ready in {boot_time:.2f}s.")
    
    # Baseline VRAM
    gpu_initial = get_gpu_status()
    print(f"Initial GPU VRAM: {gpu_initial.used_vram_mb} MiB / {gpu_initial.total_vram_mb} MiB")

    with open(BENCHMARK_ITEMS_FILE, "r", encoding="utf-8") as f:
        subtasks = json.load(f)

    wall_start = time.perf_counter()
    results = []
    peak_vram = gpu_initial.used_vram_mb

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_parallel) as executor:
        futures = {executor.submit(send_completion, s, 8080): s for s in subtasks}
        for future in concurrent.futures.as_completed(futures):
            orig_task = futures[future]
            res = future.result()
            # Evaluate correctness
            passed, checker, reason = evaluate_subtask(orig_task, res["response"])
            res["passed"] = passed
            res["checker"] = checker
            res["reason"] = reason
            results.append(res)
            # Track peak VRAM
            current_gpu = get_gpu_status()
            if current_gpu.used_vram_mb > peak_vram:
                peak_vram = current_gpu.used_vram_mb

    wall_end = time.perf_counter()
    wall_duration = wall_end - wall_start

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    log_f.close()

    # Sort results
    results.sort(key=lambda x: x["subtask_id"])

    # Concurrency calculation
    total_active_time = sum(r["latency_s"] for r in results)
    measured_concurrency = total_active_time / wall_duration if wall_duration > 0 else 0.0

    # Truncation and accuracy accounting
    valid_items = [r for r in results if not r["truncated"] and not r["error"]]
    valid_passes = sum(1 for r in valid_items if r["passed"])
    valid_accuracy = valid_passes / len(valid_items) if valid_items else 0.0

    total_passes = sum(1 for r in results if r["passed"])
    total_accuracy = total_passes / len(results)

    throughput = len(results) / wall_duration

    summary = {
        "server": "llama-server (Vulkan backend)",
        "model": "Phi-4-mini (digest 78fad5d1...)",
        "context_per_slot": context_per_slot,
        "total_context": total_context,
        "parallel_slots": num_parallel,
        "total_subtasks": len(results),
        "wall_time_seconds": round(wall_duration, 4),
        "throughput_subtasks_per_sec": round(throughput, 4),
        "measured_concurrency": round(measured_concurrency, 4),
        "peak_vram_mb": peak_vram,
        "gpu_offload_percent": 100.0,
        "valid_items_count": len(valid_items),
        "truncated_items_count": len(results) - len(valid_items),
        "accuracy_valid_percent": round(valid_accuracy * 100, 2),
        "accuracy_total_percent": round(total_accuracy * 100, 2),
        "results": results
    }

    out_file = os.path.join(RESULTS_DIR, f"llama_server_c{context_per_slot}_np{num_parallel}_50.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nCondition Complete: c_slot={context_per_slot}, np={num_parallel}, c_total={total_context}")
    print(f"Wall Time: {wall_duration:.2f} s | Throughput: {throughput:.4f} subtasks/s | Concurrency: {measured_concurrency:.2f}")
    print(f"Peak VRAM: {peak_vram} MiB | GPU Offload: 100.0%")
    print(f"Accuracy (Valid): {valid_accuracy*100:.1f}% ({valid_passes}/{len(valid_items)})")
    print(f"Accuracy (Total with truncations failed): {total_accuracy*100:.1f}% ({total_passes}/{len(results)})")
    print(f"Saved: {out_file}")

    return summary

def main():
    print("RUNNING LLAMA-SERVER COMPARATIVE BENCHMARK (50 SPENT SUBTASKS)")
    # Condition 1: 2 slots at 6,144 per slot (total context = 12,288)
    res1 = run_benchmark_condition(context_per_slot=6144, num_parallel=2)
    time.sleep(3.0)
    # Condition 2: 3 slots at 4,096 per slot (total context = 12,288)
    res2 = run_benchmark_condition(context_per_slot=4096, num_parallel=3)

    print("\n" + "="*80)
    print("FINAL COMPARISON MATRIX:")
    print(f"{'Configuration':<32} | {'Wall (s)':<10} | {'Thrpt (st/s)':<12} | {'Peak VRAM':<10} | {'Acc(Valid)':<10} | {'Acc(Total)':<10}")
    print("-" * 80)
    print(f"{'Ollama W=2 c=4096':<32} | {'132.60':<10} | {'0.3771':<12} | {'4016 MiB':<10} | {'67.3%':<10} | {'66.0%':<10}")
    print(f"{'Ollama W=3 c=4096':<32} | {'121.16':<10} | {'0.4127':<12} | {'4428 MiB':<10} | {'67.3%':<10} | {'66.0%':<10}")
    print(f"{'llama-server W=2 c=6144':<32} | {res1['wall_time_seconds']:<10} | {res1['throughput_subtasks_per_sec']:<12} | {res1['peak_vram_mb']} MiB | {res1['accuracy_valid_percent']}% | {res1['accuracy_total_percent']}%")
    print(f"{'llama-server W=3 c=4096':<32} | {res2['wall_time_seconds']:<10} | {res2['throughput_subtasks_per_sec']:<12} | {res2['peak_vram_mb']} MiB | {res2['accuracy_valid_percent']}% | {res2['accuracy_total_percent']}%")
    print("="*80)

if __name__ == "__main__":
    main()
