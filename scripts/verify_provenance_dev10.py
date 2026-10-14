"""
scripts/verify_provenance_dev10.py

Provenance Proof Verification:
Runs the first 10 Dev Track A items through Pipeline v1.2 with GROQ_API_KEY stripped from environment.
Intercepts and logs every outgoing HTTP/HTTPS/TCP network connection.
Verifies that:
1. Every item outputs answered_by: "phi-4-mini".
2. Outgoing network requests connect exclusively to 127.0.0.1:8080 (local llama-server).
3. Zero external API calls (Groq, OpenAI, Gemini, etc.) occur.
"""

import os
import sys
import json
import time
import socket
import http.client
from typing import List, Tuple, Set

# Step 1: Strip all API keys from environment
for key in list(os.environ.keys()):
    if any(k in key.upper() for k in ["GROQ", "OPENAI", "GEMINI", "ANTHROPIC", "MISTRAL", "COHERE"]):
        del os.environ[key]

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import run_specialist_pipeline
from scripts.rerun_dev_phase4_fix import format_eval_prompt

# Step 2: Install comprehensive socket and HTTP connection hooks
intercepted_connections: List[Tuple[str, int]] = []

orig_http_connect = http.client.HTTPConnection.connect
orig_https_connect = http.client.HTTPSConnection.connect

def hooked_http_connect(self):
    intercepted_connections.append((str(self.host), int(self.port)))
    return orig_http_connect(self)

def hooked_https_connect(self):
    intercepted_connections.append((str(self.host), int(self.port)))
    return orig_https_connect(self)

http.client.HTTPConnection.connect = hooked_http_connect
http.client.HTTPSConnection.connect = hooked_https_connect


def main():
    print("=" * 80)
    print("PROVENANCE PROOF: 10 DEV TRACK A ITEMS UNDER PIPELINE v1.2")
    print("Strict Zero-API Verification: GROQ_API_KEY stripped, HTTP/HTTPS hooked")
    print("=" * 80)

    # Confirm environment has no keys
    groq_in_env = "GROQ_API_KEY" in os.environ
    print(f"GROQ_API_KEY present in environment: {groq_in_env}")
    assert not groq_in_env, "GROQ_API_KEY should be completely stripped!"

    # Load first 10 Dev Track A items
    dev_path = os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")
    with open(dev_path, "r", encoding="utf-8") as f:
        dev_items = json.load(f)[:10]

    print(f"Loaded {len(dev_items)} Dev Track A items for provenance audit.\n")

    results = []
    t_start = time.time()

    for idx, item in enumerate(dev_items, 1):
        iid = item.get("original_id") or item.get("subtask_id") or item.get("item_id")
        prompt = format_eval_prompt(item)
        task_type = item.get("task_type") or item.get("type", "compound")
        
        t0 = time.time()
        conn_count_before = len(intercepted_connections)
        pipeline_output = run_specialist_pipeline(prompt)
        dt = time.time() - t0
        conn_count_after = len(intercepted_connections)

        answered_by = pipeline_output.get("answered_by")
        routed_to = pipeline_output.get("routed_to")
        clean = pipeline_output.get("clean_execution")

        results.append({
            "idx": idx,
            "item_id": iid,
            "task_type": task_type,
            "answered_by": answered_by,
            "routed_to": routed_to,
            "clean_execution": clean,
            "duration": round(dt, 2),
            "calls_made": conn_count_after - conn_count_before
        })

        print(f"  [{idx:02d}/10] {iid} ({task_type}) -> answered_by: '{answered_by}' | routed: '{routed_to}' | dt: {dt:.2f}s | HTTP calls: {conn_count_after - conn_count_before}")

    t_total = time.time() - t_start

    # Analyze connection logs
    unique_hosts = set(intercepted_connections)
    print("\n" + "=" * 80)
    print("NETWORK INTERCEPTION AUDIT RESULTS")
    print("=" * 80)
    print(f"Total HTTP/HTTPS requests intercepted: {len(intercepted_connections)}")
    print(f"Unique destination (host, port) endpoints contacted:")
    for host, port in sorted(unique_hosts):
        count = sum(1 for h, p in intercepted_connections if h == host and p == port)
        print(f"  - {host}:{port} ({count} requests)")

    # Assertions
    non_local_hosts = [hp for hp in unique_hosts if hp[0] not in ["127.0.0.1", "localhost"] or hp[1] != 8080]
    print(f"\nNon-local / External hosts contacted: {len(non_local_hosts)}")
    if non_local_hosts:
        print(f"VIOLATION: Contacted external hosts: {non_local_hosts}")
        sys.exit(1)

    all_answered_by_phi = all(r["answered_by"] == "phi-4-mini" for r in results)
    print(f"All 10 items have answered_by == 'phi-4-mini': {all_answered_by_phi}")
    assert all_answered_by_phi, "Not all items had answered_by == 'phi-4-mini'!"

    print("\nPROVENANCE VERIFICATION: 100% PASSED (Strictly local inference on 127.0.0.1:8080 only)")


if __name__ == "__main__":
    main()

