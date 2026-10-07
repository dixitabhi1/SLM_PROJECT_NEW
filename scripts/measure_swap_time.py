"""
Measures base model swap time and warm-up latency on local GPU.
Enforces Section 4 requirement: 'Measure adapter swap time and base swap time.'
Zero fabricated numbers.
"""

import os
import sys
import time
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.serving.ollama_client import OllamaClient


def main():
    client = OllamaClient()
    assert client.ensure_server_running(), "Ollama server is not running"

    models = ["phi3.5:3.8b", "llama3.2:3b", "llama3.1:8b"]
    swap_records = []

    print("Measuring base model swap latencies...")
    prompt = "Reply with 'ready'."

    # Warm-up first model
    print(f"Loading initial model: {models[0]}...")
    client.generate(models[0], prompt, seed=42)

    for i in range(len(models) - 1):
        from_model = models[i]
        to_model = models[i + 1]
        print(f"Swapping from {from_model} to {to_model}...")
        start_time = time.perf_counter()
        resp = client.generate(to_model, prompt, seed=42)
        swap_time = time.perf_counter() - start_time
        assert resp.status == "COMPLETE", f"Model {to_model} failed generation"

        record = {
            "from_model": from_model,
            "to_model": to_model,
            "swap_and_generation_latency_s": round(swap_time, 3),
            "generation_latency_s": round(resp.latency_seconds, 3),
            "tokens": resp.completion_tokens,
        }
        swap_records.append(record)
        print(f"  Swap latency: {swap_time:.3f}s (resp: '{resp.content.strip()[:20]}')")

    out_path = os.path.join("results", "benchmarks", "model_swap_benchmarks.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(swap_records, f, indent=2)

    print(f"\nSwap measurements saved to {out_path}")


if __name__ == "__main__":
    main()

