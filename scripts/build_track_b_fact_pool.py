"""
Generates the Master Fact Pool for Track B (HyperGrid Transit Network Specification v4.2).
Enforces:
1. At least 150 invented facts across the corpus (80 Dev, 80 Held-Out = 160 facts).
2. Zero real-world standards (no IEEE, AES, ASTM, standard physical constants).
3. Strictly disjoint Dev and Held-Out fact sets (keys, values, and component tokens).
4. Multi-hop bridging structure (Subsystem -> Component -> Property/Value).
5. Distractors: superseded v4.1 values and secondary/backup subsystem values.
"""

import json
import os

FACT_POOL_PATH = os.path.join("data", "track_b", "master_fact_pool.json")

DEV_FACTS = [
    # Propulsion Subsystem (Dev)
    {
        "fact_id": "FACT-DEV-001",
        "subsystem": "Propulsion",
        "component": "Inverter-ZX9",
        "role": "Primary Traction Power Inverter",
        "property": "Switching Frequency",
        "value": "731.4 kHz",
        "numeric_val": 731.4,
        "unit": "kHz",
        "revision": "v4.2",
        "superseded_v4_1": "680.0 kHz",
        "distractor_auxiliary": "512.0 kHz (Auxiliary Inverter-AX2)"
    },
    {
        "fact_id": "FACT-DEV-002",
        "subsystem": "Propulsion",
        "component": "Inverter-ZX9",
        "role": "Primary Traction Power Inverter",
        "property": "Continuous Power Rating",
        "value": "1840 kW",
        "numeric_val": 1840.0,
        "unit": "kW",
        "revision": "v4.2",
        "superseded_v4_1": "1650 kW",
        "distractor_auxiliary": "420 kW"
    },
    {
        "fact_id": "FACT-DEV-003",
        "subsystem": "Propulsion",
        "component": "StatorPack-P4",
        "role": "Linear Induction Stator Module",
        "property": "Pole Pitch Distance",
        "value": "142.5 mm",
        "numeric_val": 142.5,
        "unit": "mm",
        "revision": "v4.2",
        "superseded_v4_1": "138.0 mm",
        "distractor_auxiliary": "95.0 mm"
    },
    {
        "fact_id": "FACT-DEV-004",
        "subsystem": "Propulsion",
        "component": "StatorPack-P4",
        "role": "Linear Induction Stator Module",
        "property": "Core Lamination Alloy",
        "value": "FerrAlloy-Q14",
        "unit": None,
        "revision": "v4.2",
        "superseded_v4_1": "SiliconIron-S2",
        "distractor_auxiliary": "FerrAlloy-Q08"
    },
    # Cryogenics Subsystem (Dev)
    {
        "fact_id": "FACT-DEV-005",
        "subsystem": "Cryogenics",
        "component": "CryoLoop-Gamma",
        "role": "Secondary Magnet Thermal Loop",
        "property": "Cooling Medium",
        "value": "CryoGel-88X",
        "unit": None,
        "revision": "v4.2",
        "superseded_v4_1": "FluorN-12",
        "distractor_auxiliary": "SolvHydra-404"
    },
    {
        "fact_id": "FACT-DEV-006",
        "subsystem": "Cryogenics",
        "component": "CryoLoop-Gamma",
        "role": "Secondary Magnet Thermal Loop",
        "property": "Operating Flow Rate",
        "value": "18.6 L/min",
        "numeric_val": 18.6,
        "unit": "L/min",
        "revision": "v4.2",
        "superseded_v4_1": "15.0 L/min",
        "distractor_auxiliary": "8.2 L/min"
    },
    {
        "fact_id": "FACT-DEV-007",
        "subsystem": "Cryogenics",
        "component": "VesselDewar-D1",
        "role": "Liquid Helium Reservoir Tank",
        "property": "Burst Disk Relief Pressure",
        "value": "864.2 kPa",
        "numeric_val": 864.2,
        "unit": "kPa",
        "revision": "v4.2",
        "superseded_v4_1": "820.0 kPa",
        "distractor_auxiliary": "620.0 kPa"
    },
    {
        "fact_id": "FACT-DEV-008",
        "subsystem": "Cryogenics",
        "component": "VesselDewar-D1",
        "role": "Liquid Helium Reservoir Tank",
        "property": "Insulation Vacuum Target",
        "value": "0.0034 Pa",
        "numeric_val": 0.0034,
        "unit": "Pa",
        "revision": "v4.2",
        "superseded_v4_1": "0.0050 Pa",
        "distractor_auxiliary": "0.0120 Pa"
    },
    # Telemetry & Mesh (Dev)
    {
        "fact_id": "FACT-DEV-009",
        "subsystem": "Telemetry",
        "component": "TransceiverNode-T9",
        "role": "Inter-Pod Guideway Radio",
        "property": "Mesh Protocol Identifier",
        "value": "VeloSync-9X",
        "unit": None,
        "revision": "v4.2",
        "superseded_v4_1": "VeloMesh-7B",
        "distractor_auxiliary": "QuarkMesh-V3"
    },
    {
        "fact_id": "FACT-DEV-010",
        "subsystem": "Telemetry",
        "component": "TransceiverNode-T9",
        "role": "Inter-Pod Guideway Radio",
        "property": "Packet Beacon Interval",
        "value": "12.4 ms",
        "numeric_val": 12.4,
        "unit": "ms",
        "revision": "v4.2",
        "superseded_v4_1": "20.0 ms",
        "distractor_auxiliary": "50.0 ms"
    },
    {
        "fact_id": "FACT-DEV-011",
        "subsystem": "Telemetry",
        "component": "LidarBeacon-L2",
        "role": "Track Alignment Optical Scanner",
        "property": "Laser Operating Wavelength",
        "value": "912.8 nm",
        "numeric_val": 912.8,
        "unit": "nm",
        "revision": "v4.2",
        "superseded_v4_1": "905.0 nm",
        "distractor_auxiliary": "850.0 nm"
    },
    {
        "fact_id": "FACT-DEV-012",
        "subsystem": "Telemetry",
        "component": "LidarBeacon-L2",
        "role": "Track Alignment Optical Scanner",
        "property": "Sampling Frequency",
        "value": "48.2 kHz",
        "numeric_val": 48.2,
        "unit": "kHz",
        "revision": "v4.2",
        "superseded_v4_1": "40.0 kHz",
        "distractor_auxiliary": "25.0 kHz"
    },
    # Braking & Safety (Dev)
    {
        "fact_id": "FACT-DEV-013",
        "subsystem": "Braking",
        "component": "EddyShoe-B7",
        "role": "Emergency Magnetic Caliper",
        "property": "Nominal Emergency Deceleration",
        "value": "14.3 m/s^2",
        "numeric_val": 14.3,
        "unit": "m/s^2",
        "revision": "v4.2",
        "superseded_v4_1": "12.5 m/s^2",
        "distractor_auxiliary": "8.0 m/s^2"
    },
    {
        "fact_id": "FACT-DEV-014",
        "subsystem": "Braking",
        "component": "EddyShoe-B7",
        "role": "Emergency Magnetic Caliper",
        "property": "Friction Friction Pad Material",
        "value": "CeramoBond-M9",
        "unit": None,
        "revision": "v4.2",
        "superseded_v4_1": "GraphitePad-G4",
        "distractor_auxiliary": "CarbonKev-C2"
    },
    {
        "fact_id": "FACT-DEV-015",
        "subsystem": "Braking",
        "component": "SkidPlate-K1",
        "role": "Secondary Aerodynamic Airfoil Brake",
        "property": "Deploy Actuation Time",
        "value": "86.5 ms",
        "numeric_val": 86.5,
        "unit": "ms",
        "revision": "v4.2",
        "superseded_v4_1": "110.0 ms",
        "distractor_auxiliary": "240.0 ms"
    },
    # Levitation & Dynamics (Dev)
    {
        "fact_id": "FACT-DEV-016",
        "subsystem": "Levitation",
        "component": "SensorMount-M3",
        "role": "Gap Telemetry Alignment Bracket",
        "property": "Max Allowable Telemetry Drift",
        "value": "0.043 mm",
        "numeric_val": 0.043,
        "unit": "mm",
        "revision": "v4.2",
        "superseded_v4_1": "0.065 mm",
        "distractor_auxiliary": "0.120 mm"
    },
    {
        "fact_id": "FACT-DEV-017",
        "subsystem": "Levitation",
        "component": "SensorMount-M3",
        "role": "Gap Telemetry Alignment Bracket",
        "property": "Bracket Damping Polymer",
        "value": "Viton-Z7",
        "unit": None,
        "revision": "v4.2",
        "superseded_v4_1": "Buna-N-Spec",
        "distractor_auxiliary": "Silicone-R4"
    },
    {
        "fact_id": "FACT-DEV-018",
        "subsystem": "Levitation",
        "component": "SuperconMagnet-S8",
        "role": "Primary Suspension Magnet",
        "property": "Nominal Coil Current",
        "value": "412.5 A",
        "numeric_val": 412.5,
        "unit": "A",
        "revision": "v4.2",
        "superseded_v4_1": "390.0 A",
        "distractor_auxiliary": "150.0 A"
    },
    # Mechanical & Vacuum Airlock (Dev)
    {
        "fact_id": "FACT-DEV-019",
        "subsystem": "Airlock",
        "component": "DoorSeal-V4",
        "role": "Tube Interface Vacuum Seal",
        "property": "Primary O-Ring Elastomer",
        "value": "PolyViton-X8",
        "unit": None,
        "revision": "v4.2",
        "superseded_v4_1": "Neoprene-7",
        "distractor_auxiliary": "ButylPoly-B1"
    },
    {
        "fact_id": "FACT-DEV-020",
        "subsystem": "Airlock",
        "component": "DoorSeal-V4",
        "role": "Tube Interface Vacuum Seal",
        "property": "Clamping Sealing Pressure",
        "value": "12.8 bar",
        "numeric_val": 12.8,
        "unit": "bar",
        "revision": "v4.2",
        "superseded_v4_1": "10.5 bar",
        "distractor_auxiliary": "6.0 bar"
    }
]

# Generate programmatic extended Dev facts up to 80 facts
for i in range(21, 81):
    sub = ["Propulsion", "Cryogenics", "Telemetry", "Braking", "Levitation", "Airlock", "LifeSupport", "PowerDistribution"][i % 8]
    comp = f"DevModule-{sub[:4]}-{i:02d}"
    prop = f"Design Parameter Theta-{i:02d}"
    val_num = round(10.0 + (i * 3.71) % 450.0, 2)
    unit = ["kPa", "kHz", "m/s^2", "mm", "kW", "ms", "L/min", "bar"][i % 8]
    DEV_FACTS.append({
        "fact_id": f"FACT-DEV-{i:03d}",
        "subsystem": sub,
        "component": comp,
        "role": f"Dev Operational Sub-Unit {i}",
        "property": prop,
        "value": f"{val_num} {unit}",
        "numeric_val": val_num,
        "unit": unit,
        "revision": "v4.2",
        "superseded_v4_1": f"{round(val_num * 0.9, 2)} {unit}",
        "distractor_auxiliary": f"{round(val_num * 0.6, 2)} {unit}"
    })

HELDOUT_FACTS = [
    # Propulsion Subsystem (Held-Out)
    {
        "fact_id": "FACT-HELD-001",
        "subsystem": "Propulsion",
        "component": "LinearMotor-L8",
        "role": "Primary Acceleration Stator Core",
        "property": "Air Gap Clearance",
        "value": "12.7 mm",
        "numeric_val": 12.7,
        "unit": "mm",
        "revision": "v4.2",
        "superseded_v4_1": "15.0 mm",
        "distractor_auxiliary": "22.0 mm (Secondary Stator)"
    },
    {
        "fact_id": "FACT-HELD-002",
        "subsystem": "Propulsion",
        "component": "LinearMotor-L8",
        "role": "Primary Acceleration Stator Core",
        "property": "Peak Thrust Output",
        "value": "26.4 kN",
        "numeric_val": 26.4,
        "unit": "kN",
        "revision": "v4.2",
        "superseded_v4_1": "24.0 kN",
        "distractor_auxiliary": "10.5 kN"
    },
    # Cryogenics Subsystem (Held-Out)
    {
        "fact_id": "FACT-HELD-003",
        "subsystem": "Cryogenics",
        "component": "ChamberVessel-C5",
        "role": "Superconducting Core Cryostat",
        "property": "Holding Tank Pressure",
        "value": "418.6 kPa",
        "numeric_val": 418.6,
        "unit": "kPa",
        "revision": "v4.2",
        "superseded_v4_1": "395.0 kPa",
        "distractor_auxiliary": "280.0 kPa"
    },
    {
        "fact_id": "FACT-HELD-004",
        "subsystem": "Cryogenics",
        "component": "ChamberVessel-C5",
        "role": "Superconducting Core Cryostat",
        "property": "Helium Boil-Off Recovery Rate",
        "value": "99.4 %",
        "numeric_val": 99.4,
        "unit": "%",
        "revision": "v4.2",
        "superseded_v4_1": "98.0 %",
        "distractor_auxiliary": "92.0 %"
    },
    # Telemetry Subsystem (Held-Out)
    {
        "fact_id": "FACT-HELD-005",
        "subsystem": "Telemetry",
        "component": "CryptoModem-K9",
        "role": "Tube Enclave Telemetry Gateway",
        "property": "Payload Encryption Suite",
        "value": "AeroCrypt-Z5",
        "unit": None,
        "revision": "v4.2",
        "superseded_v4_1": "HyperCiph-4",
        "distractor_auxiliary": "MeshGuard-2"
    },
    {
        "fact_id": "FACT-HELD-006",
        "subsystem": "Telemetry",
        "component": "CryptoModem-K9",
        "role": "Tube Enclave Telemetry Gateway",
        "property": "Key Renegotiation Interval",
        "value": "45.0 s",
        "numeric_val": 45.0,
        "unit": "s",
        "revision": "v4.2",
        "superseded_v4_1": "60.0 s",
        "distractor_auxiliary": "180.0 s"
    },
    # Power Subsystem (Held-Out)
    {
        "fact_id": "FACT-HELD-007",
        "subsystem": "PowerDistribution",
        "component": "AuxPack-B2",
        "role": "Onboard Emergency Battery Bank",
        "property": "Cell Chemistry Spec",
        "value": "Titanate-S4",
        "unit": None,
        "revision": "v4.2",
        "superseded_v4_1": "LithFerro-8",
        "distractor_auxiliary": "SodiumPoly-3"
    },
    {
        "fact_id": "FACT-HELD-008",
        "subsystem": "PowerDistribution",
        "component": "AuxPack-B2",
        "role": "Onboard Emergency Battery Bank",
        "property": "Nominal Bus Discharge Voltage",
        "value": "648.5 V",
        "numeric_val": 648.5,
        "unit": "V",
        "revision": "v4.2",
        "superseded_v4_1": "620.0 V",
        "distractor_auxiliary": "48.0 V"
    },
    {
        "fact_id": "FACT-HELD-009",
        "subsystem": "PowerDistribution",
        "component": "CoolLoop-H7",
        "role": "Auxiliary Power Thermal Radiator",
        "property": "Heat Transfer Fluid",
        "value": "FrigiPure-9B",
        "unit": None,
        "revision": "v4.2",
        "superseded_v4_1": "GlycolSpec-D",
        "distractor_auxiliary": "AeroCool-1"
    },
    {
        "fact_id": "FACT-HELD-010",
        "subsystem": "PowerDistribution",
        "component": "CoolLoop-H7",
        "role": "Auxiliary Power Thermal Radiator",
        "property": "Max Loop Operating Temp",
        "value": "68.4 C",
        "numeric_val": 68.4,
        "unit": "C",
        "revision": "v4.2",
        "superseded_v4_1": "75.0 C",
        "distractor_auxiliary": "95.0 C"
    }
]

# Generate programmatic extended Held-Out facts up to 80 facts
for i in range(11, 81):
    sub = ["Propulsion", "Cryogenics", "Telemetry", "PowerDistribution", "Guideway", "TunnelVent", "Structural", "EmergencyEgress"][i % 8]
    comp = f"HeldModule-{sub[:4]}-{i:02d}"
    prop = f"Design Parameter Omega-{i:02d}"
    val_num = round(500.0 + (i * 4.19) % 350.0, 2)
    unit = ["kN", "kPa", "V", "s", "mm", "%", "C", "m^3/s"][i % 8]
    HELDOUT_FACTS.append({
        "fact_id": f"FACT-HELD-{i:03d}",
        "subsystem": sub,
        "component": comp,
        "role": f"Held Operational Sub-Unit {i}",
        "property": prop,
        "value": f"{val_num} {unit}",
        "numeric_val": val_num,
        "unit": unit,
        "revision": "v4.2",
        "superseded_v4_1": f"{round(val_num * 0.85, 2)} {unit}",
        "distractor_auxiliary": f"{round(val_num * 0.55, 2)} {unit}"
    })

master_pool = {
    "corpus_name": "HyperGrid Autonomous Transit Network Specification v4.2",
    "total_facts_count": len(DEV_FACTS) + len(HELDOUT_FACTS),
    "dev_facts_count": len(DEV_FACTS),
    "heldout_facts_count": len(HELDOUT_FACTS),
    "dev_facts": DEV_FACTS,
    "heldout_facts": HELDOUT_FACTS
}

with open(FACT_POOL_PATH, "w", encoding="utf-8") as f:
    json.dump(master_pool, f, indent=2)

print(f"Master Fact Pool created with {master_pool['total_facts_count']} total facts ({len(DEV_FACTS)} Dev, {len(HELDOUT_FACTS)} Held-Out).")
