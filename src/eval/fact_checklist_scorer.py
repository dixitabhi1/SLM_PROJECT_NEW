"""
Automated Fact Checklist Scorer for Track B (HyperGrid Evaluation).

Evaluates candidate model outputs against objective, deterministic fact checklists:
1. Exact regex token matching (case-preserved identifiers).
2. Numeric extraction with bounded tolerances and unit grounding.
3. Normalized phrase matching.
4. Negative hallucination guards (banned tokens/phrases).
5. Returns Recall, Precision, and Binary Pass verdict with zero LLM judge and zero API calls.
"""

import re
from typing import Dict, Any, List, Tuple

def score_fact_checklist(output_text: str, gold_facts: List[Dict[str, Any]], max_word_cap: int = 75) -> Dict[str, Any]:
    passed_facts = []
    failed_facts = []
    negative_violations = []
    
    words = output_text.strip().split()
    if len(words) > max_word_cap:
        return {
            "binary_pass": False,
            "recall": 0.0,
            "precision": 0.0,
            "passed_facts_count": 0,
            "total_positive_facts": len([f for f in gold_facts if f.get("type") != "negative"]),
            "passed_facts": [],
            "failed_facts": [f"Answer exceeds length cap: {len(words)} words (max {max_word_cap})"],
            "negative_violations": ["Length cap exceeded; full-corpus pasting rejected"],
            "word_count": len(words)
        }
    
    total_positive = 0
    
    for fact in gold_facts:
        f_type = fact.get("type")
        desc = fact.get("description", str(fact))
        
        if f_type == "negative":
            banned = fact.get("banned_tokens", [])
            for b in banned:
                # Word boundary search
                pattern = r"\b" + re.escape(b) + r"\b"
                if re.search(pattern, output_text, re.IGNORECASE):
                    negative_violations.append(f"Triggered banned token: '{b}'")
            continue
            
        total_positive += 1
        
        if f_type == "token":
            val = fact["value"]
            pattern = r"\b" + re.escape(val) + r"\b"
            if re.search(pattern, output_text):
                passed_facts.append(desc)
            else:
                failed_facts.append(f"Missing token '{val}' ({desc})")
                
        elif f_type == "phrase":
            phrase = fact["value"].lower().strip()
            if phrase in output_text.lower():
                passed_facts.append(desc)
            else:
                failed_facts.append(f"Missing phrase '{phrase}' ({desc})")
                
        elif f_type == "numeric":
            target = float(fact["target"])
            tol = float(fact.get("tolerance", 0.0))
            unit = fact.get("unit", "")
            
            # Regex to find numbers near unit or standalone
            # e.g., "340 kPa" or "340.0"
            num_pattern = r"(-?\d+(?:\.\d+)?)"
            if unit:
                esc_unit = re.escape(unit)
                # Check for number immediately preceding unit
                unit_matches = re.findall(num_pattern + r"\s*" + esc_unit, output_text, re.IGNORECASE)
                candidates = [float(m) for m in unit_matches]
            else:
                candidates = []
                
            # If no unit match found, fallback to all standalone numbers
            if not candidates:
                all_nums = re.findall(num_pattern, output_text)
                candidates = [float(m) for m in all_nums]
                
            matched = False
            for cand in candidates:
                if abs(cand - target) <= tol:
                    matched = True
                    break
                    
            if matched:
                passed_facts.append(desc)
            else:
                failed_facts.append(f"Numeric mismatch for {target} {unit} +/- {tol} ({desc})")
                
    recall = len(passed_facts) / total_positive if total_positive > 0 else 1.0
    prec_denom = len(passed_facts) + len(negative_violations)
    precision = len(passed_facts) / prec_denom if prec_denom > 0 else 0.0
    
    binary_pass = (len(failed_facts) == 0 and len(negative_violations) == 0)
    
    return {
        "binary_pass": binary_pass,
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "passed_facts_count": len(passed_facts),
        "total_positive_facts": total_positive,
        "passed_facts": passed_facts,
        "failed_facts": failed_facts,
        "negative_violations": negative_violations
    }

if __name__ == "__main__":
    # Smoke test
    test_facts = [
        {"type": "numeric", "unit": "kPa", "target": 340.0, "tolerance": 5.0, "description": "compressor pressure 340 kPa +/- 5 kPa"},
        {"type": "token", "value": "BV-104", "description": "secondary bypass valve BV-104"},
        {"type": "phrase", "value": "stator coil", "description": "stator coil component"},
        {"type": "negative", "banned_tokens": ["Vent Valve V-12", "Legacy-v2"]}
    ]
    
    good_text = "The system operates at 341 kPa with stator coil SC-44 and actuates BV-104 under fault."
    res_good = score_fact_checklist(good_text, test_facts)
    print("Good text score:", res_good["binary_pass"], res_good["recall"], res_good["precision"])
    assert res_good["binary_pass"] is True
    
    bad_text = "The pressure is 100 kPa and uses Vent Valve V-12."
    res_bad = score_fact_checklist(bad_text, test_facts)
    print("Bad text score:", res_bad["binary_pass"], res_bad["recall"], res_bad["negative_violations"])
    assert res_bad["binary_pass"] is False
    print("Smoke tests passed successfully.")

