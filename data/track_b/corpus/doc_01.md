# HyperGrid Technical Specification v4.2 — Chapter 1
**Subsystem Focus:** Propulsion Dynamics and Inverter Topology
**Baseline Revision:** v4.2 (Supercedes Engineering Standard v4.1)

## 1. System Architecture Overview
This chapter outlines operational parameters, physical integration limits, and diagnostic margins for propulsion dynamics and inverter topology within the HyperGrid automated guideway transit network.

## 2. Active Engineering Parameters (Specification v4.2)
The following parameter values are mandatory for all production vehicles and wayside stations deployed under baseline v4.2:

### Inverter-ZX9 — Switching Frequency
- **Designation & Subsystem:** `Inverter-ZX9` (Primary Traction Power Inverter, Subsystem: Propulsion)
- **Active Specification (v4.2):** **`731.4 kHz`**
- **Superseded Standard (v4.1):** `680.0 kHz` (Do not use for v4.2 certification)
- **Auxiliary / Secondary Channel:** `512.0 kHz (Auxiliary Inverter-AX2)`
- **Engineering Context:** Operational compliance of Inverter-ZX9 requires maintaining switching frequency within strict system limits under active load.

### Inverter-ZX9 — Continuous Power Rating
- **Designation & Subsystem:** `Inverter-ZX9` (Primary Traction Power Inverter, Subsystem: Propulsion)
- **Active Specification (v4.2):** **`1840 kW`**
- **Superseded Standard (v4.1):** `1650 kW` (Do not use for v4.2 certification)
- **Auxiliary / Secondary Channel:** `420 kW`
- **Engineering Context:** Operational compliance of Inverter-ZX9 requires maintaining continuous power rating within strict system limits under active load.

### StatorPack-P4 — Pole Pitch Distance
- **Designation & Subsystem:** `StatorPack-P4` (Linear Induction Stator Module, Subsystem: Propulsion)
- **Active Specification (v4.2):** **`142.5 mm`**
- **Superseded Standard (v4.1):** `138.0 mm` (Do not use for v4.2 certification)
- **Auxiliary / Secondary Channel:** `95.0 mm`
- **Engineering Context:** Operational compliance of StatorPack-P4 requires maintaining pole pitch distance within strict system limits under active load.

### StatorPack-P4 — Core Lamination Alloy
- **Designation & Subsystem:** `StatorPack-P4` (Linear Induction Stator Module, Subsystem: Propulsion)
- **Active Specification (v4.2):** **`FerrAlloy-Q14`**
- **Superseded Standard (v4.1):** `SiliconIron-S2` (Do not use for v4.2 certification)
- **Auxiliary / Secondary Channel:** `FerrAlloy-Q08`
- **Engineering Context:** Operational compliance of StatorPack-P4 requires maintaining core lamination alloy within strict system limits under active load.

## 3. Quality Assurance & Inspection Procedures
All field diagnostic probes must execute automated loop checks prior to dispatching vehicles into high-speed transit blocks.
Discrepancies exceeding allowable thresholds must trigger automated line stops.
