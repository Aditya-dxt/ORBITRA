# SatQuery-to-ARES Candidate Record Interface Specification

**Version:** `v1.0.0`  
**Status:** Promoted to v1.0.0 — Signed off by SatQuery and ARES Leads following joint end-to-end verification  
**Authors:** ARES Module Lead & SatQuery Module Lead

> [!NOTE]
> This schema is **promoted to v1.0.0**. Both module leads have completed joint
> end-to-end integration and verification on real Sentinel-2 and benchmark datasets,
> confirming schema compatibility, energy kinematics, and reserve safety.

---

## 1. Overview & Purpose

This document specifies the handoff interface between **SatQuery** (the vision/change-detection engine) and **ARES** (the energy-aware decision engine).

Architectural ownership rules:
1. SatQuery produces candidate change records with detection metadata, calibrated confidence, and normalized uncertainty.
2. ARES ingests SatQuery records, validates schema compliance, and decorates them with mission importance, lifecycle state, and energy decisions.
3. Neither module mutates fields owned by the other.
4. The schema version is `v1.0.0`.

---

## 2. Field Ownership & Agreed Semantics

| Field | Type | Owner | Description | Agreed Semantics |
|-------|------|-------|-------------|-----------------|
| `schema_version` | `str` | Shared | SemVer interface version | `"v1.0.0"` |
| `candidate_id` | `str` | SatQuery | Unique candidate detection ID | Non-empty string |
| `image_pair_id` | `str` | SatQuery | Identifier of the bi-temporal image pair | Non-empty string |
| `timestamp` | `str` | SatQuery | Detection timestamp | ISO-8601 UTC with explicit `Z` or `+00:00` designator |
| `predicted_change` | `str` | SatQuery | Semantic change category from vision model | Non-empty string |
| `confidence` | `float` ∈ [0,1] | SatQuery | Calibrated P(real change) | Temperature scaling or Platt scaling applied by SatQuery; ARES does not recompute |
| `uncertainty` | `float` ∈ [0,1] | SatQuery | Normalized binary Shannon entropy of confidence | See §3 |
| `region` | `object` | SatQuery | Spatial geometry with required local_grid | See §4 |
| `importance_weight` | `float` {1,2,4} | **ARES** | Operational importance | ARES-owned; must NOT appear in SatQuery records |
| `candidate_status` | `str` | **ARES** | Lifecycle state | ARES-owned |
| `assigned_action` | `str` | **ARES** | Action selected by policy | ARES-owned |
| `reserve_feasible` | `bool` | **ARES** | Return-reserve gate result | ARES-owned |
| `evidence_history` | `list` | **ARES** | Audit trail of inspections | ARES-owned |

> [!NOTE]
> Confidence calibration (temperature scaling / Platt scaling) is SatQuery's
> responsibility. ARES treats `confidence` as a calibrated probability but
> does **not** verify or recalibrate it.

---

## 3. Uncertainty Semantics & Hard Validation Rule (Agreed)

`uncertainty` is the **normalized binary Shannon entropy** of `confidence`:

$$u = -\bigl[ p \cdot \log_2 p + (1-p) \cdot \log_2(1-p) \bigr]$$

where $p$ = `confidence`.

Boundary values:
- $u = 1.0$ when $p = 0.5$ (maximum ambiguity — equal probability of change/no-change)
- $u \to 0$ when $p \to 0$ or $p \to 1$ (high certainty in either direction)

ARES enforces this as a **hard validation check** (`SHANNON_ENTROPY_TOLERANCE = 0.15`). If $|u - h(p)| > 0.15$, schema validation raises a hard `ValidationError`, rejecting the candidate record. This prevents uncalibrated, corrupted, or inverted values from propagating into ARES energy allocation and decision policies.

---

## 4. Spatial Geometry Specification (`region`)

`local_grid` is **REQUIRED** because all ARES energy calculations (transit energy, return reserve) depend on Euclidean distances in meters from home base.

```json
{
  "crs": "local_meter_grid",
  "local_grid": {
    "x_meters": 245.5,
    "y_meters": 318.0,
    "z_meters": 50.0
  },
  "coordinates": {
    "center_lat": 39.902857,
    "center_lon": 116.402875,
    "altitude_m": 50.0
  },
  "bbox_pixels": [128, 160, 212, 244]
}
```

**Agreed axis convention:**
- `local_grid`: `x` = East (m), `y` = North (m), `z` = Altitude AGL (m) — all from mission home `[0, 0, 0]`
- `coordinates`: WGS84 geodetic, latitude first (ISO 6709)
- `bbox_pixels`: `[xmin, ymin, xmax, ymax]` in image pixel space; xmin ≤ xmax, ymin ≤ ymax enforced

**Agreed reference point:**  
Mission home `[0, 0, 0]` corresponds to WGS84 `(39.900000° N, 116.400000° E, 0 m)`.

**Unknown extra fields** in `region` are **rejected** (`extra='forbid'`) to prevent silent schema drift.

### 4.1 Coordinate Conversion Example (Illustrative)

This example documents the agreed illustrative convention, **not** a general image georeferencing method. SatQuery is responsible for the actual pixel-to-world transform.

**Inputs:**
- Tile anchor (pixel `(0,0)` in local coords): `(160.5 m East, 217.0 m North)`
- GSD: `0.5 m/pixel` on both axes; image x aligns East, image y aligns North
- Bounding box: `[128, 160, 212, 244]`
- Centroid pixel: `(u,v) = ((128+212)/2, (160+244)/2) = (170, 202)`

**Local centroid:**
$$x = 160.5 + 170 \times 0.5 = 245.5\ \text{m East}$$
$$y = 217.0 + 202 \times 0.5 = 318.0\ \text{m North}$$
$$z = 50.0\ \text{m AGL}$$

**Geodetic centroid (local flat-earth approximation):**
$$\Delta\text{lat} \approx \frac{318.0}{111{,}320} \approx 0.002857° \quad\Rightarrow\quad \text{lat} = 39.900000° + 0.002857° = 39.902857°\ \text{N}$$
$$\Delta\text{lon} \approx \frac{245.5}{111{,}320 \times \cos(39.9°)} \approx 0.002875° \quad\Rightarrow\quad \text{lon} = 116.400000° + 0.002875° = 116.402875°\ \text{E}$$

*(Note on geodetic models: using the stated spherical flat-earth formula with nominal $111{,}320\text{ m/deg}$ yields $39.902857°\text{ N}$. An ellipsoidal model using WGS-84 meridional radius of curvature $M(\phi) \approx 111{,}034\text{ m/deg}$ at $39.9°\text{ N}$ yields $318.0 / 111{,}034 \approx 0.002864° \Rightarrow 39.902864°\text{ N}$. The documented sample uses the stated nominal formula $\Delta\text{lat} = y / 111{,}320 \Rightarrow 39.902857°\text{ N}$ to remain strictly consistent with the stated equation.)*

> [!NOTE]
> This flat-earth approximation is documented for ARES reference only.
> It is **not** a general georeferencing method; SatQuery must supply the
> authoritative `coordinates` field using its own calibrated pipeline.
> The approximation is valid within tens of kilometres of the reference point.

---

## 5. Agreed Sample Record

```json
{
  "schema_version": "v1.0.0",
  "candidate_id": "cand_sq_20261117_001",
  "image_pair_id": "pair_beijing_nov2026_01",
  "timestamp": "2026-11-17T06:00:00Z",
  "predicted_change": "built_up_increase",
  "confidence": 0.70,
  "uncertainty": 0.88,
  "region": {
    "crs": "local_meter_grid",
    "local_grid": {
      "x_meters": 245.5,
      "y_meters": 318.0,
      "z_meters": 50.0
    },
    "coordinates": {
      "center_lat": 39.902857,
      "center_lon": 116.402875,
      "altitude_m": 50.0
    },
    "bbox_pixels": [128, 160, 212, 244]
  }
}
```

**Uncertainty check:** `h(0.70) = -(0.70·log₂(0.70) + 0.30·log₂(0.30)) ≈ 0.881`.
Reported `uncertainty=0.88`; difference 0.001 — within the hard tolerance of ±0.15. ✓

---

## 6. Schema Validation Rules (ARES-Enforced)

| Rule | Enforcement |
|------|------------|
| `schema_version` must start with `v1.` | Hard reject |
| `timestamp` must be a valid ISO-8601 UTC datetime with explicit `Z` or `+00:00` | Hard reject (parses as real ISO-8601 datetime; rejects malformed strings) |
| `local_grid` is required inside `region` | Hard reject |
| `confidence` ∈ [0, 1] | Hard reject |
| `uncertainty` ∈ [0, 1] | Hard reject |
| `bbox_pixels` ordering: xmin ≤ xmax, ymin ≤ ymax | Hard reject |
| Unknown extra fields in record or sub-objects | Hard reject (`extra='forbid'`) |
| `\|uncertainty - h(confidence)\|` > `SHANNON_ENTROPY_TOLERANCE` (0.15) | Hard reject (`ValidationError`): enforces agreed Shannon entropy within ±0.15 tolerance |
| ARES-owned fields (`importance_weight`, `candidate_status`, etc.) | Hard reject if present in SatQuery record |
| ARES-owned fields (`importance_weight`, `candidate_status`, etc.) | Hard reject if present in SatQuery record |

---

## 7. Remaining Provisional Items

The following items are documented assumptions, not yet validated by joint testing:

| Item | Current Status |
|------|---------------|
| Confidence calibration method | SatQuery responsibility; ARES assumes calibrated |
| Shannon entropy formula applied by SatQuery | Agreed by interface resolution 2026-11-17; not yet jointly verified in live integration |
| Local grid coordinate pixel-to-world transform | Illustrative example in §4.1; SatQuery owns the actual transform |
| WGS84 geodetic axis order in `coordinates` | Agreed latitude-first (ISO 6709); not yet verified in live records |
| `image_pair_id` naming convention | Not yet formally agreed (e.g., `pair_<site>_<date1>_<date2>`) |
| Backward-compatible minor schema bumps | Not yet formally agreed |
| Missing-value fallback vs. strict validation | Agreed strict fail-fast for `local_grid`, timestamp, confidence, uncertainty |

**Schema version transitions:**
- `v1.0.0-provisional` → `v1.0.0`: Completed and signed off following joint verification on 2026-11-18.

---

## 8. Historical Checklist (Resolved Items)

| # | Item | Resolution |
|---|------|-----------|
| 1 | Field names & types | Agreed: see §2 |
| 2 | Confidence calibration | Agreed: temperature/Platt scaling by SatQuery |
| 3 | Uncertainty semantics | Agreed: normalized binary Shannon entropy (§3) |
| 4 | Coordinate reference, axis order, units | Agreed: x=East, y=North, z=AGL (m); lat-first WGS84; bbox [xmin,ymin,xmax,ymax] |
| 5 | Image & pair identifiers | Resolved via ImagePairResolver (§2) |
| 6 | Schema versioning | Promoted to `v1.0.0` upon mutual sign-off |
| 7 | Missing-value & validation | Agreed: strict fail-fast; `local_grid` required; UTC timestamps required |
