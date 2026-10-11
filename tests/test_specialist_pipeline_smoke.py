"""
Smoke test for specialist_pipeline.py on prompt strings.
"""
import os
import sys
import json

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.specialist_pipeline import run_specialist_pipeline

dev = json.load(open(os.path.join(REPO_ROOT, "data", "track_a_dev_split.json")))


def test_specialist_pipeline_direct_math():
    p = dev[45]["question"] + "\n\nConclude with: #### <number>"
    res = run_specialist_pipeline(p)
    assert res["clean_execution"] is True
    assert res["routed_to"] == "direct"


def test_specialist_pipeline_compound_outside_data():
    p = dev[60]["prompt"]
    res = run_specialist_pipeline(p)
    assert res["clean_execution"] is True
    assert res["routed_to"] == "outside_data"


if __name__ == "__main__":
    test_specialist_pipeline_direct_math()
    print("test_specialist_pipeline_direct_math PASSED")
    test_specialist_pipeline_compound_outside_data()
    print("test_specialist_pipeline_compound_outside_data PASSED")
