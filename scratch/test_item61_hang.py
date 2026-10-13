import os
import sys
import json
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.run_heldout_baselines_b1 import identify_database, get_table_schema, call_groq_api, execute_sql_tolerant, extract_sql_query
from src.eval.versioned_scorer import score_record

items = json.load(open(os.path.join(REPO_ROOT, "data", "track_a_heldout_split.json"), encoding="utf-8"))
item = items[61]
model_name = "qwen/qwen3.8-27b"
raw_prompt = item["prompt"]

print("STEP 1: identify DB")
db_name = identify_database(item)
print("DB:", db_name)

print("STEP 2: schema")
schema = get_table_schema(db_name)

sql_prompt = (
    f"Task: {raw_prompt}\n\n"
    f"Database: {db_name}\n"
    f"Schema:\n{schema}\n\n"
    f"Write exactly one SQLite query enclosed in ```sql ... ``` to extract the required data from '{db_name}'. "
    f"Select ONLY the single requested column."
)

print("STEP 3: call groq sql 1")
resp_sql = call_groq_api(
    model_name,
    sql_prompt,
    system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
    max_tokens=256
)
print("resp_sql 1 done, content len:", len(resp_sql["content"]))

q = extract_sql_query(resp_sql["content"])
print("STEP 4: execute sql tolerant 1")
clean, out_text = execute_sql_tolerant(db_name, q, prompt_context=raw_prompt)
print("clean:", clean, "out_text:", out_text[:100])

if not clean:
    print("STEP 5: retry sql")
    retry_sql = (
        f"{sql_prompt}\n\n"
        f"Previous query produced error: {out_text}\n"
        f"Please output the corrected SQLite query in ```sql ... ```:"
    )
    resp_sql2 = call_groq_api(
        model_name,
        retry_sql,
        system_prompt="You are an expert SQLite query assistant. Output ONLY the SQLite query enclosed in ```sql ... ```.",
        max_tokens=256
    )
    print("resp_sql 2 done")
    q2 = extract_sql_query(resp_sql2["content"])
    clean, out_text = execute_sql_tolerant(db_name, q2, prompt_context=raw_prompt)
    print("clean 2:", clean, "out_text 2:", out_text[:100])

print("STEP 6: downstream reasoning prompt")
downstream_prompt = (
    f"Task: {raw_prompt}\n\n"
    f"Database Query Executed: {q}\n"
    f"Retrieved Query Data: {out_text}\n\n"
    f"Based on the retrieved data, solve the problem step by step.\n"
    f"Conclude your final answer with: 'Final Answer: <answer>' or '#### <answer>'."
)

print("STEP 7: call groq reason")
resp_reason = call_groq_api(
    model_name,
    downstream_prompt,
    system_prompt="You are an expert mathematical and logical reasoning assistant.",
    max_tokens=512
)
print("resp_reason done! content:", resp_reason["content"][:200])

print("STEP 8: score_record")
t0 = time.time()
sc = score_record(item, resp_reason["content"])
print("score_record done in", time.time() - t0, "sc:", sc)

