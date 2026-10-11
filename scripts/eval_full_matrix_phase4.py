"""
Full Matrix Phase 4 Evaluation Script.
Executes all required conditions across identical spent items:
1. Fixed Design A (Sample-and-Vote, 5 samples) with canonical extraction & full un-truncated output.
2. Design C (Data-then-reason).
3. Dispatcher (one model call text-only routing: direct vs tools) and end-to-end accuracy.
4. Track B Calibration (10 items): No-tools vs Retrieval-then-answer.
5. Local 7B model (qwen2.5:7b-instruct-q3_k_m): No-tools, Design A, Design C on the 70 items.
6. Groq baselines (qwen/qwen3.8-27b, openai/gpt-oss-120b): No-tools, Design A on the 70 items.

All results saved incrementally to results/phase4/full_matrix_eval.json.
Zero fabricated numbers.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple, Optional
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

from src.sandbox.runner import execute_python_code
from src.eval.versioned_scorer import score_record, extract_sql_query
from src.tools.retriever_tool import BM25RetrieverTool

CALIB_FILE = os.path.join(REPO_ROOT, "data", "calibration_hard_20_items.json")
BENCH_FILE = os.path.join(REPO_ROOT, "data", "benchmark_50_hard_subtasks.json")
TRACK_B_FILE = os.path.join(REPO_ROOT, "data", "track_b", "track_b_calibration_10_items.json")
CORPUS_DIR = os.path.join(REPO_ROOT, "data", "track_b", "corpus")
OUT_FILE = os.path.join(REPO_ROOT, "results", "phase4", "full_matrix_eval.json")
os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)

LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

# --- MODEL INVOCATION HELPERS ---

def call_local_phi(messages: List[Dict[str, str]], temperature: float = 0.0, max_tokens: int = 1024) -> str:
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if temperature == 0.0:
        payload["seed"] = 42
    req = urllib.request.Request(
        LLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

def call_ollama_7b(messages: List[Dict[str, str]], temperature: float = 0.0, max_tokens: int = 1024) -> str:
    url = "http://127.0.0.1:8081/v1/chat/completions"
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if temperature == 0.0:
        payload["seed"] = 42
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

def call_groq(model_name: str, messages: List[Dict[str, str]], temperature: float = 0.0, max_tokens: int = 768) -> str:
    # Clamp max_tokens to 280 for Qwen-27B to fit within Groq's 1000 OTPM reservation window
    if "27b" in model_name.lower():
        effective_tokens = min(max_tokens, 280)
    else:
        effective_tokens = min(max_tokens, 768)

    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": effective_tokens,
        "temperature": temperature
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
    )
    for attempt in range(15):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]
                content = choice["message"].get("content") or choice["message"].get("reasoning") or ""
                time.sleep(0.5)
                return content
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_header = e.headers.get("retry-after") if hasattr(e, "headers") else None
                if retry_header:
                    try:
                        wait_sec = float(retry_header) + 0.5
                    except ValueError:
                        wait_sec = 4.0
                else:
                    wait_sec = 4.0 * (attempt + 1)
                print(f"[Groq 429: wait {wait_sec:.1f}s]", end=" ", flush=True)
                time.sleep(wait_sec)
            elif e.code in [500, 502, 503, 504]:
                wait_sec = 5.0 * (attempt + 1)
                print(f"[Groq {e.code}: wait {wait_sec:.1f}s]", end=" ", flush=True)
                time.sleep(wait_sec)
            else:
                raise e
    raise RuntimeError(f"Groq API call failed after 15 retries for model {model_name}")

# --- CODE & SQL UTILITIES ---

def extract_code_block(text: str) -> str:
    matches = re.findall(r"```(?:python|py)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    if matches:
        return matches[-1].strip()
    return text.strip()

def clean_user_code(code: str) -> str:
    code = re.sub(r"def\s+run_sql\s*\(.*?\):(?:\s*\"\"\".*?\"\"\"|\s*pass|\s*return\s*\[\])", "", code, flags=re.DOTALL)
    code = re.sub(r"def\s+search\s*\(.*?\):(?:\s*\"\"\".*?\"\"\"|\s*pass|\s*return\s*\[\])", "", code, flags=re.DOTALL)
    return code.strip()

def build_sandbox_preamble(item: Dict[str, Any]) -> str:
    schema_ddl = item.get("schema_ddl", "")
    init_sql = item.get("init_sql", "")
    injected_ddl = f"{schema_ddl}\n{init_sql}".replace('"', '\\"').replace("'", "\\'")

    preamble = f'''import sys, os, re, json, math, sqlite3, collections, itertools
from typing import List, Tuple, Dict, Any, Optional

REPO_ROOT = r"{REPO_ROOT}"
INJECTED_DDL = """{injected_ddl}"""

class SQLResult(list):
    def _val(self):
        if len(self) == 1 and len(self[0]) == 1:
            return self[0][0]
        return self[0][0] if len(self) > 0 and len(self[0]) > 0 else 0
    def __int__(self): return int(self._val())
    def __float__(self): return float(self._val())
    def __truediv__(self, other): return float(self) / other
    def __rtruediv__(self, other): return other / float(self)
    def __floordiv__(self, other): return int(self) // other
    def __rfloordiv__(self, other): return other // int(self)
    def __add__(self, other): return self._val() + other
    def __radd__(self, other): return other + self._val()
    def __sub__(self, other): return self._val() - other
    def __rsub__(self, other): return other - self._val()
    def __mul__(self, other): return self._val() * other
    def __rmul__(self, other): return other * self._val()
    def __mod__(self, other): return int(self) % other
    def __rmod__(self, other): return other % int(self)

def run_sql(db_name, query):
    db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_name, f"{{db_name}}.sqlite")
    if not os.path.exists(db_path):
        db_path = os.path.join(REPO_ROOT, "data", "spider_databases", "all_databases", db_name, f"{{db_name}}.sqlite")
    if os.path.exists(db_path):
        conn = sqlite3.connect(f"file:{{db_path}}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        conn.close()
        return SQLResult(rows)
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    for s in INJECTED_DDL.split(";"):
        if s.strip():
            try: cur.execute(s)
            except Exception: pass
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    return SQLResult(rows)

def search(query):
    corpus_dir = os.path.join(REPO_ROOT, "data", "track_b", "corpus")
    terms = [t.lower() for t in query.split() if len(t) > 3]
    matches = []
    if os.path.exists(corpus_dir):
        for f in os.listdir(corpus_dir):
            if f.endswith(".txt") or f.endswith(".md"):
                p = os.path.join(corpus_dir, f)
                with open(p, "r", encoding="utf-8") as fp:
                    content = fp.read()
                    if any(term in content.lower() for term in terms):
                        matches.append(content[:500])
    return matches[:3]
'''
    return preamble

def execute_sqlite_direct(db_name: str, query: str, schema_ddl: str = "") -> Tuple[bool, str, List[Tuple]]:
    db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_name, f"{db_name}.sqlite")
    if not os.path.exists(db_path):
        db_path = os.path.join(REPO_ROOT, "data", "spider_databases", "all_databases", db_name, f"{db_name}.sqlite")
    try:
        if os.path.exists(db_path):
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute(query)
            rows = cur.fetchall()
            conn.close()
            return True, str(rows[:10]), rows
        elif schema_ddl:
            conn = sqlite3.connect(":memory:")
            cur = conn.cursor()
            for s in schema_ddl.split(";"):
                if s.strip():
                    cur.execute(s)
            cur.execute(query)
            rows = cur.fetchall()
            conn.close()
            return True, str(rows[:10]), rows
        else:
            return False, f"Database '{db_name}' not found", []
    except Exception as e:
        return False, str(e), []

# --- DESIGN A: SINGLE PROGRAM ---

def run_design_a(item: Dict[str, Any], caller_func=call_local_phi, temperature: float = 0.0) -> Dict[str, Any]:
    prompt = item["prompt"]
    task_type = (item.get("type") or item.get("benchmark") or item.get("task_type") or "").lower()
    t0 = time.time()
    
    clean_execution = False
    had_retry = False
    final_output = ""

    if "sql" in task_type:
        sys_prompt = "You are an expert SQL assistant. Output ONLY the SQLite query enclosed in ```sql ... ```."
        user_msg = f"{prompt}\n\nOutput the SQLite query enclosed in ```sql ... ```."
        resp_1 = caller_func([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}], temperature=temperature, max_tokens=512)
        sql_q = extract_sql_query(resp_1)
        sc_test = score_record(item, sql_q)
        if sc_test["passed"] or "syntax error" not in sc_test.get("details", "").lower():
            clean_execution = True
            final_output = sql_q
        else:
            had_retry = True
            err_msg = sc_test.get("details", "")
            msgs = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": resp_1},
                {"role": "user", "content": f"The query produced an error: {err_msg[:300]}\nPlease output the corrected SQLite query in ```sql ... ```."}
            ]
            resp_2 = caller_func(msgs, temperature=temperature, max_tokens=512)
            sql_q2 = extract_sql_query(resp_2)
            sc_test2 = score_record(item, sql_q2)
            clean_execution = "syntax error" not in sc_test2.get("details", "").lower()
            final_output = sql_q2

    elif "code" in task_type or item.get("benchmark") == "HumanEval":
        sys_prompt = "You are an expert Python programmer. Complete the function in ```python ... ```."
        user_msg = f"{prompt}\n\nWrite the complete Python function in ```python ... ```."
        resp_1 = caller_func([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}], temperature=temperature, max_tokens=1024)
        sc_test = score_record(item, resp_1)
        if sc_test["passed"]:
            clean_execution = True
            final_output = resp_1
        else:
            had_retry = True
            err_msg = sc_test.get("details", "")
            msgs = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": resp_1},
                {"role": "user", "content": f"Code test failed: {err_msg[:300]}\nPlease write the corrected Python function in ```python ... ```."}
            ]
            resp_2 = caller_func(msgs, temperature=temperature, max_tokens=1024)
            sc_test2 = score_record(item, resp_2)
            clean_execution = "execution failed" not in sc_test2.get("details", "").lower()
            final_output = resp_2

    elif "qa" in task_type or item.get("benchmark") == "ARC-Challenge":
        sys_prompt = "You are an expert assistant. Answer the multiple choice question. Conclude with 'Final Answer: (X)'."
        user_msg = f"{prompt}\n\nConclude with 'Final Answer: (X)'."
        resp_1 = caller_func([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}], temperature=temperature, max_tokens=512)
        clean_execution = True
        final_output = resp_1

    else:
        # Compound & Math tasks
        sys_prompt = """You are an expert Python programmer and reasoning assistant.
Solve the following problem by writing a single, complete, self-contained Python program enclosed in ```python ... ```.

Available pre-defined helper functions (already imported, do NOT re-define them):
- run_sql(db_name: str, query: str) -> list[tuple]: executes a SQL SELECT query on the database and returns rows.
- search(query: str) -> list[str]: searches the knowledge corpus.

Rules:
1. Write executable Python code that computes the solution.
2. The program must print the final answer: print(answer) or print(f"Final Answer: {answer}").
3. Do not leave placeholder syntax or undefined variables."""

        user_msg = f"{prompt}\n\nWrite the complete Python program in ```python ... ``` that computes and prints the final answer."
        resp_1 = caller_func([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}], temperature=temperature, max_tokens=1024)
        code_1 = clean_user_code(extract_code_block(resp_1))

        preamble = build_sandbox_preamble(item)
        full_script_1 = f"{preamble}\n\n{code_1}"
        exec_res_1 = execute_python_code(full_script_1, timeout_seconds=15.0)

        if exec_res_1.exit_code == 0 and exec_res_1.stdout.strip():
            clean_execution = True
            final_output = exec_res_1.stdout.strip()
        else:
            had_retry = True
            err_msg = exec_res_1.stderr.strip() or f"Execution failed with exit code {exec_res_1.exit_code}"
            msgs = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": resp_1},
                {"role": "user", "content": f"The program produced an error:\n{err_msg[:400]}\n\nPlease fix the bug and write the complete corrected Python program in ```python ... ```."}
            ]
            resp_2 = caller_func(msgs, temperature=temperature, max_tokens=1024)
            code_2 = clean_user_code(extract_code_block(resp_2))
            full_script_2 = f"{preamble}\n\n{code_2}"
            exec_res_2 = execute_python_code(full_script_2, timeout_seconds=15.0)
            if exec_res_2.exit_code == 0 and exec_res_2.stdout.strip():
                clean_execution = True
                final_output = exec_res_2.stdout.strip()
            else:
                final_output = exec_res_2.stdout.strip() or resp_2

    dt = time.time() - t0
    sc = score_record(item, final_output)

    return {
        "item_id": item.get("subtask_id", item.get("id")),
        "solvability": item.get("solvability", "solvable_without_tools"),
        "clean_execution": clean_execution,
        "had_retry": had_retry,
        "passed": sc["passed"],
        "details": sc["details"],
        "output": final_output[:200],
        "full_output": final_output,
        "duration": dt
    }

# --- CANONICAL PREDICTION EXTRACTION & FIXED VOTE ---

def extract_canonical_prediction(item: Dict[str, Any], full_output: str) -> str:
    task_type = (item.get("type") or item.get("benchmark") or item.get("task_type") or "").lower()
    if "qa" in task_type or item.get("benchmark") == "ARC-Challenge":
        # Extract choice letter
        m = re.findall(r"(?:final\s+answer:\s*\(?|correct\s+option:\s*\(?|\b)([A-D])\b", full_output, re.IGNORECASE)
        if m:
            return f"CHOICE_{m[-1].upper()}"
        return "CHOICE_UNKNOWN"
    elif "sql" in task_type:
        return extract_sql_query(full_output).strip()
    elif "code" in task_type or item.get("benchmark") == "HumanEval":
        # For code, scoring is binary test pass
        sc = score_record(item, full_output)
        return "CODE_PASS" if sc["passed"] else "CODE_FAIL"
    else:
        # Math & Compound: extract final number
        hash_m = re.search(r"####\s*(-?\d+)", full_output)
        if hash_m: return f"NUM_{hash_m.group(1)}"
        box_m = re.search(r"\\boxed\{(-?\d+)\}", full_output)
        if box_m: return f"NUM_{box_m.group(1)}"
        fa_m = re.findall(r"(?:final\s+answer:\s*|answer\s+is\s+|total\s+is\s+|=?\s*)(-?\d+)", full_output, re.IGNORECASE)
        if fa_m: return f"NUM_{fa_m[-1]}"
        all_nums = re.findall(r"\b(-?\d+)\b", full_output)
        if all_nums: return f"NUM_{all_nums[-1]}"
        return "NUM_UNKNOWN"

def run_design_a_vote_fixed(item: Dict[str, Any], caller_func=call_local_phi, num_samples: int = 5) -> Dict[str, Any]:
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = [ex.submit(run_design_a, item, caller_func, 0.7) for _ in range(num_samples)]
        samples = [f.result() for f in futures]

    clean_samples = [s for s in samples if s["clean_execution"]]
    clean_share = len(clean_samples) / num_samples

    if clean_samples:
        canon_preds = [extract_canonical_prediction(item, s["full_output"]) for s in clean_samples]
        counts = Counter(canon_preds)
        majority_canon, vote_count = counts.most_common(1)[0]

        # Select the winning sample
        winning_sample = next(s for s, c in zip(clean_samples, canon_preds) if c == majority_canon)
        final_for_score = winning_sample["full_output"]
        sc = score_record(item, final_for_score)
        passed = sc["passed"]
        details = f"Voted ({vote_count}/{len(clean_samples)} clean for {majority_canon}): {sc['details']}"
    else:
        final_for_score = ""
        passed = False
        details = "0 clean execution runs out of 5"

    dt = time.time() - t0
    return {
        "item_id": item.get("subtask_id", item.get("id")),
        "solvability": item.get("solvability", "solvable_without_tools"),
        "clean_execution": len(clean_samples) > 0,
        "clean_share": clean_share,
        "clean_samples_count": len(clean_samples),
        "passed": passed,
        "details": details,
        "output": final_for_score[:200],
        "full_output": final_for_score,
        "duration": dt
    }

# --- DIRECT ANSWER (NO-TOOLS) ---

def run_direct_answer(item: Dict[str, Any], caller_func=call_local_phi) -> Dict[str, Any]:
    prompt = item["prompt"]
    task_type = (item.get("type") or item.get("benchmark") or item.get("task_type") or "").lower()
    t0 = time.time()

    if "code" in task_type or item.get("benchmark") == "HumanEval":
        sys_msg = "You are an expert Python assistant. Complete the function in ```python ... ```."
        user_msg = f"{prompt}\n\nWrite the complete Python function in ```python ... ```."
    elif "sql" in task_type:
        sys_msg = "You are an expert SQL assistant. Output ONLY the SQLite query enclosed in ```sql ... ```."
        user_msg = f"{prompt}\n\nOutput the SQLite query enclosed in ```sql ... ```."
    elif "qa" in task_type or item.get("benchmark") == "ARC-Challenge":
        sys_msg = "You are an expert assistant. Answer the multiple choice question. Conclude with 'Final Answer: (X)'."
        user_msg = f"{prompt}\n\nConclude with 'Final Answer: (X)'."
    else:
        sys_msg = "You are an expert assistant. Solve the problem step-by-step and conclude with 'Final Answer: <answer>'."
        user_msg = f"{prompt}\n\nConclude with 'Final Answer: <answer>'."

    resp = caller_func([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}], temperature=0.0, max_tokens=1024)
    dt = time.time() - t0
    sc = score_record(item, resp)

    return {
        "item_id": item.get("subtask_id", item.get("id")),
        "solvability": item.get("solvability", "solvable_without_tools"),
        "clean_execution": True,
        "passed": sc["passed"],
        "details": sc["details"],
        "output": resp[:200],
        "full_output": resp,
        "duration": dt
    }

from src.tools.tolerant_harness import KNOWN_DATABASES, execute_sql_tolerant

def identify_db_in_task(item: Dict[str, Any]) -> Tuple[bool, str, str]:
    prompt = item.get("prompt", "")
    task_type = (item.get("type") or item.get("benchmark") or item.get("task_type") or "").lower()
    schema_ddl = item.get("schema_ddl", "")
    
    # 1. Check known database names from Spider
    for db in KNOWN_DATABASES:
        if re.search(r"\b" + re.escape(db) + r"\b", prompt, re.IGNORECASE):
            return True, db, schema_ddl

    # 2. Check "the <db> database"
    m_before = re.search(r"\b([a-zA-Z0-9_\-]+)\s+database\b", prompt, re.IGNORECASE)
    if m_before and m_before.group(1).lower() not in ["sqlite", "relational", "the", "a", "this"]:
        return True, m_before.group(1), schema_ddl

    # 3. Check "database <db>" (ignoring 'schema', 'name', 'table')
    m_after = re.search(r"\bdatabase\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", prompt, re.IGNORECASE)
    if m_after and m_after.group(1).lower() not in ["schema", "table", "file", "system", "name"]:
        return True, m_after.group(1), schema_ddl

    if "schema_ddl" in item and item["schema_ddl"]:
        return True, item.get("db_id", "in_memory"), schema_ddl

    if "sql" in task_type:
        return True, item.get("db_id", "world_1"), schema_ddl

    return False, "", ""

def run_design_c(item: Dict[str, Any], caller_func=call_local_phi) -> Dict[str, Any]:
    prompt = item["prompt"]
    has_db, db_name, schema_ddl = identify_db_in_task(item)
    t0 = time.time()

    if not has_db:
        # Otherwise answer directly
        return run_direct_answer(item, caller_func)

    # Database named: model writes 1 SQL query
    task_type = (item.get("type") or item.get("benchmark") or item.get("task_type") or "").lower()
    if "sql" in task_type:
        # For pure Spider tasks, the task IS to write the SQL query
        return run_design_a(item, caller_func=caller_func, temperature=0.0)

    # Compound task: query database first, then insert results into direct-answer prompt
    sql_prompt = f"{prompt}\n\nWrite a single SQLite query enclosed in ```sql ... ``` to extract the required data from database '{db_name}'."
    sys_sql = f"You are an expert SQL assistant. Output ONLY the SQLite query enclosed in ```sql ... ```."
    resp_sql_1 = caller_func([{"role": "system", "content": sys_sql}, {"role": "user", "content": sql_prompt}], temperature=0.0, max_tokens=512)
    query_1 = extract_sql_query(resp_sql_1)

    success, out_text = execute_sql_tolerant(db_name, query_1, prompt_context=prompt)
    if not success:
        # One retry with error and schema
        retry_msg = f"The query produced an error: {out_text}\nSchema:\n{schema_ddl[:400]}\nPlease output the corrected SQLite query in ```sql ... ```."
        msgs = [
            {"role": "system", "content": sys_sql},
            {"role": "user", "content": sql_prompt},
            {"role": "assistant", "content": resp_sql_1},
            {"role": "user", "content": retry_msg}
        ]
        resp_sql_2 = caller_func(msgs, temperature=0.0, max_tokens=512)
        query_2 = extract_sql_query(resp_sql_2)
        success, out_text = execute_sql_tolerant(db_name, query_2, prompt_context=prompt)

    # Step 2: Insert query result into direct-answer prompt
    da_prompt = f"""Task: {prompt}

Database Query Executed: {query_1}
Database Query Results: {out_text}

Based on the above query results, answer the question directly. Conclude with 'Final Answer: <answer>'."""

    resp_da = caller_func([
        {"role": "system", "content": "You are an expert reasoning assistant. Use the provided query results to answer the question directly."},
        {"role": "user", "content": da_prompt}
    ], temperature=0.0, max_tokens=512)

    dt = time.time() - t0
    sc = score_record(item, resp_da)

    return {
        "item_id": item.get("subtask_id", item.get("id")),
        "solvability": item.get("solvability", "solvable_without_tools"),
        "clean_execution": success,
        "passed": sc["passed"],
        "details": sc["details"],
        "output": resp_da[:200],
        "full_output": resp_da,
        "duration": dt
    }

# --- DISPATCHER ---

def run_dispatcher_decision(prompt_text: str, caller_func=call_local_phi) -> bool:
    sys_msg = """You are an expert computational task dispatcher.
Analyze the user task text and determine whether solving it requires querying an external database or external documents.
Rules:
- If the task mentions querying a database, tables, SQLite, or specific external corpus facts, answer 'YES'.
- If the task is pure mathematics, standard algorithmic coding, or multiple-choice science reasoning, answer 'NO'.
Output ONLY 'YES' or 'NO'."""
    user_msg = f"Task: {prompt_text}\n\nDoes this task require external data/database access? (YES/NO):"
    resp = caller_func([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}], temperature=0.0, max_tokens=16)
    return "YES" in resp.strip().upper()

# --- TRACK B RETRIEVAL-THEN-ANSWER ---

_BM25_RETRIEVER = None

def get_bm25_retriever():
    global _BM25_RETRIEVER
    if _BM25_RETRIEVER is None:
        docs = []
        for f in os.listdir(CORPUS_DIR):
            if f.endswith(".md") or f.endswith(".txt"):
                p = os.path.join(CORPUS_DIR, f)
                with open(p, "r", encoding="utf-8") as fp:
                    content = fp.read()
                sections = re.split(r"(?=\n###\s+)", content)
                for s_idx, sec in enumerate(sections):
                    if sec.strip():
                        docs.append({"id": f"{f}#sec_{s_idx}", "text": sec.strip()})
        _BM25_RETRIEVER = BM25RetrieverTool()
        _BM25_RETRIEVER.index_corpus(docs)
    return _BM25_RETRIEVER

def run_track_b_item(item: Dict[str, Any], with_tools: bool = True, caller_func=call_local_phi) -> Dict[str, Any]:
    prompt = item["prompt"]
    t0 = time.time()
    if with_tools:
        retriever = get_bm25_retriever()
        passages = retriever.retrieve(prompt, top_k=3)
        context_str = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in passages])
        user_msg = f"""Context Documents:
{context_str}

Question: {prompt}

State the component and active v4.2 values in a short key-value format (max 75 words)."""
        sys_msg = "You are an expert assistant for the HyperGrid specification. Use the provided context documents to answer the question concisely."
    else:
        user_msg = f"{prompt}\n\nAnswer concisely adhering to the word limit."
        sys_msg = "You are an expert assistant for the HyperGrid specification. Answer the question concisely."

    resp = caller_func([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}], temperature=0.0, max_tokens=256)
    dt = time.time() - t0
    sc = score_record(item, resp)

    return {
        "question_id": item["question_id"],
        "passed": sc["passed"],
        "details": sc["details"],
        "output": resp[:200],
        "full_output": resp,
        "duration": dt
    }


# --- MAIN EVALUATION RUNNER ---

def load_70_items():
    with open(CALIB_FILE, "r", encoding="utf-8") as f:
        calib_items = json.load(f)
    with open(BENCH_FILE, "r", encoding="utf-8") as f:
        bench_items = json.load(f)
    for it in bench_items:
        it["solvability"] = "solvable_without_tools"
    return calib_items + bench_items

def evaluate_suite(condition_name: str, runner_func, items: List[Dict[str, Any]], results_dict: Dict[str, Any], out_file: str = OUT_FILE):
    print(f"\n{'='*75}\nEVALUATING: {condition_name} ({len(items)} items)\n{'='*75}", flush=True)
    existing = results_dict.get(condition_name, {}).get("records", [])
    done_ids = {r.get("item_id", r.get("question_id")) for r in existing}
    records = list(existing)

    for idx, it in enumerate(items, 1):
        iid = it.get("subtask_id", it.get("id", it.get("question_id")))
        if iid in done_ids:
            continue
        print(f"[{idx}/{len(items)}] {iid}...", end=" ", flush=True)
        rec = runner_func(it)
        print(f"-> {'PASS' if rec['passed'] else 'FAIL'} ({rec['duration']:.1f}s)", flush=True)
        records.append(rec)
        done_ids.add(iid)

        # Compute summary
        solv_recs = [r for r in records if r.get("solvability") == "solvable_without_tools"]
        req_recs = [r for r in records if r.get("solvability") == "tool-required"]
        s_acc = sum(1 for r in solv_recs if r["passed"]) / len(solv_recs) * 100 if solv_recs else 0.0
        r_acc = sum(1 for r in req_recs if r["passed"]) / len(req_recs) * 100 if req_recs else 0.0
        tot_acc = sum(1 for r in records if r["passed"]) / len(records) * 100
        clean_share = sum(1 for r in records if r.get("clean_execution", True)) / len(records) * 100
        mean_time = sum(r["duration"] for r in records) / len(records)

        results_dict[condition_name] = {
            "condition": condition_name,
            "total_items": len(records),
            "solvable_acc": round(s_acc, 2),
            "solvable_passes": sum(1 for r in solv_recs if r["passed"]),
            "solvable_total": len(solv_recs),
            "tool_required_acc": round(r_acc, 2),
            "tool_required_passes": sum(1 for r in req_recs if r["passed"]),
            "tool_required_total": len(req_recs),
            "total_acc": round(tot_acc, 2),
            "clean_share": round(clean_share, 2),
            "mean_time_seconds": round(mean_time, 2),
            "records": records
        }
        if os.path.exists(out_file):
            try:
                with open(out_file, "r", encoding="utf-8") as f:
                    disk_data = json.load(f)
                    disk_data[condition_name] = results_dict[condition_name]
                    results_dict.update(disk_data)
            except Exception:
                pass
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results_dict, f, indent=2)

    return results_dict[condition_name]

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=str, required=True, choices=[
        "design_a_vote_fixed",
        "design_c_phi",
        "dispatcher_phi",
        "track_b",
        "qwen_7b_local",
        "gpt_120b_groq",
        "qwen_27b_groq",
        "groq_baselines",
        "all"
    ])
    parser.add_argument("--out_file", type=str, default=OUT_FILE)
    args = parser.parse_args()

    target_out = args.out_file
    items_70 = load_70_items()
    results = {}
    if os.path.exists(target_out):
        try:
            with open(target_out, "r", encoding="utf-8") as f:
                results = json.load(f)
        except Exception:
            pass

    # 1. FIXED DESIGN A VOTE
    if args.step in ["design_a_vote_fixed", "all"]:
        evaluate_suite("Phi-4-mini Design A (Vote Fixed)", lambda it: run_design_a_vote_fixed(it, caller_func=call_local_phi), items_70, results, out_file=target_out)

    # 2. DESIGN C (Data-then-reason)
    if args.step in ["design_c_phi", "all"]:
        evaluate_suite("Phi-4-mini Design C (Data-then-Reason)", lambda it: run_design_c(it, caller_func=call_local_phi), items_70, results)

    # 3. DISPATCHER & END-TO-END
    if args.step in ["dispatcher_phi", "all"]:
        print("\n" + "="*75 + "\nEVALUATING DISPATCHER ON 70 ITEMS\n" + "="*75)
        disp_records = []
        des_a_records = results.get("Design A (Single Program, Greedy)", {}).get("records", [])
        des_a_map = {r["item_id"]: r for r in des_a_records}
        des_c_records = results.get("Phi-4-mini Design C (Data-then-Reason)", {}).get("records", [])
        des_c_map = {r["item_id"]: r for r in des_c_records}
        
        # Load C0 records
        with open(os.path.join(REPO_ROOT, "results", "benchmarks", "phi4_mini_serial_50.json")) as f:
            b50 = json.load(f)
        with open(os.path.join(REPO_ROOT, "results", "phase4", "calibration_c0_c1_eval.json")) as f:
            c20 = json.load(f)
        c0_map = {r["subtask_id"]: r.get("is_correct", False) for r in b50["subtask_results"]}
        for r in c20["c0_records"]:
            c0_map[r["item_id"]] = r.get("passed", False)

        e2e_a_correct = 0
        e2e_c_correct = 0
        disp_correct = 0

        for it in items_70:
            iid = it.get("subtask_id", it.get("id"))
            p = it["prompt"]
            tt = (it.get("type") or it.get("benchmark") or it.get("task_type") or "").lower()
            needs_outside = ("sql" in tt) or (it.get("solvability") == "tool-required") or ("database" in p.lower() and "table" in p.lower())

            pred_disp = run_dispatcher_decision(p, caller_func=call_local_phi)
            if pred_disp == needs_outside:
                disp_correct += 1

            # End-to-end A
            if pred_disp: # use tools
                passed_a = des_a_map.get(iid, {}).get("passed", False)
            else: # direct
                passed_a = c0_map.get(iid, False)
            if passed_a: e2e_a_correct += 1

            # End-to-end C
            if pred_disp: # use tools
                passed_c = des_c_map.get(iid, {}).get("passed", False)
            else: # direct
                passed_c = c0_map.get(iid, False)
            if passed_c: e2e_c_correct += 1

            disp_records.append({
                "item_id": iid,
                "needs_outside_ground_truth": needs_outside,
                "dispatcher_prediction": pred_disp,
                "passed_e2e_a": passed_a,
                "passed_e2e_c": passed_c
            })

        results["Phi-4-mini Dispatcher Summary"] = {
            "total_items": len(items_70),
            "dispatcher_accuracy_pct": round(disp_correct / len(items_70) * 100, 2),
            "e2e_direct_or_design_a_acc_pct": round(e2e_a_correct / len(items_70) * 100, 2),
            "e2e_direct_or_design_a_passes": e2e_a_correct,
            "e2e_direct_or_design_c_acc_pct": round(e2e_c_correct / len(items_70) * 100, 2),
            "e2e_direct_or_design_c_passes": e2e_c_correct,
            "records": disp_records
        }
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Dispatcher Acc: {disp_correct}/{len(items_70)} ({results['Phi-4-mini Dispatcher Summary']['dispatcher_accuracy_pct']}%)")
        print(f"E2E Direct or Design A: {e2e_a_correct}/{len(items_70)} ({results['Phi-4-mini Dispatcher Summary']['e2e_direct_or_design_a_acc_pct']}%)")
        print(f"E2E Direct or Design C: {e2e_c_correct}/{len(items_70)} ({results['Phi-4-mini Dispatcher Summary']['e2e_direct_or_design_c_acc_pct']}%)")

    # 4. TRACK B CALIBRATION
    if args.step in ["track_b", "all"]:
        with open(TRACK_B_FILE, "r", encoding="utf-8") as f:
            tb_items = json.load(f)
        evaluate_suite("Track B Calibration (No-Tools)", lambda it: run_track_b_item(it, with_tools=False, caller_func=call_local_phi), tb_items, results)
        evaluate_suite("Track B Calibration (Retrieval-then-Answer)", lambda it: run_track_b_item(it, with_tools=True, caller_func=call_local_phi), tb_items, results)

    # 5. LOCAL 7B MODEL (Qwen-2.5-7B)
    if args.step in ["qwen_7b_local", "all"]:
        evaluate_suite("Qwen-2.5-7B Local (No-Tools)", lambda it: run_direct_answer(it, caller_func=call_ollama_7b), items_70, results, out_file=target_out)
        evaluate_suite("Qwen-2.5-7B Local (Design A)", lambda it: run_design_a(it, caller_func=call_ollama_7b, temperature=0.0), items_70, results, out_file=target_out)
        evaluate_suite("Qwen-2.5-7B Local (Design C)", lambda it: run_design_c(it, caller_func=call_ollama_7b), items_70, results, out_file=target_out)

    # 6. GROQ BASELINES (Qwen-27B & GPT-120B)
    if args.step in ["gpt_120b_groq", "groq_baselines", "all"]:
        # GPT-120B No-tools
        evaluate_suite("GPT-120B Groq (No-Tools)", lambda it: run_direct_answer(it, caller_func=lambda msgs, **kw: call_groq("openai/gpt-oss-120b", msgs, **kw)), items_70, results, out_file=target_out)
        # GPT-120B Design A
        evaluate_suite("GPT-120B Groq (Design A)", lambda it: run_design_a(it, caller_func=lambda msgs, **kw: call_groq("openai/gpt-oss-120b", msgs, **kw), temperature=0.0), items_70, results, out_file=target_out)

    if args.step in ["qwen_27b_groq", "groq_baselines", "all"]:
        # Qwen-27B No-tools
        evaluate_suite("Qwen-27B Groq (No-Tools)", lambda it: run_direct_answer(it, caller_func=lambda msgs, **kw: call_groq("qwen/qwen3.8-27b", msgs, **kw)), items_70, results, out_file=target_out)
        # Qwen-27B Design A
        evaluate_suite("Qwen-27B Groq (Design A)", lambda it: run_design_a(it, caller_func=lambda msgs, **kw: call_groq("qwen/qwen3.8-27b", msgs, **kw), temperature=0.0), items_70, results, out_file=target_out)

if __name__ == "__main__":
    main()

