# ARES

**Owner:** Energy Modelling & Intelligent Decision-Making Lead  
**System:** ORBITRA  
**Status:** Milestone 2 Complete (Importance Scoring Model, Action Cost & Outcome Models, Reserve Reconciliation, B0/B1, Simulator)

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
│   ├── scoring/                  # Mission-importance scoring decoupled from model confidence
│   ├── actions/                  # Action cost (J) & outcome models (RECAPTURE, STRONGER_MODEL, HUMAN_REVIEW)
│   ├── ledger/                   # Structured decision audit trail (J, Wh, SIMULATED tags)
│   ├── policies/                 # B0 (Fixed Pass) & B1 (Uncertainty First); B2-B4 as PLANNED
│   └── simulation/               # Discrete-event runner with [SYNTHETIC EXAMPLE]s
└── tests/                        # Automated unit tests
```

---

## Key Principles & Starting Assumptions

1. **Internal Joules:** All energy math, kinematics, and internal states operate strictly in **Joules (J)**. Watt-hours (Wh) are derived solely for user display ($1\text{ Wh} = 3600\text{ J}$).
2. **Decoupled Importance Scoring (`ares/scoring/`):**
   - Operational importance weights ($\{1.0, 2.0, 4.0\}$) are assigned based on semantic change categories and zone multipliers (e.g., $1.5\times$ for protected conservation areas).
   - Importance reflects operational consequence, kept strictly independent of vision detector confidence ($[0.0, 1.0]$). Tagged as `ASSUMED`.
3. **Action Cost & Outcome Models (`ares/actions/`):**
   - **`RECAPTURE`**: Models UAV flight transit, hover dwell, sensor capture, edge compute, and telemetry. Flight energy dominates ($>80\%$). Outcome cuts uncertainty by $\sim 70\%$.
   - **`STRONGER_MODEL`**: Models high-capacity inference on edge accelerator or server offload. Zero flight/hover energy. Outcome cuts uncertainty by $\sim 40\%$.
   - **`HUMAN_REVIEW`**: Models queueing for human analyst/pilot triage. Charges minimal comms energy ($50\text{ J}$) and consumes $1.0$ queue capacity slot. Outcome resolves uncertainty conclusively ($u' \le 0.05$).
4. **Protected Return Reserve:**
   - Evaluated strictly from the **candidate's coordinates after the action** back to home base.
   - Enforces **exactly one uncertainty allowance** to prevent double-counting: supports either relative fraction ($20\%$, reconciling $k=2$ with $10\%$ CoV) or absolute standard deviation ($k \cdot \sigma_E$ in Joules).
   - Includes a separate, additive headwind margin parameter ($E_{\text{wind}}$ in Joules).
   - Tagged as `ASSUMED`, not certified physical flight safety guarantees.
5. **Data Provenance:** Every metric, assumption, and outcome is explicitly categorized as `ASSUMED`, `SIMULATED`, or `MEASURED`. No physical drone flights or unverified measurements are claimed.

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
| **B2** | Adaptive Computation | Planned (Milestone 3) | Dynamic edge vs. server inference depth per candidate. |
| **B3** | Joint Policy | Planned (Milestone 4) | Joint candidate selection and action depth optimization. |
| **B4** | Greedy Benefit-per-Energy | Planned (Milestone 5) | Marginal utility per Joule maximization ($\Delta B / \Delta E$). |
| **P1** | Confidence Ranked | Supplementary Baseline | Compares against pure detector confidence ranking. |
| **P2** | Importance Ranked | Supplementary Baseline | Compares against pure importance ranking. |
| **P5** | Zone-Weighted Spatial | Supplementary Baseline | Compares against spatial sector risk ranking. |

---

## Development Sequence

| Weeks | Planned ARES work | Status |
| --- | --- | --- |
| 1-3 | Review energy-aware UAV research; outline simulator; design doc & schema proposal | **Completed (Milestone 1)** |
| 4-7 | Candidate-state architecture, Joules energy model, return-reserve rule, decision ledger, B0/B1 | **Completed (Milestone 1)** |
| 8-11 | Importance scoring model and action cost/outcome models (RECAPTURE, STRONGER_MODEL, HUMAN_REVIEW) | **Completed (Milestone 2)** |
| 12-15 | Energy model calibration and geodetic GIS coordinate integration | Planned |
| 16-19 | Policies B2-B4 implementation and decision logging | Planned |
| 20-23 | Matched-budget policy experiments and ablations | Planned |
| 24-32 | Dashboard, end-to-end integration with SatQuery records, final reporting | Planned |

---

## Running Implementation Log

### Milestone 2: Importance Scoring & Action Models — 2026-11-16
- **Summary:** Added the mission-importance scoring engine (`ares/scoring/`) decoupled from detector confidence, and implemented formal action cost and simulated outcome models (`ares/actions/`) for `RECAPTURE`, `STRONGER_MODEL`, and `HUMAN_REVIEW`.
- **Changed Files:**
  - `ARES/ares/scoring/importance.py` & `__init__.py`: Category weight mappings, zone multipliers, and candidate state integration.
  - `ARES/ares/actions/models.py` & `__init__.py`: Energy (J & Wh), duration (s), and human capacity slot modeling for each action, with simulated outcome generators.
  - `ARES/docs/DESIGN.md`: Added sections 4 & 5 documenting scoring logic and action model specifications.
  - `ARES/tests/test_importance.py`: Unit tests verifying decoupling from confidence, category lookups, and zone multipliers.
  - `ARES/tests/test_actions.py`: Unit tests verifying flight vs non-flight energy math and outcome simulation.
- **Checks Actually Performed:**
  - Ran `python -m unittest discover -s ARES/tests -t ARES -v`: all 34 tests passed cleanly.
  - Confirmed decoupling: high-confidence / low-priority candidates receive Low weight ($1.0$), while low-confidence / high-hazard candidates receive High weight ($4.0$).
  - Confirmed zero flight energy for non-flight actions (`STRONGER_MODEL` compute/offload only; `HUMAN_REVIEW` alert comms only).
- **Known Limitations:**
  - SatQuery output schema remains strictly provisional (`v1.0.0-provisional`) as teammate has not implemented candidate generation yet.
  - Action costs and outcome parameters are theoretical starting assumptions (`ASSUMED`).
  - No physical drone flights have been conducted; all outcomes are labeled `[SIMULATED]`.
- **Action Needed from SatQuery Owner:**
  - Review `ARES/docs/INTERFACE_PROPOSAL.md` when SatQuery work begins.
