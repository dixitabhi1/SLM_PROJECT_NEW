"""
Detailed Diagnostic Script for C1 (Phi-4-mini with JSON-based Tool Harness)
Runs the 20 Calibration Items and logs complete turn-by-turn messages.
Classifies each outcome into:
- correct
- malformed tool call
- tool error not recovered
- wrong final format
- ran out of turns
- context overflow
- reasoning error
"""

import os
import sys
import json
import time
import re
import urllib.request
import sqlite3
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.sandbox.runner import execute_python_code
from src.eval.versioned_scorer import score_record
from scripts.eval_calibration_hard_20 import (
    TOOL_SYSTEM_PROMPT,
    parse_tool_call,
    execute_tool_call,
    call_local_llama_chat,
    CALIB_FILE,
)

DIAG_OUT = os.path.join(REPO_ROOT, "results", "phase4", "c1_diagnosis_detailed.json")

def run_diagnose_c1(item: Dict[str, Any], max_turns: int = 8) -> Dict[str, Any]:
    user_prompt = f"{item['prompt']}\n\nYou may use execute_python or execute_sql to calculate values. Conclude with 'Final Answer: <number>'."
    messages = [
        {"role": "system", "content": TOOL_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]
    
    turns_log = []
    malformed_count = 0
    tool_error_count = 0
    last_tool_error = None
    ran_out = False
    context_overflow = False
    
    for turn in range(max_turns):
        resp = call_local_llama_chat(messages, max_tokens=1024)
        content = resp["content"]
        finish_reason = resp.get("finish_reason")
        
        if resp.get("prompt_tokens", 0) > 4000:
            context_overflow = True
        
        messages.append({"role": "assistant", "content": content})
        
        # Check if model emitted tool call
        has_tool, tool_name, args = parse_tool_call(content)
        
        # Check if text looks like a tool call but failed to parse
        looks_like_tool = "```tool_call" in content or "```python" in content or "execute_sql" in content or "execute_python" in content
        if looks_like_tool and not has_tool and not ("Final Answer:" in content):
            malformed_count += 1
            
        turn_entry = {
            "turn": turn + 1,
            "assistant_content": content,
            "has_tool": has_tool,
            "tool_name": tool_name if has_tool else None,
            "tool_args": args if has_tool else None,
            "finish_reason": finish_reason
        }
        
        if not has_tool:
            turns_log.append(turn_entry)
            break
            
        tool_output = execute_tool_call(tool_name, args)
        if tool_output.startswith("ERROR:"):
            tool_error_count += 1
            last_tool_error = tool_output
            
        turn_entry["tool_output"] = tool_output
        turns_log.append(turn_entry)
        
        tool_response_msg = f"```tool_response\n{{\n  \"name\": \"{tool_name}\",\n  \"output\": \"{tool_output}\"\n}}\n```"
        messages.append({"role": "user", "content": tool_response_msg})
    else:
        ran_out = True
        
    final_output = messages[-1]["content"]
    sc = score_record(item, final_output)
    passed = sc["passed"]
    
    # Classify outcome
    if passed:
        outcome = "correct"
    elif context_overflow:
        outcome = "context overflow"
    elif ran_out:
        outcome = "ran out of turns"
    elif malformed_count > 0 and not has_tool:
        outcome = "malformed tool call"
    elif last_tool_error and ("error" in final_output.lower() or "unable" in final_output.lower()):
        outcome = "tool error not recovered"
    elif not ("Final Answer:" in final_output or re.search(r"####\s*-?\d+", final_output)):
        outcome = "wrong final format"
    elif re.search(r"Final Answer:\s*-?\d+\.\d+", final_output):
        outcome = "wrong final format"
    else:
        outcome = "reasoning error"
        
    return {
        "item_id": item["subtask_id"],
        "solvability": item["solvability"],
        "num_stages": item["num_stages"],
        "passed": passed,
        "gold_answer": item["gold_answer"],
        "outcome": outcome,
        "turns_count": len(turns_log),
        "ran_out_of_turns": ran_out,
        "malformed_calls": malformed_count,
        "tool_errors": tool_error_count,
        "details": sc["details"],
        "final_output": final_output,
        "turns": turns_log
    }

def main():
    with open(CALIB_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)
        
    print(f"Diagnosing C1 on {len(items)} calibration items...")
    results = []
    for idx, it in enumerate(items, 1):
        print(f"[{idx}/{len(items)}] {it['subtask_id']} ({it['solvability']})...", end=" ", flush=True)
        res = run_diagnose_c1(it)
        print(f"-> {res['outcome'].upper()} (passed={res['passed']})")
        results.append(res)
        
    with open(DIAG_OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"\nSaved detailed diagnosis to {DIAG_OUT}")

if __name__ == "__main__":
    main()

