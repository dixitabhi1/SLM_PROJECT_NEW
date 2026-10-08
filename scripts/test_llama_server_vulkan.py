"""
Test and verify llama-server with Vulkan GPU offload on NVIDIA RTX 3050.
Polls until /health returns 200 (ok), measures VRAM via nvidia-smi, and performs a test completion.
"""

import os
import subprocess
import time
import requests

MODEL_PATH = r"C:\Users\ACER\.ollama\models\blobs\sha256-3c168af1dea0a414299c7d9077e100ac763370e5a98b3c53801a958a47f0a5db"
SERVER_BIN = os.path.abspath(r"tools\llama_bin\llama-server.exe")

cmd = [
    SERVER_BIN,
    "-m", MODEL_PATH,
    "--device", "Vulkan0",
    "-ngl", "99",
    "-c", "4096",
    "-np", "3",
    "--port", "8080",
    "--host", "127.0.0.1"
]

print("Launching llama-server...")
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

t0 = time.time()
ready = False
try:
    for i in range(40):
        time.sleep(1)
        try:
            r = requests.get("http://127.0.0.1:8080/health", timeout=1)
            if r.status_code == 200:
                print(f"llama-server READY in {time.time() - t0:.2f}s! Health: {r.json()}")
                ready = True
                break
            else:
                print(f"Waiting for model load... [{i+1}s] Status {r.status_code}: {r.text[:60]}")
        except Exception:
            pass

    if ready:
        # Check nvidia-smi
        smi = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
        print("\n--- NVIDIA-SMI OUTPUT ---")
        print(smi.stdout)

        # Send test prompt
        payload = {
            "prompt": "User: What is 2 + 2?\nAssistant:",
            "n_predict": 30,
            "temperature": 0.0
        }
        t_req = time.time()
        resp = requests.post("http://127.0.0.1:8080/completion", json=payload, timeout=30)
        req_dur = time.time() - t_req
        print(f"\n--- TEST COMPLETION ({req_dur:.2f}s) ---")
        print(resp.json().get("content", ""))
    else:
        print("Timeout waiting for server to be ready.")

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    out, err = proc.communicate()
    print("\n--- SERVER STDERR LOG SAMPLE ---")
    lines = [l for l in err.splitlines() if any(k in l.lower() for k in ["vulkan", "offload", "kv", "buffer", "memory", "layers", "model"])]
    for l in lines[:25]:
        print(l)
