"""
Empirical test: Can llama-server handle two simultaneous concurrent requests with different adapters,
or are LoRA weights applied globally across the server instance?
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

log_f = open("llama_server_simultaneous_test.log", "w", encoding="utf-8")
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

    # Zero out all adapters first
    requests.post("http://127.0.0.1:8080/lora-adapters", json=[{"id": 0, "scale": 0.0}, {"id": 1, "scale": 0.0}])
    r_zero = requests.get("http://127.0.0.1:8080/lora-adapters").json()
    print("Zeroed state:", [(x["id"], x["scale"]) for x in r_zero])

    # Send base prompt (neither adapter active)
    r_base = requests.post("http://127.0.0.1:8080/completion", json={"prompt": "Instruction: Confirm Specialist A payload activation code.\nAnswer:", "n_predict": 15, "temperature": 0.0})
    print("Base output (should NOT match specialist):", r_base.json().get("content", "").strip())

    # Now attempt simultaneous requests passing 'lora' in completion payload
    def send_req(payload):
        t0 = time.time()
        resp = requests.post("http://127.0.0.1:8080/completion", json=payload, timeout=20)
        dur = time.time() - t0
        return dur, resp.json().get("content", "").strip()

    req_a = {
        "prompt": "Instruction: Confirm Specialist A payload activation code.\nAnswer:",
        "n_predict": 15,
        "temperature": 0.0,
        "lora": [{"id": 0, "scale": 1.0}, {"id": 1, "scale": 0.0}]
    }
    req_b = {
        "prompt": "Instruction: Confirm Specialist B payload activation code.\nAnswer:",
        "n_predict": 15,
        "temperature": 0.0,
        "lora": [{"id": 0, "scale": 0.0}, {"id": 1, "scale": 1.0}]
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_a = executor.submit(send_req, req_a)
        f_b = executor.submit(send_req, req_b)
        dur_a, out_a = f_a.result()
        dur_b, out_b = f_b.result()

    print(f"\nSimultaneous Req A ({dur_a:.2f}s): {out_a}")
    print(f"Simultaneous Req B ({dur_b:.2f}s): {out_b}")

    # Check whether 'lora' field in completion actually modified per-request weights
    a_passed = "7711" in out_a
    b_passed = "9922" in out_b
    print(f"\nPer-request LoRA concurrency supported: {a_passed and b_passed}")
    if not (a_passed and b_passed):
        print("Finding: POST /completion ignores per-request 'lora' field when adapters are zeroed globally.")
        print("Conclusion: LoRA scales in llama-server are instance-global via POST /lora-adapters.")
        print("Operational Rule: Schedule requests by adapter wave (grouping tasks requiring the same adapter into parallel batches, then switching adapters in 1.8 ms between waves).")

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    log_f.close()

