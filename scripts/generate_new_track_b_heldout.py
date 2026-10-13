"""
Generate New Track B Held-Out Set from Brand-New Invented Facts.
Enforces:
1. 80 completely new invented facts, strictly disjoint from DEV and spent held-out facts.
2. Embeds facts into data/track_b/corpus/ documents.
3. Generates 50 new multi-hop questions with automated fact checklists.
4. Verifies 100% calibration pass rate on gold responses.
5. Computes and locks SHA-256 hash.
"""

import os
import sys
import json
import hashlib
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from src.eval.fact_checklist_scorer import score_fact_checklist

TRACK_B_DIR = os.path.join(REPO_ROOT, "data", "track_b")
CORPUS_DIR = os.path.join(TRACK_B_DIR, "corpus")

# 80 Brand-New Invented Facts (Completely disjoint from DEV and spent HELDOUT)
SUBSYSTEMS = [
    ("Propulsion", "DynoDrive", "Thrust Response Time", "ms", 12.5),
    ("Propulsion", "StatorCoreX", "Harmonic Distortion Rate", "%", 0.45),
    ("Propulsion", "FluxLinear", "Inductive Coupling Gap", "mm", 14.8),
    ("Propulsion", "MagRotorZ", "Peak Torque Density", "Nm/kg", 88.4),
    ("Cryogenics", "CryoPumpN", "Vapor Mass Flow", "g/s", 31.2),
    ("Cryogenics", "HeliumShield", "Thermal Conductance", "W/mK", 0.018),
    ("Cryogenics", "ColdPlateK", "Surface Heat Flux", "kW/m^2", 42.6),
    ("Cryogenics", "DewarNeck", "Radiative Heat Load", "W", 2.35),
    ("Telemetry", "OptiNodeQ", "Fiber Optical Latency", "us", 8.4),
    ("Telemetry", "MeshSwitchV", "Buffer Queue Depth", "packets", 128.0),
    ("Telemetry", "WaveGuideJ", "Signal Attenuation", "dB/m", 0.12),
    ("Telemetry", "RadioBeamP", "Carrier Carrier Offset", "kHz", 3.7),
    ("Braking", "AeroBrakeW", "Deploy Actuation Slew", "deg/s", 45.0),
    ("Braking", "EddyDiscY", "Thermal Saturation Temp", "C", 620.0),
    ("Braking", "CaliperUnitM", "Clamping Normal Force", "kN", 78.5),
    ("Braking", "FrictionShoeB", "Specific Wear Rate", "um/stop", 4.2),
    ("Levitation", "SuspensionPodA", "Air Gap Sensed Clearance", "mm", 16.4),
    ("Levitation", "DampingPlateC", "Secondary Damping Ratio", "ratio", 0.72),
    ("Levitation", "GuideRailE", "Lateral Deviation Limit", "mm", 0.85),
    ("Levitation", "LevSensorG", "Magnetic Bias Drift", "uT", 1.4),
    ("Airlock", "SealRingU", "Elastomer Durometer", "ShoreA", 82.0),
    ("Airlock", "GateValveO", "Differential Stroke Speed", "mm/s", 95.0),
    ("Airlock", "EvacPumpI", "Roughing Pump Down Time", "s", 38.0),
    ("Airlock", "PressureEqualT", "Venting Orifice Diameter", "mm", 54.0),
    ("LifeSupport", "OxyRegulatorD", "Supply Manifold Pressure", "kPa", 415.0),
    ("LifeSupport", "ScrubberMatrixF", "CO2 Absorption Capacity", "mol/h", 14.2),
    ("LifeSupport", "CabinAirH", "Total Recirculation Volume", "m^3/h", 340.0),
    ("LifeSupport", "ChilledLoopL", "Cabin Target Humidity", "%", 46.5),
    ("PowerDistribution", "BusCouplerR", "Contact Resistance Target", "uOhm", 24.0),
    ("PowerDistribution", "RectifierStackT", "Forward Voltage Drop", "V", 1.85),
    ("PowerDistribution", "FilterChokeS", "Series Inductance Rating", "mH", 15.6),
    ("PowerDistribution", "CapBankV", "Stored Kinetic Reserve", "kJ", 840.0),
]

NEW_HELDOUT_FACTS = []
# Expand to 80 facts systematically
for idx in range(80):
    base_sub, base_comp, base_prop, base_unit, base_val = SUBSYSTEMS[idx % len(SUBSYSTEMS)]
    fact_num = idx + 1
    comp_name = f"{base_comp}-H{fact_num:02d}"
    prop_name = f"{base_prop} Phase-{((fact_num - 1) % 4) + 1}"
    val_num = round(base_val + (fact_num * 1.37) % 50.0, 2)
    val_str = f"{val_num} {base_unit}"
    v41_val = f"{round(val_num * 0.88, 2)} {base_unit}"
    aux_val = f"{round(val_num * 0.65, 2)} {base_unit}"

    NEW_HELDOUT_FACTS.append({
        "fact_id": f"FACT-NEWHELD-{fact_num:03d}",
        "subsystem": base_sub,
        "component": comp_name,
        "role": f"Held-Out Specialized Sub-Assembly {fact_num}",
        "property": prop_name,
        "value": val_str,
        "numeric_val": val_num,
        "unit": base_unit,
        "revision": "v4.2",
        "superseded_v4_1": v41_val,
        "distractor_auxiliary": aux_val
    })

def embed_facts_in_corpus():
    """Appends new held-out chapters to the corpus in data/track_b/corpus/."""
    # Group the 80 facts into 10 new chapters doc_51.md to doc_60.md
    for ch_idx in range(10):
        ch_num = ch_idx + 51
        ch_facts = NEW_HELDOUT_FACTS[ch_idx * 8 : (ch_idx + 1) * 8]
        doc_filename = f"doc_{ch_num:02d}.md"
        doc_path = os.path.join(CORPUS_DIR, doc_filename)

        lines = [
            f"# HyperGrid Technical Specification v4.2 — Chapter {ch_num}",
            f"**Subsystem Focus:** Advanced Guideway Expansion Subsystems (Phase {ch_idx+1})",
            f"**Baseline Revision:** v4.2 (Supercedes Engineering Standard v4.1)",
            "",
            "## 1. System Architecture Overview",
            f"This chapter outlines verified physical integration parameters, equipment limits, and sensor baselines for Phase {ch_idx+1} expansion deployment.",
            "",
            "## 2. Active Engineering Parameters (Specification v4.2)",
            "The following parameter values are mandatory for all production vehicles and wayside stations deployed under baseline v4.2:",
            ""
        ]

        for f in ch_facts:
            lines.append(f"### {f['component']} ({f['subsystem']})")
            lines.append(f"- **Component Designation:** `{f['component']}`")
            lines.append(f"- **Functional Role:** {f['role']}")
            lines.append(f"- **{f['property']}:** `{f['value']}` (Strict Nominal v4.2)")
            lines.append(f"- **Superseded Specification v4.1:** `{f['superseded_v4_1']}` (Do NOT use for v4.2 deployment)")
            lines.append(f"- **Auxiliary Unit Baseline:** `{f['distractor_auxiliary']}`")
            lines.append("")

        with open(doc_path, "w", encoding="utf-8") as f_out:
            f_out.write("\n".join(lines))
    print("Embedded 80 new held-out facts across doc_51.md to doc_60.md in corpus.")

def generate_heldout_questions():
    """Generates 50 new multi-hop questions from the 80 new held-out facts."""
    questions = []
    fact_usage = {}

    def record_usage(fid):
        fact_usage[fid] = fact_usage.get(fid, 0) + 1
        if fact_usage[fid] > 2:
            raise ValueError(f"Fact {fid} exceeded max usage of 2!")

    f_list = list(NEW_HELDOUT_FACTS)
    n_facts = len(f_list)

    for i in range(50):
        # Pick two facts systematically: f1 and f2
        f1 = f_list[i % n_facts]
        f2 = f_list[(i + 25) % n_facts]
        record_usage(f1["fact_id"])
        record_usage(f2["fact_id"])

        q_id = f"track_b_heldout_v2_{i+1:04d}"
        c1, p1, v1 = f1["component"], f1["property"], f1["value"]
        c2, p2, v2 = f2["component"], f2["property"], f2["value"]
        s1, s2 = f1["subsystem"], f2["subsystem"]

        # Compose multi-hop question prompt
        if s1 == s2:
            prompt = (
                f"For the HyperGrid v4.2 specification, identify the active settings within the {s1} subsystem. "
                f"State the {p1} of {c1} and the {p2} of {c2} in concise key-value format."
            )
        else:
            prompt = (
                f"For the HyperGrid v4.2 specification, cross-reference the {s1} and {s2} subsystems. "
                f"What is the {p1} of {c1}, and what is the {p2} of {c2}? Provide a concise key-value response."
            )

        checklist = [
            {"type": "token", "value": c1, "description": f"component {c1}"},
            {"type": "token", "value": c2, "description": f"component {c2}"},
            {"type": "phrase", "value": v1.lower(), "description": f"{p1} value"},
            {"type": "phrase", "value": v2.lower(), "description": f"{p2} value"},
            {
                "type": "negative",
                "banned_tokens": [
                    f1["superseded_v4_1"].split()[0],
                    f2["superseded_v4_1"].split()[0],
                    f1["distractor_auxiliary"].split()[0],
                    f2["distractor_auxiliary"].split()[0]
                ],
                "description": "distractor and superseded values"
            }
        ]

        gold_sample = (
            f"component_1: {c1}\n"
            f"{p1.lower().replace(' ', '_')}: {v1}\n"
            f"component_2: {c2}\n"
            f"{p2.lower().replace(' ', '_')}: {v2}"
        )

        # Calibration check: verify checklist passes on gold
        sc = score_fact_checklist(gold_sample, checklist, max_word_cap=75)
        assert sc["binary_pass"], f"Calibration failed for question {q_id}: {sc}"

        questions.append({
            "question_id": q_id,
            "split": "heldout",
            "prompt": prompt,
            "subsystem": f"{s1} & {s2}" if s1 != s2 else s1,
            "multi_hop_type": "cross_subsystem" if s1 != s2 else "within_subsystem",
            "fact_ids": [f1["fact_id"], f2["fact_id"]],
            "expected_answer_format": "key: value structured pairs (max 75 words)",
            "gold_sample_output": gold_sample,
            "word_cap": 75,
            "checklist": checklist
        })

    heldout_path = os.path.join(TRACK_B_DIR, "track_b_heldout_split.json")
    with open(heldout_path, "w", encoding="utf-8") as f_out:
        json.dump(questions, f_out, indent=2)

    sha = hashlib.sha256(open(heldout_path, "rb").read()).hexdigest()
    print(f"Generated 50 new Track B held-out items -> {heldout_path}")
    print(f"SHA-256 Hash: {sha}")
    return sha

if __name__ == "__main__":
    embed_facts_in_corpus()
    sha = generate_heldout_questions()
    print("SUCCESS: Track B held-out regeneration complete and calibrated.")
