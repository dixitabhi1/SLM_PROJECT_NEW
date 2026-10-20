"""
src/eval/public_graders.py

Automated, deterministic grading functions for public benchmarks:
1. GSM-Hard: exact numeric match, relative tolerance 1e-4.
2. FinQA: exact numeric match, relative tolerance 1%; 0.25 and 25% equal.
3. InfiAgent-DABench: official regex @answer_name[value] and tolerance 1e-6.
"""

import re
from typing import Dict, Any, List, Tuple, Optional


def extract_numbers_from_text(text: str) -> List[float]:
    """Extracts all floating-point numbers from string, handling signs and commas."""
    t_clean = text.replace(",", "")
    nums = []
    # Match standard numbers, scientific notation, and percentages
    matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?%?", t_clean)
    for m in matches:
        is_pct = m.endswith("%")
        m_val = m.rstrip("%")
        try:
            val = float(m_val)
            if is_pct:
                val = val / 100.0
            nums.append(val)
        except ValueError:
            continue
    return nums


def extract_final_answer_candidate(text: str) -> Optional[str]:
    """Extracts candidate answer string from model output."""
    if not text:
        return None
        
    # Check for #### pattern
    m_hash = re.search(r"####\s*([^\n\r]+)", text)
    if m_hash:
        return m_hash.group(1).strip()
        
    # Check for Final Answer: pattern
    m_final = re.search(r"(?:Final Answer|Answer|The answer is):\s*([^\n\r]+)", text, re.IGNORECASE)
    if m_final:
        return m_final.group(1).strip()
        
    # Check last non-empty line
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if lines:
        return lines[-1]
    return None


def grade_gsmhard(pred: str, gold: float) -> Tuple[bool, Optional[float], str]:
    """
    Grades GSM-Hard predictions.
    Relative tolerance: 1e-4 (|pred - gold| / max(|gold|, 1e-9) <= 1e-4).
    """
    if not pred or not pred.strip():
        return False, None, "empty_prediction"

    cand_str = extract_final_answer_candidate(pred)
    nums = extract_numbers_from_text(cand_str) if cand_str else []
    if not nums:
        # Fall back to searching entire text
        all_nums = extract_numbers_from_text(pred)
        if all_nums:
            pred_num = all_nums[-1]
        else:
            return False, None, "no_numbers_found"
    else:
        pred_num = nums[-1]

    denom = max(abs(gold), 1e-9)
    rel_err = abs(pred_num - gold) / denom
    passed = rel_err <= 1e-4

    details = f"pred={pred_num}, gold={gold}, rel_err={rel_err:.6e}, tol=1e-4"
    return passed, pred_num, details


def grade_finqa(pred: str, gold_str: str, exe_ans: Any) -> Tuple[bool, Optional[float], str]:
    """
    Grades FinQA predictions.
    Relative tolerance: 1% (0.01).
    0.25 and 25% are treated as equal.
    """
    if not pred or not pred.strip():
        return False, None, "empty_prediction"

    cand_str = extract_final_answer_candidate(pred)
    cand_lower = (cand_str or pred).strip().lower()

    # Check for boolean or categorical answers (e.g. 'yes' / 'no')
    gold_str_lower = str(gold_str).strip().lower()
    if gold_str_lower in ("yes", "no"):
        passed = (cand_lower == gold_str_lower) or (f" {gold_str_lower}" in f" {cand_lower}")
        return passed, None, f"categorical: pred='{cand_lower}', gold='{gold_str_lower}'"

    # Extract numeric candidate
    nums = extract_numbers_from_text(cand_str) if cand_str else []
    if not nums:
        all_nums = extract_numbers_from_text(pred)
        if all_nums:
            pred_num = all_nums[-1]
        else:
            return False, None, "no_numbers_found"
    else:
        pred_num = nums[-1]

    # Candidate values to check against (both raw and percentage scaled)
    cand_candidates = [pred_num]
    # If the user output or model emitted 25, that could represent 0.25 or 25%
    cand_candidates.append(pred_num / 100.0)
    cand_candidates.append(pred_num * 100.0)

    # Gold reference numbers
    gold_numbers = []
    if exe_ans is not None:
        try:
            gold_numbers.append(float(exe_ans))
        except (ValueError, TypeError):
            pass
    gold_extracted = extract_numbers_from_text(str(gold_str))
    for gn in gold_extracted:
        if gn not in gold_numbers:
            gold_numbers.append(gn)

    if not gold_numbers:
        return False, pred_num, f"unparseable_gold: '{gold_str}'"

    # Check match within 1% relative tolerance
    best_rel_err = float("inf")
    matched = False
    for g in gold_numbers:
        denom = max(abs(g), 1e-9)
        for c in cand_candidates:
            err = abs(c - g) / denom
            if err < best_rel_err:
                best_rel_err = err
            if err <= 0.01:
                matched = True
                break
        if matched:
            break

    details = f"pred={pred_num}, gold_nums={gold_numbers}, best_rel_err={best_rel_err:.4f}, tol=0.01"
    return matched, pred_num, details


def grade_dabench(pred: str, common_answers: List[List[str]]) -> Tuple[bool, Dict[str, Any], str]:
    """
    Grades InfiAgent-DABench predictions using the official evaluation format:
    Pattern: @answer_name[value]
    Equivalence: string equality or absolute/relative tolerance 1e-6.
    """
    if not pred or not pred.strip():
        return False, {}, "empty_prediction"

    pattern = r"@(\w+)\[(.*?)\]"
    matches = re.findall(pattern, pred)
    extracted = {m[0]: m[1].strip() for m in matches}

    label_answers = {ans[0]: str(ans[1]).strip() for ans in common_answers if len(ans) >= 2}

    def is_equal(response_val: str, label_val: str) -> bool:
        if response_val.lower() == label_val.lower():
            return True
        try:
            v_resp = float(response_val.replace(",", "").rstrip("%"))
            v_lab = float(label_val.replace(",", "").rstrip("%"))
            # Absolute or relative tolerance 1e-6
            denom = max(abs(v_lab), 1.0)
            return (abs(v_resp - v_lab) / denom) < 1e-6 or abs(v_resp - v_lab) < 1e-6
        except Exception:
            return False

    # Check correctness per key in label_answers
    correctness = {}
    for k, v in label_answers.items():
        if k in extracted:
            correctness[k] = is_equal(extracted[k], v)
        else:
            # Fall back to finding value in final answer lines
            cand_str = extract_final_answer_candidate(pred) or ""
            # If label is numeric or simple string
            if is_equal(cand_str, v):
                correctness[k] = True
            else:
                correctness[k] = False

    all_correct = len(correctness) > 0 and all(correctness.values())
    details = f"extracted={extracted}, label={label_answers}, correctness={correctness}"
    return all_correct, extracted, details


def grade_benchmark_item(
    benchmark: str,
    pred: str,
    gold_item: Dict[str, Any],
    finish_reason: str = "stop"
) -> Tuple[bool, Any, str]:
    """
    Universal grader dispatcher for public benchmarks.
    Enforces Hard Rule 3: Truncated answer (finish_reason == 'length') is failed.
    """
    if finish_reason == "length":
        return False, None, "failed_truncation: finish_reason == length"

    b_lower = benchmark.lower()
    if "gsm" in b_lower:
        gold = float(gold_item.get("target", 0.0))
        return grade_gsmhard(pred, gold)
    elif "finqa" in b_lower:
        qa = gold_item.get("qa", {})
        gold_str = qa.get("answer", "")
        exe_ans = qa.get("exe_ans")
        return grade_finqa(pred, gold_str, exe_ans)
    elif "dabench" in b_lower or "infi" in b_lower:
        common_answers = gold_item.get("common_answers", [])
        return grade_dabench(pred, common_answers)
    else:
        raise ValueError(f"Unknown benchmark for grading: {benchmark}")
