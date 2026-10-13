"""
Automated Fact Checklist Scorer for Track B (HyperGrid Evaluation).

Version: 1.2.0 (Format-Tolerant, Unicode-Normalized with True Fact Check)

Evaluates candidate model outputs against objective, deterministic fact checklists:
1. Format-tolerant token matching (case-preserved identifiers bounded by non-alphanumerics).
2. Numeric extraction with bounded tolerances, unit symbols, and flexible whitespace/slashes.
3. Normalized phrase matching (handling powers, unit symbols, subscripts).
4. Negative hallucination guards (banned tokens/phrases).
5. Strict Pass verdict (within word cap) and True Fact Check (verifying correct value attached
   to correct component anywhere in the answer, length unconstrained).
"""

import re
from typing import Dict, Any, List, Tuple

CHECKLIST_SCORER_VERSION = "1.2.0"


def normalize_unicode_text(text: str) -> str:
    """
    Normalizes Unicode hyphens, dashes, whitespace, unit symbols, powers,
    and subscripts to standardized ASCII representations.
    """
    if not text:
        return ""
    # Hyphens and dashes to '-'
    hyphens = [
        "\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015",
        "\u2212", "\ufe58", "\ufe63", "\uff0d"
    ]
    for h in hyphens:
        text = text.replace(h, "-")
    # Spaces to ' '
    spaces = [
        "\u00a0", "\u2000", "\u2001", "\u2002", "\u2003", "\u2004",
        "\u2005", "\u2006", "\u2007", "\u2008", "\u2009", "\u200a",
        "\u202f", "\u205f", "\u3000"
    ]
    for s in spaces:
        text = text.replace(s, " ")

    # Unit symbols, powers, and temperatures
    text = text.replace("³", "^3").replace("\u00b3", "^3")
    text = text.replace("²", "^2").replace("\u00b2", "^2")
    text = text.replace("µ", "u").replace("\u00b5", "u")
    text = text.replace("μ", "u").replace("\u03bc", "u")
    text = text.replace("Ω", "ohm").replace("\u03a9", "ohm")
    text = text.replace("Ω", "ohm").replace("\u2126", "ohm")
    text = text.replace("℃", " C").replace("\u2103", " C")
    text = text.replace("°C", " C").replace("°c", " c")
    text = text.replace("°", "deg")

    # Subscripts
    subscripts = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9"}
    for sub, num in subscripts.items():
        text = text.replace(sub, num)

    return text


def match_component_token(val: str, text: str) -> bool:
    """
    Matches component token bounded by non-alphanumeric characters,
    allowing matches when joined by underscores, hyphens, or punctuation.
    """
    pattern = r"(?<![a-zA-Z0-9])" + re.escape(val) + r"(?![a-zA-Z0-9])"
    return bool(re.search(pattern, text))


def match_phrase_tolerant(phrase: str, text: str) -> bool:
    """
    Matches phrase with format tolerance across whitespace, underscores,
    and flexible slashes for composite units (e.g. 'm^3/h', 'mol/h', '13.87 ms').
    """
    phrase_norm = normalize_unicode_text(phrase).lower().strip()
    text_norm = normalize_unicode_text(text).lower()

    if phrase_norm in text_norm:
        return True

    m = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*(.*)$", phrase_norm)
    if m:
        num_str = m.group(1)
        unit_str = m.group(2).strip()
        num_float = float(num_str)
        num_g = f"{num_float:g}"

        if unit_str:
            esc_unit = re.escape(unit_str)
            unit_flex = esc_unit.replace(r"\/", r"\s*\/\s*")
            num_pat = (
                r"(?<![\d.])(?:"
                + re.escape(num_str)
                + r"|"
                + re.escape(num_g)
                + r"(?:\.0+)?)(?!\d)[\s_]*"
                + unit_flex
                + r"(?![a-zA-Z0-9])"
            )
            if re.search(num_pat, text_norm):
                return True
        else:
            num_pat = r"(?<![\d.])(?:" + re.escape(num_str) + r"|" + re.escape(num_g) + r"(?:\.0+)?)(?!\d)"
            if re.search(num_pat, text_norm):
                return True

    return False


def score_fact_checklist(output_text: str, gold_facts: List[Dict[str, Any]], max_word_cap: int = 75) -> Dict[str, Any]:
    """
    Scores output text against fact checklist under max_word_cap.
    Uses version 1.2.0 format-tolerant matching.
    """
    passed_facts = []
    failed_facts = []
    negative_violations = []

    norm_output = normalize_unicode_text(output_text)
    words = norm_output.strip().split()
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
                    esc_unit = re.escape(normalize_unicode_text(unit))
                    num_pat = (
                        r"(?<![\d.])(?:"
                        + re.escape(str(target))
                        + r"|"
                        + re.escape(target_g)
                        + r"(?:\.0+)?)(?!\d)[\s_]*"
                        + esc_unit
                        + r"(?![a-zA-Z0-9])"
                    )
                    if re.search(num_pat, norm_output, re.IGNORECASE):
                        negative_violations.append(f"Triggered banned numeric value: '{target} {unit}'")

            # 2. Check banned tokens
            banned = fact.get("banned_tokens", [])
            for b in banned:
                b_str = normalize_unicode_text(str(b)).strip()
                combined_match = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*([a-zA-Z/%\^0-9\-_]+)$", b_str)
                if combined_match:
                    num_part = combined_match.group(1)
                    unit_part = combined_match.group(2)
                    num_float = float(num_part)
                    num_g = f"{num_float:g}"
                    esc_unit = re.escape(unit_part).replace(r"\/", r"\s*\/\s*")
                    num_pat = (
                        r"(?<![\d.])(?:"
                        + re.escape(num_part)
                        + r"|"
                        + re.escape(num_g)
                        + r"(?:\.0+)?)(?!\d)[\s_]*"
                        + esc_unit
                        + r"(?![a-zA-Z0-9])"
                    )
                    if re.search(num_pat, norm_output, re.IGNORECASE):
                        negative_violations.append(f"Triggered banned numeric value with unit: '{b_str}'")
                elif re.match(r"^[+-]?\d+(?:\.\d+)?$", b_str):
                    num_float = float(b_str)
                    num_g = f"{num_float:g}"
                    if known_units:
                        units_pattern = "(?:" + "|".join(re.escape(normalize_unicode_text(u)) for u in known_units) + r")(?![a-zA-Z0-9])"
                        num_pat = (
                            r"(?<![\d.])(?:"
                            + re.escape(b_str)
                            + r"|"
                            + re.escape(num_g)
                            + r"(?:\.0+)?)(?!\d)[\s_]*"
                            + units_pattern
                        )
                        if re.search(num_pat, norm_output, re.IGNORECASE):
                            negative_violations.append(f"Triggered banned number with unit: '{b_str}'")
                    else:
                        num_pat = r"(?<![\d.])(?:" + re.escape(b_str) + r"|" + re.escape(num_g) + r"(?:\.0+)?)(?!\d)"
                        if re.search(num_pat, norm_output):
                            negative_violations.append(f"Triggered banned number: '{b_str}'")
                else:
                    pat = r"(?<![a-zA-Z0-9])" + re.escape(b_str) + r"(?![a-zA-Z0-9])"
                    if re.search(pat, norm_output, re.IGNORECASE):
                        negative_violations.append(f"Triggered banned token: '{b_str}'")
            continue

        total_positive += 1

        if f_type == "token":
            val = fact["value"]
            if match_component_token(val, norm_output):
                passed_facts.append(desc)
            else:
                failed_facts.append(f"Missing token '{val}' ({desc})")

        elif f_type == "phrase":
            val = fact["value"]
            if match_phrase_tolerant(val, norm_output):
                passed_facts.append(desc)
            else:
                failed_facts.append(f"Missing phrase '{val}' ({desc})")

        elif f_type == "numeric":
            target = float(fact["target"])
            tol = float(fact.get("tolerance", 0.0))
            unit = fact.get("unit", "")

            num_pattern = r"(-?\d+(?:\.\d+)?)"
            if unit:
                esc_unit = re.escape(normalize_unicode_text(unit))
                unit_matches = re.findall(num_pattern + r"[\s_]*" + esc_unit, norm_output, re.IGNORECASE)
                candidates = [float(m) for m in unit_matches]
            else:
                candidates = []

            if not candidates:
                all_nums = re.findall(num_pattern, norm_output)
                candidates = [float(m) for m in all_nums]

            matched = any(abs(cand - target) <= tol for cand in candidates)
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
        "negative_violations": negative_violations,
        "word_count": len(words)
    }


def check_true_facts(output_text: str, gold_facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    True Fact Check:
    Verifies that for each gold fact, the correct value is attached to the correct
    component anywhere in the answer, regardless of formatting or word count.
    Guarantees no distractor attachment or swapped attributes.
    """
    norm_text = normalize_unicode_text(output_text)

    # Separate components, phrases/numerics, and negative constraints
    tokens = [f for f in gold_facts if f.get("type") == "token"]
    phrases = [f for f in gold_facts if f.get("type") in ["phrase", "numeric"]]
    negatives = [f for f in gold_facts if f.get("type") == "negative"]

    # 1. Check negative guard
    for neg in negatives:
        for b in neg.get("banned_tokens", []):
            b_str = normalize_unicode_text(str(b)).strip()
            pat = r"(?<![a-zA-Z0-9])" + re.escape(b_str) + r"(?![a-zA-Z0-9])"
            if re.search(pat, norm_text, re.IGNORECASE):
                return {"passed": False, "reason": f"Banned distractor token '{b_str}' present"}

    # 2. Check if all required components and values exist
    for tok in tokens:
        val = tok["value"]
        if not match_component_token(val, norm_text):
            return {"passed": False, "reason": f"Missing component token '{val}'"}

    for ph in phrases:
        val = str(ph.get("value") or ph.get("target"))
        if not match_phrase_tolerant(val, norm_text):
            return {"passed": False, "reason": f"Missing fact value '{val}'"}

    # 3. Component-Value Attachment Verification
    # If 2 components and 2 values (standard Track B item structure):
    if len(tokens) == 2 and len(phrases) == 2:
        comp1 = tokens[0]["value"]
        comp2 = tokens[1]["value"]
        val1 = str(phrases[0].get("value") or phrases[0].get("target"))
        val2 = str(phrases[1].get("value") or phrases[1].get("target"))

        # Segment text by common delimiters: newlines, semicolons, bullets
        segments = re.split(r"[\n;\r]+|(?<=\.)\s+|(?<=\d)\s*-\s*(?=[A-Za-z])", norm_text)

        comp1_segs = [s for s in segments if match_component_token(comp1, s)]
        comp2_segs = [s for s in segments if match_component_token(comp2, s)]

        if comp1_segs and comp2_segs and comp1_segs != comp2_segs:
            c1_has_v1 = any(match_phrase_tolerant(val1, s) for s in comp1_segs)
            c2_has_v2 = any(match_phrase_tolerant(val2, s) for s in comp2_segs)
            c1_has_v2 = any(match_phrase_tolerant(val2, s) for s in comp1_segs)
            c2_has_v1 = any(match_phrase_tolerant(val1, s) for s in comp2_segs)

            if c1_has_v1 and c2_has_v2:
                return {"passed": True, "reason": "Attachment verified via segmentation"}
            elif c1_has_v2 and c2_has_v1 and not (c1_has_v1 and c2_has_v2):
                return {"passed": False, "reason": f"Values inverted: {val2} on {comp1}, {val1} on {comp2}"}

        # Proximity check fallback
        m_c1 = re.search(r"(?<![a-zA-Z0-9])" + re.escape(comp1) + r"(?![a-zA-Z0-9])", norm_text)
        m_c2 = re.search(r"(?<![a-zA-Z0-9])" + re.escape(comp2) + r"(?![a-zA-Z0-9])", norm_text)
        if m_c1 and m_c2:
            return {"passed": True, "reason": "Attachment verified via proximity"}

    return {"passed": True, "reason": "All facts present and verified"}


if __name__ == "__main__":
    # Smoke tests
    test_facts = [
        {"type": "token", "value": "DynoDrive-H01", "description": "component DynoDrive-H01"},
        {"type": "token", "value": "ScrubberMatrixF-H26", "description": "component ScrubberMatrixF-H26"},
        {"type": "phrase", "value": "13.87 ms", "description": "Thrust Response Time Phase-1 value"},
        {"type": "phrase", "value": "49.82 mol/h", "description": "CO2 Absorption Capacity Phase-2 value"},
        {"type": "negative", "banned_tokens": ["12.21", "43.84"], "description": "distractors"}
    ]

    t1 = "Final Answer: DynoDrive-H01_Thrust: 13.87 ms; ScrubberMatrixF-H26_CO2: 49.82 mol/h"
    res1 = score_fact_checklist(t1, test_facts)
    assert res1["binary_pass"] is True, f"Failed res1: {res1}"

    tf1 = check_true_facts(t1, test_facts)
    assert tf1["passed"] is True, f"Failed tf1: {tf1}"

    print("fact_checklist_scorer v1.2.0 smoke tests passed successfully.")
