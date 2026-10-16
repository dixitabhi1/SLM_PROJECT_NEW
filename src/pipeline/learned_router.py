"""
src/pipeline/learned_router.py

Experiment 4 (CoLabTEL Thrust 1): Learned Adaptive Router
Replaces heuristic stage routing with a trained, lightweight classifier that
predicts the optimal execution route from surface prompt features, task analyser outputs,
and route latency penalties.

Routes:
1. direct_reasoner
2. direct_sql
3. code_execution
4. decompose_reasoner
5. decompose_code

Constraints:
- Pure SLM execution: only local phi-4-mini calls via port 8080.
- Hard Rule for CORPUS: if analyser.source == 'CORPUS', code execution routes are forbidden (hard-coded).
- Fallback: if max confidence < threshold tau, falls back to frozen Pipeline v1.3 rule.
"""

import os
import sys
import re
import json
import numpy as np
from typing import Dict, Any, List, Tuple, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold

MODEL_PATH = os.path.join(REPO_ROOT, "artifacts", "e4", "router_model.json")

# Canonical routes
ROUTES = [
    "direct_reasoner",
    "direct_sql",
    "code_execution",
    "decompose_reasoner",
    "decompose_code"
]

# Baseline route latencies (empirically measured across dev/pool runs)
ROUTE_MEAN_LATENCY = {
    "direct_reasoner": 7.74,
    "direct_sql": 5.31,
    "code_execution": 10.11,
    "decompose_reasoner": 20.33,
    "decompose_code": 16.25
}

# Known database names for SQL route matching
KNOWN_DBS = {
    'academic', 'activity_1', 'aircraft', 'allergy_1', 'apartment_rentals',
    'battle_death', 'bike_1', 'book_2', 'candidate_poll', 'car_1',
    'chinook_1', 'cinema', 'climbing', 'coffee_shop', 'college_1',
    'concert_singer', 'course_teach', 'cre_Doc_Template_Mgt', 'dog_kennels',
    'dorm_1', 'employee_hire_evaluation', 'flight_2', 'game_injury',
    'match_season', 'museum_visit', 'orchestra', 'pets_1', 'poker_player',
    'real_estate_properties', 'student_transcripts_tracking', 'tvshow',
    'world_1', 'wta_1'
}


def extract_surface_features(prompt: str) -> Dict[str, float]:
    """Extracts surface-level syntactic and lexical features from prompt string."""
    char_len = len(prompt)
    words = prompt.split()
    word_len = len(words)
    num_digits = len(re.findall(r"\d", prompt))
    num_symbols = len(re.findall(r"[^\w\s]", prompt))
    num_lines = prompt.count("\n") + 1

    has_question_mark = 1.0 if "?" in prompt else 0.0
    has_dollar = 1.0 if "$" in prompt else 0.0
    has_hash_box = 1.0 if ("####" in prompt or "\\boxed" in prompt) else 0.0
    has_multiple_choice = 1.0 if re.search(r"\([A-D]\)", prompt) else 0.0
    has_code_syntax = 1.0 if re.search(r"\b(def|import|class|return|assert|print)\b", prompt) else 0.0
    has_sql_syntax = 1.0 if re.search(r"\b(SELECT|FROM|WHERE|JOIN|GROUP BY|ORDER BY|DATABASE)\b", prompt, re.IGNORECASE) else 0.0
    has_math_ops = 1.0 if re.search(r"[\+\-\*\/\%\^]\s*\d", prompt) else 0.0

    return {
        "char_len": float(char_len),
        "word_len": float(word_len),
        "num_digits": float(num_digits),
        "num_symbols": float(num_symbols),
        "num_lines": float(num_lines),
        "has_question_mark": has_question_mark,
        "has_dollar": has_dollar,
        "has_hash_box": has_hash_box,
        "has_multiple_choice": has_multiple_choice,
        "has_code_syntax": has_code_syntax,
        "has_sql_syntax": has_sql_syntax,
        "has_math_ops": has_math_ops,
    }


def extract_analyser_features(analyser_dict: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Extracts features from Stage 1 Task Analyser output."""
    feats = {
        "task_type_sql": 0.0,
        "task_type_math": 0.0,
        "task_type_code": 0.0,
        "task_type_qa": 0.0,
        "task_type_compound": 0.0,
        "solvability_atomic": 0.0,
        "solvability_solvable": 0.0,
        "solvability_tool_req": 0.0,
        "source_db": 0.0,
        "source_sandbox": 0.0,
        "source_corpus": 0.0,
        "source_none": 0.0,
        "db_identified": 0.0,
        "plan_present": 0.0,
        "step_count": 1.0,
        "task_asks_for_query": 0.0,
    }

    if not analyser_dict:
        return feats

    tt = str(analyser_dict.get("task_type", "")).lower()
    if "sql" in tt: feats["task_type_sql"] = 1.0
    elif "math" in tt: feats["task_type_math"] = 1.0
    elif "code" in tt: feats["task_type_code"] = 1.0
    elif "qa" in tt: feats["task_type_qa"] = 1.0
    elif "compound" in tt or "multi" in tt: feats["task_type_compound"] = 1.0

    solv = str(analyser_dict.get("solvability", "")).lower()
    if "atomic" in solv: feats["solvability_atomic"] = 1.0
    elif "tool" in solv: feats["solvability_tool_req"] = 1.0
    elif "solv" in solv: feats["solvability_solvable"] = 1.0

    src = str(analyser_dict.get("source", "")).upper()
    if "DB" in src: feats["source_db"] = 1.0
    elif "SANDBOX" in src: feats["source_sandbox"] = 1.0
    elif "CORPUS" in src: feats["source_corpus"] = 1.0
    elif "NONE" in src or not src: feats["source_none"] = 1.0

    db = analyser_dict.get("db_name", "")
    if db and db in KNOWN_DBS:
        feats["db_identified"] = 1.0

    plan = analyser_dict.get("decomposition_plan", [])
    if plan and len(plan) > 0:
        feats["plan_present"] = 1.0
        feats["step_count"] = float(len(plan))

    if analyser_dict.get("task_asks_for_query"):
        feats["task_asks_for_query"] = 1.0

    return feats


def extract_features(prompt: str, analyser_dict: Optional[Dict[str, Any]] = None) -> Tuple[List[float], List[str]]:
    """Combines surface prompt features and analyser features into a single feature vector."""
    surf = extract_surface_features(prompt)
    anal = extract_analyser_features(analyser_dict)

    combined = {}
    combined.update(surf)
    combined.update(anal)

    keys = sorted(combined.keys())
    vec = [combined[k] for k in keys]
    return vec, keys


class LearnedRouter:
    """
    Learned Adaptive Router predicting route success probabilities
    and applying route latency penalties with low-confidence fallback to v1.3 rule.
    """

    def __init__(self, lambda_latency: float = 0.005, tau_confidence: float = 0.40):
        self.lambda_latency = lambda_latency
        self.tau_confidence = tau_confidence
        self.routes = ROUTES
        self.models: Dict[str, LogisticRegression] = {}
        self.feature_names: List[str] = []
        self.is_fitted = False

    def fit(self, X: np.ndarray, Y_per_route: Dict[str, np.ndarray], feature_names: List[str]):
        """Fits one LogisticRegression classifier per route."""
        self.feature_names = feature_names
        for r in self.routes:
            y = Y_per_route[r]
            # Handle edge cases where all 0s or all 1s
            if len(np.unique(y)) < 2:
                clf = LogisticRegression()
                clf.classes_ = np.array([0, 1])
                clf.coef_ = np.zeros((1, X.shape[1]))
                clf.intercept_ = np.array([1.0 if y[0] == 1 else -1.0])
            else:
                clf = LogisticRegression(penalty="l2", C=1.0, max_iter=1000, random_state=42)
                clf.fit(X, y)
            self.models[r] = clf
        self.is_fitted = True

    def predict_route(
        self,
        prompt: str,
        analyser_dict: Optional[Dict[str, Any]] = None,
        v13_default_route: str = "direct_reasoner"
    ) -> Tuple[str, float, Dict[str, Any]]:
        """
        Predicts optimal route for task prompt with latency penalty and hard CORPUS guard.
        Returns: (selected_route, confidence, metadata)
        """
        vec, _ = extract_features(prompt, analyser_dict)
        x = np.array(vec).reshape(1, -1)

        # 1. Hard Rule: CORPUS forbids code routes
        source = (analyser_dict.get("source") if analyser_dict else "") or ""
        is_corpus = ("CORPUS" in str(source).upper())

        # 2. Probability estimation per route
        probs = {}
        for r in self.routes:
            if not self.is_fitted or r not in self.models:
                probs[r] = 0.5
            else:
                clf = self.models[r]
                try:
                    p = clf.predict_proba(x)[0, 1]
                except Exception:
                    p = 0.5
                probs[r] = float(p)

        # 3. Penalize latency
        scores = {}
        for r in self.routes:
            if is_corpus and r in ("code_execution", "decompose_code"):
                scores[r] = -999.0  # Hard rule constraint
                continue
            base_prob = probs[r]
            lat = ROUTE_MEAN_LATENCY.get(r, 10.0)
            scores[r] = base_prob - self.lambda_latency * lat

        # 4. Find best route
        best_route = max(scores, key=scores.get)
        best_prob = probs.get(best_route, 0.0)

        # 5. Fallback on low confidence
        fallback_triggered = False
        if best_prob < self.tau_confidence:
            best_route = v13_default_route
            fallback_triggered = True

        meta = {
            "probs": probs,
            "scores": scores,
            "best_prob": best_prob,
            "fallback_triggered": fallback_triggered,
            "is_corpus_guard_applied": is_corpus,
            "features": dict(zip(self.feature_names, vec))
        }
        return best_route, best_prob, meta

    def save(self, filepath: str = MODEL_PATH):
        """Saves model weights, feature names, and parameters to JSON."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        data = {
            "lambda_latency": self.lambda_latency,
            "tau_confidence": self.tau_confidence,
            "routes": self.routes,
            "feature_names": self.feature_names,
            "models": {}
        }
        for r, clf in self.models.items():
            data["models"][r] = {
                "coef": clf.coef_.tolist(),
                "intercept": clf.intercept_.tolist(),
                "classes": clf.classes_.tolist()
            }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, filepath: str = MODEL_PATH):
        """Loads model weights, feature names, and parameters from JSON."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.lambda_latency = data.get("lambda_latency", 0.005)
        self.tau_confidence = data.get("tau_confidence", 0.40)
        self.routes = data.get("routes", ROUTES)
        self.feature_names = data.get("feature_names", [])
        self.models = {}
        for r, m_data in data.get("models", {}).items():
            clf = LogisticRegression()
            clf.classes_ = np.array(m_data["classes"])
            clf.coef_ = np.array(m_data["coef"])
            clf.intercept_ = np.array(m_data["intercept"])
            self.models[r] = clf
        self.is_fitted = True

