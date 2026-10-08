# HyperGrid Technical Specification v4.2 — Chapter 2
**Subsystem Focus:** Linear Induction Stator Core Engineering
**Baseline Revision:** v4.2 (Supercedes Engineering Standard v4.1)

## 1. System Architecture Overview
This chapter outlines operational parameters, physical integration limits, and diagnostic margins for linear induction stator core engineering within the HyperGrid automated guideway transit network.

## 2. Active Engineering Parameters (Specification v4.2)
The following parameter values are mandatory for all production vehicles and wayside stations deployed under baseline v4.2:

### CryoLoop-Gamma — Cooling Medium
- **Designation & Subsystem:** `CryoLoop-Gamma` (Secondary Magnet Thermal Loop, Subsystem: Cryogenics)
- **Active Specification (v4.2):** **`CryoGel-88X`**
- **Superseded Standard (v4.1):** `FluorN-12` (Do not use for v4.2 certification)
- **Auxiliary / Secondary Channel:** `SolvHydra-404`
- **Engineering Context:** Operational compliance of CryoLoop-Gamma requires maintaining cooling medium within strict system limits under active load.

### CryoLoop-Gamma — Operating Flow Rate
- **Designation & Subsystem:** `CryoLoop-Gamma` (Secondary Magnet Thermal Loop, Subsystem: Cryogenics)
- **Active Specification (v4.2):** **`18.6 L/min`**
- **Superseded Standard (v4.1):** `15.0 L/min` (Do not use for v4.2 certification)
- **Auxiliary / Secondary Channel:** `8.2 L/min`
- **Engineering Context:** Operational compliance of CryoLoop-Gamma requires maintaining operating flow rate within strict system limits under active load.

### VesselDewar-D1 — Burst Disk Relief Pressure
- **Designation & Subsystem:** `VesselDewar-D1` (Liquid Helium Reservoir Tank, Subsystem: Cryogenics)
- **Active Specification (v4.2):** **`864.2 kPa`**
- **Superseded Standard (v4.1):** `820.0 kPa` (Do not use for v4.2 certification)
- **Auxiliary / Secondary Channel:** `620.0 kPa`
- **Engineering Context:** Operational compliance of VesselDewar-D1 requires maintaining burst disk relief pressure within strict system limits under active load.

### VesselDewar-D1 — Insulation Vacuum Target
- **Designation & Subsystem:** `VesselDewar-D1` (Liquid Helium Reservoir Tank, Subsystem: Cryogenics)
- **Active Specification (v4.2):** **`0.0034 Pa`**
- **Superseded Standard (v4.1):** `0.0050 Pa` (Do not use for v4.2 certification)
- **Auxiliary / Secondary Channel:** `0.0120 Pa`
- **Engineering Context:** Operational compliance of VesselDewar-D1 requires maintaining insulation vacuum target within strict system limits under active load.

## 3. Quality Assurance & Inspection Procedures
All field diagnostic probes must execute automated loop checks prior to dispatching vehicles into high-speed transit blocks.
Discrepancies exceeding allowable thresholds must trigger automated line stops.
