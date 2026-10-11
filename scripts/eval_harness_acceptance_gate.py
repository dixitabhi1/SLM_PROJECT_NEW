"""
Harness Acceptance Gate Evaluation Script.
Evaluates the Tool Harness on spent items only:
- 20 Calibration items (10 tool-required, 10 solvable-without-tools)
- 50 Hard Benchmark items (15 HumanEval, 15 GSM8K, 10 Spider, 10 ARC)
Total: 70 spent items.

Measures:
1. Tool Call Well-Formedness: >= 95% well-formed and executed across all calls.
2. Accuracy on Solvable-Without-Tools: with-tools >= no-tools baseline.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

from src.tools.tolerant_harness import (
    run_local_python,
    run_local_sql,
    run_local_search,
    execute_sql_tolerant,
    parse_fenced_tool_call,
    NATIVE_TOOLS_DEF,
    SYSTEM_PROMPT_FENCED,
    SYSTEM_PROMPT_NATIVE,
)
from src.eval.versioned_scorer import score_record

CALIB_FILE = os.path.join(REPO_ROOT, "data", "calibration_hard_20_items.json")
BENCH_FILE = os.path.join(REPO_ROOT, "data", "benchmark_50_hard_subtasks.json")
OUT_DIR = os.path.join(REPO_ROOT, "results", "phase4")
os.makedirs(OUT_DIR, exist_ok=True)

def call_local_llama(messages: List[Dict[str, str]], max_tokens: int = 1024) -> Dict[str, Any]:
    url = "http://127.0.0.1:8080/v1/chat/completions"
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": 42
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            prompt_tokens = data.get("usage", {}).get("prompt_tokens", 0)
            print(f"[p_tok: {prompt_tokens}]", end=" ", flush=True)
            return data
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8") if e.fp else ""
        if e.code == 400 and "exceeds the available context size" in err_body.lower():
            print(f"[CONTEXT OVERFLOW 400]", end=" ", flush=True)
            return {
                "context_overflow": True,
                "error": "context overflow",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "context_overflow": True
                    }
                }],
                "usage": {"prompt_tokens": 6144}
            }
        raise e

def call_groq_api(payload: Dict[str, Any], max_retries: int = 6) -> Dict[str, Any]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
    )
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            is_rate_limit = (e.code == 429) or ("rate_limit_exceeded" in err_body) or ("Rate limit reached" in err_body)
            if is_rate_limit:
                wait_time = 15.0
                m = re.search(r"Please try again in (?:(\d+)m)?([0-9\.]+)s", err_body)
                if m:
                    mins = float(m.group(1)) if m.group(1) else 0.0
                    secs = float(m.group(2)) if m.group(2) else 0.0
                    wait_time = mins * 60.0 + secs + 2.0
                else:
                    try:
                        val = float(e.headers.get("retry-after", 15.0))
                        if val > 60.0 and "m" not in str(val):
                            val = val / 1000.0
                        wait_time = val + 1.0
                    except Exception:
                        pass
                print(f"[Rate Limit {e.code}] Sleeping {wait_time:.1f}s (retry {attempt+1}/{max_retries})...", flush=True)
                time.sleep(wait_time)
            elif e.code == 400:
                # Return structured error so caller can log actual malformed tool call
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "http_400_error": err_body
                        }
                    }]
                }
            else:
                raise e
        except Exception as e:
            time.sleep(5.0)
            if attempt == max_retries - 1:
                raise e
    raise RuntimeError("Exceeded maximum Groq API retries.")

# --- Single Item Evaluator ---

def evaluate_item_with_tools(
    model_name: str,
    item: Dict[str, Any],
    max_turns: int = 8
) -> Dict[str, Any]:
    """
    Evaluates a single item with the tool harness.
    model_name: 'phi4-mini', 'qwen/qwen3.8-27b', 'openai/gpt-oss-120b'
    """
    prompt = item["prompt"]
    is_groq = model_name != "phi4-mini"
    
    # Tool tracking
    tool_calls_attempted = 0
    tool_calls_executed = 0
    tool_calls_malformed = 0
    is_context_overflow = False
    turns_log = []
    
    if is_groq:
        # Groq Native Tools Loop
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_NATIVE},
            {"role": "user", "content": f"{prompt}\n\nConclude with 'Final Answer: <answer>'."}
        ]
        
        for turn in range(max_turns):
            payload = {
                "model": model_name,
                "messages": messages,
                "tools": NATIVE_TOOLS_DEF,
                "max_tokens": 1024,
                "temperature": 0.0
            }
            res = call_groq_api(payload)
            time.sleep(3.0) # rate limit spacing
            choice = res["choices"][0]
            msg = choice["message"]
            
            # Check if Groq returned an HTTP 400 tool parse failure
            if "http_400_error" in msg:
                tool_calls_attempted += 1
                tool_calls_malformed += 1
                err_body = msg["http_400_error"]
                turns_log.append({
                    "turn": turn + 1,
                    "content": f"[HTTP 400 Malformed Tool Call]: {err_body[:150]}",
                    "tool_calls": []
                })
                messages.append({
                    "role": "assistant",
                    "content": "I encountered an error calling the tool."
                })
                messages.append({
                    "role": "user",
                    "content": "ERROR: Tool arguments were not valid JSON. Please provide arguments as a JSON object, e.g. {\"code\": \"...\"}, or provide your Final Answer."
                })
                continue

            messages.append(msg)
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                # Finished without calling tool
                turns_log.append({
                    "turn": turn + 1,
                    "content": msg.get("content", ""),
                    "tool_calls": []
                })
                break
                
            turn_tool_records = []
            for tc in tool_calls:
                tool_calls_attempted += 1
                func_name = tc["function"]["name"]
                args_str = tc["function"]["arguments"]
                try:
                    args = json.loads(args_str)
                    args_valid = True
                except Exception:
                    args = {}
                    args_valid = False
                    tool_calls_malformed += 1
                    
                if not args_valid:
                    tool_output = "ERROR: Failed to parse arguments as valid JSON."
                else:
                    if func_name == "execute_python":
                        code = args.get("code", "")
                        success, tool_output = run_local_python(code)
                        if success: tool_calls_executed += 1
                    elif func_name == "execute_sql":
                        db_cand = args.get("db_name", "")
                        query = args.get("query", "")
                        success, tool_output = execute_sql_tolerant(db_cand, query, prompt)
                        if success: tool_calls_executed += 1
                    elif func_name == "search_hypergrid":
                        q = args.get("query", "")
                        success, tool_output = run_local_search(q)
                        if success: tool_calls_executed += 1
                    else:
                        tool_output = f"ERROR: Unknown tool '{func_name}'."
                        tool_calls_malformed += 1
                        
                turn_tool_records.append({
                    "name": func_name,
                    "arguments": args,
                    "output": tool_output
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": func_name,
                    "content": tool_output
                })
                
            turns_log.append({
                "turn": turn + 1,
                "content": msg.get("content", ""),
                "tool_calls": turn_tool_records
            })
            
    else:
        # Local Phi-4-mini Fenced Protocol Loop
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_FENCED},
            {"role": "user", "content": f"{prompt}\n\nYou may use python or sql tools. Conclude with 'Final Answer: <answer>'."}
        ]
        
        for turn in range(max_turns):
            res = call_local_llama(messages, max_tokens=1024)
            if res.get("context_overflow"):
                is_context_overflow = True
                break
                
            content = res["choices"][0]["message"]["content"]
            messages.append({"role": "assistant", "content": content})
            
            has_tool, tool_name, args, is_malformed = parse_fenced_tool_call(content, prompt_context=prompt)
            
            if is_malformed:
                tool_calls_attempted += 1
                tool_calls_malformed += 1
                turns_log.append({
                    "turn": turn + 1,
                    "content": content,
                    "is_malformed": True
                })
                messages.append({
                    "role": "user",
                    "content": "ERROR: Malformed code fence. Please close your code block or provide your Final Answer."
                })
                continue
                
            if not has_tool:
                turns_log.append({
                    "turn": turn + 1,
                    "content": content,
                    "has_tool": False
                })
                break
                
            tool_calls_attempted += 1
            if tool_name == "execute_python":
                success, tool_output = run_local_python(args.get("code", ""))
                if success: tool_calls_executed += 1
            elif tool_name == "execute_sql":
                success, tool_output = execute_sql_tolerant(args.get("db_name", ""), args.get("query", ""), prompt)
                if success: tool_calls_executed += 1
            elif tool_name == "search_hypergrid":
                success, tool_output = run_local_search(args.get("query", ""))
                if success: tool_calls_executed += 1
            else:
                success, tool_output = False, f"ERROR: Unknown tool '{tool_name}'."
                tool_calls_malformed += 1
                
            turns_log.append({
                "turn": turn + 1,
                "content": content,
                "has_tool": True,
                "tool_name": tool_name,
                "arguments": args,
                "output": tool_output
            })
            
            tool_resp_msg = f"```tool_output\n{tool_output}\n```"
            messages.append({"role": "user", "content": tool_resp_msg})

    if is_context_overflow:
        return {
            "item_id": item.get("subtask_id", item.get("id")),
            "solvability": item.get("solvability", "solvable_without_tools"),
            "task_type": item.get("type", item.get("task_type", "compound")),
            "passed": False,
            "score_details": "context overflow",
            "tool_calls_attempted": tool_calls_attempted,
            "tool_calls_executed": tool_calls_executed,
            "tool_calls_malformed": tool_calls_malformed,
            "is_context_overflow": True,
            "turns_count": len(turns_log),
            "final_output": "",
            "turns": turns_log
        }

    # Extract candidate final text across all assistant turns
    is_code_task = (
        item.get("benchmark") == "HumanEval" or
        item.get("type") == "code" or
        item.get("checker") == "python_sandbox_test"
    )
    
    asst_contents = [m.get("content", "") for m in messages if m.get("role") == "assistant" and m.get("content")]
    
    if is_code_task:
        # Collect any Python function definitions across assistant turns
        all_py_blocks = []
        for c in asst_contents:
            blocks = re.findall(r"```(?:python|py)?\s*\n?(.*?)\n?```", c, re.DOTALL | re.IGNORECASE)
            for b in blocks:
                if "def " in b:
                    all_py_blocks.append(b)
        if all_py_blocks:
            final_text = "```python\n" + "\n\n".join(all_py_blocks) + "\n```"
        elif asst_contents:
            final_text = asst_contents[-1]
        else:
            final_text = ""
    else:
        # For non-code tasks, prefer assistant message with 'Final Answer:', else last assistant message
        final_text = ""
        for c in reversed(asst_contents):
            if "final answer" in c.lower():
                final_text = c
                break
        if not final_text and asst_contents:
            final_text = asst_contents[-1]
            
    # Score output with versioned scorer
    sc = score_record(item, final_text)
    
    return {
        "item_id": item.get("subtask_id", item.get("id")),
        "solvability": item.get("solvability", "solvable_without_tools"),
        "task_type": item.get("type", item.get("task_type", "compound")),
        "passed": sc["passed"],
        "score_details": sc["details"],
        "tool_calls_attempted": tool_calls_attempted,
        "tool_calls_executed": tool_calls_executed,
        "tool_calls_malformed": tool_calls_malformed,
        "is_context_overflow": False,
        "turns_count": len(turns_log),
        "final_output": final_text,
        "turns": turns_log
    }

def run_acceptance_suite_for_model(model_name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    print(f"\n{'='*70}", flush=True)
    print(f"RUNNING HARNESS ACCEPTANCE GATE: {model_name} on {len(items)} items", flush=True)
    print(f"{'='*70}", flush=True)
    
    safe_name = model_name.replace("/", "_")
    out_file = os.path.join(OUT_DIR, f"harness_acceptance_{safe_name}.json")
    results = []
    done_ids = set()
    if os.path.exists(out_file):
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                results = existing_data.get("results", [])
                done_ids = {r["item_id"] for r in results if not r.get("error")}
                print(f"Resuming: found {len(done_ids)} successfully completed records.", flush=True)
        except Exception:
            pass

    overflow_count = sum(1 for r in results if r.get("is_context_overflow"))
    for idx, it in enumerate(items, 1):
        item_id = it.get("subtask_id", it.get("id"))
        solv = it.get("solvability", "solvable_without_tools")
        if item_id in done_ids:
            continue
        print(f"[{idx}/{len(items)}] {item_id} ({solv})...", end=" ", flush=True)
        t0 = time.time()
        try:
            res = evaluate_item_with_tools(model_name, it)
            passed = res["passed"]
            calls = res["tool_calls_attempted"]
            execs = res["tool_calls_executed"]
            if res.get("is_context_overflow"):
                overflow_count += 1
            dt = time.time() - t0
            print(f"-> {'PASS' if passed else 'FAIL'} (tools: {execs}/{calls}, {dt:.1f}s)", flush=True)
            results.append(res)
            done_ids.add(item_id)
        except Exception as e:
            print(f"-> ERROR: {e}", flush=True)
            results.append({
                "item_id": item_id,
                "solvability": solv,
                "passed": False,
                "error": str(e),
                "tool_calls_attempted": 0,
                "tool_calls_executed": 0,
                "tool_calls_malformed": 0
            })
            
        # Incremental save
        tmp_summary = {
            "model": model_name,
            "total_items": len(results),
            "results": results
        }
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(tmp_summary, f, indent=2)
            
    # Metrics
    tot_calls = sum(r["tool_calls_attempted"] for r in results)
    tot_exec = sum(r["tool_calls_executed"] for r in results)
    tot_malformed = sum(r.get("tool_calls_malformed", 0) for r in results)
    well_formed_rate = (tot_exec / tot_calls * 100) if tot_calls > 0 else 100.0
    
    solv_items = [r for r in results if r["solvability"] == "solvable_without_tools"]
    solv_passes = sum(1 for r in solv_items if r["passed"])
    solv_acc = (solv_passes / len(solv_items) * 100) if solv_items else 0.0
    
    req_items = [r for r in results if r["solvability"] == "tool-required"]
    req_passes = sum(1 for r in req_items if r["passed"])
    req_acc = (req_passes / len(req_items) * 100) if req_items else 0.0
    
    total_acc = sum(1 for r in results if r["passed"]) / len(results) * 100
    
    summary = {
        "model": model_name,
        "total_items": len(results),
        "total_accuracy_percent": round(total_acc, 2),
        "solvable_w_o_tools_acc_percent": round(solv_acc, 2),
        "solvable_w_o_tools_passed": solv_passes,
        "solvable_w_o_tools_total": len(solv_items),
        "tool_required_acc_percent": round(req_acc, 2),
        "tool_required_passed": req_passes,
        "tool_required_total": len(req_items),
        "total_tool_calls_attempted": tot_calls,
        "total_tool_calls_executed": tot_exec,
        "total_tool_calls_malformed": tot_malformed,
        "tool_well_formed_rate_percent": round(well_formed_rate, 2),
        "context_overflow_count": overflow_count,
        "context_overflow_rate_percent": round(overflow_count / len(results) * 100, 2),
        "results": results
    }
    
    safe_name = model_name.replace("/", "_")
    out_file = os.path.join(OUT_DIR, f"harness_acceptance_{safe_name}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        
    print(f"\nSummary for {model_name}:", flush=True)
    print(f"Tool Well-Formedness: {well_formed_rate:.2f}% ({tot_exec}/{tot_calls})", flush=True)
    print(f"Solvable w/o tools Acc: {solv_acc:.2f}% ({solv_passes}/{len(solv_items)})", flush=True)
    print(f"Tool-required Acc: {req_acc:.2f}% ({req_passes}/{len(req_items)})", flush=True)
    print(f"Context Overflow: {overflow_count}/{len(results)} ({summary['context_overflow_rate_percent']}%)", flush=True)
    print(f"Saved to: {out_file}", flush=True)
    
    return summary

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="all", choices=["all", "phi4-mini", "qwen", "gpt120b"])
    args = parser.parse_args()

    with open(CALIB_FILE, "r", encoding="utf-8") as f:
        calib_items = json.load(f)
    with open(BENCH_FILE, "r", encoding="utf-8") as f:
        bench_items = json.load(f)
        
    for it in bench_items:
        it["solvability"] = "solvable_without_tools"
        
    all_70_items = calib_items + bench_items
    print(f"Total spent items loaded: {len(all_70_items)} (20 calibration + 50 benchmark)", flush=True)
    
    if args.model in ["all", "phi4-mini"]:
        run_acceptance_suite_for_model("phi4-mini", all_70_items)
        
    if args.model in ["all", "qwen"]:
        run_acceptance_suite_for_model("qwen/qwen3.8-27b", all_70_items)
        
    if args.model in ["all", "gpt120b"]:
        run_acceptance_suite_for_model("openai/gpt-oss-120b", all_70_items)
        
    print("\n" + "="*80, flush=True)
    print("HARNESS ACCEPTANCE RUN COMPLETED!", flush=True)
    print("="*80, flush=True)

if __name__ == "__main__":
    main()
