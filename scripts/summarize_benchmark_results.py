"""
Script to summarize parallelism benchmark results directly from results/benchmarks/parallelism_benchmark.json.
Reports exact metrics without hand-tuning or fabrication.
"""

import os
import json
import sys


def summarize_benchmarks(json_path: str = "results/benchmarks/parallelism_benchmark.json"):
    if not os.path.exists(json_path):
        print(f"Error: {json_path} does not exist.")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("=" * 80)
    print(f"PARALLELISM BENCHMARK SUMMARY ({len(data)} configurations)")
    print("=" * 80)

    for c in data:
        print("-" * 80)
        print(f"Config ID:       {c.get('config_id')}")
        print(f"Config Name:     {c.get('config_name')}")
        print(f"Context Length:  {c.get('context_length', 'N/A')} tokens")
        print(f"Models:          {', '.join(c.get('models_used', []))}")
        print(f"Workers:         {c.get('max_workers')}")
        print(f"Elapsed Time:    {c.get('elapsed_seconds')} s")
        print(f"Throughput:      {c.get('throughput_subtasks_per_sec')} subtasks/s")
        print(f"Concurrency C:   {c.get('mean_concurrency')}")
        print(f"Idle VRAM:       {c.get('baseline_vram_mb')} MiB")
        print(f"Peak VRAM:       {c.get('peak_vram_mb')} MiB")
        print(f"Delta VRAM:      {c.get('delta_vram_mb')} MiB")
        print(f"Accuracy:        {c.get('correct_subtasks')}/{c.get('total_subtasks')} ({c.get('accuracy_percent')}%)")
        print(f"Verdict:         {'DISQUALIFIED' if c.get('disqualified') else 'QUALIFIED'}")
        if c.get("disqualified"):
            print(f"Reason:          {c.get('disqualification_reason')}")
        print(f"ollama ps:\n{c.get('ollama_ps_output', '').strip()}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "results/benchmarks/parallelism_benchmark.json"
    summarize_benchmarks(path)

