import os
import sys
import json
import time

sys.path.insert(0, ".")
from scripts.run_all_outstanding_reruns import call_groq_api, format_eval_prompt_b0, B0_QWEN_PATH, TRACK_A_PATH
from src.eval.versioned_scorer import score_record

tra = json.load(open(TRACK_A_PATH, encoding="utf-8"))
def get_id(it):
    return it.get("item_id") or it.get("subtask_id") or it.get("original_id")
tra_map = {get_id(it): it for it in tra}

for iid in ["compound_heldout_v2_0002", "compound_heldout_v2_0008"]:
    it = tra_map[iid]
    p = format_eval_prompt_b0(it)
    print(f"Running {iid}...")
    resp = call_groq_api("qwen/qwen3.8-27b", p, max_tokens=4096)
    sc = score_record(it, resp["content"])
    rec = {
        "item_id": iid,
        "model": "qwen/qwen3.8-27b",
        "condition": "B0",
        "track": "A",
        "stratum": it.get("stratum", ""),
        "task_type": it.get("task_type") or it.get("type", ""),
        "solvability": it.get("solvability", ""),
        "prompt": p,
        "output": resp["content"][:300],
        "full_output": resp["content"],
        "finish_reason": resp["finish_reason"],
        "prompt_tokens": resp["prompt_tokens"],
        "completion_tokens": resp["completion_tokens"],
        "total_tokens": resp["total_tokens"],
        "status": resp["status"],
        "clean_execution": resp["status"] == "COMPLETE",
        "passed": sc["passed"],
        "details": sc["details"],
        "duration": resp["latency_seconds"],
        "rerun_4096": True,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    with open(B0_QWEN_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"Finished {iid}: fr={resp['finish_reason']}, status={resp['status']}, passed={sc['passed']}")
    time.sleep(3.0)

