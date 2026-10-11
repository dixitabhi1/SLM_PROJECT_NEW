import os
import sys
import json
import time
import urllib.request
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

from src.eval.versioned_scorer import score_record

CALIB_FILE = os.path.join(REPO_ROOT, "data", "calibration_hard_20_items.json")
OUT_FILE = os.path.join(REPO_ROOT, "results", "phase4", "calibration_qwen_b0_eval.json")

def call_groq_with_retry(payload, max_retries=5):
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = 15.0
                try:
                    retry_after = float(e.headers.get("retry-after", 15.0))
                except Exception:
                    pass
                wait_time = max(retry_after, 12.0)
                print(f"[HTTP 429] Pacing: sleeping {wait_time:.1f}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise e
    raise RuntimeError("Exceeded maximum retries for Groq API call.")

def main():
    with open(CALIB_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)
        
    print(f"Running B0 (Qwen-27B No Tools) with robust rate-limit pacing on {len(items)} calibration items...")
    records = []
    
    for idx, it in enumerate(items, 1):
        prompt = f"{it['prompt']}\n\nConclude your reasoning with the exact final numeric answer: Final Answer: [number]"
        payload = {
            "model": "qwen/qwen3.8-27b",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.0
        }
        try:
            data = call_groq_with_retry(payload)
            content = data["choices"][0]["message"]["content"]
            sc = score_record(it, content)
            passed = sc["passed"]
            print(f"[{idx}/{len(items)}] {it['subtask_id']} ({it['solvability']}): passed={passed}")
            records.append({
                "item_id": it["subtask_id"],
                "solvability": it["solvability"],
                "num_stages": it["num_stages"],
                "passed": passed,
                "gold": it["gold_answer"],
                "output": content,
                "details": sc["details"]
            })
        except Exception as e:
            print(f"[{idx}/{len(items)}] {it['subtask_id']} ERROR: {e}")
            records.append({
                "item_id": it["subtask_id"],
                "solvability": it["solvability"],
                "passed": False,
                "error": str(e)
            })
        # Sleep 5s between items to stay well below 8,000 TPM limit
        time.sleep(5.0)
        
    total_acc = sum(1 for r in records if r.get("passed")) / len(records) * 100
    solv_acc = sum(1 for r in records if r.get("solvability") == "solvable_without_tools" and r.get("passed")) / 10 * 100
    tool_req_acc = sum(1 for r in records if r.get("solvability") == "tool-required" and r.get("passed")) / 10 * 100
    
    summary = {
        "model": "qwen/qwen3.8-27b",
        "condition": "B0 (no tools)",
        "total_items": len(items),
        "total_accuracy_percent": round(total_acc, 2),
        "solvable_w_o_tools_acc_percent": round(solv_acc, 2),
        "tool_required_acc_percent": round(tool_req_acc, 2),
        "records": records
    }
    
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        
    print(f"\nB0 Qwen-27B Complete!")
    print(f"Total Acc: {total_acc:.2f}% | Solvable w/o tools: {solv_acc:.2f}% | Tool-required: {tool_req_acc:.2f}%")

if __name__ == "__main__":
    main()

