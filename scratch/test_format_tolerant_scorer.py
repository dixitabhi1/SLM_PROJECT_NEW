import os, sys, json, re
sys.path.insert(0, os.path.abspath("."))

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
    # Match component token bounded by anything that is not alphanumeric
    pattern = r"(?<![a-zA-Z0-9])" + re.escape(val) + r"(?![a-zA-Z0-9])"
    return bool(re.search(pattern, text))


def match_phrase_tolerant(phrase: str, text: str) -> bool:
    phrase_norm = normalize_format_tolerant(phrase).lower().strip()
    text_norm = normalize_format_tolerant(text).lower()
    
    # Direct substring match
    if phrase_norm in text_norm:
        return True
        
    # Check if phrase is number + unit, e.g. "13.87 ms"
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*(.*)$", phrase_norm)
    if m:
        num_str = m.group(1)
        unit_str = m.group(2).strip()
        num_float = float(num_str)
        num_g = f"{num_float:g}"
        
        # Pattern allowing optional space or underscore between number and unit
        if unit_str:
            esc_unit = re.escape(unit_str)
            # Allow flexible spacing around slashes in units, e.g. "m^3/h" vs "m^3 / h"
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


def test_scorer():
    with open("data/track_b/track_b_heldout_split.json", "r", encoding="utf-8") as f:
        items = json.load(f)

    def load_records(path):
        with open(path, "r", encoding="utf-8") as f:
            recs = {}
            for l in f:
                r = json.loads(l)
                if r.get("track") == "B" and (r.get("rerun_topk5_fair") or "pipeline" in path):
                    recs[r.get("item_id") or r.get("question_id")] = r
        return recs

    pipe = load_records("results/phase4/heldout_pipeline_records.jsonl")
    qwen = load_records("results/phase4/b1_qwen27b_heldout_records.jsonl")
    gpt = load_records("results/phase4/b1_gpt120b_heldout_records.jsonl")

    for name, recs in [("Pipeline", pipe), ("Qwen-27B", qwen), ("GPT-120B", gpt)]:
        passed_count = 0
        failed_items = []
        for it in items:
            qid = it["question_id"]
            r = recs.get(qid)
            if not r:
                failed_items.append((qid, "missing record"))
                continue
            out = normalize_format_tolerant(r["full_output"])
            words = out.strip().split()
            if len(words) > it.get("word_cap", 75):
                failed_items.append((qid, f"word cap {len(words)} > 75"))
                continue
                
            all_ok = True
            for chk in it["checklist"]:
                ctype = chk.get("type")
                if ctype == "token":
                    if not match_component_token(chk["value"], out):
                        all_ok = False
                        failed_items.append((qid, f"missing token {chk['value']}"))
                        break
                elif ctype == "phrase":
                    if not match_phrase_tolerant(chk["value"], out):
                        all_ok = False
                        failed_items.append((qid, f"missing phrase {chk['value']}"))
                        break
                elif ctype == "negative":
                    # Check banned tokens
                    for b in chk.get("banned_tokens", []):
                        b_str = normalize_format_tolerant(str(b)).strip()
                        pat = r"\b" + re.escape(b_str) + r"\b"
                        if re.search(pat, out, re.IGNORECASE):
                            all_ok = False
                            failed_items.append((qid, f"banned token {b_str}"))
                            break
                    if not all_ok:
                        break
            if all_ok:
                passed_count += 1
        print(f"{name}: {passed_count}/{len(items)} passed ({passed_count/len(items)*100:.1f}%)")
        if failed_items:
            print(f"  Failures for {name} ({len(failed_items)}):")
            for fid, reason in failed_items[:5]:
                print(f"    {fid}: {reason}")

if __name__ == "__main__":
    test_scorer()

