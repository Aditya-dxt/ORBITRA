# SatQuery-to-ARES Candidate Record Interface Specification

**Schema Version:** `v1.0.0-provisional`  
**Status:** Agreed between SatQuery and ARES Module Leads  
**Effective Date:** 2026-11-16  

---

## 1. Overview & Architectural Boundaries

SatQuery generates candidate change records from bi-temporal satellite imagery. ARES ingests these records, evaluates mission importance and energy feasibility, and selects actions under an energy budget and safe-return reserve.

### Field Ownership

- **SatQuery Supplies:** `schema_version`, `candidate_id`, `image_pair_id`, `timestamp`, `predicted_change`, `confidence`, `uncertainty`, `region`.
- **ARES Enriches:** `importance_weight`, `candidate_status`, `evidence_history`, `assigned_action`, `estimated_energy_joules`, `reserve_feasible`.
- **Validation Rule:** Strict rejection of unknown/extra fields (`extra='forbid'`). SatQuery exports do not include ARES fields.

---

## 2. Georeferencing & Coordinate Assumptions

To support both planar drone kinematics (in ARES) and geographic GIS mapping:

1. **Tile Anchor Assumption:** $(X_{\text{tile}}, Y_{\text{tile}})$ represents the local metric coordinate of image top-left pixel $(0, 0)$.
2. **Image Axes Alignment:** Pixel column index $u$ increases Eastward ($+x$), and pixel row index $v$ corresponds to Northing ($+y$) via:
   $$x_{\text{meters}} = X_{\text{tile}} + (u_{\text{centroid}} \times \text{GSD}_x)$$
   $$y_{\text{meters}} = Y_{\text{tile}} + (v_{\text{centroid}} \times \text{GSD}_y)$$
3. **Ground Sampling Distance (GSD):** $0.5\text{ m / pixel}$ along both axes ($\text{GSD}_x = \text{GSD}_y = 0.5$).
4. **Geodetic Conversion (Local Approximation):** Local ENU meter coordinates are projected to WGS-84 decimal degrees using the reference ellipsoid radii of curvature at mission home base $(39.900000^\circ\text{N}, 116.400000^\circ\text{E}, 0.0\text{ m})$:
   $$\text{center\_lat} = \text{lat}_0 + \frac{y_{\text{meters}}}{111,034\text{ m/deg}}$$
   $$\text{center\_lon} = \text{lon}_0 + \frac{x_{\text{meters}}}{85,396\text{ m/deg}}$$
   *Note:* Labeled explicitly as a local flat-Earth/ellipsoidal approximation for tactical UAV ranges ($< 15\text{ km}$).

---

## 3. Confidence Calibration & Uncertainty Semantics

1. **Confidence ($p_i \in [0.0, 1.0]$):**
   Calibrated probability that candidate $i$ represents a genuine structural change, fitted via Platt scaling (logistic sigmoid) on the validation split. Evaluated on the held-out test split using Expected Calibration Error (ECE) and Brier Score.
2. **Uncertainty ($u_i \in [0.0, 1.0]$):**
   Normalized binary Shannon entropy of the calibrated probability:
   $$u_i = -\left[ p_i \log_2(p_i) + (1 - p_i) \log_2(1 - p_i) \right]$$
   - $u_i = 1.0$ when $p_i = 0.5$ (maximal detector ambiguity).
   - $u_i \to 0.0$ when $p_i \to 1.0$ or $p_i \to 0.0$ (high detector decisiveness).

---

## 4. Production JSON Record Example

```json
{
  "schema_version": "v1.0.0-provisional",
  "candidate_id": "cand_sq_levir_042_001",
  "image_pair_id": "pair_levir_test_042",
  "timestamp": "2026-11-16T10:30:00Z",
  "predicted_change": "urban_building_construction",
  "confidence": 0.842,
  "uncertainty": 0.627,
  "region": {
    "crs": "local_meter_grid",
    "local_grid": {
      "x_meters": 245.5,
      "y_meters": 318.0,
      "z_meters": 50.0
    },
    "coordinates": {
      "center_lat": 39.902864,
      "center_lon": 116.402875,
      "altitude_m": 50.0
    },
    "bbox_pixels": [128, 160, 212, 244]
  }
}
```

---

## 5. Strict Fail-Fast Validation Checklist

- `schema_version`: Must start with `"v1."`.
- `candidate_id` & `image_pair_id`: Non-empty strings.
- `timestamp`: Timezone-aware ISO-8601 UTC string (must include timezone indicator, e.g. `'Z'` or `'+00:00'`).
- `confidence` & `uncertainty`: Strictly bounded in $[0.0, 1.0]$.
- `region.local_grid`: Strictly required; missing coordinates fail validation.
- `region.bbox_pixels`: Exactly 4 integers $[x_{\min}, y_{\min}, x_{\max}, y_{\max}]$ with $x_{\min} \le x_{\max}$ and $y_{\min} \le y_{\max}$.
- `extra='forbid'`: Reject any unrecognized fields.
