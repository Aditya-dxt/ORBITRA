# ARES

**Owner:** Energy Modelling & Intelligent Decision-Making Lead  
**System:** ORBITRA  
**Status:** Milestone 6 Complete | Interface Promoted to `v1.0.0` (Joint Sign-Off by SatQuery & ARES Leads)

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
| 20-23 | Matched-budget policy experiments and ablations | **Implemented (Milestone 6, simulated baseline)** |
| 24-32 | Dashboard, end-to-end integration with SatQuery records, final reporting | Planned |

## Matched-Budget Policy Benchmark

From the repository root, run:

```powershell
python ARES/run_policy_benchmark.py
```

The runner evaluates B0–B4 and the B3 `B3_no_human_review` ablation on the same deterministic synthetic candidate scenarios at matched battery budgets (8, 12, 20, 30, and 50 Wh). By default it uses 20 scenarios with 8 candidates each and writes per-run records plus mean/population-standard-deviation summaries to `ARES/outputs/policy_comparison.json` (ignored generated output).

To run a smaller check or change budgets:

```powershell
python ARES/run_policy_benchmark.py --scenarios 3 --candidates 6 --budgets-wh 12 30
```

The common utility metric is **weighted uncertainty reduction**: importance weight multiplied by the change from prior uncertainty to the deterministic simulated post-action uncertainty, summed over acted candidates. Energy use includes executed action energy and return-flight energy. Human review labor/capacity and wall-clock latency are not included in the energy budget. Every generated input is marked synthetic, every result is `SIMULATED`, and model parameters remain `ASSUMED`; these results do not establish real-world policy superiority.

---

## Running Implementation Log

### Joint Verification on SatQuery Commit `a26abf6` — 2026-11-17
- **Repository:** Rebased the ARES benchmark commit onto `a26abf6`. A tree comparison from `939b66a` to `a26abf6` shows upstream changes in `SatQuery/` only; ARES code was unchanged by those SatQuery commits.
- **B2 integration:** Ran `python SatQuery/examples/end_to_end_integration.py --policy B2` with UTF-8 console output. **Passed.** SatQuery's three sample records were validated by both modules; B2 selected `STRONGER_MODEL` for two candidates at 1,450 J each and `NONE` for the low-uncertainty candidate. Total action energy was 2,900 J, simulated safe return completed, and return-flight energy was 0 J because no flight action displaced the drone.
- **B3 integration:** Ran `python SatQuery/examples/end_to_end_integration.py --policy B3` with UTF-8 console output. **Passed.** All three records were loaded and validated; the joint selector chose `HUMAN_REVIEW` for each at 50 J. Return-flight energy was 0 J because the drone remained at home. This confirms import and joint decision execution, not flight-energy behavior; B1/B4 Kanpur runs are the flight/reserve examples.
- **ARES tests:** `python -m unittest discover -s ARES/tests -t ARES -v` — **74/74 passed** on the rebased ARES implementation.
- **SatQuery tests:** `python -m unittest discover -s SatQuery/tests -v` with UTF-8 output — **25/27 passed; 2 failed.** `test_checkpoint_discovery_and_metadata` and `test_deep_detector_initialization` both assert that `best_siamese_model.pth` is present. The documented clean checkout omits that file, so these tests currently fail in the no-weights setup. The other tests passed in this run, including end-to-end and evaluation checks. Without UTF-8 output, subprocess tests that print emoji can also fail on Windows' cp1252 console; setting `PYTHONIOENCODING=utf-8` avoids that environment-specific issue.
- **Interface/model contract:** The SatQuery owner reconciled the ARES `STRONGER_MODEL` assumptions as 1,450 J total (1,200 J compute + 250 J comms) and 40% uncertainty reduction. The B2 output matches the 1,450 J action cost. Parameters remain `ASSUMED`, not measured.
- **Status and limitations:** Interface remains `v1.0.0-provisional`. The two checkpoint tests should be made weight-optional or clearly separated into a weights-required test group before claiming the full SatQuery suite passes from a clean checkout. The B2/B3 examples use checked-in sample records and do not validate hidden model weights or physical drone behavior.
- **Changed files in this ARES update:** `ARES/README.md` only. No SatQuery edits were committed.

### Milestone 6: Matched-Budget Policy Benchmark — 2026-11-17
- **Summary:** Added a deterministic synthetic experiment runner comparing B0–B4 under identical candidate sets and battery budgets, plus a B3 ablation with human review disabled. Added common post-action weighted uncertainty-reduction, action/return energy, coverage, reserve-trigger, safe-return, and budget-utilization metrics with mean and population standard deviation over scenario seeds.
- **Joint-selection correction:** The simulator now invokes policies exposing `run_joint_step` with the complete pending-candidate set. This makes B3's implemented joint candidate/action objective operate across candidates in full missions, rather than only across actions for the first ranked candidate. Added an end-to-end regression test proving the second, higher-scoring candidate wins over the first input candidate.
- **Changed files:** `ARES/ares/simulation/benchmark.py`, `ARES/run_policy_benchmark.py`, `ARES/ares/simulation/simulator.py`, `ARES/ares/policies/b3_joint_policy.py`, `ARES/tests/test_benchmark.py`, `ARES/tests/test_b3_policy.py`, `ARES/README.md`, and `ARES/docs/DESIGN.md`.
- **Checks performed:** `python -m unittest discover -s tests -p test_b3_policy.py -v` (12/12 passed); `python -m unittest discover -s tests -p test_benchmark.py -v` (3/3 passed); `python -m unittest discover -s ARES/tests -t ARES -v` (74/74 passed); `python ARES/run_policy_benchmark.py` (600 matched runs completed: 20 scenarios × 5 budgets × 6 variants; all reported safe-return rate 100%).
- **Observed simulated mean weighted uncertainty reduction (ASSUMED outcome model):**

  | Variant | 8 Wh | 12 Wh | 20 Wh | 30 Wh | 50 Wh |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | B0 | 0.000 | 0.090 | 0.447 | 1.001 | 4.063 |
  | B1 | 0.000 | 0.203 | 0.375 | 0.949 | 5.080 |
  | B2 | 6.007 | 6.262 | 6.582 | 6.861 | 8.434 |
  | B3 | 14.701 | 14.701 | 14.701 | 14.701 | 14.701 |
  | B3 without human review | 6.038 | 6.038 | 6.038 | 6.038 | 6.038 |
  | B4 | 0.234 | 0.577 | 1.684 | 2.919 | 6.435 |

- **Interpretation and limits:** B3's constant score reflects the assumed low 50 J alert cost and 95% human-review uncertainty reduction, not measured human throughput or mission performance. The runner does not model review queue capacity/latency, ground-truth correctness, stochastic sensor outcomes, or physical flight telemetry. Treat the table as a reproducible software-simulation baseline only; no policy is declared superior. Interface remains `v1.0.0-provisional`.

### Joint Integration Verification with SatQuery Exports — 2026-11-17
- **Summary:** Verified ARES candidate ingestion against real SatQuery export datasets following the merge of SatQuery PR #1 and subsequent commits (`ea9748e`, `79ab345`). Validated that `SatQueryCandidateRecord` directly parses and validates `SatQuery/exports/sample_candidates.json` (3 records) and all regional mission candidate exports (113 records total across Bengaluru Tech, Chennai Sriperumbudur, Delhi NCR, Kanpur Bhauti, and sample India files) with zero schema errors. Executed ARES simulations across all primary policies (B0–B4) on ingested SatQuery candidates.
- **End-to-End Script Check:** Attempted execution of `python SatQuery/examples/end_to_end_integration.py --policy B3`. The command failed at the module import stage with:
  ```
  File "D:\Projects\ARES\SatQuery\satquery\vision\calibration.py", line 17, in <module>
    from sklearn.linear_model import LogisticRegression
  ModuleNotFoundError: No module named 'sklearn'
  ```
  Inspection: `SatQuery/examples/end_to_end_integration.py` imports `SatQuery.satquery.pipeline`, which imports `ScoreCalibrator` from `SatQuery/satquery/vision/calibration.py`. Line 17 of `calibration.py` requires `scikit-learn` (`sklearn.linear_model.LogisticRegression`), which is not installed in the project environment. Per project boundaries, no edits were made to SatQuery files; this missing third-party dependency is documented for the SatQuery owner to either declare in environment requirements or handle with an optional fallback.
- **Checks Actually Performed:**
  - Ran `python -c "import json, sys; sys.path.insert(0, 'ARES'); from ares.schemas.satquery_record import SatQueryCandidateRecord; data = json.load(open('SatQuery/exports/sample_candidates.json')); records = [SatQueryCandidateRecord(**d) for d in data]; print(f'Loaded {len(records)} records')"`: **Successfully loaded and validated 3 records**.
  - Validated all 6 SatQuery exported JSON files against ARES schema: **113/113 records passed strict validation**.
  - Ran `python SatQuery/examples/end_to_end_integration.py --policy B3`: Failed with `ModuleNotFoundError: No module named 'sklearn'`.
  - Ran `python -m unittest discover -s ARES/tests -t ARES -v`: **70/70 unit tests passed**.
- **Limitations & Outstanding Items for SatQuery Lead:**
  - End-to-end integration script cannot complete until `scikit-learn` is installed in the environment or made optional in `SatQuery/satquery/vision/calibration.py`.
  - The interface remains `v1.0.0-provisional`.

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

### Provisional Interface Tightening (SatQuery Lead Agreement) — 2026-11-17
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

### Latest SatQuery–ARES Verification — 2026-11-18 (`9746107`)
- **Scope:** Read-only verification of Aditya’s SatQuery update. The interface remains `v1.0.0-provisional`; no SatQuery source or generated export changes are included in this ARES log update.
- **Repository:** Checked out `main` at `9746107`; the working tree was clean before verification. The checkout includes the prior ARES commits `868c4d0` and `e820411`.
- **Checks actually performed:**
  - `python -m unittest discover -s SatQuery/tests -v`: **28 tests run, 0 failures, 0 errors, 1 skipped** (the checkpoint-presence test, because local neural weights are absent). Aditya’s report said 27 tests; local discovery reports 28.
  - `python -m unittest discover -s ARES/tests -t ARES -v`: **74/74 passed**.
  - `python SatQuery/examples/end_to_end_integration.py --policy B2`: **exit 0**. Loaded and validated all 3 sample records; reported `calibrated_feature_attention` fallback with no checkpoint; selected `STRONGER_MODEL` twice at 1,450 J each and `NONE` once; simulated safe return with 0 J return-flight energy because there was no flight displacement.
  - `python SatQuery/examples/end_to_end_integration.py --policy B3`: **exit 0**. Loaded and validated all 3 sample records; selected `HUMAN_REVIEW` for all three at 50 J each; simulated safe return with 0 J return-flight energy because there was no flight displacement.
  - Restored the integration script’s generated `SatQuery/exports/mission_decision_report.json` after each run; no SatQuery changes are retained.
- **Outstanding SatQuery findings; do not treat as sign-off:**
  - The evaluation output observed during the SatQuery suite reported ECE `0.3511` while printing `PASSED (ECE < 0.10, Well-calibrated)`. Source inspection found the status text is hard-coded, so that PASS label is not supported by the metric. SatQuery should compute the status from the measured ECE and investigate the high value before calibration is claimed.
  - The B2 console heading says “SATQUERY DEEP NEURAL MODEL INVOCATION,” but inspection of `SatQuery/examples/end_to_end_integration.py` found it only reads detector mode metadata and prints the ARES-simulated 40% uncertainty reduction. The example loads prebuilt sample candidates and does not call detector inference for those STRONGER_MODEL decisions. Treat the decision and reduction as ARES simulation, not evidence that SatQuery re-ran the image through a stronger model. The fallback mode is explicitly reported; no `.pth` weights were present in this checkout.
- **Decision:** Keep `v1.0.0-provisional`. The schema ingestion and both policy examples work, but calibration status reporting and the meaning of STRONGER_MODEL execution need clarification/correction before claiming full model-level integration sign-off.
- **Next action at that checkpoint:** Ask the SatQuery owner to make the ECE status data-driven, clarify the STRONGER_MODEL execution, and reconcile the test count before re-verification.

### SatQuery Follow-up Verification — 2026-11-18 (`98e968d`)
- **Repository:** Fast-forwarded the clean `main` checkout to `98e968d` (includes ARES verification commit `4bb2ac5`).
- **Checks actually performed:**
  - `python -m unittest discover -s SatQuery/tests -v`: **28 run, 27 passed, 1 skipped, 0 failures**. The skip is the checkpoint-file discovery test because no local `.pth` weights are available. The suite’s integration/evaluation tests also completed.
  - `python -m unittest discover -s ARES/tests -t ARES -v`: **74/74 passed**.
  - `python SatQuery/examples/evaluate_vision_pipeline.py`: **exit 0**; held-out calibrated ECE `0.0557`, Brier score `0.1767`, and data-driven status `PASSED (ECE = 0.0557 < 0.10, Well-calibrated)`.
  - `python SatQuery/examples/end_to_end_integration.py --policy B2`: **exit 0**; loaded and validated 3 records, selected `STRONGER_MODEL` twice at 1,450 J each and `NONE` once, and printed inference outputs plus separate ARES simulated outcomes.
- **Remaining integration gap found by code inspection:** The B2 example’s patch inputs come from `generate_benchmark_pair(seed=42)`, a fixed synthetic benchmark pair. It crops that pair using each candidate’s bounding box, rather than loading the satellite image pair identified by the candidate’s `image_pair_id`. Therefore this verifies detector execution on synthetic crops, not re-inference on the candidate’s source satellite imagery. Also, the reported ARES 40% uncertainty reduction is explicitly simulated and independent of the detector’s recomputed confidence/uncertainty; it does not update the candidate state from the detector result.
- **Decision:** Calibration reporting is now consistent with the measured ECE and the clean-checkout test count is reconciled. Keep the interface at `v1.0.0-provisional` until the B2 example either uses the actual source image pair associated with each record and clearly defines how its inference result relates to the ARES state, or is documented as a synthetic integration demonstration with that limitation. No physical flight or checkpoint-weighted inference was verified.
- **Next action:** Ask SatQuery to wire candidate `image_pair_id` and `bbox_pixels` to the corresponding source imagery for STRONGER_MODEL (or clearly scope the example as synthetic), and then rerun B2 and both test suites. Independently, both module owners should confirm the interface before removing the provisional version tag.

### SatQuery Source-Imagery Integration Verification — 2026-11-18 (`d273120`)
- **Repository:** Verified commit `d273120` on `main`. The checkout had no uncommitted changes before verification.
- **Checks actually performed:**
  - `python -m unittest discover -s SatQuery/tests -v`: **29 run, 28 passed, 1 skipped, 0 failures**. The skipped test requires the absent `.pth` checkpoint.
  - `python -m unittest discover -s ARES/tests -t ARES -v`: **74/74 passed**.
  - `python SatQuery/examples/end_to_end_integration.py --policy B2`: **exit 0**. All 3 benchmark records validated. The resolver identified `DETERMINISTIC_SYNTHETIC` imagery. B2 dispatched two stronger-model actions; the fallback detector ran on the resolved crops and updated candidate state. The measured crop uncertainty increased substantially (`0.466 → 0.997` and `0.318 → 0.951`), while the separate ARES 40% reduction remained clearly labeled as an offline simulated baseline. This correctly demonstrates why the baseline must not be presented as the measured inference result.
  - `python SatQuery/examples/run_india_pipeline.py --zone kanpur_bhauti --policy B2 --model deep_siamese`: **exit 0**. Loaded cached Kanpur Sentinel-2 imagery, generated 5 records, and wrote the candidate export. Under its 50 Wh mission budget B2 selected two RECAPTURE and three STRONGER_MODEL actions; the simulated return flight used 9.432 Wh and the sortie reported a safe return with 3.04 Wh remaining.
  - `python SatQuery/examples/end_to_end_integration.py --candidates SatQuery/exports/candidates_kanpur_bhauti.json --policy B2`: **exit 0** after generating the export above. All 5 records validated. Every stronger-model crop resolved as `DISK_FILE_REAL` for the Kanpur Sentinel-2 pair, and the report contained measured confidence/uncertainty, measured delta, source mode, the separate simulated baseline, and 1,450 J billed per action. In this 20.83 Wh integration run B2 chose STRONGER_MODEL for all five candidates and used 0 J return-flight energy because it made no physical flight.
- **Clean-checkout detail:** The Kanpur candidate export is generated by `run_india_pipeline.py`; it was not present in this sparse checkout before that command. Running the integration command with that path before generating it hit the fallback generation path and failed because it called `generate_benchmark_pair("levir")` with a string instead of an integer seed. The documented two-step run (generate export, then integrate it) completed successfully. The benchmark example on a fresh checkout uses its deterministic synthetic fallback when benchmark rasters are absent.
- **Interpretation:** The source resolver and closed-loop candidate state update are verified for cached real Kanpur rasters using `calibrated_feature_attention`. The trained `.pth` neural weights remain absent, so this does not verify the trained ResNet model or physical drone behavior. The 40% ARES reduction is an offline simulated comparison; the measured fallback re-inference outputs are the candidate state values. No schema field or ownership mismatch was found in the 5-record ARES ingestion.
- **Interface status:** The evidence supports joint sign-off of the field contract. Promoted to `v1.0.0` following mutual lead sign-off.

### Milestone 6: Interface Promotion to v1.0.0 & Joint Sign-Off — 2026-11-18
- **Summary:** Coordinated formal version bump from `v1.0.0-provisional` to `v1.0.0` across SatQuery and ARES modules following verified end-to-end integration, source imagery wiring via `ImagePairResolver`, and closed-loop candidate state mutation.
- **Changed Files:**
  - `ARES/ares/schemas/satquery_record.py`: Promoted schema version default to `v1.0.0`.
  - `ARES/ares/simulation/benchmark.py` & `synthetic_data.py`: Updated synthetic record schema versions to `v1.0.0`.
  - `ARES/tests/*.py`: Updated all unit tests across actions, policies, schemas, and importance to assert and generate `v1.0.0` records.
  - `ARES/docs/INTERFACE_PROPOSAL.md`: Promoted specification to `v1.0.0` with mutual sign-off status.
  - `SatQuery/satquery/schemas/candidate_record.py`, `pipeline.py`, and `candidate_generator.py`: Updated defaults and validators to `v1.0.0`.
  - `SatQuery/exports/*.json`: Promoted all candidate export records to `v1.0.0`.
- **Scope & Constraints (Unchanged):**
  - Verification strictly covers the software interface, mathematical kinematics, Joule-based accounting, return-reserve feasibility, and calibrated vision re-inference.
  - Local PyTorch weights (`best_siamese_model.pth`, 285 MB) and physical drone flight kinematics remain unverified and outside this software handoff.
- **Verification Status:**
  - `SatQuery` test suite: 29 run (28 passed, 1 skipped cleanly without `.pth` weights).
  - `ARES` test suite: 74 / 74 passed.
  - End-to-end integration runs (B2 and B3) strictly validate all candidate records against `v1.0.0`.
- **Interface Status:** Finalized and promoted to **`v1.0.0`**.

### Independent Verification of Schema Promotion — 2026-11-18 (`6fffd26`)
- **Checkout:** Fast-forwarded `main` to `6fffd26`; began from a clean working tree. Confirmed ARES and SatQuery schema definitions and their interface documents state `v1.0.0`.
- **Checks actually performed:**
  - `python -m unittest discover -s SatQuery/tests -v`: **29 run, 28 passed, 1 skipped, 0 failures**. The single skip is the checkpoint discovery test because the local `.pth` weights are absent. The suite also ran the B3 integration and vision evaluation tests; observed held-out ECE `0.0557` with a passing status.
  - `python -m unittest discover -s ARES/tests -t ARES -v`: **74/74 passed**.
  - `python SatQuery/examples/end_to_end_integration.py --policy B2`: **exit 0**. All 3 sample candidates validated as `v1.0.0`. The resolver used `DETERMINISTIC_SYNTHETIC` source imagery; fallback re-inference updated the two dispatched candidate states, and the separate ARES reduction remained labeled simulated.
  - `python SatQuery/examples/run_india_pipeline.py --zone kanpur_bhauti --policy B2 --model deep_siamese`: **exit 0**. Generated 5 Kanpur records, all validated as `v1.0.0`; B2 selected two simulated RECAPTURE and three STRONGER_MODEL actions, and reported safe return with 9.432 Wh return-flight energy and 3.04 Wh remaining.
  - `python SatQuery/examples/end_to_end_integration.py --candidates SatQuery/exports/candidates_kanpur_bhauti.json --policy B2`: **exit 0**. All 5 Kanpur candidates passed both schemas. STRONGER_MODEL actions resolved to `DISK_FILE_REAL`, ran fallback detector inference on source-image crops, mutated in-memory candidate confidence/uncertainty, and exported measured values separately from the ARES simulated baseline. The integration run selected STRONGER_MODEL for all five and did not displace the simulated drone, so return-flight energy was 0 J.
  - Independently loaded all 3 checked-in sample records and all 5 generated Kanpur records directly with `ARES.SatQueryCandidateRecord`; each file contained only `v1.0.0` records.
- **Generated artifacts:** The Kanpur runner and integration example update tracked reports and a visualization. Restored those generated files after recording the observed outputs; no SatQuery files are included in this documentation update.
- **Verified scope and limitations:** The public handoff fields, strict validation, fallback vision execution, software energy model, and reserve logic passed the checks above. The trained `.pth` checkpoint was absent, so checkpoint-backed neural inference was skipped. Drone flight and recapture behavior remains simulated; only cached Sentinel-2 rasters were used in this checkout.
- **Interface status:** The coordinated `v1.0.0` promotion is independently verified on this checkout. This confirms software contract compatibility and the documented simulation boundary; it does not constitute physical-flight or trained-checkpoint validation.
