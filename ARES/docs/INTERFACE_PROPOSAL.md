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

*Note:* For early synthetic simulation milestones, `local_grid` (Euclidean distance in meters from home base $[0, 0, 0]$ with axes $x=\text{East}$, $y=\text{North}$, $z=\text{Altitude}$) is utilized for kinematics and transit energy calculations. Geodetic transformations will be supported in Phase 4.

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

## 5. SatQuery Owner Review & Agreement Checklist

Before finalizing this schema for end-to-end integration, the SatQuery and ARES module leads must confirm agreement on the following 7 technical items:

- [ ] **1. Field Names & Types:** Confirm exact casing and types (`candidate_id: str`, `image_pair_id: str`, `confidence: float`, `uncertainty: float`, `region: dict`).
- [ ] **2. Confidence Calibration:** Confirm whether `confidence` represents a calibrated probability $P(\text{real change}) \in [0.0, 1.0]$ (e.g. from temperature scaling or isotonic regression) or a raw neural network softmax score.
- [ ] **3. Uncertainty Semantics:** Confirm mathematical meaning of `uncertainty` $\in [0.0, 1.0]$ (e.g., normalized predictive entropy, MC-dropout variance, or ensemble spread, where $0.0 = \text{completely certain}$ and $1.0 = \text{maximum entropy/ambiguity}$).
- [ ] **4. Coordinate Reference, Axis Order & Units:** Confirm local coordinate axis convention ($x=\text{East}$, $y=\text{North}$, $z=\text{Altitude}$ in meters), geodetic axis order (`[latitude, longitude]` vs `[longitude, latitude]`), and pixel bounding box format (`[xmin, ymin, xmax, ymax]`).
- [ ] **5. Image & Pair Identifiers:** Confirm standard string naming convention for `image_pair_id` (e.g., `pair_<site_id>_<date1>_<date2>`).
- [ ] **6. Schema Versioning:** Confirm SemVer convention (`v1.0.0-provisional` transitioning to `v1.0.0` upon mutual agreement) and whether backward-compatible minor bumps are supported without code breakage.
- [ ] **7. Missing-Value Behavior & Validation Errors:** Confirm strict fail-fast validation behavior (rejecting any candidate missing required coordinates or with out-of-bound confidence/uncertainty) versus providing fallback defaults.
