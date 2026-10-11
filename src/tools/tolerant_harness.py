"""
Tolerant Tool Harness for SLM and Baseline Evaluations (B1 / C1).
Supports:
1. Local text-based fenced protocol:
   - ```python ... ```
   - ```sql <db_name> ... ``` (tolerant of db on fence line, first line of code, or prompt context)
   - Tolerant of direct answers without tool calls.
2. Groq native tool calling API with exact same tools and limits:
   - execute_python(code: str)
   - execute_sql(db_name: str, query: str)
   - search_hypergrid(query: str, top_k: int)
3. Strict execution isolation, timeout enforcement (10.0s), and turn cap (8 turns).
"""

import os
import sys
import re
import json
import sqlite3
import urllib.request
from typing import Dict, Any, List, Tuple, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from src.sandbox.runner import execute_python_code
from src.tools.retriever_tool import BM25RetrieverTool

# Global cached retriever for HyperGrid
_RETRIEVER = None

def get_retriever():
    global _RETRIEVER
    if _RETRIEVER is None:
        try:
            _RETRIEVER = BM25RetrieverTool()
        except Exception:
            _RETRIEVER = None
    return _RETRIEVER

# Known Spider databases on disk
SPIDER_DB_DIR = os.path.join(REPO_ROOT, "data", "spider", "database")

def list_known_databases() -> List[str]:
    if not os.path.exists(SPIDER_DB_DIR):
        return []
    return [d for d in os.listdir(SPIDER_DB_DIR) if os.path.isdir(os.path.join(SPIDER_DB_DIR, d))]

KNOWN_DATABASES = list_known_databases()

# --- Tool Execution Functions ---

def run_local_python(code: str, timeout_seconds: float = 10.0) -> Tuple[bool, str]:
    """Executes Python code in isolated sandbox."""
    try:
        res = execute_python_code(code, timeout_seconds=timeout_seconds)
        if res.timed_out:
            return False, "ERROR: Execution timed out after 10.0 seconds."
        if res.exit_code != 0:
            err = res.stderr.strip() if res.stderr else f"Exit code {res.exit_code}"
            return False, f"ERROR: {err}"
        out = res.stdout.strip()
        if not out:
            out = "(Code executed successfully with no stdout output)"
        # Cap output to 2000 chars
        if len(out) > 2000:
            out = out[:2000] + "\n...[output truncated]"
        return True, out
    except Exception as e:
        return False, f"ERROR: {str(e)}"

def run_local_sql(db_name: str, query: str) -> Tuple[bool, str]:
    """Executes SQLite query against Spider database."""
    # Clean db_name
    db_name = db_name.strip().replace("'", "").replace('"', '').replace("`", "")
    db_path = os.path.join(SPIDER_DB_DIR, db_name, f"{db_name}.sqlite")
    
    if not os.path.exists(db_path):
        # Case insensitive match among known databases
        for cand in KNOWN_DATABASES:
            if cand.lower() == db_name.lower():
                db_name = cand
                db_path = os.path.join(SPIDER_DB_DIR, db_name, f"{db_name}.sqlite")
                break
                
    if not os.path.exists(db_path):
        return False, f"ERROR: Database '{db_name}' not found on disk."
        
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        col_names = [desc[0] for desc in cur.description] if cur.description else []
        conn.close()
        
        # Format output cleanly
        if not rows:
            return True, "Empty result (0 rows returned)."
        
        # If single scalar value, format directly
        if len(rows) == 1 and len(rows[0]) == 1:
            val = rows[0][0]
            return True, f"Result: {val} (raw: {rows})"
            
        # Format up to 10 rows
        out_lines = [f"Columns: {col_names}"]
        for r in rows[:10]:
            out_lines.append(str(r))
        if len(rows) > 10:
            out_lines.append(f"...[{len(rows) - 10} more rows]")
        return True, "\n".join(out_lines)
    except Exception as e:
        return False, f"ERROR: {str(e)}"

def execute_sql_tolerant(db_name: str, query: str, prompt_context: str = "") -> Tuple[bool, str]:
    """
    Executes SQLite query against Spider database on disk, or synthesizes an
    in-memory SQLite table if the schema and rows are provided in the prompt context.
    """
    success, out = run_local_sql(db_name, query)
    if success:
        return True, out

    # Check if prompt defines an in-memory table schema and rows
    if prompt_context:
        m = re.search(r"\[(CREATE TABLE\s+([a-zA-Z0-9_]+)\s*\([^\]]+\))\]", prompt_context, re.IGNORECASE)
        if m:
            ddl, tbl = m.group(1), m.group(2)
            try:
                import ast
                conn = sqlite3.connect(":memory:")
                # Create alias view if an alternative table name precedes the bracket
                alias_m = re.search(r"table\s+([a-zA-Z0-9_]+)\s*\[CREATE TABLE", prompt_context, re.IGNORECASE)
                if alias_m and alias_m.group(1).lower() != tbl.lower():
                    try:
                        conn.execute(f"CREATE VIEW {alias_m.group(1)} AS SELECT * FROM {tbl}")
                    except Exception:
                        pass
                row_match = re.search(r"(?:contains|populated with)\s+(?:\d+\s+)?(?:rows|entries)?[:\s]+(.*?);", prompt_context, re.IGNORECASE | re.DOTALL)
                if row_match:
                    tuples = re.findall(r"\(([^)]+)\)", row_match.group(1))
                    for t in tuples:
                        try:
                            row = ast.literal_eval(f"({t})")
                            if not isinstance(row, tuple):
                                row = (row,)
                            placeholders = ",".join(["?"] * len(row))
                            conn.execute(f"INSERT INTO {tbl} VALUES ({placeholders})", row)
                        except Exception:
                            pass
                cur = conn.cursor()
                cur.execute(query)
                rows = cur.fetchall()
                col_names = [desc[0] for desc in cur.description] if cur.description else []
                conn.close()
                if len(rows) == 1 and len(rows[0]) == 1:
                    return True, f"Result: {rows[0][0]} (raw: {rows})"
                out_lines = [f"Columns: {col_names}"]
                for r in rows[:10]:
                    out_lines.append(str(r))
                if len(rows) > 10:
                    out_lines.append(f"...[{len(rows) - 10} more rows]")
                return True, "\n".join(out_lines)
            except Exception as e:
                return False, f"ERROR in in-memory table execution: {str(e)}"
    return False, out

def run_local_search(query: str, top_k: int = 3) -> Tuple[bool, str]:
    """Searches Track B HyperGrid corpus using BM25."""
    retriever = get_retriever()
    if retriever is None:
        return False, "ERROR: BM25 retriever not initialized."
    try:
        results = retriever.search(query, top_k=top_k)
        if not results:
            return True, "No matching documents found."
        out_passages = []
        for idx, r in enumerate(results, 1):
            out_passages.append(f"[{idx}] {r.get('title', '')} ({r.get('section', '')}):\n{r.get('text', '')}")
        return True, "\n\n".join(out_passages)
    except Exception as e:
        return False, f"ERROR: {str(e)}"


# --- Tolerant Text Protocol Parser ---

def parse_fenced_tool_call(text: str, prompt_context: str = "") -> Tuple[bool, Optional[str], Dict[str, Any], bool]:
    """
    Parses a fenced code block into tool_name and arguments.
    Returns: (has_tool_call, tool_name, arguments_dict, is_malformed)
    """
    # 1. Check for Python block
    py_match = re.search(r"```(?:python|py)\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if py_match:
        code = py_match.group(1).strip()
        if code:
            return True, "execute_python", {"code": code}, False

    # 2. Check for SQL block
    # Matches:
    # ```sql <db_name>
    # ```sql:<db_name>
    # ```sqlite <db_name>
    # ```sql
    sql_match = re.search(r"```(?:sql|sqlite)(?:[:=\s]+([a-zA-Z0-9_\-]+))?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        db_cand = sql_match.group(1)
        query = sql_match.group(2).strip()
        
        # Check if first line inside block contains database hint
        lines = query.split("\n")
        first_line = lines[0].strip() if lines else ""
        first_line_match = re.search(r"^(?:--\s*(?:database|db)[:=\s]+|use\s+|db[:=\s]+)([a-zA-Z0-9_\-]+)", first_line, re.IGNORECASE)
        if first_line_match:
            db_cand = first_line_match.group(1)
            query = "\n".join(lines[1:]).strip()
            
        # If no DB in block, search prompt context
        if not db_cand and prompt_context:
            # Pattern: in/from/query the <db> database
            m = re.search(r"(?:in|from|query|using)\s+the\s+([a-zA-Z0-9_\-]+)\s+database", prompt_context, re.IGNORECASE)
            if m:
                db_cand = m.group(1)
            else:
                # Check for any known database name mentioned in prompt
                for cand in KNOWN_DATABASES:
                    if re.search(r"\b" + re.escape(cand) + r"\b", prompt_context, re.IGNORECASE):
                        db_cand = cand
                        break
                        
        if not db_cand:
            db_cand = "unknown_db"
            
        if query:
            return True, "execute_sql", {"db_name": db_cand, "query": query}, False

    # 3. Check for Search / Hypergrid block
    search_match = re.search(r"```(?:search|hypergrid)\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if search_match:
        q = search_match.group(1).strip()
        if q:
            return True, "search_hypergrid", {"query": q}, False

    # 4. Check for legacy ```tool_call JSON block
    tool_json_match = re.search(r"```tool_call\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if tool_json_match:
        raw_json = tool_json_match.group(1).strip()
        try:
            data = json.loads(raw_json)
            name = data.get("name")
            args = data.get("arguments", {})
            return True, name, args, False
        except Exception:
            return True, "unknown", {}, True

    # 5. Check if output looks like an unclosed tool call (malformed)
    if "```sql" in text and "```" not in text[text.find("```sql")+3:]:
        return False, None, {}, True
    if "```python" in text and "```" not in text[text.find("```python")+3:]:
        return False, None, {}, True

    return False, None, {}, False


# --- Native Tools API Definitions for Groq ---

NATIVE_TOOLS_DEF = [
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Executes Python code in a secure local sandbox and returns standard output. Arguments must be valid JSON: {\"code\": \"<python code>\"}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The Python code string to execute."}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "Executes a SQL SELECT query against a target SQLite database. Arguments must be valid JSON: {\"db_name\": \"<db>\", \"query\": \"<sql>\"}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_name": {"type": "string", "description": "The SQLite database identifier (e.g. 'world_1', 'orchestra', 'flight_2')."},
                    "query": {"type": "string", "description": "The SQL query to execute."}
                },
                "required": ["db_name", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_hypergrid",
            "description": "Searches the HyperGrid technical specification documents using BM25.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query terms."}
                },
                "required": ["query"]
            }
        }
    }
]

SYSTEM_PROMPT_FENCED = """You are an expert reasoning assistant. You have access to local tools:
1. To run Python:
```python
# your code
print(...)
```
2. To run SQL against a SQLite database:
```sql <database_name>
SELECT ...;
```
3. To search HyperGrid specifications:
```search
<query>
```

When you call a tool, wait for the ```tool_output``` block before continuing.
You may also answer directly without calling tools if you know the answer.
When you are ready, conclude your final response with:
Final Answer: <answer>"""

SYSTEM_PROMPT_NATIVE = """You are an expert reasoning assistant equipped with tools: execute_python, execute_sql, and search_hypergrid.
When calling tools, you MUST ensure arguments are strictly valid JSON objects (e.g. {"code": "print(1)"}).
You may also answer directly without calling tools if you know the answer.
When you are ready, conclude your final response with:
Final Answer: <answer>"""
