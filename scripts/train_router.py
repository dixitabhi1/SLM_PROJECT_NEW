"""
scripts/train_router.py

Trains the Learned Adaptive Router (Experiment 4 / CoLabTEL Thrust 1)
using strictly data/router_train_pool.json and results/phase4/router_train_pool_route_records.jsonl.
Evaluates 5-fold cross-validation strictly on the training pool (never on dev).
Saves model weights to: artifacts/e4/router_model.json
Saves CV metrics & feature importances to: results/phase4/router_training_cv_report.json
"""

import os
import sys
import json
import numpy as np
from typing import Dict, Any, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.pipeline.learned_router import (
    LearnedRouter,
    extract_features,
    ROUTES,
    ROUTE_MEAN_LATENCY,
    MODEL_PATH
)
from scripts.eval_train_pool_routes import format_pool_prompt

POOL_PATH = os.path.join(REPO_ROOT, "data", "router_train_pool.json")
RECORDS_PATH = os.path.join(REPO_ROOT, "results", "phase4", "router_train_pool_route_records.jsonl")
REPORT_PATH = os.path.join(REPO_ROOT, "results", "phase4", "router_training_cv_report.json")


def load_pool_dataset() -> Tuple[List[Dict[str, Any]], Dict[Tuple[str, str], bool], Dict[Tuple[str, str], float]]:
    """Loads pool items and route records."""
    with open(POOL_PATH, "r", encoding="utf-8") as f:
        pool_items = json.load(f)

    passes = {}
    durations = {}
    if os.path.exists(RECORDS_PATH):
        with open(RECORDS_PATH, "r", encoding="utf-8") as f:
            for l in f:
                if l.strip():
                    r = json.loads(l)
                    pid = r["pool_id"]
                    rt = r["route"]
                    passes[(pid, rt)] = bool(r["passed"])
                    durations[(pid, rt)] = float(r.get("duration", 5.0))

    return pool_items, passes, durations


def main():
    print("=" * 80)
    print("TRAINING LEARNED ROUTER (EXPERIMENT 4)")
    print("=" * 80)

    pool_items, passes, durations = load_pool_dataset()
    print(f"Loaded {len(pool_items)} pool items and {len(passes)} route evaluation records.")

    # Find items that have evaluations for routes
    evaluated_items = []
    for it in pool_items:
        pid = it["pool_id"]
        # Check if item has at least 1 evaluation
        if any((pid, rt) in passes for rt in ROUTES):
            evaluated_items.append(it)

    print(f"Found {len(evaluated_items)} items with route evaluations.")

    # Extract feature matrix X and targets Y
    X_list = []
    feat_names = None
    item_routes_pass = {rt: [] for rt in ROUTES}
    item_oracle = []

    for it in evaluated_items:
        pid = it["pool_id"]
        prompt = format_pool_prompt(it)

        # Build dummy analyser output from ground truth metadata for training features
        cat = it.get("category", "")
        analyser_mock = {
            "task_type": "sql" if "sql" in cat else ("math" if "math" in cat else ("code" if "code" in cat else ("qa" if "qa" in cat else "compound"))),
            "solvability": "tool_required" if "tool_req" in cat else ("solvable" if "solv" in cat else "atomic"),
            "source": "DB" if "sql" in cat else ("SANDBOX" if ("code" in cat or "tool_req" in cat) else "NONE"),
            "db_name": it.get("db_id", ""),
            "decomposition_plan": ["step1", "step2"] if "compound" in cat else [],
            "task_asks_for_query": bool("sql" in cat)
        }

        vec, names = extract_features(prompt, analyser_mock)
        if feat_names is None:
            feat_names = names
        X_list.append(vec)

        any_pass = False
        for rt in ROUTES:
            p = passes.get((pid, rt), False)
            item_routes_pass[rt].append(1 if p else 0)
            if p:
                any_pass = True
        item_oracle.append(1 if any_pass else 0)

    X = np.array(X_list)
    Y_per_route = {rt: np.array(item_routes_pass[rt]) for rt in ROUTES}

    print(f"Feature matrix shape: {X.shape} with {len(feat_names)} features.")
    for rt in ROUTES:
        acc = np.mean(Y_per_route[rt]) * 100.0
        print(f"  - Route '{rt}': {np.sum(Y_per_route[rt])}/{len(evaluated_items)} passed ({acc:.1f}%)")
    print(f"  - Oracle Accuracy: {np.sum(item_oracle)}/{len(evaluated_items)} ({np.mean(item_oracle)*100.0:.1f}%)")

    # 5-fold cross-validation on pool items
    from sklearn.model_selection import KFold
    kf = KFold(n_splits=5, shuffle=True, random_state=42)

    cv_router_correct = 0
    cv_total = 0
    route_chosen_counts = {rt: 0 for rt in ROUTES}

    for train_idx, val_idx in kf.split(X):
        X_tr, X_val = X[train_idx], X[val_idx]
        Y_tr = {rt: Y_per_route[rt][train_idx] for rt in ROUTES}

        # Train fold router
        fold_router = LearnedRouter(lambda_latency=0.005, tau_confidence=0.40)
        fold_router.fit(X_tr, Y_tr, feat_names)

        # Evaluate on validation fold
        for i_val in val_idx:
            it = evaluated_items[i_val]
            pid = it["pool_id"]
            prompt = format_pool_prompt(it)

            cat = it.get("category", "")
            analyser_mock = {
                "task_type": "sql" if "sql" in cat else ("math" if "math" in cat else ("code" if "code" in cat else ("qa" if "qa" in cat else "compound"))),
                "solvability": "tool_required" if "tool_req" in cat else ("solvable" if "solv" in cat else "atomic"),
                "source": "DB" if "sql" in cat else ("SANDBOX" if ("code" in cat or "tool_req" in cat) else "NONE"),
                "db_name": it.get("db_id", ""),
                "decomposition_plan": ["step1", "step2"] if "compound" in cat else [],
                "task_asks_for_query": bool("sql" in cat)
            }

            pred_route, conf, meta = fold_router.predict_route(prompt, analyser_mock)
            route_chosen_counts[pred_route] += 1
            if passes.get((pid, pred_route), False):
                cv_router_correct += 1
            cv_total += 1

    cv_acc = (cv_router_correct / max(1, cv_total)) * 100.0
    print("\n" + "=" * 80)
    print("5-FOLD CROSS-VALIDATION RESULTS (TRAINING POOL ONLY)")
    print("=" * 80)
    print(f"Learned Router CV Accuracy: {cv_router_correct}/{cv_total} ({cv_acc:.2f}%)")
    print("Route Selection Distribution across CV:")
    for rt, cnt in route_chosen_counts.items():
        print(f"  - {rt:22s}: {cnt}/{cv_total} ({cnt/max(1, cv_total)*100.0:.1f}%)")

    # Fit final router on all training pool items
    final_router = LearnedRouter(lambda_latency=0.005, tau_confidence=0.40)
    final_router.fit(X, Y_per_route, feat_names)
    final_router.save(MODEL_PATH)
    print(f"\nFinal router model saved to: {MODEL_PATH}")

    # Feature importances
    feat_importances = {}
    for rt in ROUTES:
        clf = final_router.models[rt]
        coefs = clf.coef_[0]
        # Top 5 positive features
        top_pos_idx = np.argsort(coefs)[-5:][::-1]
        top_pos = [(feat_names[idx], round(float(coefs[idx]), 4)) for idx in top_pos_idx]
        feat_importances[rt] = top_pos
        print(f"\nTop positive features for '{rt}':")
        for f_name, weight in top_pos:
            print(f"    {f_name:24s}: {weight:+.4f}")

    report = {
        "timestamp": os.path.basename(REPORT_PATH),
        "total_evaluated_items": len(evaluated_items),
        "feature_count": len(feat_names),
        "cv_accuracy_pct": cv_acc,
        "oracle_accuracy_pct": np.mean(item_oracle) * 100.0,
        "route_chosen_counts": route_chosen_counts,
        "feature_importances": feat_importances
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()

