# ARES

**Owner:** Energy Modelling & Intelligent Decision-Making Lead  
**System:** ORBITRA  
**Status:** Milestone 1 Complete (Foundations, Schemas, Energy Guardrails, B0/B1, Decision Ledger, Simulator)

ARES consumes candidate change records produced by SatQuery and decides what to inspect, compute, defer, or stop while strictly respecting the mission energy budget and safe-return reserve.

---

## Architecture & Modules

```
ARES/
├── README.md                     # Module documentation & running implementation log
├── docs/
│   ├── DESIGN.md                 # Architecture, energy kinematics, reserve math, policy arena
│   └── INTERFACE_PROPOSAL.md     # Provisional schema proposal & 7-point review checklist
├── ares/
│   ├── schemas/                  # Pydantic validation (SatQueryRecord vs AresCandidateState)
│   ├── energy/                   # Joule-based accounting, kinematics, post-action return reserve
│   ├── ledger/                   # Structured decision audit trail (J, Wh, SIMULATED tags)
│   ├── policies/                 # B0 (Fixed Pass) & B1 (Uncertainty First); B2-B4 as PLANNED
│   └── simulation/               # Discrete-event runner with [SYNTHETIC EXAMPLE]s
└── tests/                        # Automated unit tests
```

---

## Key Principles & Starting Assumptions

1. **Internal Joules:** All energy math, kinematics, and internal states operate strictly in **Joules (J)**. Watt-hours (Wh) are derived solely for user display ($1\text{ Wh} = 3600\text{ J}$).
2. **Decoupled Importance:** Operational importance weights ($\{1.0, 2.0, 4.0\}$) are assigned by mission rules and decoupled from vision confidence ($[0.0, 1.0]$). Tagged as `ASSUMED`.
3. **Protected Return Reserve & $k=2$ / 20% Reconciliation:**
   - Evaluated strictly from the **candidate's coordinates after the action** back to home base.
   - Enforces **exactly one uncertainty allowance** to prevent double-counting:
     - When absolute standard deviation $\sigma_E$ (in Joules) is provided: $\text{Allowance} = k \cdot \sigma_E$ (with $k=2.0$ coverage factor).
     - Otherwise, uses a relative return energy fraction $\alpha = 0.20$ ($20\%$), which reconciles $k=2.0$ with an assumed $10\%$ coefficient of variation ($\text{CoV} = 0.10 \implies k \times \text{CoV} = 2.0 \times 0.10 = 0.20$).
   - A separate, explicit additive headwind margin parameter ($E_{\text{wind}}$ in Joules) is included.
   - All parameters are unvalidated starting assumptions (`ASSUMED`), not physical flight safety guarantees.
4. **Data Provenance:** Every metric, assumption, and outcome is explicitly categorized as `ASSUMED`, `SIMULATED`, or `MEASURED`. No physical drone flights or unverified measurements are claimed.

---

## How to Run Tests

From the repository root:
```powershell
python -m unittest discover -s ARES/tests -t ARES -v
```

Or from inside the `ARES/` directory:
```powershell
python -m unittest discover -s tests -v
```

---

## Policy Status

| Policy ID | Policy Name | Implementation Status | Notes |
| --- | --- | --- | --- |
| **B0** | Fixed Pass | **Implemented (Milestone 1)** | Sequential candidate pass; baseline reference. |
| **B1** | Uncertainty First | **Implemented (Milestone 1)** | Prioritizes targets with highest detector uncertainty. |
| **B2** | Adaptive Computation | Planned (Milestone 2) | Dynamic edge vs. server inference depth per candidate. |
| **B3** | Joint Policy | Planned (Milestone 3) | Joint candidate selection and action depth optimization. |
| **B4** | Greedy Benefit-per-Energy | Planned (Milestone 4) | Marginal utility per Joule maximization ($\Delta B / \Delta E$). |
| **P1** | Confidence Ranked | Supplementary Baseline | Compares against pure detector confidence ranking. |
| **P2** | Importance Ranked | Supplementary Baseline | Compares against pure importance ranking. |
| **P5** | Zone-Weighted Spatial | Supplementary Baseline | Compares against spatial sector risk ranking. |

---

## Development Sequence

| Weeks | Planned ARES work | Status |
| --- | --- | --- |
| 1-3 | Review energy-aware UAV research; outline simulator; design doc & schema proposal | **Completed (Milestone 1)** |
| 4-7 | Candidate-state architecture, Joules energy model, return-reserve rule, decision ledger, B0/B1 | **Completed (Milestone 1)** |
| 8-11 | Importance scoring and action outcome models with calibrated probability tables | Planned |
| 12-15 | Energy model calibration and geodetic GIS coordinate integration | Planned |
| 16-19 | Policies B2-B4 implementation and decision logging | Planned |
| 20-23 | Matched-budget policy experiments and ablations | Planned |
| 24-32 | Dashboard, end-to-end integration with SatQuery records, final reporting | Planned |

---

## Running Implementation Log

### Reserve Rule Reconciliation & Interface Checklist — 2026-11-16
- **Summary:** Reconciled $k=2$ statistical coverage with the 20% relative reserve allowance in `ares/energy/reserve.py` and `docs/DESIGN.md`, ensuring strict single-uncertainty math without double-counting. Expanded `docs/INTERFACE_PROPOSAL.md` with a comprehensive 7-point review checklist for the SatQuery lead.
- **Changed Files:**
  - `ARES/ares/energy/reserve.py`: Added explicit dual support for $k \cdot \sigma_E$ (Joules) or relative fraction ($0.20$), guaranteeing only one allowance is applied.
  - `ARES/docs/DESIGN.md`: Documented reconciliation between $k=2$ coverage, $10\%$ relative flight uncertainty standard deviation, and the resulting $20\%$ allowance.
  - `ARES/docs/INTERFACE_PROPOSAL.md`: Added 7-point review checklist (field names/types, calibration, uncertainty meaning, CRS/axis order, image pair IDs, schema versioning, missing-value handling).
  - `ARES/tests/test_reserve.py`: Added test `test_k_sigma_explicit_energy_allowance_without_double_counting`.
- **Checks Actually Performed:**
  - Ran `python -m unittest discover -s ARES/tests -t ARES -v`: all 24 tests passed cleanly.
  - Verified that setting `sigma_return_energy_joules` activates $k \cdot \sigma_E$ without adding the 20% relative fraction.
- **Action Needed from SatQuery Owner:**
  - Review the 7 checklist items in `ARES/docs/INTERFACE_PROPOSAL.md` once SatQuery begins candidate generation.
