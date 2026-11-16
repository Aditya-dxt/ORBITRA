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
│   └── INTERFACE_PROPOSAL.md     # Provisional schema proposal for SatQuery owner review
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
3. **Protected Return Reserve:** Evaluated strictly from the **candidate's coordinates after the action** back to home base, applying a **single uncertainty multiplier** ($\alpha_{\text{reserve}} = 20\%$) and an explicit headwind margin ($E_{\text{wind}}$ in Joules) to avoid double-counting.
4. **Data Provenance:** Every metric, assumption, and outcome is explicitly categorized as `ASSUMED`, `SIMULATED`, or `MEASURED`. No fake real-world flights or measurements are claimed.

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

### Milestone 1 — 2026-11-16
- **Summary:** Built initial ARES module foundation, provisional candidate schema validation, Joule-based energy accounting, post-action return-reserve guardrail, decision audit ledger, B0/B1 policies, and discrete-event synthetic simulator.
- **Changed Files:**
  - `ARES/docs/DESIGN.md`: Technical architecture document.
  - `ARES/docs/INTERFACE_PROPOSAL.md`: Provisional SatQuery-to-ARES contract proposal (`v1.0.0-provisional`).
  - `ARES/ares/schemas/`: Data provenance, SatQueryCandidateRecord, AresCandidateState, and ActionType models.
  - `ARES/ares/energy/`: Joule/Wh conversions, DroneEnergyModel ($k=2$), and ReturnReserveCalculator.
  - `ARES/ares/ledger/`: DecisionLedger and DecisionRecord audit trail.
  - `ARES/ares/policies/`: BasePolicy, B0FixedPassPolicy, B1UncertaintyFirstPolicy, and registry catalog.
  - `ARES/ares/simulation/`: Synthetic candidate generator with `[SYNTHETIC EXAMPLE]` tags and MissionSimulator.
  - `ARES/tests/`: 23 automated unit tests covering all components.
- **Checks Actually Performed:**
  - Ran `python -m unittest discover -s ARES/tests -t ARES -v`: all 23 tests passed cleanly.
  - Verified bounds checking: confidence and uncertainty outside $[0, 1]$ properly raise validation errors.
  - Verified reserve constraint: actions that leave less than post-action return reserve trigger an immediate abort/deferral.
  - Verified B1 ordering: confirmed candidates are sorted by highest uncertainty first.
- **Known Limitations:**
  - Synthetic data only: no real SatQuery detector records or paired image tiles are available yet.
  - Simulation only: energy models and capture costs are theoretical starting assumptions (`ASSUMED`), not empirical flight measurements.
  - Local Cartesian grid: 3D Euclidean distances are used; geodetic GIS transformations (EPSG:4326) will be added in Phase 4.
- **Action Needed from SatQuery Owner:**
  - Review `ARES/docs/INTERFACE_PROPOSAL.md` and confirm candidate schema fields, coordinate formats, and uncertainty normalization.
