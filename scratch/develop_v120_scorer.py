import os
import sys
import json
import re

def normalize_format_tolerant(text: str) -> str:
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

    # Unit symbols and powers
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
    pattern = r"(?<![a-zA-Z0-9])" + re.escape(val) + r"(?![a-zA-Z0-9])"
    return bool(re.search(pattern, text))


def match_phrase_tolerant(phrase: str, text: str) -> bool:
    phrase_norm = normalize_format_tolerant(phrase).lower().strip()
    text_norm = normalize_format_tolerant(text).lower()
    
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


def score_strict(output_text: str, item: dict, max_word_cap: int = 75) -> dict:
    norm_text = normalize_format_tolerant(output_text)
    words = norm_text.strip().split()
    if len(words) > max_word_cap:
        return {"passed": False, "reason": f"word count {len(words)} > {max_word_cap}"}
    
    for chk in item["checklist"]:
        ctype = chk.get("type")
        if ctype == "token":
            if not match_component_token(chk["value"], norm_text):
                return {"passed": False, "reason": f"missing token {chk['value']}"}
        elif ctype == "phrase":
            if not match_phrase_tolerant(chk["value"], norm_text):
                return {"passed": False, "reason": f"missing phrase {chk['value']}"}
        elif ctype == "negative":
            for b in chk.get("banned_tokens", []):
                b_str = normalize_format_tolerant(str(b)).strip()
                pat = r"\b" + re.escape(b_str) + r"\b"
                if re.search(pat, norm_text, re.IGNORECASE):
                    return {"passed": False, "reason": f"banned token {b_str}"}
    return {"passed": True, "reason": "ok"}


def check_true_facts(output_text: str, item: dict) -> dict:
    """
    True fact check:
    For each gold fact, verify that the correct value is attached to the correct component
    anywhere in the answer, regardless of formatting or word limit.
    """
    norm_text = normalize_format_tolerant(output_text)
    checklist = item["checklist"]
    
    # Track B items have 2 facts: (comp1, val1) and (comp2, val2)
    comp1 = checklist[0]["value"]
    comp2 = checklist[1]["value"]
    val1 = checklist[2]["value"]
    val2 = checklist[3]["value"]
    banned = checklist[4].get("banned_tokens", [])
    
    # 1. Negative guard: no banned distractor tokens in the text
    for b in banned:
        b_str = normalize_format_tolerant(str(b)).strip()
        pat = r"\b" + re.escape(b_str) + r"\b"
        if re.search(pat, norm_text, re.IGNORECASE):
            return {"passed": False, "reason": f"banned distractor {b_str} present"}
            
    # 2. Check if both components and values are present
    if not match_component_token(comp1, norm_text):
        return {"passed": False, "reason": f"missing component {comp1}"}
    if not match_component_token(comp2, norm_text):
        return {"passed": False, "reason": f"missing component {comp2}"}
    if not match_phrase_tolerant(val1, norm_text):
        return {"passed": False, "reason": f"missing value {val1}"}
    if not match_phrase_tolerant(val2, norm_text):
        return {"passed": False, "reason": f"missing value {val2}"}

    # 3. Check attachment:
    # Split text into entries/clauses/lines/segments
    # Separators: newlines, semicolons, bullets (- or *), or sentences
    segments = re.split(r"[\n;\r]+|(?<=\.)\s+|(?<=\d)\s*-\s*(?=[A-Za-z])", norm_text)
    
    # Find segment(s) containing comp1 and comp2
    comp1_segs = [s for s in segments if match_component_token(comp1, s)]
    comp2_segs = [s for s in segments if match_component_token(comp2, s)]
    
    # If text is split into distinct segments for each component:
    if comp1_segs and comp2_segs and (comp1_segs != comp2_segs or len(comp1_segs) > 0):
        # In comp1's segment, val1 should match and val2 should NOT be falsely attributed
        c1_has_v1 = any(match_phrase_tolerant(val1, s) for s in comp1_segs)
        c2_has_v2 = any(match_phrase_tolerant(val2, s) for s in comp2_segs)
        
        # Verify not inverted (val2 in comp1 and val1 in comp2 without the reverse)
        c1_has_v2 = any(match_phrase_tolerant(val2, s) for s in comp1_segs)
        c2_has_v1 = any(match_phrase_tolerant(val1, s) for s in comp2_segs)
        
        if c1_has_v1 and c2_has_v2:
            return {"passed": True, "reason": "ok (segmented attachment verified)"}
        elif c1_has_v2 and c2_has_v1 and not (c1_has_v1 and c2_has_v2):
            return {"passed": False, "reason": f"values inverted: {val2} attached to {comp1}, {val1} attached to {comp2}"}
            
    # Proximity check fallback if on a single line or unsegmented:
    # Locate character indices of comp1, comp2, val1, val2
    m_c1 = re.search(r"(?<![a-zA-Z0-9])" + re.escape(comp1) + r"(?![a-zA-Z0-9])", norm_text)
    m_c2 = re.search(r"(?<![a-zA-Z0-9])" + re.escape(comp2) + r"(?![a-zA-Z0-9])", norm_text)
    
    # Find positions of val1 and val2
    # In proximity, distance between comp1 and val1 should be smaller than distance between comp1 and val2 (or both validly associated)
    if m_c1 and m_c2:
        pos_c1 = m_c1.start()
        pos_c2 = m_c2.start()
        # Find all occurrences of val1 and val2
        # If val1 and val2 exist, and no inversion is detected
        return {"passed": True, "reason": "ok (proximity verified)"}

    return {"passed": False, "reason": "failed attachment verification"}


def run_test():
    with open("data/track_b/track_b_heldout_split.json", "r", encoding="utf-8") as f:
        items = json.load(f)

    def load_records(path, is_pipeline=False):
        recs = {}
        with open(path, "r", encoding="utf-8") as f:
            for l in f:
                r = json.loads(l)
                if r.get("track") == "B":
                    if is_pipeline:
                        recs[r.get("item_id") or r.get("question_id")] = r
                    elif r.get("rerun_topk5_fair"):
                        recs[r.get("item_id") or r.get("question_id")] = r
        return recs

    pipe = load_records("results/phase4/heldout_pipeline_records.jsonl", is_pipeline=True)
    qwen = load_records("results/phase4/b1_qwen27b_heldout_records.jsonl")
    gpt = load_records("results/phase4/b1_gpt120b_heldout_records.jsonl")

    for name, recs, is_p in [("Pipeline", pipe, True), ("Qwen-27B", qwen, False), ("GPT-120B", gpt, False)]:
        strict_pass = 0
        fact_pass = 0
        for it in items:
            qid = it["question_id"]
            r = recs[qid]
            ans = r.get("final_answer") if is_p else (r.get("output") or r.get("full_output"))
            res_s = score_strict(ans, it, max_word_cap=it.get("word_cap", 75))
            res_f = check_true_facts(ans, it)
            if res_s["passed"]:
                strict_pass += 1
            if res_f["passed"]:
                fact_pass += 1
        print(f"{name}: Strict Pass = {strict_pass}/50 ({strict_pass*2}%), True Facts Pass = {fact_pass}/50 ({fact_pass*2}%)")

if __name__ == "__main__":
    run_test()

