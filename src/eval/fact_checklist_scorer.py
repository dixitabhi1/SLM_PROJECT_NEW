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
    
    # Collect known units from positive numeric facts for context-aware unit bounding
    known_units = [f["unit"].strip() for f in gold_facts if f.get("type") == "numeric" and f.get("unit")]

    for fact in gold_facts:
        f_type = fact.get("type")
        desc = fact.get("description", str(fact))
        
        if f_type == "negative":
            # 1. Check explicit banned numbers with units
            banned_nums = fact.get("banned_numbers", [])
            for bn in banned_nums:
                target = bn.get("target") or bn.get("value")
                unit = bn.get("unit", "").strip()
                if target is not None and unit:
                    target_float = float(target)
                    target_g = f"{target_float:g}"
                    esc_unit = re.escape(unit)
                    num_pat = (
                        r"(?<![\d.])(?:"
                        + re.escape(str(target))
                        + r"|"
                        + re.escape(target_g)
                        + r"(?:\.0+)?)(?!\d)\s*"
                        + esc_unit
                        + r"\b"
                    )
                    if re.search(num_pat, output_text, re.IGNORECASE):
                        negative_violations.append(f"Triggered banned numeric value: '{target} {unit}'")

            # 2. Check banned tokens (handling both strings and number+unit tokens)
            banned = fact.get("banned_tokens", [])
            for b in banned:
                b_str = str(b).strip()
                # Check if token is a combined number + unit (e.g. '680.0 kHz' or '15.0 L/min')
                combined_match = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*([a-zA-Z/%\^0-9\-_]+)$", b_str)
                if combined_match:
                    num_part = combined_match.group(1)
                    unit_part = combined_match.group(2)
                    num_float = float(num_part)
                    num_g = f"{num_float:g}"
                    esc_unit = re.escape(unit_part)
                    num_pat = (
                        r"(?<![\d.])(?:"
                        + re.escape(num_part)
                        + r"|"
                        + re.escape(num_g)
                        + r"(?:\.0+)?)(?!\d)\s*"
                        + esc_unit
                        + r"\b"
                    )
                    if re.search(num_pat, output_text, re.IGNORECASE):
                        negative_violations.append(f"Triggered banned numeric value with unit: '{b_str}'")
                elif re.match(r"^[+-]?\d+(?:\.\d+)?$", b_str):
                    # Bare number in banned list: must match on number boundary WITH relevant unit
                    num_float = float(b_str)
                    num_g = f"{num_float:g}"
                    if known_units:
                        units_pattern = "(?:" + "|".join(re.escape(u) for u in known_units) + r")\b"
                        num_pat = (
                            r"(?<![\d.])(?:"
                            + re.escape(b_str)
                            + r"|"
                            + re.escape(num_g)
                            + r"(?:\.0+)?)(?!\d)\s*"
                            + units_pattern
                        )
                        if re.search(num_pat, output_text, re.IGNORECASE):
                            negative_violations.append(f"Triggered banned number with unit: '{b_str}'")
                    # If not paired with known unit, pure number alone does not penalize innocent text
                else:
                    # Non-numeric token: match on word boundary
                    pattern = r"\b" + re.escape(b_str) + r"\b"
                    if re.search(pattern, output_text, re.IGNORECASE):
                        negative_violations.append(f"Triggered banned token: '{b_str}'")
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

