"""
Specialist Pipeline Architecture for Phi-4-mini (No Adapters).

Orchestration Stages:
1. Stage 1: Analyser (Model Call)
   - Input: Task prompt string (prompt: str)
   - Decides: needs_outside_data (YES/NO), source (DATABASE/CORPUS/NONE), database_name
   - Fallback (Rule, target <=10%): Scans prompt for database/corpus keywords if unparseable.

2. Stage 2: Router (Rule)
   - Input: Analyser output
   - If needs_outside_data == False:
     -> DIRECT ANSWER PATH: Single model call with zero decomposition.
   - If needs_outside_data == True:
     -> OUTSIDE DATA ORCHESTRATION: Proceeds through Stages 3-7.

3. Stage 3: Decomposer (Model Call)
   - Input: Task prompt string
   - Breaks task into data retrieval step (Subtask 1) and downstream reasoning (Subtask 2).
   - Generic Over-splitting Handler (Rule): If >2 subtasks returned, merges all subsequent
     subtasks (subtasks[1:]) into Subtask 2. Never relies on hard-coded stage count.

4. Stage 4: Colorer with Feedback (Model Call, max 3 levels)
   - Input: Subtask descriptions
   - Assigns execution colors: SQL_DATA, CORPUS_RAG, CODE_EXEC, DIRECT_REASON.
   - Feedback Loop: Re-prompts up to 3 times if Subtask 1 is not a retrieval modality.

5. Stage 5: Matcher (Model Call)
   - Input: Colored subtasks
   - Dispatches subtasks to specialist execution tools.

6. Stage 6: Data Fetch Specialist Execution (Tool + Model Call)
   - SQLite Specialist: Generates SQLite query selecting only requested column; runs via sandbox with 1 retry on error.
   - Corpus Specialist: Retrieves top-3 passages via BM25 from Track B corpus.

7. Stage 7: Downstream Reasoning Specialist with Numeric Passing (Model Call)
   - Injects clean numeric value or retrieved context directly into prompt.
   - Executes Python sandbox for code, or direct reasoning for math/logic.
   - Concludes with final verified answer.

Strict Leakage Constraint:
The entry point run_specialist_pipeline accepts ONLY the task text string (prompt: str).
It never receives or accesses any dataset metadata dictionary.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from src.sandbox.runner import execute_python_code
from src.tools.tolerant_harness import execute_sql_tolerant, KNOWN_DATABASES
from src.tools.retriever_tool import BM25RetrieverTool

LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"

# Global cached BM25 retriever
_RETRIEVER = None


def get_bm25_retriever():
    global _RETRIEVER
    if _RETRIEVER is None:
        docs = []
        corpus_dir = os.path.join(REPO_ROOT, "data", "track_b", "corpus")
        if os.path.exists(corpus_dir):
            for fn in sorted(os.listdir(corpus_dir)):
                if fn.endswith(".md"):
                    with open(os.path.join(corpus_dir, fn), "r", encoding="utf-8") as f:
                        text = f.read()
                    sections = re.split(r"(?=###\s+)", text)
                    for s_idx, sec in enumerate(sections):
                        sec_str = sec.strip()
                        if sec_str:
                            docs.append({"id": f"{fn}#sec_{s_idx}", "doc_id": f"{fn}#sec_{s_idx}", "text": sec_str})
        _RETRIEVER = BM25RetrieverTool()
        _RETRIEVER.index_corpus(docs)
    return _RETRIEVER


def get_table_schema(db_name: str) -> str:
    """Extracts table schema DDL from SQLite database."""
    import sqlite3
    db_clean = db_name.strip().replace("'", "").replace('"', '').replace("`", "")
    db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_clean, f"{db_clean}.sqlite")
    if not os.path.exists(db_path):
        for cand in KNOWN_DATABASES:
            if cand.lower() == db_clean.lower():
                db_clean = cand
                db_path = os.path.join(REPO_ROOT, "data", "spider", "database", db_clean, f"{db_clean}.sqlite")
                break
    if not os.path.exists(db_path):
        return ""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL;")
        rows = cur.fetchall()
        conn.close()
        return "\n".join(" ".join(r[0].split()) for r in rows)
    except Exception:
        return ""


def call_phi(messages: List[Dict[str, str]], temperature: float = 0.0, max_tokens: int = 1024) -> str:
    """Calls local llama-server on port 8080 with retry backoff."""
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if temperature == 0.0:
        payload["seed"] = 42

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        LLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                res_obj = json.loads(resp.read().decode("utf-8"))
                return res_obj["choices"][0]["message"]["content"].strip()
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return ""


def extract_sql_from_text(text: str) -> str:
    """Extracts SQL query from fenced block or text."""
    m = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(";")
    lines = text.strip().split("\n")
    for line in lines:
        if line.strip().upper().startswith("SELECT"):
            return line.strip().rstrip(";")
    return text.strip().rstrip(";")


# =========================================================================
# STAGE 1: TASK ANALYSER (MODEL CALL)
# =========================================================================

ANALYSIS_SYS = """You are an expert task analyser. Analyze the given user task.
Determine whether answering the task requires retrieving external outside data (such as querying an external SQLite database or searching a specification document corpus).

Rules:
1. If the task names an external database (e.g. contains '[Database: ...]' or mentions querying a database) or requires executing a database query:
   NEEDS_OUTSIDE_DATA: YES
   SOURCE: DATABASE
   DATABASE_NAME: <name of database>
2. If the task asks about the HyperGrid specification or corpus:
   NEEDS_OUTSIDE_DATA: YES
   SOURCE: CORPUS
   DATABASE_NAME: NONE
3. Otherwise (self-contained math problem, programming/code implementation, multiple-choice QA, or logic puzzle):
   NEEDS_OUTSIDE_DATA: NO
   SOURCE: NONE
   DATABASE_NAME: NONE

Respond in EXACTLY this format:
NEEDS_OUTSIDE_DATA: <YES or NO>
SOURCE: <DATABASE, CORPUS, or NONE>
DATABASE_NAME: <name or NONE>"""


def task_asks_for_query(prompt: str) -> bool:
    """
    Stage 1/2 Helper: Generic detection of whether the user task asks for a query as the answer.
    Operates strictly on the raw prompt text string (never on item metadata).
    """
    p_lower = prompt.lower()
    indicators = [
        "write a valid sqlite query",
        "write a sqlite query",
        "write an sql query",
        "write a sql query",
        "return a valid sqlite query",
        "return an sqlite query",
        "return an sql query",
    ]
    if any(ind in p_lower for ind in indicators):
        return True
    if "```sql" in p_lower and ("query" in p_lower or "select" in p_lower):
        if re.search(r"(?:write|return|output|provide)\s+.*?(?:query|sql)", p_lower):
            return True
    return False


def analyse_task_model_call(prompt: str) -> Tuple[Dict[str, Any], bool]:
    """
    Stage 1: Model Call to analyse if outside data is needed.
    Returns: (analysis_dict, used_fallback: bool)
    """
    resp = call_phi([
        {"role": "system", "content": ANALYSIS_SYS},
        {"role": "user", "content": f"Task Prompt:\n{prompt}\n\nAnalysis:"}
    ], temperature=0.0, max_tokens=100)

    # Parse model response
    needs_m = re.search(r"NEEDS_OUTSIDE_DATA:\s*(YES|NO)", resp, re.IGNORECASE)
    source_m = re.search(r"SOURCE:\s*(DATABASE|CORPUS|NONE)", resp, re.IGNORECASE)
    db_m = re.search(r"DATABASE_NAME:\s*([a-zA-Z0-9_\-]+)", resp, re.IGNORECASE)

    asks_query = task_asks_for_query(prompt)

    if needs_m and source_m:
        needs_val = needs_m.group(1).upper() == "YES"
        source_val = source_m.group(1).upper()
        db_val = db_m.group(1) if db_m and db_m.group(1).upper() != "NONE" else ""
        return {
            "needs_outside_data": needs_val,
            "source": source_val,
            "database_name": db_val,
            "asks_for_query": asks_query,
            "raw_response": resp
        }, False

    # Fallback (Rule, if unparseable):
    p_lower = prompt.lower()
    is_corpus = "hypergrid" in p_lower or "v4.2" in p_lower
    db_name = ""
    for db in KNOWN_DATABASES:
        if db.lower() in p_lower:
            db_name = db
            break
    has_db = bool(db_name) or "[database:" in p_lower or "query the" in p_lower

    if is_corpus:
        return {"needs_outside_data": True, "source": "CORPUS", "database_name": "", "asks_for_query": asks_query, "raw_response": resp}, True
    if has_db:
        return {"needs_outside_data": True, "source": "DATABASE", "database_name": db_name, "asks_for_query": asks_query, "raw_response": resp}, True

    return {"needs_outside_data": False, "source": "NONE", "database_name": "", "asks_for_query": asks_query, "raw_response": resp}, True


# =========================================================================
# STAGE 3: DECOMPOSER (MODEL CALL)
# =========================================================================

DECOMP_SYS = """You are an expert task decomposer. Break down the task into sequential subtasks:
Subtask 1: The data retrieval step (the exact database query or corpus search to retrieve the necessary data).
Subtask 2: The downstream reasoning, calculation, or synthesis step that uses the retrieved data to produce the final answer.

Format your response as:
Subtask 1: <instruction>
Subtask 2: <instruction>"""


def decompose_task_model_call(prompt: str) -> Tuple[List[str], bool]:
    """
    Stage 3: Model Call to decompose outside data task.
    Generic over-splitting handler merges all subsequent steps into Subtask 2.
    Returns: (subtasks_list, used_fallback: bool)
    """
    resp = call_phi([
        {"role": "system", "content": DECOMP_SYS},
        {"role": "user", "content": f"Task Prompt:\n{prompt}\n\nDecomposition:"}
    ], temperature=0.0, max_tokens=300)

    # Extract subtasks generically
    matches = re.findall(
        r"(?:^|\n)\s*(?:Subtask|Stage|\bStep)\s*(\d+)\s*:\s*(.*?)(?=(?:\n\s*(?:Subtask|Stage|\bStep)\s*\d+\s*:|$))",
        resp,
        re.DOTALL | re.IGNORECASE
    )

    if matches and len(matches) >= 2:
        # Generic over-splitting handler: Subtask 1 is data retrieval; subtasks[1:] merged into Subtask 2
        st1 = matches[0][1].strip()
        downstream_parts = [m[1].strip() for m in matches[1:] if m[1].strip()]
        st2 = " Then: ".join(downstream_parts)
        return [st1, st2], False

    if matches and len(matches) == 1:
        return [matches[0][1].strip(), prompt], False

    # Fallback (Rule, if unparseable):
    sentences = [s.strip() for s in prompt.split(";") if s.strip()]
    if len(sentences) >= 2:
        return [sentences[0], " Then: ".join(sentences[1:])], True
    return [prompt, prompt], True


# =========================================================================
# STAGE 4: COLORER WITH FEEDBACK (MODEL CALL, MAX 3 LEVELS)
# =========================================================================

COLORER_SYS = """You are an execution modality colorer. Assign an execution color to each subtask:
Available Colors:
- SQL_DATA: Querying a SQLite database.
- CORPUS_RAG: Retrieving passages from a document corpus.
- CODE_EXEC: Writing and running Python code.
- DIRECT_REASON: Mathematical calculation or logical reasoning.

Format your response as:
Subtask 1 Color: <COLOR>
Subtask 2 Color: <COLOR>"""


def color_subtasks_with_feedback(subtasks: List[str], prompt: str, source: str, max_levels: int = 3) -> Tuple[List[str], bool]:
    """
    Stage 4: Model Call with feedback loop (up to max_levels) to assign colors.
    Returns: (colors_list, used_fallback: bool)
    """
    subtasks_text = "\n".join(f"Subtask {i}: {s}" for i, s in enumerate(subtasks, 1))
    messages = [
        {"role": "system", "content": COLORER_SYS},
        {"role": "user", "content": f"{subtasks_text}\n\nColors:"}
    ]

    for level in range(1, max_levels + 1):
        resp = call_phi(messages, temperature=0.0, max_tokens=100)

        c1_m = re.search(r"Subtask\s*1\s*Color:\s*([A-Z_]+)", resp, re.IGNORECASE)
        c2_m = re.search(r"Subtask\s*2\s*Color:\s*([A-Z_]+)", resp, re.IGNORECASE)

        if c1_m and c2_m:
            c1 = c1_m.group(1).upper()
            c2 = c2_m.group(1).upper()
            # Validate Subtask 1 is a retrieval modality
            valid_retrieval = c1 in ("SQL_DATA", "CORPUS_RAG")
            if valid_retrieval:
                return [c1, c2], False

            # Feedback loop
            if level < max_levels:
                fb_msg = (
                    "Feedback: Subtask 1 is a data-retrieval step and must be colored as either SQL_DATA or CORPUS_RAG. "
                    "Please re-assign colors."
                )
                messages.append({"role": "assistant", "content": resp})
                messages.append({"role": "user", "content": fb_msg})
                continue

    # Fallback (Rule, if unparseable or rejected after 3 levels):
    c1_fallback = "CORPUS_RAG" if source == "CORPUS" else "SQL_DATA"
    return [c1_fallback, "DIRECT_REASON"], True


# =========================================================================
# STAGE 5: MATCHER (MODEL CALL)
# =========================================================================

MATCHER_SYS = """You are a specialist matcher. Bind each subtask to an execution specialist:
Available Specialists:
- SQLite Specialist: Runs a SQL query against a local SQLite database.
- HyperGrid Corpus Specialist: Searches document corpus using BM25.
- Python Sandbox Specialist: Executes Python code in a secure sandbox.
- Direct Reasoning Specialist: Performs analytical and step-by-step reasoning.

Format your response as:
Subtask 1 Specialist: <Specialist Name>
Subtask 2 Specialist: <Specialist Name>"""


def match_specialists_model_call(subtasks: List[str], colors: List[str]) -> Tuple[List[str], bool]:
    """
    Stage 5: Model Call to match subtasks to execution specialists.
    Returns: (specialists_list, used_fallback: bool)
    """
    text_desc = "\n".join(f"Subtask {i} [{colors[i-1]}]: {subtasks[i-1]}" for i in range(1, len(subtasks) + 1))
    resp = call_phi([
        {"role": "system", "content": MATCHER_SYS},
        {"role": "user", "content": f"{text_desc}\n\nAssignments:"}
    ], temperature=0.0, max_tokens=100)

    s1_m = re.search(r"Subtask\s*1\s*Specialist:\s*(.*?)(?=\n|$)", resp, re.IGNORECASE)
    s2_m = re.search(r"Subtask\s*2\s*Specialist:\s*(.*?)(?=\n|$)", resp, re.IGNORECASE)

    if s1_m and s2_m:
        return [s1_m.group(1).strip(), s2_m.group(1).strip()], False

    # Fallback (Rule, if unparseable):
    color_map = {
        "SQL_DATA": "SQLite Specialist",
        "CORPUS_RAG": "HyperGrid Corpus Specialist",
        "CODE_EXEC": "Python Sandbox Specialist",
        "DIRECT_REASON": "Direct Reasoning Specialist"
    }
    s1 = color_map.get(colors[0], "SQLite Specialist")
    s2 = color_map.get(colors[1], "Direct Reasoning Specialist")
    return [s1, s2], True


# =========================================================================
# STAGE 6: DATA FETCH SPECIALIST EXECUTION
# =========================================================================

def execute_data_fetch(subtask_1: str, color_1: str, db_name: str, prompt: str) -> Tuple[bool, str, Any]:
    """
    Stage 6: Executes data retrieval via SQLite or BM25 Corpus.
    Returns: (clean_execution: bool, output_text: str, extracted_data: Any)
    """
    if color_1 == "CORPUS_RAG" or "hypergrid" in prompt.lower():
        retriever = get_bm25_retriever()
        passages = retriever.retrieve(prompt, top_k=5)
        context_str = "\n\n".join([f"[{p.doc_id}]:\n{p.text}" for p in passages])
        return True, context_str, context_str

    # SQLite Specialist
    db_to_use = db_name
    if not db_to_use or db_to_use not in KNOWN_DATABASES:
        # Detect from prompt
        for db in KNOWN_DATABASES:
            if db.lower() in prompt.lower():
                db_to_use = db
                break
    if not db_to_use:
        return False, "Error: No database identified in task prompt", None

    schema_str = get_table_schema(db_to_use)

    sys_sql = (
        "You are an expert SQLite query specialist. Write exactly one SQLite query enclosed in ```sql ... ```. "
        "Select ONLY the single requested column. Do NOT include extra count, rank, or helper columns in the SELECT clause."
    )
    user_sql = (
        f"Database: {db_to_use}\n"
        f"Schema:\n{schema_str}\n"
        f"Task: {subtask_1}\n"
        f"Instruction: Return only the requested column.\n\n"
        f"Write one SQLite query in ```sql ... ```:"
    )

    resp_1 = call_phi([
        {"role": "system", "content": sys_sql},
        {"role": "user", "content": user_sql}
    ], temperature=0.0, max_tokens=256)

    query_1 = extract_sql_from_text(resp_1)
    clean, out_text = execute_sql_tolerant(db_to_use, query_1, prompt_context=prompt)

    if not clean:
        # Retry with error message
        retry_msg = (
            f"The query produced an error: {out_text}\n"
            f"Please output the corrected SQLite query in ```sql ... ```. Select ONLY the single requested column."
        )
        resp_2 = call_phi([
            {"role": "system", "content": sys_sql},
            {"role": "user", "content": user_sql},
            {"role": "assistant", "content": resp_1},
            {"role": "user", "content": retry_msg}
        ], temperature=0.0, max_tokens=256)
        query_2 = extract_sql_from_text(resp_2)
        clean, out_text = execute_sql_tolerant(db_to_use, query_2, prompt_context=prompt)
        final_query = query_2
    else:
        final_query = query_1

    # Extract scalar if numeric
    scalar_val = out_text
    nums = re.findall(r"-?\d+(?:\.\d+)?", out_text)
    if nums:
        scalar_val = float(nums[-1]) if "." in nums[-1] else int(nums[-1])

    result_summary = f"SQL Query Executed:\n```sql\n{final_query}\n```\nQuery Output: {out_text}"
    return clean, result_summary, scalar_val


# =========================================================================
# STAGE 7: DOWNSTREAM REASONING SPECIALIST (NUMERIC PASSING)
# =========================================================================

def execute_downstream_reasoning(subtask_2: str, fetched_data: Any, fetched_summary: str, color_2: str, prompt: str = "") -> Tuple[bool, str, str]:
    """
    Stage 7: Downstream Reasoning with clean numeric passing.
    Returns: (clean_execution: bool, full_output: str, final_answer: str)
    """
    # Track B technical document retrieval path
    if "[HyperGrid_" in fetched_summary or "hypergrid" in prompt.lower() or color_2 == "CORPUS_RAG":
        user_msg = (
            f"Task:\n{prompt}\n\n"
            f"Retrieved Documents:\n{fetched_summary}\n\n"
            f"Answer the question in concise key-value pairs (max 75 words). "
            f"Explicitly include all component designations, names, and parameters mentioned in the text.\n"
            f"Conclude with: Final Answer: <key-value pairs>"
        )
        resp = call_phi([
            {"role": "system", "content": "You are an expert technical assistant. Answer the question based on the provided reference documents in concise key-value format."},
            {"role": "user", "content": user_msg}
        ], temperature=0.0, max_tokens=512)
        return True, resp, resp

    # Clean numeric passing to prevent conversational error compounding
    if isinstance(fetched_data, (int, float)):
        context_str = f"The verified data retrieved from the database is: {fetched_data}."
    else:
        context_str = f"The data retrieved is:\n{fetched_summary}"

    user_msg = (
        f"Task:\n{prompt}\n\n"
        f"Retrieved Context:\n{context_str}\n\n"
        f"Step to Complete:\n{subtask_2}\n\n"
        f"Reason step-by-step and conclude with 'Final Answer: <answer>' or '#### <answer>'."
    )

    resp = call_phi([
        {"role": "system", "content": "You are an expert reasoning assistant. Use the provided retrieved data to solve the task step-by-step. Conclude with 'Final Answer: <answer>' or '#### <answer>'."},
        {"role": "user", "content": user_msg}
    ], temperature=0.0, max_tokens=768)

    # If code execution is indicated in color_2 or response contains python code block
    if color_2 == "CODE_EXEC" or "```python" in resp:
        code_m = re.search(r"```python\s*(.*?)\s*```", resp, re.DOTALL | re.IGNORECASE)
        if code_m:
            code = code_m.group(1).strip()
            res = execute_python_code(code, timeout_seconds=5.0)
            if res.exit_code == 0 and res.stdout.strip():
                out_v = res.stdout.strip()
                ans_nums = re.findall(r"-?\d+", out_v)
                v = ans_nums[-1] if ans_nums else out_v
                return True, f"{resp}\n\nExecuted Python Output: {out_v}\nFinal Answer: {v}", f"Final Answer: {v}"

    ans_m = re.search(r"(?:Final\s+Answer:|Answer:)\s*(.*)", resp, re.DOTALL | re.IGNORECASE)
    clean_ans = ans_m.group(0).strip() if ans_m else resp
    return True, resp, clean_ans


# =========================================================================
# FULL SPECIALIST PIPELINE ENTRY POINT (PROMPT-ONLY INPUT)
# =========================================================================

def run_specialist_pipeline(prompt: str) -> Dict[str, Any]:
    """
    Entry point for the Specialist Pipeline.
    Strictly accepts ONLY the prompt text string (prompt: str).
    Returns execution record dictionary.
    """
    t0 = time.time()
    fallbacks = {
        "analyser": False,
        "database_identifier": False,
        "decomposer": False,
        "colorer": False,
        "matcher": False
    }

    # Stage 1: Analyser (Model Call)
    analysis, fb_analyser = analyse_task_model_call(prompt)
    fallbacks["analyser"] = fb_analyser
    needs_outside = analysis["needs_outside_data"]

    # Stage 2: Routing Rule
    if analysis.get("asks_for_query", False):
        # DIRECT QUERY-WRITING PATH (v1.1 SQL FIX)
        t_sql = time.time()
        db_to_use = analysis.get("database_name", "")
        if not db_to_use or db_to_use not in KNOWN_DATABASES:
            for db in KNOWN_DATABASES:
                if db.lower() in prompt.lower():
                    db_to_use = db
                    break
        if not db_to_use:
            fallbacks["database_identifier"] = True
            schema_str = ""
        else:
            schema_str = get_table_schema(db_to_use)

        if "[database schema:" not in prompt.lower() and schema_str:
            query_prompt = f"Database: {db_to_use}\nSchema:\n{schema_str}\n\n{prompt}"
        else:
            query_prompt = prompt

        direct_sql_sys = (
            "You are an expert SQL assistant. Given the database schema and question, write a single valid SQLite query that answers the question.\n"
            "Guidelines:\n"
            "- Return ONLY the exact column(s) requested by the question. Do not include auxiliary count or aggregate columns in the SELECT clause unless explicitly asked.\n"
            "- Ensure necessary table joins are included when attributes belong to relational tables.\n"
            "- Output strictly the SQL query enclosed in ```sql\n<query>\n```. Do not provide conversational explanations."
        )

        resp_1 = call_phi([
            {"role": "system", "content": direct_sql_sys},
            {"role": "user", "content": query_prompt}
        ], temperature=0.0, max_tokens=256)
        query_1 = extract_sql_from_text(resp_1)
        clean_1, out_1 = execute_sql_tolerant(db_to_use, query_1, prompt_context=prompt)
        final_query = query_1
        retried = False
        all_clean = clean_1

        if not clean_1:
            retried = True
            retry_msg = (
                f"The query failed execution with error:\n{out_1}\n"
                f"Please fix the query and provide a valid SQLite query in ```sql ... ```."
            )
            resp_2 = call_phi([
                {"role": "system", "content": direct_sql_sys},
                {"role": "user", "content": query_prompt},
                {"role": "assistant", "content": f"```sql\n{query_1}\n```"},
                {"role": "user", "content": retry_msg}
            ], temperature=0.0, max_tokens=256)
            query_2 = extract_sql_from_text(resp_2)
            clean_2, out_2 = execute_sql_tolerant(db_to_use, query_2, prompt_context=prompt)
            final_query = query_2
            all_clean = clean_2

        formatted_output = f"```sql\n{final_query}\n```"
        dt = time.time() - t0

        return {
            "routed_to": "direct_sql",
            "answered_by": "phi-4-mini",
            "source": analysis.get("source", "DATABASE"),
            "needs_outside_data": True,
            "clean_execution": all_clean,
            "output": formatted_output,
            "full_output": formatted_output,
            "final_answer": formatted_output,
            "fallbacks": fallbacks,
            "subtasks": [prompt],
            "colors": ["SQL_DATA"],
            "retried": retried,
            "stages": [
                {
                    "stage_num": 1,
                    "name": "direct_sql_query",
                    "type": "model_call",
                    "clean_execution": all_clean,
                    "retried": retried,
                    "output": formatted_output,
                    "duration": time.time() - t_sql
                }
            ],
            "duration": dt
        }

    if not needs_outside:
        # DIRECT ANSWER PATH: Single model call, zero decomposition
        t_direct = time.time()
        direct_resp = call_phi([
            {"role": "system", "content": "You are a helpful, precise assistant. Reason step-by-step and provide your final answer in the requested format."},
            {"role": "user", "content": prompt}
        ], temperature=0.0, max_tokens=1024)
        dt = time.time() - t0

        return {
            "routed_to": "direct",
            "answered_by": "phi-4-mini",
            "source": analysis.get("source", "NONE"),
            "needs_outside_data": False,
            "clean_execution": bool(direct_resp.strip()),
            "output": direct_resp[:300],
            "full_output": direct_resp,
            "final_answer": direct_resp,
            "fallbacks": fallbacks,
            "subtasks": [],
            "colors": [],
            "stages": [
                {
                    "stage_num": 1,
                    "name": "direct_reasoning",
                    "type": "model_call",
                    "clean_execution": bool(direct_resp.strip()),
                    "output": direct_resp[:200],
                    "duration": time.time() - t_direct
                }
            ],
            "duration": dt
        }

    # OUTSIDE DATA ORCHESTRATION PATH
    # Stage 3: Decomposer (Model Call)
    subtasks, fb_decomp = decompose_task_model_call(prompt)
    fallbacks["decomposer"] = fb_decomp

    # Stage 4: Colorer with Feedback (Model Call, max 3 levels)
    colors, fb_colorer = color_subtasks_with_feedback(subtasks, prompt, source=analysis["source"], max_levels=3)
    fallbacks["colorer"] = fb_colorer

    # Stage 5: Matcher (Model Call)
    specialists, fb_matcher = match_specialists_model_call(subtasks, colors)
    fallbacks["matcher"] = fb_matcher

    # Stage 6: Data Fetch Specialist Execution
    t_s6 = time.time()
    clean_fetch, fetch_summary, fetched_val = execute_data_fetch(
        subtask_1=subtasks[0],
        color_1=colors[0],
        db_name=analysis.get("database_name", ""),
        prompt=prompt
    )
    dt_s6 = time.time() - t_s6
    if not clean_fetch and "No database identified" in str(fetch_summary):
        fallbacks["database_identifier"] = True

    # Stage 7: Downstream Reasoning Specialist with Numeric Passing
    t_s7 = time.time()
    clean_downstream, full_downstream, clean_ans = execute_downstream_reasoning(
        subtask_2=subtasks[1],
        fetched_data=fetched_val,
        fetched_summary=fetch_summary,
        color_2=colors[1],
        prompt=prompt
    )
    dt_s7 = time.time() - t_s7

    dt_total = time.time() - t0
    all_clean = clean_fetch and clean_downstream

    # Combine query summary and reasoning for transparent scoring
    combined_output = f"{fetch_summary}\n\n{full_downstream}"

    return {
        "routed_to": "outside_data",
        "answered_by": "phi-4-mini",
        "source": analysis.get("source", ""),
        "needs_outside_data": True,
        "clean_execution": all_clean,
        "output": combined_output[:300],
        "full_output": combined_output,
        "final_answer": clean_ans,
        "fallbacks": fallbacks,
        "subtasks": subtasks,
        "colors": colors,
        "stages": [
            {
                "stage_num": 1,
                "name": "data_fetch",
                "specialist": specialists[0],
                "color": colors[0],
                "clean_execution": clean_fetch,
                "extracted_val": fetched_val,
                "duration": dt_s6
            },
            {
                "stage_num": 2,
                "name": "downstream_reasoning",
                "specialist": specialists[1],
                "color": colors[1],
                "clean_execution": clean_downstream,
                "duration": dt_s7
            }
        ],
        "duration": dt_total
    }
