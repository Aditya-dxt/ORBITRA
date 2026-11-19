# 🛰️ SatQuery

**Owner:** Computer Vision & Image Processing Lead (Aditya)  
**System:** ORBITRA  
**Status:** Milestone 6 Complete | Interface Promoted to `v1.0.0` (Joint Sign-Off by SatQuery & ARES Leads)  

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
│   │   ├── india_satellite_data.py    # Automated STAC Sentinel-2 imagery loader over Indian mission corridors
│   │   └── synthetic_sample_data.py   # Self-contained reproducible benchmark scenes
│   ├── models/
│   │   ├── checkpoint_loader.py       # Safe checkpoint inspector & weight parser (*.pth)
│   │   ├── classifier.py              # Semantic change classifier (building, road, vegetation, natural)
│   │   └── siamese_unet.py            # Deep Siamese ResNet-34 with Spatial-Temporal Attention
│   ├── vision/
│   │   ├── deep_detector.py           # High-precision deep change detector (PyTorch & calibrated fallback)
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

## 📦 Dependencies & Setup

Install required Python dependencies from repository root:
```powershell
pip install -r SatQuery/requirements.txt
```
Dependencies declared in `SatQuery/requirements.txt`:
- `numpy>=1.24.0` (Array computing)
- `opencv-python-headless>=4.8.0` (Image processing & morphological filtering)
- `pydantic>=2.0.0` (Strict schema contract validation)
- `scikit-learn>=1.3.0` (Platt scaling logistic regression)
- `scipy>=1.10.0` (Sub-pixel 2D phase correlation & optimization)
- `pillow>=9.5.0` (Raster encoding & visual montage generation)

*(Note: `SatQuery/satquery/vision/calibration.py` includes a zero-dependency pure-NumPy Platt scaling fallback, ensuring graceful execution even if `scikit-learn` is not yet installed).*

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

### Reproducing Deep Model Runs & Clean-Checkout Behavior

1. **Clean-Checkout Behavior (Zero-Setup Fallback):**
   - The 285 MB weights file (`best_siamese_model.pth`) is excluded from Git via `.gitignore` to comply with GitHub's strict 100 MB per-file push limit.
   - On a fresh clone without the `.pth` file, SatQuery automatically runs in **`calibrated_feature_attention` fallback mode**. All 27 unit tests, candidate generation, calibration, georeferencing, and ARES integrations run completely out-of-the-box with **zero crashes**.

2. **Obtaining & Staging Trained Weights:**
   - Place `best_siamese_model.pth` (285 MB) into:
     ```
     SatQuery/models/checkpoints/best_siamese_model.pth
     ```
     *(The loader also auto-discovers the file if located in your user `Downloads/` directory).*
   - Install PyTorch (optional, for GPU/CPU tensor acceleration):
     ```powershell
     pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
     ```
   - When present, `DeepSiameseChangeDetector` automatically verifies all 315 layers and engages `pytorch_resnet34` execution mode.

3. **Exercising `STRONGER_MODEL` Action in ARES:**
   - To verify the high-capacity `STRONGER_MODEL` action (costing 1,450 J total: 1,200 J edge compute + 250 J comms offload, reducing uncertainty by 40%), run Policy B2 (Adaptive Computation):
     ```powershell
     python SatQuery/examples/end_to_end_integration.py --policy B2
     ```
   - This adaptively selects `STRONGER_MODEL` for moderate-uncertainty candidates ($u \in [0.30, 0.65]$), expending 1,450 J per candidate with zero drone flight energy.

---

## 📋 Running Implementation Log

### Update: 2026-11-18 — Milestone 6: Interface Promotion to v1.0.0, ImagePairResolver, & Closed-Loop State Mutation
- **Summary:** Coordinated formal schema promotion from `v1.0.0-provisional` to `v1.0.0` with ARES lead (Vaibhav) following successful source imagery wiring and state mutation:
  1. Implemented `ImagePairResolver` (`satquery/data/image_resolver.py`), resolving each candidate's `image_pair_id` to actual multi-spectral or benchmark rasters (e.g. real Sentinel-2 Level-2A pairs for Kanpur/Bengaluru, or cached/synthetic LEVIR-CD pairs).
  2. Implemented closed-loop candidate state mutation upon `STRONGER_MODEL` dispatch, replacing initial prior uncertainty with empirical measured post-inference uncertainty ($u_{\text{crop}}$) and recording a `[MEASURED]` `EvidenceRecord`.
  3. Promoted default schema version to `v1.0.0` across Pydantic schemas, pipeline exports, unit tests, and `SatQuery/docs/INTERFACE_SPECIFICATION.md`.
  4. Expanded test suite to **29 tests** (added `test_image_pair_resolver_benchmark_and_real_scenes`).
- **Changed Files:**
  - `SatQuery/satquery/data/image_resolver.py` (New source imagery pair resolver)
  - `SatQuery/satquery/data/__init__.py` (Exported `ImagePairResolver` and `ResolvedImagePair`)
  - `SatQuery/satquery/schemas/candidate_record.py` (Promoted default to `v1.0.0`)
  - `SatQuery/satquery/pipeline.py` & `candidate_generator.py` (Updated defaults to `v1.0.0`)
  - `SatQuery/docs/INTERFACE_SPECIFICATION.md` (Updated version to `v1.0.0` and added §6 Re-Inference Contract)
  - `SatQuery/examples/end_to_end_integration.py` (Closed-loop candidate state update and dual-mode reporting)
  - `SatQuery/tests/test_india_data.py` (Added image pair resolver unit tests)
  - `SatQuery/tests/test_schemas.py` & `test_deep_model.py` (Updated to `v1.0.0`)
  - `SatQuery/exports/*.json` (Updated all candidate exports to `v1.0.0`)
- **Checks Performed:**
  - `python -m unittest discover -s SatQuery/tests -v` (29 tests: 28 passed, 1 skipped)
  - `python -m unittest discover -s ARES/tests -t ARES -v` (74/74 passed)
  - `python SatQuery/examples/end_to_end_integration.py --policy B2` (Passed: all candidates validated against `v1.0.0`)
  - `python SatQuery/examples/end_to_end_integration.py --candidates SatQuery/exports/candidates_kanpur_bhauti.json --policy B2` (Passed: real Sentinel-2 crops re-inferred)


### Update: 2026-11-18 — Calibration Optimizer Fix, Data-Driven Status, and Real Crop Re-Inference
- **Summary:** Resolved teammate findings regarding calibration status reporting and STRONGER_MODEL execution:
  1. Replaced naive gradient descent in the pure-NumPy Platt scaling fallback (`calibration.py`) with L2-regularized Newton-Raphson IRLS. This eliminates the optimization lag that caused ECE 0.3511 in clean environments, achieving rapid convergence (8 iterations) with true calibrated **ECE = 0.0557** ($< 0.10$) and Brier score 0.1767.
  2. Made calibration status reporting in `evaluate_vision_pipeline.py` strictly data-driven based on measured ECE (`PASSED (ECE = 0.0557 < 0.10, Well-calibrated)`).
  3. Upgraded `end_to_end_integration.py` to extract candidate patch crops (`img_pre`, `img_post`) and run actual detector inference during `STRONGER_MODEL` dispatch, while clearly distinguishing real vision re-inference from ARES's theoretical decision simulation and energy billing.
  4. Confirmed the SatQuery test suite count of **28 tests** (27 passed, 1 skipped for local weights).
- **Changed Files:**
  - `SatQuery/satquery/vision/calibration.py` (L2-regularized Newton-Raphson IRLS optimizer in pure-NumPy fallback)
  - `SatQuery/examples/evaluate_vision_pipeline.py` (Data-driven calibration status and held-out ECE benchmark)
  - `SatQuery/examples/end_to_end_integration.py` (Actual patch crop inference on STRONGER_MODEL dispatch + explicit simulation labeling)
  - `SatQuery/docs/EVALUATION_REPORT.md` & `SatQuery/exports/vision_evaluation_report.json` (Updated with true measured calibration metrics)
- **Checks Performed:**
  - `python -m unittest discover -s SatQuery/tests -v` (28 tests: 27 passed, 1 skipped)
  - `python -m unittest discover -s ARES/tests -t ARES -v` (74/74 passed)
  - `python SatQuery/examples/evaluate_vision_pipeline.py` (Passed: Calibrated ECE = 0.0557)
  - `python SatQuery/examples/end_to_end_integration.py --policy B2` (Passed: Real patch crop inference + ARES simulated outcome logged)

### Update: 2026-11-17 — Deep Siamese ResNet-34 + CBAM Model Integration & Audit
- **Summary:** Audited and integrated the trained deep Siamese neural network (`best_siamese_model.pth`, 285 MB) into SatQuery. The model incorporates a weight-shared Siamese ResNet-34 backbone with dual-stream Channel and Spatial Attention (CBAM) difference weighting across 4 spatial scales, coupled with a progressive transposed-convolution decoder. Audited checkpoint confirms 35 completed epochs with Cosine Annealing, achieving **84.75% Validation F1** and **73.54% Validation IoU** (a +22.0% IoU and +34.7% F1 gain over the differential baseline). Provided a PyTorch inference engine with a seamless calibrated feature-attention fallback for environments without PyTorch. Integrated model selection (`--model deep_siamese` / `--model baseline`) into pipeline runners and added unit tests in `SatQuery/tests/test_deep_model.py`.
- **Changed Files:**
  - `SatQuery/satquery/models/checkpoint_loader.py` (Safe checkpoint inspector and metadata parser)
  - `SatQuery/satquery/models/siamese_unet.py` (Full 315-tensor PyTorch Siamese ResNet-34 architecture matching `best_siamese_model.pth`)
  - `SatQuery/satquery/vision/deep_detector.py` (Deep Siamese detector wrapper with PyTorch / calibrated fallback)
  - `SatQuery/satquery/pipeline.py` (Supported `model_type` selection)
  - `SatQuery/examples/run_india_pipeline.py` (Added `--model` flag and diagnostic telemetry)
  - `SatQuery/examples/end_to_end_integration.py` (Added `--model` and `--regenerate` flags)
  - `SatQuery/tests/test_deep_model.py` (Unit tests for checkpoint discovery, metadata audit, inference, and candidate generation)
- **Checks Performed:**
  - `python -m unittest discover -s SatQuery/tests -v` (27/27 passed)
  - `python -m unittest discover -s ARES/tests -t ARES -v` (70/70 passed)
  - `python SatQuery/examples/end_to_end_integration.py --policy B3 --model deep_siamese` (Success)
  - `python SatQuery/examples/run_india_pipeline.py --zone kanpur_bhauti --policy B3 --model deep_siamese` (Success: 5 candidates detected and verified)
  - `python SatQuery/examples/run_india_pipeline.py --zone kanpur_bhauti --policy B4 --no-human-review --model deep_siamese` (Success: Recaptured 3 targets, safety reserve guardrail triggered for 4th target, safe return completed with 16.79 Wh return flight energy)

### Update: 2026-11-17 — Dependency Declaration & Scikit-Learn Graceful Fallback
- **Summary:** Declared official dependencies in `SatQuery/requirements.txt` (including `scikit-learn>=1.3.0`, `opencv-python-headless`, `pydantic`, `numpy`, `scipy`, `pillow`). Added a clean environment setup guide in `README.md`. Implemented a pure-NumPy logistic regression fallback in `SatQuery/satquery/vision/calibration.py` so that Platt scaling and end-to-end integration execute cleanly even on environments where `scikit-learn` is not yet installed.
- **Changed Files:**
  - `SatQuery/requirements.txt` (Declared all SatQuery dependencies)
  - `SatQuery/satquery/vision/calibration.py` (Graceful NumPy fallback for Platt scaling when `sklearn` is missing)
  - `SatQuery/README.md` (Documented clean setup instructions and dependency declaration)
- **Checks Performed:**
  - `python SatQuery/examples/end_to_end_integration.py --policy B3` (Success: Safe return True)
  - `python SatQuery/examples/run_india_pipeline.py --zone kanpur_bhauti --policy B1` (Success: Flight recapture & return reserve exercised)
  - `python SatQuery/examples/run_india_pipeline.py --zone kanpur_bhauti --policy B4` (Success: Dynamic spatial dispatch & return reserve exercised)
  - `python -m unittest discover -s SatQuery/tests -v` (23/23 passed)
  - `python -m unittest discover -s ARES/tests -t ARES -v` (70/70 passed)
- **Action Needed from ARES:**
  - Pull latest commit and run `pip install -r SatQuery/requirements.txt` (optional, since the pure-NumPy fallback also allows execution without `sklearn`). Confirm clean run to finalize `v1.0.0`.
