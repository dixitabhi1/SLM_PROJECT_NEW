"""
Track B Calibration Dataset Setup.
Creates 10 calibration items with 20 newly invented facts that exist in NEITHER
the dev nor held-out fact pools.
Appends the facts to data/track_b/corpus/doc_51_calibration.md and saves
the calibration questions to data/track_b/track_b_calibration_10_items.json.
All 10 items are marked SPENT immediately upon generation.
"""

import os
import json

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CORPUS_FILE = os.path.join(REPO_ROOT, "data", "track_b", "corpus", "doc_51_calibration.md")
CALIB_JSON = os.path.join(REPO_ROOT, "data", "track_b", "track_b_calibration_10_items.json")

# 20 brand-new invented facts (FACT-CALIB-001 to FACT-CALIB-020)
CALIB_FACTS = [
    {
        "fact_id": "FACT-CALIB-001",
        "component": "Converter-KV7",
        "subsystem": "Auxiliary Power",
        "property": "Nominal Bus Voltage",
        "active_v4_2": "842.6 V",
        "numeric_val": 842.6,
        "unit": "V",
        "superseded_v4_1": "790.0 V",
        "auxiliary": "620.0 V"
    },
    {
        "fact_id": "FACT-CALIB-002",
        "component": "Converter-KV7",
        "subsystem": "Auxiliary Power",
        "property": "Peak Efficiency Rating",
        "active_v4_2": "97.8 %",
        "numeric_val": 97.8,
        "unit": "%",
        "superseded_v4_1": "94.2 %",
        "auxiliary": "91.5 %"
    },
    {
        "fact_id": "FACT-CALIB-003",
        "component": "TelemetryMod-T9",
        "subsystem": "Telemetry Dynamics",
        "property": "Transmission Baud Rate",
        "active_v4_2": "460.8 kbps",
        "numeric_val": 460.8,
        "unit": "kbps",
        "superseded_v4_1": "384.0 kbps",
        "auxiliary": "192.0 kbps"
    },
    {
        "fact_id": "FACT-CALIB-004",
        "component": "TelemetryMod-T9",
        "subsystem": "Telemetry Dynamics",
        "property": "Buffer Queue Capacity",
        "active_v4_2": "512 packets",
        "numeric_val": 512,
        "unit": "packets",
        "superseded_v4_1": "256 packets",
        "auxiliary": "128 packets"
    },
    {
        "fact_id": "FACT-CALIB-005",
        "component": "LevitationPad-L3",
        "subsystem": "Guideway Levitation",
        "property": "Nominal Air Gap Clearance",
        "active_v4_2": "18.4 mm",
        "numeric_val": 18.4,
        "unit": "mm",
        "superseded_v4_1": "22.0 mm",
        "auxiliary": "12.0 mm"
    },
    {
        "fact_id": "FACT-CALIB-006",
        "component": "LevitationPad-L3",
        "subsystem": "Guideway Levitation",
        "property": "Electromagnetic Slew Rate",
        "active_v4_2": "125.0 A/ms",
        "numeric_val": 125.0,
        "unit": "A/ms",
        "superseded_v4_1": "100.0 A/ms",
        "auxiliary": "80.0 A/ms"
    },
    {
        "fact_id": "FACT-CALIB-007",
        "component": "RadiatorCore-R5",
        "subsystem": "Thermal Dissipation",
        "property": "Heat Rejection Capacity",
        "active_v4_2": "345.2 kW",
        "numeric_val": 345.2,
        "unit": "kW",
        "superseded_v4_1": "310.0 kW",
        "auxiliary": "210.0 kW"
    },
    {
        "fact_id": "FACT-CALIB-008",
        "component": "RadiatorCore-R5",
        "subsystem": "Thermal Dissipation",
        "property": "Coolant Volumetric Flow Rate",
        "active_v4_2": "86.5 L/min",
        "numeric_val": 86.5,
        "unit": "L/min",
        "superseded_v4_1": "75.0 L/min",
        "auxiliary": "50.0 L/min"
    },
    {
        "fact_id": "FACT-CALIB-009",
        "component": "BrakeCaliper-BC2",
        "subsystem": "Pneumatic Braking",
        "property": "Clamping Force Margin",
        "active_v4_2": "42.8 kN",
        "numeric_val": 42.8,
        "unit": "kN",
        "superseded_v4_1": "38.0 kN",
        "auxiliary": "25.0 kN"
    },
    {
        "fact_id": "FACT-CALIB-010",
        "component": "BrakeCaliper-BC2",
        "subsystem": "Pneumatic Braking",
        "property": "Response Time Threshold",
        "active_v4_2": "14.2 ms",
        "numeric_val": 14.2,
        "unit": "ms",
        "superseded_v4_1": "18.0 ms",
        "auxiliary": "25.0 ms"
    },
    {
        "fact_id": "FACT-CALIB-011",
        "component": "OpticSensor-OS8",
        "subsystem": "Guideway Alignment",
        "property": "Laser Sampling Frequency",
        "active_v4_2": "250.0 Hz",
        "numeric_val": 250.0,
        "unit": "Hz",
        "superseded_v4_1": "200.0 Hz",
        "auxiliary": "100.0 Hz"
    },
    {
        "fact_id": "FACT-CALIB-012",
        "component": "OpticSensor-OS8",
        "subsystem": "Guideway Alignment",
        "property": "Detection Angular FOV",
        "active_v4_2": "64.5 deg",
        "numeric_val": 64.5,
        "unit": "deg",
        "superseded_v4_1": "55.0 deg",
        "auxiliary": "40.0 deg"
    },
    {
        "fact_id": "FACT-CALIB-013",
        "component": "InertialUnit-IMU4",
        "subsystem": "Guidance Navigation",
        "property": "Gyroscope Drift Bias",
        "active_v4_2": "0.035 deg/hr",
        "numeric_val": 0.035,
        "unit": "deg/hr",
        "superseded_v4_1": "0.050 deg/hr",
        "auxiliary": "0.100 deg/hr"
    },
    {
        "fact_id": "FACT-CALIB-014",
        "component": "InertialUnit-IMU4",
        "subsystem": "Guidance Navigation",
        "property": "Accelerometer Dynamic Range",
        "active_v4_2": "16.0 g",
        "numeric_val": 16.0,
        "unit": "g",
        "superseded_v4_1": "12.0 g",
        "auxiliary": "8.0 g"
    },
    {
        "fact_id": "FACT-CALIB-015",
        "component": "BatteryPack-BP9",
        "subsystem": "Energy Storage",
        "property": "Internal Pack Impedance",
        "active_v4_2": "28.4 mOhm",
        "numeric_val": 28.4,
        "unit": "mOhm",
        "superseded_v4_1": "35.0 mOhm",
        "auxiliary": "48.0 mOhm"
    },
    {
        "fact_id": "FACT-CALIB-016",
        "component": "BatteryPack-BP9",
        "subsystem": "Energy Storage",
        "property": "Charge C-Rate Cap",
        "active_v4_2": "3.5 C",
        "numeric_val": 3.5,
        "unit": "C",
        "superseded_v4_1": "2.8 C",
        "auxiliary": "1.5 C"
    },
    {
        "fact_id": "FACT-CALIB-017",
        "component": "CryoVent-CV3",
        "subsystem": "Cryogenics",
        "property": "Exhaust Burst Pressure",
        "active_v4_2": "18.6 bar",
        "numeric_val": 18.6,
        "unit": "bar",
        "superseded_v4_1": "15.0 bar",
        "auxiliary": "10.0 bar"
    },
    {
        "fact_id": "FACT-CALIB-018",
        "component": "CryoVent-CV3",
        "subsystem": "Cryogenics",
        "property": "Valve Orifice Diameter",
        "active_v4_2": "4.8 mm",
        "numeric_val": 4.8,
        "unit": "mm",
        "superseded_v4_1": "4.0 mm",
        "auxiliary": "3.2 mm"
    },
    {
        "fact_id": "FACT-CALIB-019",
        "component": "AntennaArray-AA5",
        "subsystem": "Communications",
        "property": "Center Resonance Frequency",
        "active_v4_2": "5.85 GHz",
        "numeric_val": 5.85,
        "unit": "GHz",
        "superseded_v4_1": "5.40 GHz",
        "auxiliary": "2.40 GHz"
    },
    {
        "fact_id": "FACT-CALIB-020",
        "component": "AntennaArray-AA5",
        "subsystem": "Communications",
        "property": "Main Lobe Peak Gain",
        "active_v4_2": "14.2 dBi",
        "numeric_val": 14.2,
        "unit": "dBi",
        "superseded_v4_1": "11.5 dBi",
        "auxiliary": "8.0 dBi"
    }
]

# Write Corpus Document doc_51_calibration.md
def build_corpus_markdown():
    lines = [
        "# HyperGrid Technical Specification v4.2 — Chapter 51",
        "**Subsystem Focus:** Auxiliary Power, Telemetry, Guidance, and Communications Calibration",
        "**Baseline Revision:** v4.2 (Supercedes Engineering Standard v4.1)",
        "**Status:** CALIBRATION SPENT CORPUS",
        "",
        "## 1. System Overview",
        "This chapter documents certified calibration parameter baselines for auxiliary conversion, telemetry, levitation dynamics, braking, sensing, energy storage, and cryo-venting within the HyperGrid transit infrastructure.",
        "",
        "## 2. Certified Engineering Specifications (v4.2)",
        ""
    ]
    for f in CALIB_FACTS:
        lines.append(f"### {f['component']} — {f['property']}")
        lines.append(f"- **Designation & Subsystem:** `{f['component']}` (Subsystem: {f['subsystem']})")
        lines.append(f"- **Active Specification (v4.2):** **`{f['active_v4_2']}`**")
        lines.append(f"- **Superseded Standard (v4.1):** `{f['superseded_v4_1']}` (Do not use for v4.2 certification)")
        lines.append(f"- **Auxiliary / Secondary Channel:** `{f['auxiliary']}`")
        lines.append(f"- **Engineering Context:** Compliance for {f['component']} requires strictly maintaining {f['property'].lower()} within certified tolerances under nominal load.")
        lines.append("")
    return "\n".join(lines)

# 10 Calibration Questions
def build_calibration_questions():
    questions = [
        {
            "question_id": "track_b_calib_0001",
            "prompt": "Identify the primary auxiliary power converter assigned to the Auxiliary Power subsystem in the HyperGrid v4.2 specification, and state both its nominal bus voltage and peak efficiency rating in a short key-value format.",
            "subsystem": "Auxiliary Power",
            "fact_ids": ["FACT-CALIB-001", "FACT-CALIB-002"],
            "word_cap": 75,
            "checklist": [
                {"type": "token", "value": "Converter-KV7", "description": "component Converter-KV7"},
                {"type": "numeric", "target": 842.6, "tolerance": 0.5, "unit": "V", "description": "bus voltage 842.6 V"},
                {"type": "numeric", "target": 97.8, "tolerance": 0.2, "unit": "%", "description": "peak efficiency 97.8 %"},
                {"type": "negative", "banned_tokens": ["790.0", "94.2", "620.0", "91.5"], "description": "banned superseded values"}
            ]
        },
        {
            "question_id": "track_b_calib_0002",
            "prompt": "Under HyperGrid v4.2 specifications for Telemetry Dynamics, state the active transmission baud rate and the buffer queue capacity for TelemetryMod-T9.",
            "subsystem": "Telemetry Dynamics",
            "fact_ids": ["FACT-CALIB-003", "FACT-CALIB-004"],
            "word_cap": 75,
            "checklist": [
                {"type": "token", "value": "TelemetryMod-T9", "description": "component TelemetryMod-T9"},
                {"type": "numeric", "target": 460.8, "tolerance": 0.5, "unit": "kbps", "description": "baud rate 460.8 kbps"},
                {"type": "numeric", "target": 512, "tolerance": 1, "unit": "packets", "description": "buffer capacity 512 packets"},
                {"type": "negative", "banned_tokens": ["384.0", "256", "192.0", "128"], "description": "banned superseded values"}
            ]
        },
        {
            "question_id": "track_b_calib_0003",
            "prompt": "Identify the nominal air gap clearance and electromagnetic slew rate certified for LevitationPad-L3 under HyperGrid v4.2 guideway levitation standards.",
            "subsystem": "Guideway Levitation",
            "fact_ids": ["FACT-CALIB-005", "FACT-CALIB-006"],
            "word_cap": 75,
            "checklist": [
                {"type": "token", "value": "LevitationPad-L3", "description": "component LevitationPad-L3"},
                {"type": "numeric", "target": 18.4, "tolerance": 0.2, "unit": "mm", "description": "air gap clearance 18.4 mm"},
                {"type": "numeric", "target": 125.0, "tolerance": 0.5, "unit": "A/ms", "description": "slew rate 125.0 A/ms"},
                {"type": "negative", "banned_tokens": ["22.0", "100.0", "12.0", "80.0"], "description": "banned superseded values"}
            ]
        },
        {
            "question_id": "track_b_calib_0004",
            "prompt": "State the active heat rejection capacity and coolant volumetric flow rate for RadiatorCore-R5 under the HyperGrid v4.2 Thermal Dissipation standard.",
            "subsystem": "Thermal Dissipation",
            "fact_ids": ["FACT-CALIB-007", "FACT-CALIB-008"],
            "word_cap": 75,
            "checklist": [
                {"type": "token", "value": "RadiatorCore-R5", "description": "component RadiatorCore-R5"},
                {"type": "numeric", "target": 345.2, "tolerance": 0.5, "unit": "kW", "description": "heat rejection 345.2 kW"},
                {"type": "numeric", "target": 86.5, "tolerance": 0.5, "unit": "L/min", "description": "flow rate 86.5 L/min"},
                {"type": "negative", "banned_tokens": ["310.0", "75.0", "210.0", "50.0"], "description": "banned superseded values"}
            ]
        },
        {
            "question_id": "track_b_calib_0005",
            "prompt": "Under the HyperGrid v4.2 pneumatic braking specification, state the clamping force margin and response time threshold for BrakeCaliper-BC2.",
            "subsystem": "Pneumatic Braking",
            "fact_ids": ["FACT-CALIB-009", "FACT-CALIB-010"],
            "word_cap": 75,
            "checklist": [
                {"type": "token", "value": "BrakeCaliper-BC2", "description": "component BrakeCaliper-BC2"},
                {"type": "numeric", "target": 42.8, "tolerance": 0.2, "unit": "kN", "description": "clamping force 42.8 kN"},
                {"type": "numeric", "target": 14.2, "tolerance": 0.2, "unit": "ms", "description": "response time 14.2 ms"},
                {"type": "negative", "banned_tokens": ["38.0", "18.0", "25.0"], "description": "banned superseded values"}
            ]
        },
        {
            "question_id": "track_b_calib_0006",
            "prompt": "Identify OpticSensor-OS8 in the Guideway Alignment subsystem under HyperGrid v4.2, and state its laser sampling frequency and detection angular FOV.",
            "subsystem": "Guideway Alignment",
            "fact_ids": ["FACT-CALIB-011", "FACT-CALIB-012"],
            "word_cap": 75,
            "checklist": [
                {"type": "token", "value": "OpticSensor-OS8", "description": "component OpticSensor-OS8"},
                {"type": "numeric", "target": 250.0, "tolerance": 1.0, "unit": "Hz", "description": "sampling frequency 250.0 Hz"},
                {"type": "numeric", "target": 64.5, "tolerance": 0.5, "unit": "deg", "description": "angular FOV 64.5 deg"},
                {"type": "negative", "banned_tokens": ["200.0", "55.0", "100.0", "40.0"], "description": "banned superseded values"}
            ]
        },
        {
            "question_id": "track_b_calib_0007",
            "prompt": "State the certified gyroscope drift bias and accelerometer dynamic range for InertialUnit-IMU4 in the HyperGrid v4.2 Guidance Navigation subsystem.",
            "subsystem": "Guidance Navigation",
            "fact_ids": ["FACT-CALIB-013", "FACT-CALIB-014"],
            "word_cap": 75,
            "checklist": [
                {"type": "token", "value": "InertialUnit-IMU4", "description": "component InertialUnit-IMU4"},
                {"type": "numeric", "target": 0.035, "tolerance": 0.005, "unit": "deg/hr", "description": "gyro drift bias 0.035 deg/hr"},
                {"type": "numeric", "target": 16.0, "tolerance": 0.5, "unit": "g", "description": "dynamic range 16.0 g"},
                {"type": "negative", "banned_tokens": ["0.050", "12.0", "0.100", "8.0"], "description": "banned superseded values"}
            ]
        },
        {
            "question_id": "track_b_calib_0008",
            "prompt": "Under the HyperGrid v4.2 Energy Storage baseline, state the internal pack impedance and maximum charge C-rate cap for BatteryPack-BP9.",
            "subsystem": "Energy Storage",
            "fact_ids": ["FACT-CALIB-015", "FACT-CALIB-016"],
            "word_cap": 75,
            "checklist": [
                {"type": "token", "value": "BatteryPack-BP9", "description": "component BatteryPack-BP9"},
                {"type": "numeric", "target": 28.4, "tolerance": 0.5, "unit": "mOhm", "description": "pack impedance 28.4 mOhm"},
                {"type": "numeric", "target": 3.5, "tolerance": 0.1, "unit": "C", "description": "charge C-rate 3.5 C"},
                {"type": "negative", "banned_tokens": ["35.0", "2.8", "48.0", "1.5"], "description": "banned superseded values"}
            ]
        },
        {
            "question_id": "track_b_calib_0009",
            "prompt": "Identify CryoVent-CV3 in the Cryogenics subsystem under HyperGrid v4.2, and state its exhaust burst pressure and valve orifice diameter.",
            "subsystem": "Cryogenics",
            "fact_ids": ["FACT-CALIB-017", "FACT-CALIB-018"],
            "word_cap": 75,
            "checklist": [
                {"type": "token", "value": "CryoVent-CV3", "description": "component CryoVent-CV3"},
                {"type": "numeric", "target": 18.6, "tolerance": 0.2, "unit": "bar", "description": "burst pressure 18.6 bar"},
                {"type": "numeric", "target": 4.8, "tolerance": 0.2, "unit": "mm", "description": "orifice diameter 4.8 mm"},
                {"type": "negative", "banned_tokens": ["15.0", "4.0", "10.0", "3.2"], "description": "banned superseded values"}
            ]
        },
        {
            "question_id": "track_b_calib_0010",
            "prompt": "State the center resonance frequency and main lobe peak gain certified for AntennaArray-AA5 under the HyperGrid v4.2 Communications subsystem.",
            "subsystem": "Communications",
            "fact_ids": ["FACT-CALIB-019", "FACT-CALIB-020"],
            "word_cap": 75,
            "checklist": [
                {"type": "token", "value": "AntennaArray-AA5", "description": "component AntennaArray-AA5"},
                {"type": "numeric", "target": 5.85, "tolerance": 0.05, "unit": "GHz", "description": "resonance frequency 5.85 GHz"},
                {"type": "numeric", "target": 14.2, "tolerance": 0.2, "unit": "dBi", "description": "main lobe gain 14.2 dBi"},
                {"type": "negative", "banned_tokens": ["5.40", "11.5", "2.40", "8.0"], "description": "banned superseded values"}
            ]
        }
    ]
    return questions

def main():
    print("Writing doc_51_calibration.md to corpus...")
    md_content = build_corpus_markdown()
    with open(CORPUS_FILE, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Wrote {len(md_content)} bytes to {CORPUS_FILE}")

    print("Writing track_b_calibration_10_items.json...")
    calib_q = build_calibration_questions()
    with open(CALIB_JSON, "w", encoding="utf-8") as f:
        json.dump(calib_q, f, indent=2)
    print(f"Saved {len(calib_q)} calibration items to {CALIB_JSON}")

if __name__ == "__main__":
    main()

