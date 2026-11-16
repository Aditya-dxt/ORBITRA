# SatQuery Dataset Audit & Research Protocol

**Module:** SatQuery (Computer Vision & Image Processing)  
**Project:** ORBITRA  
**Gate:** Phase 1 / Gate 1 Audit  
**Date:** 2026-11-16  

---

## 1. Primary Benchmark Audit: MAHCD vs. LEVIR-CD / OSCD

The ORBITRA project synopsis identified **MAHCD** (Wang et al., 2025) as the primary candidate dataset for satellite-to-UAV building change detection. Per Section 4 & 5 (Gate 1), a formal audit was conducted on data accessibility, licensing, correspondence, and usability.

### Dataset Audit Comparison Matrix

| Evaluation Dimension | MAHCD (Wang et al., 2025) | LEVIR-CD / LEVIR-CD+ (Chen & Shi, 2020) | OSCD (Caye Daudt et al., 2018) |
| --- | --- | --- | --- |
| **Primary Domain** | Satellite-to-UAV building change | High-resolution bi-temporal satellite | Sentinel-2 multispectral satellite |
| **Source Sensor** | Heterogeneous (Satellite + UAV) | Google Earth / High-res optical | ESA Sentinel-2 (13 spectral bands) |
| **Resolution / GSD** | Variable ($\sim 0.1\text{ m}$ to $0.8\text{ m}$) | Uniform $0.5\text{ m / pixel}$ | $10\text{ m}$ (RGB/NIR), $20\text{ m}$, $60\text{ m}$ |
| **Licensing / Access** | Hosted via 3rd-party file locker without formal open-source license file | Open academic access (standard benchmark) | Open access under CC BY-SA 4.0 |
| **Annotation Quality** | Bitemporal building change masks | Exhaustive building change masks ($1024 \times 1024$) | Pixel-level binary change masks |
| **Multi-Epoch UAV Recaptures** | **None.** Single-instance UAV imagery only; no repeated multi-pass drone visits | None (pure satellite pairs) | None (pure satellite pairs) |
| **Gate 1 Recommendation** | **Stop/Pivot to LEVIR-CD / OSCD** | **Primary benchmark adopted** | **Secondary multispectral baseline** |

---

## 2. Gate 1 Stop/Pivot Decision Justification

1. **Licensing & Reproducibility Risk:** The MAHCD repository depends on temporary third-party cloud links without an OSI/Creative Commons license file. In contrast, LEVIR-CD is the established gold-standard benchmark in remote sensing change detection with fully verifiable splits.
2. **UAV Recapture Reality Check:** Neither MAHCD nor any openly available remote-sensing dataset contains repeat-visit UAV telemetry at multiple battery states. Therefore, adhering to ORBITRA's core scientific integrity:
   - **Real Image Data:** Used exclusively for bi-temporal change detection, bounding box generation, and empirical detector evaluation (Precision, Recall, F1, IoU).
   - **UAV Flight Actions & Telemetry:** Modeled strictly as **simulation** (`SIMULATED` / `ASSUMED`) in ARES. No physical drone flights are claimed.

---

## 3. Data Splitting & Leakage Prevention Strategy

To ensure zero geographic or spatial data leakage:
- **Scene-Level Splitting:** Splits are defined strictly by entire scenes or geographic regions—**never by randomly splitting cropped patches**.
- **Validation Split:** Used strictly for tuning detection thresholds and fitting confidence calibrators (Platt scaling / temperature scaling).
- **Held-Out Test Split:** Used strictly for final metric evaluation (Precision, Recall, F1, IoU) and calibration assessment (Expected Calibration Error and Brier Score). The test split is never observed during model training or calibration parameter fitting.

---

## 4. Known Vision Pipeline Failure Modes

Remote sensing computer vision encounters systematic failure modes documented for operational transparency:

1. **Shadow Angle Shifts:** Differential solar azimuth angles cast varying building and tree shadows between dates, which baseline thresholding can misidentify as structural change. Mitigated by bilateral filtering and structural gradient weighting.
2. **Seasonal Vegetation Coloration:** Autumn browning or winter snow cover can trigger large spectral Euclidean differences. Mitigated by Excess Green (ExG) index filtering and morphological opening.
3. **Sub-Pixel Edge Misregistration:** Minor sensor misalignment produces thin 1–2 pixel change outlines along high-contrast borders. Mitigated by minimum connected-component area thresholds ($A_{\min} \ge 25\text{ pixels}$).
4. **Off-Nadir Sensor Tilt:** Perspective distortion from differing satellite viewing angles shifts building facade positions relative to their footprints.
