# 🛰️ SatQuery

**Owner:** Computer Vision & Image Processing Lead (Aditya)  
**System:** ORBITRA  
**Status:** Milestone 1 & 2 Complete (Agreed Schema v1.0.0-provisional, Vision Pipeline, Calibration, and ARES Export)  

SatQuery is responsible for satellite image processing and computer vision within ORBITRA. It turns bi-temporal satellite image inputs into structured, georeferenced, versioned candidate change records with calibrated confidence and quantified uncertainty for consumption by the **ARES** decision engine.

---

## 🏗️ Architecture & Modules

```
SatQuery/
├── README.md                          # Module documentation & running implementation log
├── docs/
│   ├── DATASET_AUDIT.md               # Gate 1 dataset audit (MAHCD vs LEVIR-CD/OSCD), licenses, limits
│   └── INTERFACE_SPECIFICATION.md     # Agreed provisional v1.0.0 schema specification & math
├── satquery/
│   ├── schemas/
│   │   └── candidate_record.py        # Strict Pydantic model (extra='forbid', UTC ISO-8601, local_grid required)
│   ├── data/
│   │   ├── dataset.py                 # LEVIR-CD & OSCD loader, pair validation, spatial alignment check
│   │   └── synthetic_sample_data.py   # Self-contained reproducible benchmark scenes
│   ├── models/
│   │   ├── classifier.py              # Semantic change classifier (building, road, vegetation, natural)
│   │   └── siamese_unet.py            # Deep learning Siamese U-Net with Spatial-Temporal Attention
│   ├── vision/
│   │   ├── detector.py                # Multi-scale differential change detector & continuous heatmap
│   │   ├── candidate_generator.py     # Contour extraction, min-area filter, pixel bbox & georeferencing
│   │   ├── georeferencing.py          # Pixel <-> Local Grid (ENU) <-> Geodetic (WGS-84) transforms
│   │   └── calibration.py             # Platt/Temperature scaling, ECE, Brier score, Shannon entropy
│   ├── evaluation/
│   │   └── metrics.py                 # Precision, Recall, F1, IoU, candidate region matching
│   └── pipeline.py                    # Master pipeline orchestrator & JSON exporter
├── tests/                             # Automated unit & integration tests
│   ├── test_schemas.py                # Strict validation, UTC timestamps, bounds, extra fields
│   ├── test_georeferencing.py         # Coordinate reconciliation, GSD, tile anchor, inverse math
│   ├── test_calibration.py            # Fit on val, evaluate on held-out test (ECE, Brier score)
│   ├── test_detector.py               # Detector outputs, metrics, no-change scene handling
│   └── test_pipeline.py               # End-to-end pipeline & cross-module ARES ingestion
└── exports/
    └── sample_candidates.json         # Documented, versioned sample candidate records for ARES
```

---

## 🎯 Key Principles & Implementations

1. **Gate 1 Dataset Audit & Benchmark Selection:**
   - Evaluated **MAHCD** (Wang et al., 2025) and executed the synopsis Gate 1 stop/pivot recommendation due to third-party file hosting, lack of standard open-source license, and absence of multi-epoch repeated UAV verification data.
   - Anchored vision baseline on the open, standardized **LEVIR-CD** benchmark ($0.5\text{ m/pixel}$ bitemporal satellite imagery, building changes, train/val/test splits) and **OSCD** (Sentinel-2 multispectral pairs).
   - **Simulation Boundary:** Real satellite imagery drives change detection and vision evaluation; all UAV flight kinematics, sensor recapture, and reviewer actions are treated as **simulation** (`SIMULATED` / `ASSUMED`) within ARES.

2. **Georeferencing & Spatial Mathematics (`satquery/vision/georeferencing.py`):**
   - **Tile Anchor Assumption:** Image pixel $(0, 0)$ is located at local metric coordinate $(X_{\text{tile}}, Y_{\text{tile}})$ relative to mission home base $[0, 0, 0]$ ($39.900000^\circ\text{N}, 116.400000^\circ\text{E}, 0.0\text{ m}$).
   - **Axes Alignment:** Pixel column index $u$ aligns with Eastward $+x$ meters; pixel row index $v$ aligns with Northing $+y$ meters.
   - **Ground Sampling Distance (GSD):** $0.5\text{ m/pixel}$ on both axes ($\text{GSD}_x = \text{GSD}_y = 0.5$).
   - **Geodetic Conversion:** Local ENU metric offsets are projected to WGS-84 decimal degrees using meridional and parallel radii of curvature at mission latitude, labeled explicitly as a local approximation for tactical UAV ranges ($< 15\text{ km}$).
   - **Reconciled Sample Coordinates:**
     - Bounding Box: $[128, 160, 212, 244]$
     - Centroid: $u_c = 170\text{ px}, v_c = 202\text{ px}$
     - Local Grid: $x = 245.5\text{ m}$ East, $y = 318.0\text{ m}$ North, $z = 50.0\text{ m}$ Altitude AGL
     - Geodetic: $\text{center\_lat} = 39.902864^\circ\text{N}$, $\text{center\_lon} = 116.402875^\circ\text{E}$

3. **Confidence Calibration & Uncertainty Quantification (`satquery/vision/calibration.py`):**
   - **Calibrated Probability ($p_i \in [0.0, 1.0]$):** Calibrated via Platt scaling (logistic regression) fitted strictly on the validation split.
   - **Held-Out Evaluation:** Expected Calibration Error (ECE), Brier Score, and Maximum Calibration Error (MCE) are evaluated strictly on a separate held-out test split, ensuring no data leakage.
   - **Uncertainty ($u_i \in [0.0, 1.0]$):** Quantified as normalized binary Shannon entropy:
     $$u_i = -\left[ p_i \log_2(p_i) + (1 - p_i) \log_2(1 - p_i) \right]$$
     where $u_i = 1.0$ at maximum ambiguity ($p_i = 0.5$) and $u_i \to 0.0$ when the detector is decisive ($p_i \to 0.0$ or $p_i \to 1.0$).

4. **Strict Schema Contract & ARES Ingestion (`satquery/schemas/candidate_record.py`):**
   - Implements agreed `v1.0.0-provisional` schema.
   - Enforces `local_grid` as strictly required (for ARES flight energy calculations).
   - Enforces timezone-aware UTC ISO-8601 timestamps.
   - Rejects unrecognized/extra fields (`extra='forbid'`), maintaining clean field boundaries between SatQuery (vision) and ARES (decision/energy).

---

## 🧪 Benchmark Vision Metrics & Results

Evaluated on synthetic benchmark scenes with known ground-truth change masks:

| Metric | Measured Value | Operational Meaning |
| --- | --- | --- |
| **Precision** | **95.51%** | Proportion of detected change pixels that correspond to real structural changes |
| **Recall** | **45.41%** | Proportion of ground-truth change pixels detected by the baseline detector |
| **F1-Score** | **61.55%** | Harmonic mean of precision and recall |
| **IoU (Jaccard)** | **44.46%** | Intersection over union between predicted mask and ground-truth mask |
| **Held-Out Brier Score** | **0.1842** | Mean squared calibration error on held-out test data (vs 0.2310 uncalibrated) |
| **Held-Out ECE** | **0.0620** | Expected calibration error across 10 probability bins on held-out data |

---

## 🚀 How to Run

### Run SatQuery Unit & Integration Tests
From repository root:
```powershell
python -m unittest discover -s SatQuery/tests -v
```

### Run SatQuery End-to-End Pipeline Demo
```powershell
python -m SatQuery.satquery.pipeline
```
This generates benchmark satellite pairs, runs baseline change detection, extracts connected candidate regions, classifies change types, computes calibrated confidence and uncertainty, georeferences the regions, and exports `SatQuery/exports/sample_candidates.json`.

### Run Real Indian Satellite Mission (Kanpur, Bengaluru, Delhi, Chennai)
```powershell
# Run change verification on real Sentinel-2 imagery over Kanpur / Bhauti (UP) under B3 Joint Policy
python SatQuery/examples/run_india_pipeline.py --zone kanpur_bhauti --policy B3

# Run on Bengaluru Electronic City IT corridor under B1 Uncertainty-First Policy
python SatQuery/examples/run_india_pipeline.py --zone bengaluru_tech --policy B1

# Run on Delhi NCR or Chennai Industrial Corridor
python SatQuery/examples/run_india_pipeline.py --zone delhi_ncr --policy B3
python SatQuery/examples/run_india_pipeline.py --zone chennai_sriperumbudur --policy B1
```
This loads genuine bi-temporal Sentinel-2 optical imagery across Indian coordinates (e.g. 2021 vs 2023 over Kanpur or 2022 vs 2024 over Bengaluru), runs sub-pixel spatial co-registration, detects changes, produces georeferenced candidate change records with real geodetic coordinates, saves a 4-panel visual montage to `SatQuery/exports/visualizations/`, and executes the mission in ARES under the return-reserve guardrail.

### Run Comprehensive Vision Pipeline Evaluation & Failure Analysis
```powershell
python SatQuery/examples/evaluate_vision_pipeline.py
```
This evaluates the pipeline against benchmark scenes with ground truth at region IoU $\tau_{\text{IoU}} = 0.50$, computes precision, recall, F1, IoU, held-out ECE and Brier calibration metrics, categorizes failure modes (shadow displacement, seasonal drying, sub-pixel contrast boundaries), and updates `SatQuery/docs/EVALUATION_REPORT.md` and `SatQuery/exports/vision_evaluation_report.json`.

### Run End-to-End Joint Integration (SatQuery -> ARES)
```powershell
# Run with B3 Joint Policy (default)
python SatQuery/examples/end_to_end_integration.py --policy B3

# Run with B0 Fixed Pass or B1 Uncertainty First
python SatQuery/examples/end_to_end_integration.py --policy B0
python SatQuery/examples/end_to_end_integration.py --policy B1
```
This loads candidate records generated by SatQuery, validates and imports them into ARES `AresCandidateState`, enforces the return reserve guardrail, runs the discrete-event mission simulation under the chosen policy, logs all decisions to the ledger, renders an explainable ASCII dashboard, and saves the audit report to `SatQuery/exports/mission_decision_report.json`.

### Verify ARES Cross-Module Compatibility
```powershell
python -c "import json, sys; sys.path.insert(0, 'ARES'); from ares.schemas.satquery_record import SatQueryCandidateRecord; data = json.load(open('SatQuery/exports/sample_candidates.json')); records = [SatQueryCandidateRecord(**d) for d in data]; print(f'Successfully loaded {len(records)} records in ARES!')"
```

---

## 📋 Running Implementation Log

### Update: 2026-11-17 — Rebase on main (ea759e0) & Python Data Module Tracking Fix
- **Summary:** Rebased on top of `main` commit `ea759e0` (ARES B4 policy). Fixed an issue where root `.gitignore` unanchored `data/` rule inadvertently excluded Python source files in `SatQuery/satquery/data/`. Explicitly tracked `synthetic_sample_data.py`, `india_satellite_data.py`, `dataset.py`, `generate_sample_assets.py`, and `__init__.py`. Re-verified all SatQuery unit tests and end-to-end integration scripts.
- **Changed Files:**
  - `SatQuery/satquery/data/synthetic_sample_data.py` (Benchmark test pair generator)
  - `SatQuery/satquery/data/india_satellite_data.py` (Real Indian Sentinel-2 pipeline)
  - `SatQuery/satquery/data/dataset.py` (Dataset loader abstractions)
  - `SatQuery/satquery/data/generate_sample_assets.py` (Sample asset & visual montage generator)
  - `SatQuery/satquery/data/__init__.py` (Package init)
  - `SatQuery/README.md` (Updated run instructions, test logs, and limitations)
- **Data Reality & Provenance Demarcation:**
  - *Real Image-Derived Detections:* Genuine ESA Sentinel-2 Level-2A surface reflectance rasters acquired over Indian geographic corridors (Kanpur/Bhauti UP, Bengaluru Electronic City, Delhi NCR, and Chennai).
  - *Synthetic Benchmark Data:* Used strictly in `synthetic_sample_data.py` for reproducible offline unit testing and held-out calibration experiments.
  - *Simulated Drone Actions:* All UAV transit flight kinematics, sensor recapture outcomes, battery depletion, and human review actions are explicitly treated as software simulations (`SIMULATED` / `ASSUMED`). No physical drone flights are claimed.
- **Limitations:**
  - Sentinel-2 GSD is 10 m/pixel; subtle sub-pixel ground changes (<10 m) can result in false negatives.
  - Seasonal vegetation phenology (dry grass vs lush green) may trigger false-positive candidate regions, appropriately mitigated by ARES priority weighting.
- **Checks Performed:**
  - `python -m unittest discover -s SatQuery/tests -v` (23/23 passed in 0.534s)
  - `python SatQuery/examples/end_to_end_integration.py --policy B3` (Success: All 3 records strictly validated by ARES, Safe return True)
  - `python SatQuery/examples/run_india_pipeline.py --zone kanpur_bhauti --policy B3` (Success: 7 real candidates detected, Safe return True)
  - `python -m unittest discover -s ARES/tests -t ARES -v` (70/70 passed)
- **Action Needed from ARES:**
  - Pull latest `main` commit and confirm end-to-end integration runs on your checkout before promoting interface schema from `v1.0.0-provisional` to finalized `v1.0.0`.
