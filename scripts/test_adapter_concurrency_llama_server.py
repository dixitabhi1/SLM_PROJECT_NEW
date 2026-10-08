"""
Test adapter selection under concurrency in llama-server.
Checks whether LoRA adapters can be applied per-request in concurrent slots,
or whether POST /lora-adapters sets weights globally.
"""

import os
import subprocess
import time
import requests
import concurrent.futures

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIN_PATH = os.path.join(REPO_ROOT, "tools", "llama_bin", "llama-server.exe")
MODEL_PATH = r"C:\Users\ACER\.ollama\models\blobs\sha256-3c168af1dea0a414299c7d9077e100ac763370e5a98b3c53801a958a47f0a5db"
ADAPTER_A = os.path.join(REPO_ROOT, "adapters", "phi4_mini_adapter_a.gguf")
ADAPTER_B = os.path.join(REPO_ROOT, "adapters", "phi4_mini_adapter_b.gguf")

cmd = [
    BIN_PATH,
    "-m", MODEL_PATH,
    "--lora", f"{ADAPTER_A},{ADAPTER_B}",
    "--lora-init-without-apply",
    "--device", "Vulkan0",
    "-ngl", "99",
    "-c", "4096",
    "-np", "2",
    "--port", "8080",
    "--host", "127.0.0.1"
]

log_f = open("llama_server_lora_test.log", "w", encoding="utf-8")
proc = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT)

try:
    for i in range(25):
        time.sleep(1)
        try:
            r = requests.get("http://127.0.0.1:8080/health", timeout=1)
            if r.status_code == 200:
                print(f"llama-server READY in {i+1}s!")
                break
        except Exception:
            pass

    # Check /lora-adapters endpoint
    r_lora = requests.get("http://127.0.0.1:8080/lora-adapters")
    print("Initial /lora-adapters state:", r_lora.status_code, r_lora.json())

    # Test 1: Test if POST /completion accepts request-level lora parameter
    prompt_a = "Instruction: Confirm Specialist A payload activation code.\nAnswer:"
    prompt_b = "Instruction: Confirm Specialist B payload activation code.\nAnswer:"

    # Request attempting per-request lora parameter
    req_a = {"prompt": prompt_a, "n_predict": 15, "temperature": 0.0, "lora": [{"id": 0, "scale": 1.0}, {"id": 1, "scale": 0.0}]}
    resp_a = requests.post("http://127.0.0.1:8080/completion", json=req_a)
    print("Request with 'lora' payload in /completion:", resp_a.status_code, resp_a.json().get("content", ""))

    # Test 2: Concurrent requests with global POST /lora-adapters
    # If LoRA is global, switching adapter A affects all slots.
    print("\nSetting global adapter to Specialist A (id 0 = 1.0, id 1 = 0.0)...")
    requests.post("http://127.0.0.1:8080/lora-adapters", json=[{"id": 0, "scale": 1.0}, {"id": 1, "scale": 0.0}])
    r1 = requests.post("http://127.0.0.1:8080/completion", json={"prompt": prompt_a, "n_predict": 15, "temperature": 0.0})
    print("Output under Adapter A:", r1.json().get("content", "").strip())

    print("\nSetting global adapter to Specialist B (id 0 = 0.0, id 1 = 1.0)...")
    requests.post("http://127.0.0.1:8080/lora-adapters", json=[{"id": 0, "scale": 0.0}, {"id": 1, "scale": 1.0}])
    r2 = requests.post("http://127.0.0.1:8080/completion", json={"prompt": prompt_b, "n_predict": 15, "temperature": 0.0})
    print("Output under Adapter B:", r2.json().get("content", "").strip())

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    log_f.close()

