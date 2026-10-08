"""
Evaluates the 10 calibration compound items on the base model (Phi-4-mini)
using llama-server.
Reports accuracy and checks if it falls in the target 30%-60% range.
"""

import os
import sys
import json
import time
import requests
import subprocess
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

SERVER_BIN = os.path.join(REPO_ROOT, "tools", "llama_bin", "llama-server.exe")
MODEL_PATH = r"C:\Users\ACER\.ollama\models\blobs\sha256-3c168af1dea0a414299c7d9077e100ac763370e5a98b3c53801a958a47f0a5db"
CALIB_FILE = os.path.join(REPO_ROOT, "data", "calibration_10_compound_items.json")
RESULTS_DIR = os.path.join(REPO_ROOT, "results", "benchmarks")
os.makedirs(RESULTS_DIR, exist_ok=True)

def wait_for_server(port=8080, max_wait=35):
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

def check_answer(gold_val: str, response_text: str) -> tuple[bool, str]:
    gold_str = str(gold_val).strip()
    
    # Try exact match on gold string
    # Look for gold_str as standalone token or in final line/answer
    pattern = r'(?<![0-9\.\,])' + re.escape(gold_str) + r'(?![0-9\.\,])'
    if re.search(pattern, response_text):
        return True, f"Found gold answer {gold_str}"
    
    # If float, check with numeric tolerance
    try:
        gold_num = float(gold_str)
        # Extract all numbers from response
        num_matches = re.findall(r'[-+]?\d*\.?\d+', response_text)
        for nm in num_matches:
            try:
                val = float(nm)
                if abs(val - gold_num) < 1e-2 or (gold_num != 0 and abs((val - gold_num)/gold_num) < 0.01):
                    return True, f"Found numeric match {val} approx {gold_num}"
            except:
                pass
    except:
        pass
        
    return False, f"Gold answer {gold_str} not found in response"

def run_calibration():
    with open(CALIB_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)

    print(f"Loaded {len(items)} calibration items.")

    cmd = [
        SERVER_BIN,
        "-m", MODEL_PATH,
        "--device", "Vulkan0",
        "-ngl", "99",
        "-c", "12288",
        "-np", "3",
        "--port", "8080",
        "--host", "127.0.0.1"
    ]

    log_path = os.path.join(RESULTS_DIR, "calib_llama_server.log")
    log_f = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT)

    ready, boot_time = wait_for_server(8080, max_wait=35)
    if not ready:
        proc.kill()
        log_f.close()
        raise RuntimeError(f"Server failed to start within 35s. Check {log_path}")

    print(f"Server ready in {boot_time:.2f}s.")

    results = []
    passes = 0

    for idx, item in enumerate(items, start=1):
        payload = {
            "model": "phi4-mini",
            "messages": [{"role": "user", "content": item["prompt"]}],
            "max_tokens": 1024,
            "temperature": 0.0,
            "seed": 42
        }

        t_start = time.perf_counter()
        resp = requests.post("http://127.0.0.1:8080/v1/chat/completions", json=payload, timeout=120)
        t_end = time.perf_counter()

        data = resp.json()
        choice = data.get("choices", [{}])[0]
        resp_text = choice.get("message", {}).get("content", "").strip()
        finish_reason = choice.get("finish_reason", "")
        truncated = (finish_reason == "length")

        # Check if code execution or python block is present in generation
        code_executed = ("```python" in resp_text) or ("```" in resp_text)

        passed, reason = check_answer(item["gold_answer"], resp_text)
        if passed and not truncated:
            passes += 1

        res_record = {
            "subtask_id": item["subtask_id"],
            "domains": item["domains"],
            "solvability": item["solvability"],
            "gold_answer": item["gold_answer"],
            "response": resp_text,
            "latency_s": round(t_end - t_start, 2),
            "truncated": truncated,
            "code_detected": code_executed,
            "passed": passed,
            "reason": reason
        }
        results.append(res_record)
        print(f"Item {idx}/10 [{item['subtask_id']}] ({item['solvability']}): {'PASS' if passed else 'FAIL'} (Latency: {t_end - t_start:.2f}s)")

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    log_f.close()

    acc = passes / len(items) * 100
    tool_req = [r for r in results if r["solvability"] == "tool-required"]
    tool_req_pass = sum(1 for r in tool_req if r["passed"])
    no_tool = [r for r in results if r["solvability"] == "solvable_without_tools"]
    no_tool_pass = sum(1 for r in no_tool if r["passed"])

    summary = {
        "benchmark": "Base Model Calibration on 10 Compound Tasks",
        "model": "Phi-4-mini (digest 78fad5d1...)",
        "total_items": len(items),
        "total_passes": passes,
        "accuracy_percent": acc,
        "target_range": [30.0, 60.0],
        "in_target_range": (30.0 <= acc <= 60.0),
        "tool_required": {
            "total": len(tool_req),
            "passes": tool_req_pass,
            "accuracy_percent": round(tool_req_pass / len(tool_req) * 100, 1) if tool_req else 0.0
        },
        "solvable_without_tools": {
            "total": len(no_tool),
            "passes": no_tool_pass,
            "accuracy_percent": round(no_tool_pass / len(no_tool) * 100, 1) if no_tool else 0.0
        },
        "results": results
    }

    out_file = os.path.join(RESULTS_DIR, "calibration_compound_10_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "="*60)
    print(f"CALIBRATION RUN COMPLETE: Accuracy = {acc:.1f}% ({passes}/{len(items)})")
    print(f"Target Range: 30% - 60% -> {'QUALIFIED' if (30.0 <= acc <= 60.0) else 'OUT OF RANGE'}")
    print(f"Solvable Without Tools: {no_tool_pass}/{len(no_tool)} ({no_tool_pass/len(no_tool)*100:.1f}%)")
    print(f"Tool-Required: {tool_req_pass}/{len(tool_req)} ({tool_req_pass/len(tool_req)*100:.1f}%)")
    print("="*60)

    return summary

if __name__ == "__main__":
    run_calibration()
