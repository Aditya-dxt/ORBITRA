# SatQuery-to-ARES Candidate Record Interface Specification

**Schema Version:** `v1.0.0`  
**Status:** Officially Signed Off & Promoted by SatQuery and ARES Leads  
**Effective Date:** 2026-11-18  

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
  "schema_version": "v1.0.0",
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

---

## 6. Image Pair Resolution & STRONGER_MODEL Re-Inference Contract

When ARES selects `STRONGER_MODEL` for a candidate, the system executes high-capacity specialist vision inference on the candidate's exact spatial crop. The architectural boundary operates as follows:

### 1. Source Imagery Resolution (`image_pair_id`)
- Every candidate record supplies a non-empty `image_pair_id` (e.g., `pair_levir_test_042`, `pair_sentinel2_kanpur_bhauti`).
- The `ImagePairResolver` (`SatQuery/satquery/data/image_resolver.py`) resolves this identifier to the concrete bi-temporal image pair $(I_{\text{pre}}, I_{\text{post}})$:
  - **Real Indian Sentinel-2 Scenes:** Resolves to cached Level-2A multi-spectral rasters (e.g., `kanpur_bhauti_{pre,post}_real.png`, 512x512 RGB).
  - **Benchmark LEVIR-CD Scenes:** Resolves to cached benchmark PNGs (`scene_levir_042_{pre,post}.png`, 256x256 RGB) or deterministically synthesizes the identical scene from seed (e.g., seed 42) when running on clean checkouts where local data caches are not checked into Git.
  - **Provenance Tagging:** Each resolved pair explicitly declares its source mode (`DISK_FILE_REAL`, `DISK_FILE_BENCHMARK`, or `DETERMINISTIC_SYNTHETIC`).

### 2. Patch Extraction & Vision Re-Inference
- The bounding box `region.bbox_pixels = [xmin, ymin, xmax, ymax]` defines the candidate crop:
  $$C_{\text{pre}} = I_{\text{pre}}[y_{\min}:y_{\max}, x_{\min}:x_{\max}], \quad C_{\text{post}} = I_{\text{post}}[y_{\min}:y_{\max}, x_{\min}:x_{\max}]$$
- The specialist detector (PyTorch Siamese network or calibrated fallback) processes $(C_{\text{pre}}, C_{\text{post}})$, computing:
  - Continuous patch change heatmap and mean change score $\bar{s}$.
  - Calibrated probability $p_{\text{crop}} = \text{Calibrator}(\bar{s}) \in [0.0, 1.0]$.
  - Measured post-inference uncertainty $u_{\text{crop}} = -\left[ p_{\text{crop}} \log_2(p_{\text{crop}}) + (1 - p_{\text{crop}}) \log_2(1 - p_{\text{crop}}) \right]$.

### 3. State Mutation vs. ARES Simulation Boundary
- **Live Closed-Loop Execution:** The candidate state object in memory is mutated to reflect the empirical measurement:
  - $p_{\text{candidate}} \leftarrow p_{\text{crop}}$
  - $u_{\text{candidate}} \leftarrow u_{\text{crop}}$
  - Measured uncertainty reduction: $\Delta u_{\text{measured}} = u_{\text{prior}} - u_{\text{crop}}$.
  - Appends an `EvidenceRecord` to `c_obj.evidence_history` tagged `[MEASURED]`.
- **ARES Offline Benchmark Baseline:** For standalone policy evaluation and reproducible benchmarking where vision weights or rasters are not loaded, ARES's `ActionOutcomeSimulator` records its theoretical model assumption:
  - $u_{\text{simulated}} = \max(0.10, u_{\text{prior}} \times 0.60)$ (assumed 40% reduction, tagged `[SIMULATED]`).
- **Energy Accounting:** Regardless of the measured $\Delta u$, ARES bills exactly $1,450.0\text{ J}$ ($1,200\text{ J}$ compute + $250\text{ J}$ offload comms) with $0.0\text{ J}$ flight energy, and enforces the post-action return reserve feasibility back to home base.

