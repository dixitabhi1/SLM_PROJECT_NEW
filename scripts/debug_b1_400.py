import urllib.request, json, os, sys
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('GROQ_API_KEY')

sys.path.insert(0, ".")
from scripts.eval_calibration_hard_20 import run_model_with_tools, CALIB_FILE

with open(CALIB_FILE) as f:
    item = json.load(f)[0]

try:
    out = run_model_with_tools(item, is_local=False, groq_key=api_key)
    print("Result:", out)
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code)
    print("Body:", e.read().decode("utf-8"))
except Exception as e:
    print("Error:", e)

