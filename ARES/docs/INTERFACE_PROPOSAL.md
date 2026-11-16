# SatQuery-to-ARES Candidate Record Interface Proposal

**Version:** `v1.0.0-provisional`  
**Status:** Provisional — Awaiting Review & Agreement with SatQuery Module Owner  
**Authors:** ARES Module Lead (for joint review with SatQuery Lead)  

---

## 1. Overview & Purpose

This document specifies the handoff interface between **SatQuery** (the vision/change detection engine) and **ARES** (the energy-aware decision engine).

To ensure high architectural modularity:
1. SatQuery produces vision candidates with detection metadata, confidence, and uncertainty.
2. ARES ingests SatQuery candidate records, validates schema compliance, and decorates them with mission importance, state tracking, and energy decisions.
3. Neither module mutates fields owned by the other.

---

## 2. Field Ownership Breakdown

| Field Name | Type | Owner | Description | Example |
| --- | --- | --- | --- | --- |
| `schema_version` | `str` | Shared | SemVer string for interface version. | `"v1.0.0-provisional"` |
| `candidate_id` | `str` | SatQuery | Unique candidate detection identifier. | `"cand_20261116_001"` |
| `image_pair_id` | `str` | SatQuery | Identifier of the bi-temporal image pair. | `"pair_cartosat_risat_042"` |
| `timestamp` | `str` (ISO-8601) | SatQuery | Observation / detection generation timestamp. | `"2026-11-16T09:30:00Z"` |
| `predicted_change` | `str` | SatQuery | Semantic change category classified by vision model. | `"built_up_increase"` |
| `confidence` | `float` ($[0.0, 1.0]$) | SatQuery | Vision model confidence in the detection. | `0.84` |
| `uncertainty` | `float` ($[0.0, 1.0]$) | SatQuery | Quantified detector uncertainty (e.g. entropy/ensemble). | `0.45` |
| `region` | `object` | SatQuery | Spatial bounding box, polygon, and coordinate reference. | *See Section 3* |
| `importance_weight` | `float` ($\{1.0, 2.0, 4.0\}$) | ARES | Operational importance assigned by mission rules. | `2.0` (`ASSUMED`) |
| `candidate_status` | `str` | ARES | Lifecycle state: `PENDING`, `INSPECTED`, `DEFERRED`, `SKIPPED`. | `"PENDING"` |
| `evidence_history` | `list[object]` | ARES | Audit trail of inspections and simulation outcomes. | `[...]` |
| `assigned_action` | `str` | ARES | Action selected by active policy: `RECAPTURE`, `STRONGER_MODEL`, etc. | `"RECAPTURE"` |
| `estimated_energy_joules` | `float` | ARES | Total estimated action energy in Joules. | `14520.0` |
| `reserve_feasible` | `bool` | ARES | Feasibility gate result from post-action return check. | `true` |

---

## 3. Spatial Geometry Specification (`region`)

To support both planar local drone test grids and geographic satellite coordinates, the `region` object supports:
```json
{
  "crs": "local_meter_grid",
  "coordinates": {
    "center_lat": 13.0827,
    "center_lon": 80.2707,
    "altitude_m": 80.0
  },
  "local_grid": {
    "x_meters": 350.0,
    "y_meters": 420.0,
    "z_meters": 80.0
  },
  "bbox_pixels": [120, 340, 210, 430]
}
```

*Note:* For early synthetic simulation milestones, `local_grid` (Euclidean distance in meters from home base $[0, 0, 0]$) is utilized for kinematics and transit energy calculations. Geodetic transformations will be supported in Phase 4.

---

## 4. Provisional JSON Sample Record (SatQuery Output)

```json
{
  "schema_version": "v1.0.0-provisional",
  "candidate_id": "cand_sq_20261116_001",
  "image_pair_id": "pair_cartosat_2s_risat_01",
  "timestamp": "2026-11-16T09:30:00Z",
  "predicted_change": "flooded_region",
  "confidence": 0.78,
  "uncertainty": 0.62,
  "region": {
    "crs": "local_meter_grid",
    "local_grid": {
      "x_meters": 500.0,
      "y_meters": 300.0,
      "z_meters": 60.0
    },
    "bbox_pixels": [245, 110, 310, 185]
  }
}
```

---

## 5. Handoff Contract Checklist for Review

- [ ] Confirm field names, types, and capitalization conventions.
- [ ] Confirm uncertainty range semantics ($0.0 = \text{certain}$, $1.0 = \text{maximally uncertain}$).
- [ ] Confirm coordinate conventions (local Cartesian meter grid for simulation vs. EPSG:4326 for GIS pairs).
- [ ] Confirm error handling when fields are missing or out of bounds (strict validation with rejection vs. fallback defaults).
