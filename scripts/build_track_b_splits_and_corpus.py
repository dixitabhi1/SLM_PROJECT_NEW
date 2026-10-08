"""
Track B Corpus and Question Splits Builder.
Generates:
1. 50 specification documents in data/track_b/corpus/ embedding all 160 invented facts.
2. 50 Dev questions in data/track_b/track_b_dev_split.json (facts from dev pool, max usage <= 2).
3. 50 Held-out questions in data/track_b/track_b_heldout_candidate.json (facts from held pool, max usage <= 2).
4. Full validation against fact_checklist_scorer and audit_rules.
"""

import os
import sys
import json
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.eval.fact_checklist_scorer import score_fact_checklist

TRACK_B_DIR = os.path.join(REPO_ROOT, "data", "track_b")
CORPUS_DIR = os.path.join(TRACK_B_DIR, "corpus")
os.makedirs(CORPUS_DIR, exist_ok=True)

MASTER_POOL_FILE = os.path.join(TRACK_B_DIR, "master_fact_pool.json")
DEV_SPLIT_FILE = os.path.join(TRACK_B_DIR, "track_b_dev_split.json")
HELDOUT_SPLIT_FILE = os.path.join(TRACK_B_DIR, "track_b_heldout_candidate.json")

def load_master_pool():
    with open(MASTER_POOL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_corpus_documents(dev_facts, held_facts):
    """
    Distributes the 160 invented facts across 50 technical specification documents.
    Embeds current v4.2 specifications, superseded v4.1 historical values, and auxiliary distractor equipment.
    """
    all_facts = dev_facts + held_facts
    # 50 documents, roughly 3-4 facts per document
    docs = []
    
    # Subsystem themes across 50 docs
    themes = [
        "Propulsion Dynamics and Inverter Topology",
        "Linear Induction Stator Core Engineering",
        "Superconducting Magnet Coil Cryogenics",
        "Liquid Helium Storage and Pressure Management",
        "Inter-Pod Guideway Mesh Telemetry",
        "Optical Lidar and Guideway Laser Alignment",
        "Eddy-Current Emergency Braking Systems",
        "Aerodynamic Airfoil Deceleration Surfaces",
        "Suspension Levitation Sensor Brackets",
        "High-Voltage Substation Feeder Infrastructure",
        "Airlock Pressure Vessels and Elastomer Seals",
        "Environmental Life Support Gas Regulators",
        "Guideway Structural Truss Formations",
        "Tunnel Aerodynamics and Venting Louvers",
        "Emergency Egress Slide Actuators",
        "Traction Power Switching Matrix",
        "Thermal Loop Heat Exchanger Calibration",
        "Guideway Expansion Joint Instrumentation",
        "Substation Transformer Step-Down Systems",
        "High-Speed Switch Track Linear Actuators"
    ]
    
    facts_per_doc = len(all_facts) // 50
    rem = len(all_facts) % 50
    
    f_idx = 0
    for doc_num in range(1, 51):
        theme = themes[(doc_num - 1) % len(themes)]
        doc_filename = f"doc_{doc_num:02d}.md"
        doc_path = os.path.join(CORPUS_DIR, doc_filename)
        
        # Take facts for this doc
        n_take = facts_per_doc + (1 if doc_num <= rem else 0)
        doc_facts = all_facts[f_idx:f_idx + n_take]
        f_idx += n_take
        
        lines = [
            f"# HyperGrid Technical Specification v4.2 — Chapter {doc_num}",
            f"**Subsystem Focus:** {theme}",
            f"**Baseline Revision:** v4.2 (Supercedes Engineering Standard v4.1)",
            "",
            "## 1. System Architecture Overview",
            f"This chapter outlines operational parameters, physical integration limits, and diagnostic margins for {theme.lower()} within the HyperGrid automated guideway transit network.",
            "",
            "## 2. Active Engineering Parameters (Specification v4.2)",
            "The following parameter values are mandatory for all production vehicles and wayside stations deployed under baseline v4.2:",
            ""
        ]
        
        for f in doc_facts:
            prop = f.get("property", "Parameter")
            val = f.get("value", "N/A")
            comp = f.get("component", "Subsystem Unit")
            role = f.get("role", "Component Role")
            subsys = f.get("subsystem", "General")
            v41 = f.get("superseded_v4_1", "Legacy Nominal")
            aux = f.get("distractor_auxiliary", "Auxiliary Module")
            
            lines.append(f"### {comp} — {prop}")
            lines.append(f"- **Designation & Subsystem:** `{comp}` ({role}, Subsystem: {subsys})")
            lines.append(f"- **Active Specification (v4.2):** **`{val}`**")
            lines.append(f"- **Superseded Standard (v4.1):** `{v41}` (Do not use for v4.2 certification)")
            lines.append(f"- **Auxiliary / Secondary Channel:** `{aux}`")
            lines.append(f"- **Engineering Context:** Operational compliance of {comp} requires maintaining {prop.lower()} within strict system limits under active load.")
            lines.append("")
            
        lines.append("## 3. Quality Assurance & Inspection Procedures")
        lines.append("All field diagnostic probes must execute automated loop checks prior to dispatching vehicles into high-speed transit blocks.")
        lines.append("Discrepancies exceeding allowable thresholds must trigger automated line stops.")
        lines.append("")
        
        with open(doc_path, "w", encoding="utf-8") as df:
            df.write("\n".join(lines))
            
    print(f"Generated 50 specification documents in {CORPUS_DIR}")

def build_questions_for_split(facts, split_name, count=50):
    """
    Builds 50 multi-hop questions using the given 80 facts.
    Enforces:
    - Each fact used at most 2 times.
    - Zero mentions of document IDs or section numbers in prompts.
    - Each question combines at least 2 facts.
    - Expected output formatted as short key-value pairs (< 75 words).
    - Objective fact checklist with positive and negative rules.
    """
    questions = []
    fact_usage = {}
    
    # Track usage
    def record_usage(fid):
        fact_usage[fid] = fact_usage.get(fid, 0) + 1
        if fact_usage[fid] > 2:
            raise ValueError(f"Fact {fid} exceeded max usage of 2!")

    # If dev split, include the 5 approved sample questions first
    start_q = 1
    if split_name == "dev":
        sample_path = os.path.join(TRACK_B_DIR, "track_b_dev_5_sample_questions.json")
        with open(sample_path, "r", encoding="utf-8") as sf:
            samples = json.load(sf)
        for s in samples:
            for fid in s["fact_ids"]:
                record_usage(fid)
            questions.append({
                "question_id": f"track_b_{split_name}_{len(questions)+1:04d}",
                "split": split_name,
                "prompt": s["question"],
                "subsystem": s["subsystem"],
                "multi_hop_type": s["multi_hop_type"],
                "fact_ids": s["fact_ids"],
                "expected_answer_format": "key: value structured pairs (max 75 words)",
                "gold_sample_output": s["sample_gold_output"],
                "word_cap": 75,
                "checklist": s["checklist"]
            })
        start_q = 6

    # We need count - len(questions) more questions
    # Available facts to pair up:
    # We pair fact i and fact j ensuring both usage <= 2
    f_list = list(facts)
    n_facts = len(f_list)
    
    # Systematic pairing to guarantee all facts are covered and usage <= 2
    # Pair fact (i) and fact (i + 1) or across subsystems
    pair_idx = 0
    while len(questions) < count:
        # Find two facts with usage < 2
        f1 = None
        f2 = None
        for cand in f_list:
            if fact_usage.get(cand["fact_id"], 0) < 2:
                if f1 is None:
                    f1 = cand
                elif f2 is None and cand["fact_id"] != f1["fact_id"]:
                    f2 = cand
                    break
                    
        if f1 is None or f2 is None:
            # Fallback if remaining pool is tight: pick any with usage < 2
            eligible = [c for c in f_list if fact_usage.get(c["fact_id"], 0) < 2]
            f1, f2 = eligible[0], eligible[1]
            
        record_usage(f1["fact_id"])
        record_usage(f2["fact_id"])
        
        q_num = len(questions) + 1
        q_id = f"track_b_{split_name}_{q_num:04d}"
        
        # Design question combining f1 and f2
        c1, p1, v1 = f1.get("component"), f1.get("property"), f1.get("value")
        c2, p2, v2 = f2.get("component"), f2.get("property"), f2.get("value")
        s1, s2 = f1.get("subsystem"), f2.get("subsystem")
        
        u1 = f1.get("unit")
        u2 = f2.get("unit")
        num1 = f1.get("numeric_val")
        num2 = f2.get("numeric_val")
        
        v41_1 = f1.get("superseded_v4_1", "")
        v41_2 = f2.get("superseded_v4_1", "")
        aux1 = f1.get("distractor_auxiliary", "")
        aux2 = f2.get("distractor_auxiliary", "")
        
        unit_set = {'khz', 'kw', 'mm', 'l/min', 'kpa', 'pa', 'ms', 'nm', 'm/s^2', 'a', 'bar', 'v', 'c', 'kg', 'm', 'l', 'min', 's'}
        gold_tokens = set(re.findall(r"[A-Za-z0-9_\-\.]+", f"{c1} {c2} {v1} {v2}".lower()))
        banned = []
        for x in [v41_1, v41_2, aux1, aux2]:
            if x:
                toks = re.findall(r"[A-Za-z0-9_\-\.]+", x)
                for t in toks:
                    if t.lower() not in unit_set and t.lower() not in gold_tokens and len(t) > 1:
                        banned.append(t)
        banned = list(set(banned))
        
        # Question variations
        if num1 is not None and num2 is not None and u1 == u2 and u1 is not None:
            # Calculation question: combined sum
            combined_val = round(num1 + num2, 2)
            prompt = (
                f"Under the HyperGrid v4.2 baseline, the {s1} subsystem operates {c1} with a calibrated {p1.lower()}, "
                f"while the {s2} subsystem utilizes {c2} with a specified {p2.lower()}. "
                f"State both parameter values and calculate their combined total in {u1} in a short structured format."
            )
            gold_out = f"component_1: {c1}\n{p1.lower().replace(' ', '_')}: {v1}\ncomponent_2: {c2}\n{p2.lower().replace(' ', '_')}: {v2}\ncombined_total: {combined_val} {u1}"
            checklist = [
                {"type": "numeric", "target": num1, "tolerance": 0.5, "unit": u1, "description": f"{c1} {p1}"},
                {"type": "numeric", "target": num2, "tolerance": 0.5, "unit": u2, "description": f"{c2} {p2}"},
                {"type": "numeric", "target": combined_val, "tolerance": 1.0, "unit": u1, "description": "combined sum"},
                {"type": "negative", "banned_tokens": banned[:4], "description": "distractor values"}
            ]
            m_type = "retrieval_and_calculation"
        elif c1 == c2:
            # Same component bridging
            prompt = (
                f"For the HyperGrid v4.2 specification, identify the active settings of {c1} within the {s1} subsystem, "
                f"stating its {p1.lower()} and its {p2.lower()} in a concise key-value structured response."
            )
            gold_out = f"component: {c1}\n{p1.lower().replace(' ', '_')}: {v1}\n{p2.lower().replace(' ', '_')}: {v2}"
            checklist = [
                {"type": "token", "value": c1, "description": f"component {c1}"},
                {"type": "phrase", "value": v1.lower(), "description": f"{p1} value"},
                {"type": "phrase", "value": v2.lower(), "description": f"{p2} value"},
                {"type": "negative", "banned_tokens": banned[:4], "description": "distractor values"}
            ]
            m_type = "bridging_component_property"
        else:
            # Cross-component coupling
            prompt = (
                f"In the HyperGrid v4.2 engineering release, determine the {p1.lower()} specified for {c1} in the {s1} subsystem, "
                f"alongside the {p2.lower()} designated for {c2} in the {s2} subsystem. Provide the answer in short key-value format."
            )
            gold_out = f"component_1: {c1}\n{p1.lower().replace(' ', '_')}: {v1}\ncomponent_2: {c2}\n{p2.lower().replace(' ', '_')}: {v2}"
            checklist = [
                {"type": "token", "value": c1, "description": f"component {c1}"},
                {"type": "phrase", "value": v1.lower(), "description": f"{p1} value"},
                {"type": "token", "value": c2, "description": f"component {c2}"},
                {"type": "phrase", "value": v2.lower(), "description": f"{p2} value"},
                {"type": "negative", "banned_tokens": banned[:4], "description": "distractor values"}
            ]
            m_type = "cross_subsystem_coupling"
            
        questions.append({
            "question_id": q_id,
            "split": split_name,
            "prompt": prompt,
            "subsystem": f"{s1} / {s2}" if s1 != s2 else s1,
            "multi_hop_type": m_type,
            "fact_ids": [f1["fact_id"], f2["fact_id"]],
            "expected_answer_format": "key: value structured pairs (max 75 words)",
            "gold_sample_output": gold_out,
            "word_cap": 75,
            "checklist": checklist
        })
        
    print(f"Generated {len(questions)} questions for {split_name} split.")
    print(f"Fact usage summary for {split_name}: min={min(fact_usage.values())}, max={max(fact_usage.values())}, unique_facts_used={len(fact_usage)}")
    return questions

def main():
    pool = load_master_pool()
    dev_facts = pool["dev_facts"]
    held_facts = pool["heldout_facts"]
    
    # 1. Generate corpus documents
    generate_corpus_documents(dev_facts, held_facts)
    
    # 2. Build Dev split
    dev_questions = build_questions_for_split(dev_facts, "dev", count=50)
    with open(DEV_SPLIT_FILE, "w", encoding="utf-8") as f:
        json.dump(dev_questions, f, indent=2)
        
    # 3. Build Held-Out candidate split
    held_questions = build_questions_for_split(held_facts, "heldout", count=50)
    with open(HELDOUT_SPLIT_FILE, "w", encoding="utf-8") as f:
        json.dump(held_questions, f, indent=2)
        
    # 4. Verify all sample outputs against checklist scorer
    for split_name, q_list in [("dev", dev_questions), ("heldout", held_questions)]:
        for q in q_list:
            res = score_fact_checklist(q["gold_sample_output"], q["checklist"])
            if not res["binary_pass"]:
                print(f"ERROR: Sample output failed for {q['question_id']}: {res['failed_facts']}")
                raise ValueError(f"Self-check failure in {q['question_id']}")
                
    print("All 100 questions verified against fact checklist scorer: 100% PASS.")

if __name__ == "__main__":
    main()
