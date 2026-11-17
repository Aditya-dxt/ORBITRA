# ARES

**Owner:** Energy Modelling & Intelligent Decision-Making Lead  
**System:** ORBITRA  
**Status:** Milestone 5 Complete (B0–B4 Implemented) | Provisional Interface Tightened (`v1.0.0-provisional`) per SatQuery Lead Agreement

ARES consumes candidate change records produced by SatQuery and decides what to inspect, compute, defer, or stop while strictly respecting the mission energy budget and safe-return reserve.

---

## Architecture & Modules

```
ARES/
├── README.md                     # Module documentation & running implementation log
├── docs/
│   ├── DESIGN.md                 # Architecture, energy kinematics, reserve math, policy arena (B0-B4)
│   └── INTERFACE_PROPOSAL.md     # Provisional schema proposal & 7-point review checklist
├── ares/
│   ├── schemas/                  # Pydantic validation (SatQueryRecord vs AresCandidateState)
│   ├── energy/                   # Joule-based accounting, kinematics, post-action return reserve
│   ├── scoring/                  # Mission-importance scoring decoupled from model confidence
│   ├── actions/                  # Action cost (J) & outcome models (RECAPTURE, STRONGER_MODEL, HUMAN_REVIEW)
│   ├── ledger/                   # Structured decision audit trail (J, Wh, SIMULATED tags)
│   ├── policies/                 # B0, B1, B2, B3, B4 (All canonical policies implemented)
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
| **B2** | Adaptive Computation | **Implemented (Milestone 3)** | 5-branch decision tree: accept / recapture / stronger-model / human-review / return-home. Configurable thresholds (`ASSUMED`). |
| **B3** | Joint Policy | **Implemented (Milestone 4)** | Jointly evaluates all (candidate, action) pairs per step; selects globally best-scoring feasible pair under reserve constraint. |
| **B4** | Greedy Benefit-per-Energy | **Implemented (Milestone 5)** | Greedily prioritizes candidates maximizing marginal benefit per expended Joule ($\Delta B / \Delta E$) using physical RECAPTURE (spatial dispatch baseline). |
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
| 12-15 | B2 Adaptive Computation policy, multi-action simulator refactor | **Completed (Milestone 3)** |
| 16-19 | B3 Joint Policy: joint candidate-and-action selection with benefit/cost objective | **Completed (Milestone 4)** |
| 20-23 | Policies B4 implementation and decision logging | **Completed (Milestone 5)** |
| 20-23 | Matched-budget policy experiments and ablations | Planned |
| 24-32 | Dashboard, end-to-end integration with SatQuery records, final reporting | Planned |

---

## Running Implementation Log

### Milestone 5: B4 Greedy Benefit-per-Energy Policy — 2026-11-17
- **Summary:** Formulated the clear architectural and measurable distinction between Policy B3 (joint candidate-and-action co-optimization across multi-modal actions) and Policy B4 (single-action spatial dispatch baseline). Implemented Policy B4 (`B4GreedyBenefitPerEnergyPolicy`), which dynamically ranks pending candidates by marginal expected benefit per Joule of physical transit and sortie energy ($\Delta B / E_{\text{recapture}}$) from the current UAV location $\mathbf{x}_{\text{current}}$, and selects physical `RECAPTURE` under the return-reserve guardrail ($E_{\text{remaining}} - E_{\text{action}} \ge E_{\text{reserve}}(\mathbf{x}_c \to \mathbf{x}_{\text{home}})$). Added B4 to the policy registry, simulator, and test suite. Documented the comparison and formal formulas in `DESIGN.md`.
- **Architectural Distinction Defined (B3 vs. B4):**
  - **Action Modality Space:** B4 is strictly single-modality (`RECAPTURE` only, 0% compute offload, 0% human review), representing the classic robotic field survey / spatial orienteering baseline. B3 optimizes over multi-modal actions (`RECAPTURE`, `STRONGER_MODEL`, `HUMAN_REVIEW`, `NONE`).
  - **Optimization Dimension:** B4 performs 1D spatial greedy ranking over candidates $\mathcal{C}$ based on dynamic distance from $\mathbf{x}_{\text{current}}$. B3 performs 2D joint co-optimization over the Cartesian product $\mathcal{C} \times \mathcal{A}$.
  - **Behavior under Reserve Constraints:** When battery cannot support flight to candidate + return to home, B4 unconditionally triggers `RETURN_HOME` and terminates the sortie. Under the same constraint, B3 dynamically downgrades to non-flight compute or analyst review, continuing candidate processing at zero flight cost.
- **Changed Files:**
  - `ARES/docs/DESIGN.md`: Added Section 8 detailing the architectural distinction, comparison table, mathematical formulation, decision rules, and configurable thresholds (`B4GreedyBenefitPerEnergyConfig`); updated Section 2.1 policy arena table; renumbered subsequent sections.
  - `ARES/ares/policies/base.py`: Updated `rank_candidates()` signature to optionally accept `current_pos: Optional[LocalGridCoordinates] = None`.
  - `ARES/ares/policies/b0_fixed_pass.py`, `b1_uncertainty_first.py`, `b2_adaptive_computation.py`, `b3_joint_policy.py`: Aligned `rank_candidates()` signatures with optional `current_pos`.
  - `ARES/ares/policies/b4_greedy_benefit_per_energy.py`: New file — `B4GreedyBenefitPerEnergyConfig` and `B4GreedyBenefitPerEnergyPolicy` implementing dynamic spatial benefit-per-Joule ranking and reserve-constrained RECAPTURE selection.
  - `ARES/ares/policies/registry.py`: B4 status → `IMPLEMENTED`; `get_policy("B4")` returns `B4GreedyBenefitPerEnergyPolicy()`.
  - `ARES/ares/policies/__init__.py`: Exported `B4GreedyBenefitPerEnergyConfig` and `B4GreedyBenefitPerEnergyPolicy`.
  - `ARES/ares/simulation/simulator.py`: Pass `current_pos=current_pos` into `policy.rank_candidates()`.
  - `ARES/tests/test_b4_policy.py`: New file — 11 comprehensive tests verifying benefit formula, spatial distance ordering, benefit ordering, dynamic re-ranking as UAV relocates, reserve guardrail enforcement, low-benefit NONE acceptance, single-modality invariant, end-to-end simulation, and behavioral contrast against B3.
  - `ARES/tests/test_policies.py`: Updated registry assertions for B4 `IMPLEMENTED` and factory instantiation.
  - `ARES/README.md`: Status badge, policy catalog, development sequence, and implementation log updated.
- **Checks Actually Performed:**
  - Ran `python -m unittest discover -s ARES/tests -t ARES -v`: **70/70 tests passed cleanly**.
  - Confirmed: B4 ranks closer candidate higher when benefit is identical (higher benefit per Joule).
  - Confirmed: B4 ranks higher-benefit candidate higher when distance is identical.
  - Confirmed: Relocating UAV position $\mathbf{x}_{\text{current}}$ dynamically updates candidate priority ordering.
  - Confirmed: Far candidate (3000m) with 5000 J battery triggers `RETURN_HOME` with `reserve_feasible=False`.
  - Confirmed: B4 never selects `STRONGER_MODEL` or `HUMAN_REVIEW` (single-action modality verified).
  - Confirmed: In matched-energy simulation (20,000 J), B4 visits the close target and aborts on the far target, whereas B3 continues processing with non-flight actions.
  - Confirmed: All other baseline policies (B0, B1, B2, B3) continue to pass all tests with zero regression.
- **Remaining Limitations & Documented Assumptions:**
  - All B4 thresholds and uncertainty reduction rates ($r_{\text{recapture}} = 0.70$) are theoretical starting values tagged `ASSUMED` — not measured from physical flight logs.
  - B4 performs myopic (single-step greedy) spatial selection without lookahead or multi-stop Traveling Salesperson / orienteering route optimization.
  - Policy performance comparisons require empirical flight or bench experiments under matched energy budgets.
  - SatQuery interface remains strictly `v1.0.0-provisional`.
- **Summary:** Updated ARES schema validation and documentation to reflect the agreed provisional interface (`v1.0.0-provisional`) with the SatQuery lead. Made `local_grid` mandatory for all ARES kinematic and reserve computations. Enforced strict ISO-8601 UTC datetime parsing (`Z` or `+00:00`), rejecting malformed strings that merely append suffixes. Enabled strict rejection of unknown extra fields (`extra='forbid'`) to prevent silent schema drift. Documented and enforced candidate uncertainty as a hard validation failure if it deviates from normalized binary Shannon entropy of calibrated confidence ($u = -[p \log_2(p) + (1-p) \log_2(1-p)]$) beyond `SHANNON_ENTROPY_TOLERANCE` (±0.15). Reconciled the documented coordinate example so sample latitude ($39.902857^\circ\text{ N}$) strictly matches the stated nominal conversion formula ($y / 111{,}320$) and inputs ($y = 318.0\text{ m}$).
- **Changed Files:**
  - `ARES/ares/schemas/satquery_record.py`: `local_grid` required; strict ISO-8601 UTC datetime parsing validator; `extra='forbid'`; hard Shannon entropy validation check with configurable `SHANNON_ENTROPY_TOLERANCE = 0.15`; detailed field and coordinate documentation.
  - `ARES/ares/schemas/__init__.py`: Exported `SHANNON_ENTROPY_TOLERANCE`.
  - `ARES/docs/INTERFACE_PROPOSAL.md`: Fully revised with agreed fields, semantics, Shannon entropy formula, hard validation rules, reconciled coordinate convention (home [0,0,0] at 39.9°N, 116.4°E, tile anchor at (160.5m E, 217.0m N), GSD 0.5m/px, centroid at local (245.5m E, 318.0m N, 50m AGL) and geodetic center at 39.902857°N, 116.402875°E), sample record, and resolved checklist.
  - `ARES/ares/simulation/synthetic_data.py`: Synthetic candidate records aligned with the agreed Shannon entropy uncertainty formula.
  - `ARES/tests/test_schemas.py`: Added tests for required `local_grid`, malformed ISO-8601 string rejection, non-UTC timestamp rejection, unknown field rejection, hard Shannon entropy validation, entropy boundary cases ($p=0, 0.5, 1.0$), and the reconciled coordinate example test.
  - `ARES/tests/test_actions.py`, `test_policies.py`, `test_b2_policy.py`, `test_b3_policy.py`, `test_importance.py`: Updated synthetic test fixtures to satisfy schema validation and entropy consistency.
  - `ARES/README.md`: Status and implementation log updated.
- **Checks Actually Performed:**
  - Ran `python -m unittest discover -s ARES/tests -t ARES -v`: **59/59 tests passed**.
  - Confirmed: Missing `local_grid` raises `ValidationError`.
  - Confirmed: Malformed ISO-8601 timestamps (`not-a-dateZ`, `invalid+00:00`, `2026-02-31T09:00:00Z`, `2026-11-17T25:00:00Z`) and non-UTC timestamps raise `ValidationError`.
  - Confirmed: Unknown extra fields raise `ValidationError`.
  - Confirmed: Hard validation failure triggers when uncertainty deviates by $>0.15$ from binary Shannon entropy.
  - Confirmed: Reconciled coordinate sample center latitude $39.902857^\circ\text{ N}$ precisely matches the stated $318.0 / 111{,}320$ formula.
  - Confirmed: All policies (B0, B1, B2, B3) and simulations run cleanly with tightened schemas.
- **Remaining Limitations & Documented Assumptions:**
  - Interface remains strictly `v1.0.0-provisional` until joint integration is executed with actual SatQuery code.
  - Confidence calibration (temperature/Platt scaling) and georeferencing coordinate transforms are documented SatQuery responsibilities and assumptions, not verified by ARES.
  - Geodetic conversion example is an illustrative local planar approximation, not a general georeferencing engine.
  - Policy B4 remains `PLANNED`.

### Milestone 4: B3 Joint Policy — 2026-11-16
- **Summary:** Implemented B3 Joint Policy — the first ARES policy that jointly decides both _which_ candidate to handle and _which_ action to apply in a single step. At each mission step, B3 enumerates all PENDING `(candidate, action)` pairs, applies the return-reserve guardrail to exclude infeasible pairs, scores each feasible pair using the joint objective `score = w × u × r_a / max(E_a, E_min)`, and executes the globally highest-scoring pair. Configured thresholds and reduction rates are `ASSUMED`. B4 remains `PLANNED`.
- **Changed Files:**
  - `ARES/ares/policies/b3_joint_policy.py`: New file — `B3JointPolicyConfig`, `B3JointPolicy` with joint objective, `run_joint_step()` interface, and `select_action()` single-candidate compatibility path.
  - `ARES/ares/policies/registry.py`: B3 status → `IMPLEMENTED`; `get_policy("B3")` returns `B3JointPolicy()`; `get_policy("B4")` raises `NotImplementedError`.
  - `ARES/ares/policies/__init__.py`: Added `B3JointPolicyConfig`, `B3JointPolicy` exports.
  - `ARES/tests/test_b3_policy.py`: New file — 11 tests covering ranking, benefit formula, joint score formula, best-pair selection, reserve guardrail enforcement, low-benefit NONE acceptance, single-candidate compatibility, end-to-end simulation, and config customisation.
  - `ARES/tests/test_policies.py`: Updated to expect B3 `IMPLEMENTED`, `get_policy("B3")` → `B3JointPolicy`, `get_policy("B4")` raises `NotImplementedError`.
  - `ARES/docs/DESIGN.md`: New Section 7 — B3 decision loop, joint objective formula and table, uncertainty reduction assumptions, special cases, configurability table, complexity note; policy arena table updated; Section 8 → 9 renumbered.
  - `ARES/README.md`: Policy table (B3 → Implemented), development sequence, Milestone 4 log.
- **Checks Actually Performed:**
  - Ran `python -m unittest discover -s ARES/tests -t ARES -v`: **51/51 tests passed**.
  - Confirmed: B3 selects from the higher-importance candidate when two candidates have equal uncertainty and distance.
  - Confirmed: `allow_human_review=False` config excludes HUMAN_REVIEW from the action space.
  - Confirmed: reserve guardrail prevents RECAPTURE to 2000m candidate with 5000 J budget.
  - Confirmed: candidate with benefit < `min_benefit_to_act` (0.05) is accepted as NONE.
  - Confirmed: B0, B1, B2 simulator tests still pass with no changes to the simulator.
- **Known Limitations:**
  - Joint score uses an **instantaneous greedy objective** per step — not a global trajectory optimisation. B3 does not look ahead across multiple future steps.
  - All uncertainty reduction rates (`RECAPTURE` 70%, `STRONGER_MODEL` 40%, `HUMAN_REVIEW` 95%) are `ASSUMED` starting values — not measured from physical experiments.
  - `HUMAN_REVIEW` (50 J, 95% reduction) tends to dominate the joint score due to the low energy denominator. This reflects the cheapness of queuing for human review in the model; tune `allow_human_review` and `min_cost_denominator_joules` to adjust.
  - No matched-budget policy comparison between B0, B1, B2, and B3 yet — requires controlled experiments.
  - SatQuery interface remains strictly provisional (`v1.0.0-provisional`).
  - **B4 remains `PLANNED`.**
- **Action Needed from SatQuery Owner:**
  - Review `ARES/docs/INTERFACE_PROPOSAL.md` when SatQuery work begins.

### Milestone 3: B2 Adaptive Computation — 2026-11-16
- **Summary:** Implemented B2 Adaptive Computation policy with a 5-branch per-candidate decision tree (accept / recapture / stronger-model / human-review / return-home). Refactored `BasePolicy` to expose an overridable `select_action()` method, and rewrote the simulator to delegate action selection to the policy (enabling full multi-action support). Added configurable thresholds in `B2AdaptiveComputationConfig` (all tagged `ASSUMED`). Added B2 to the policy registry.
- **Changed Files:**
  - `ARES/ares/policies/base.py`: Added `ActionSelectionDecision` NamedTuple and `select_action()` default method.
  - `ARES/ares/policies/b2_adaptive_computation.py`: New file — `B2AdaptiveComputationConfig`, `B2AdaptiveComputationPolicy`.
  - `ARES/ares/policies/registry.py`: B2 status → `IMPLEMENTED`; `get_policy("B2")` returns `B2AdaptiveComputationPolicy()`.
  - `ARES/ares/policies/__init__.py`: Exports for B2 symbols.
  - `ARES/ares/simulation/simulator.py`: Rewrote `run_mission()` to call `policy.select_action()` and handle all `ActionType` values.
  - `ARES/tests/test_b2_policy.py`: 6 new tests covering ranking, branch selection, downscaling, end-to-end simulation.
  - `ARES/tests/test_policies.py`: Updated registry expectations for B2.
  - `ARES/docs/DESIGN.md`: Added Section 6 (B2 decision logic, threshold table, reserve integration); updated policy arena table.
  - `ARES/README.md`: Updated policy table, development sequence, and this log.
- **Checks Actually Performed:**
  - Ran `python -m unittest discover -s ARES/tests -t ARES -v`: **40/40 tests passed**.
  - Confirmed B2 selects `NONE` for $u < 0.30$, `RECAPTURE` for high-$u$/high-$w$ within budget, `STRONGER_MODEL` for moderate-$u$, and downgrades correctly when recapture fails reserve.
  - Confirmed B0/B1 simulator tests still pass with the refactored simulator.
- **Known Limitations:**
  - All decision thresholds (`low_uncertainty=0.30`, `high_uncertainty=0.65`, `min_battery_fraction=0.35`) are `ASSUMED` starting values — not calibrated from real flight experiments.
  - Simulated outcome reduction rates (RECAPTURE ≈70%, STRONGER_MODEL ≈40%) are `SIMULATED` — no physical sensor measurements.
  - No matched-budget policy comparison between B0, B1, and B2 yet — requires controlled experiments.
  - SatQuery interface remains strictly provisional (`v1.0.0-provisional`).
  - B3 and B4 remain `PLANNED`.
- **Action Needed from SatQuery Owner:**
  - Review `ARES/docs/INTERFACE_PROPOSAL.md` when SatQuery work begins.

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
