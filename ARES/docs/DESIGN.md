# ARES Technical Design Document

**Status:** Research Prototype — Architecture & Milestone 3 B2 Adaptive Computation  
**Module:** ARES (Energy Modelling & Intelligent Decision-Making Engine)  
**Parent System:** ORBITRA  
**Owner:** Energy Modelling & Intelligent Decision-Making Lead  

---

## 1. System Mission & Scope

ARES is the decision and energy-governance module of ORBITRA. While SatQuery identifies potential change candidates from satellite image pairs, ARES answers:
> *What should the mission do next, given candidate uncertainty, operational importance, and available energy—while strictly protecting safe return?*

### Core Architectural Separation
1. **Evidence vs. Decision:** SatQuery generates candidate detections with statistical confidence and uncertainty. ARES consumes those records, assigns mission-domain importance, evaluates action costs and return-reserve feasibility, and selects actions.
2. **Confidence vs. Importance:** A high-confidence candidate detection may have low operational importance (e.g., slight seasonal vegetation shift in open wasteland), while an uncertain detection in critical infrastructure has high importance. ARES decouples these two concepts explicitly.
3. **Internals vs. Display:** All energy accounting, kinematics, and reserve calculations operate strictly in **Joules (J)**. Watt-hours (Wh) are derived strictly for user display ($1\text{ Wh} = 3600\text{ J}$).
4. **Data Provenance:** Every metric, assumption, and outcome is explicitly tagged as `ASSUMED`, `SIMULATED`, or `MEASURED`.

---

## 2. Policy Arena (B0–B4 & Supplementary Baselines)

### 2.1 Required ARES Policies (B0–B4)
ARES implements and evaluates five primary policies across matched energy budgets:

| Policy ID | Policy Name | Description | Current Status |
| --- | --- | --- | --- |
| **B0** | Fixed Pass | Processes candidate targets in a predetermined sequence (e.g., discovery order / spatial index) until energy constraints or return reserves mandate return. | **Implemented (Milestone 1)** |
| **B1** | Uncertainty First | Prioritizes candidates with highest detector uncertainty first, targeting areas where additional data/verification yields maximum entropy reduction. | **Implemented (Milestone 1)** |
| **B2** | Adaptive Computation | Dynamically allocates computation depth (e.g., lightweight on-edge detector vs. high-capacity model) per candidate based on uncertainty and importance. | **Implemented (Milestone 3)** |
| **B3** | Joint Policy | Jointly optimizes both the candidate visit sequence and the inspection/computation action level under total energy constraints. | Planned |
| **B4** | Greedy Benefit-per-Energy | Selects the next action that maximizes the ratio of expected mission benefit to total energy expenditure: $\Delta B / \Delta E$. | Planned |

### 2.2 Supplementary Baselines (P1, P2, P5)
To support comparative research without duplicating B0–B4, ARES recognizes three supplementary reference baselines:
- **P1 · Pure Confidence-Ranked Baseline:** Ranks targets strictly by model confidence (ignoring uncertainty and importance).
- **P2 · Pure Importance-Ranked Baseline:** Ranks targets strictly by operational importance weights (ignoring model uncertainty).
- **P5 · Zone-Weighted Spatial Baseline:** Evaluates candidate priority weighted by geographic zone priorities. Included as a baseline distinct from B4 only if its objective function diverges significantly from benefit-per-energy.

---

## 3. Energy Modeling & Return Reserve Architecture

### 3.1 Kinematics and Energy Breakdown (All Joules)
Drone energy consumption during a verification sortie is modeled across five operational phases:
1. **Transit Flight ($E_{\text{flight}}$):** Energy consumed cruising at nominal speed $v$ over distance $d$.
   $$t_{\text{transit}} = \frac{d}{v}, \quad E_{\text{flight}} = P_{\text{flight}} \cdot t_{\text{transit}}$$
2. **On-Station Hover ($E_{\text{hover}}$):** Energy consumed hovering over the target region for observation time $t_{\text{hover}}$.
   $$E_{\text{hover}} = P_{\text{hover}} \cdot t_{\text{hover}}$$
3. **Sensor Capture ($E_{\text{capture}}$):** Energy consumed powering payload sensors and capturing high-resolution frames.
4. **Onboard Computation ($E_{\text{compute}}$):** Energy consumed by embedded inference hardware during verification analysis.
5. **Telemetry / Comms ($E_{\text{comms}}$):** Energy consumed transmitting verification payloads and telemetry to the ground station.

### 3.2 Starting Assumptions & Parameter Meanings
- **Kinematic Drag Exponent ($k_{\text{drag}} = 2$):** Aerodynamic power scaling assumption where cruising power relates quadratically to airspeed ($P \propto v^2$). Tagged `ASSUMED`.
- **Operational Importance Weights ($w \in \{1.0, 2.0, 4.0\}$):**
  - Low priority = $1.0$ (tagged `ASSUMED`)
  - Medium priority = $2.0$ (tagged `ASSUMED`)
  - High priority = $4.0$ (tagged `ASSUMED`)

### 3.3 Return-Reserve Guardrail Rule & Reconciliation of $k=2$ vs. 20% Allowance
The technical blueprint proposes:
$$E_{\text{reserve}} = E_{\text{return}}(\mathbf{x}) + k \cdot \sigma_E$$
where $k \in [1.5, 2.0]$ is a statistical coverage factor representing the number of standard deviations $\sigma_E$ of flight energy estimation uncertainty.

#### Reconciliation & Implementation:
1. **Statistical Meaning of $k=2$:** In Gaussian estimation error models, $k = 2.0$ corresponds to a two-sided $\approx 95\%$ confidence coverage interval.
2. **Reconciliation with 20% Relative Allowance:** When absolute standard deviation $\sigma_E$ (in Joules) is not yet calibrated from physical flight logs, uncertainty is modeled as a relative estimation error. Assuming a coefficient of variation $\text{CoV} = \sigma_E / E_{\text{return\_nominal}} \approx 10\%$ ($0.10$), applying coverage factor $k = 2.0$ gives:
   $$\text{Uncertainty Allowance} = k \cdot \sigma_E = 2.0 \cdot (0.10 \cdot E_{\text{return\_nominal}}) = 0.20 \cdot E_{\text{return\_nominal}} \quad (20\%)$$
3. **Flexible Single Allowance in Code:**
   The implementation in `ReturnReserveCalculator` accepts either:
   - **Absolute uncertainty standard deviation in Joules:** $\text{UncertaintyAllowance} = k \cdot \sigma_E$ (when $\sigma_E > 0$ is provided from flight telemetry).
   - **Relative uncertainty fraction:** $\text{UncertaintyAllowance} = \alpha_{\text{margin}} \cdot E_{\text{return\_nominal}}$ (default $\alpha = 0.20$, representing $k=2$ with $10\%$ CoV).
   **Crucially, only ONE uncertainty allowance is applied**; they are never combined to prevent double-counting.
4. **Separate Additive Wind Margin ($E_{\text{wind}}$):** Headwinds and adverse gusts are parameterized as a dedicated additive energy parameter $E_{\text{wind}}$ (in Joules), cleanly decoupled from distance/flight-time uncertainty.
5. **Post-Action Position Evaluation:** The return trajectory energy $E_{\text{return}}$ must be evaluated from the **candidate's coordinates after the proposed action**, not from the initial launch origin or current position.

$$\text{Reserve Required: } E_{\text{reserve}}(\mathbf{x}_{\text{after}}) = E_{\text{return\_nominal}}(\mathbf{x}_{\text{after}} \to \mathbf{x}_{\text{home}}) + \text{UncertaintyAllowance} + E_{\text{wind}}$$

$$\text{Feasibility Gate: } E_{\text{remaining}} - E_{\text{action\_total}} \ge E_{\text{reserve}}(\mathbf{x}_{\text{after}})$$

> [!WARNING]
> All reserve allowances, $k=2$ coverage, and wind margins are **unvalidated engineering assumptions** (`ASSUMED`), not certified physical safety guarantees. Flights must never rely on software simulation models for real-world aviation safety.

---

## 4. Mission Importance Scoring Model

Mission importance captures human and institutional priority, reflecting how costly an unverified or missed change is at a specific site. It is modeled independently of vision confidence:

1. **Category Mapping:** Semantic classes map to base tiers $\{1.0, 2.0, 4.0\}$:
   - **High ($4.0$):** `government_land_encroachment`, `industrial_spill`, `water_body_change`, `critical_infrastructure`.
   - **Medium ($2.0$):** `flooded_cropland`, `vegetation_clearance`, `road_obstruction`.
   - **Low ($1.0$):** `new_construction`, `seasonal_vegetation`, `ordinary_land`.
2. **Zone Multipliers:** Geographic zoning polygons apply scalar multipliers (e.g., $1.5\times$ for protected conservation reserves, $2.0\times$ for defence buffer zones).
3. **Tagging:** Assigned weights are stored in `AresCandidateState.importance_weight` and tagged `ASSUMED`.

---

## 5. Action Cost & Outcome Models

ARES models three distinct evidence-acquisition and verification actions:

| Action | Physical / Compute Modality | Energy Breakdown (Joules) | Duration / Latency | Capacity Cost | Simulated Outcome Behavior |
| --- | --- | --- | --- | --- | --- |
| **`RECAPTURE`** | UAV physical sortie | Flight transit ($P \cdot d / v$) + Hover ($2200\text{ J}$) + Sensor ($450\text{ J}$) + Compute ($350\text{ J}$) + Comms ($120\text{ J}$). | Flight time + $10\text{s}$ hover + $1\text{s}$. | $0.0$ units | Cuts uncertainty by $\sim 70\%$; polarizes confidence toward ground truth. |
| **`STRONGER_MODEL`** | Edge accelerator or ground offload | Heavy inference compute ($1200\text{ J}$) + image tile offload comms ($250\text{ J}$). **Zero flight/hover energy.** | $2.5\text{s}$ inference latency. | $0.0$ units | Cuts uncertainty by $\sim 40\%$; refines confidence calibration. |
| **`HUMAN_REVIEW`** | Analyst triage queue | Alert packet telemetry transmission ($50\text{ J}$). **Zero flight/hover energy.** | Queue turnaround (assumed $180\text{s}$). | $1.0$ queue slot | Resolves uncertainty conclusively ($u' \le 0.05$); assigns verified ground truth label. |

All costs are tagged `ASSUMED`. All simulated outcome records are tagged `SIMULATED` and prefixed with `[SIMULATED]`.

---

## 6. Policy B2: Adaptive Computation Decision Logic

**Status:** Implemented (Milestone 3) — `ARES/ares/policies/b2_adaptive_computation.py`

B2 replaces the uniform "always try RECAPTURE" rule of B0/B1 with a **5-branch decision tree** that selects the cheapest sufficient action for each candidate, trading off uncertainty reduction, mission importance, and remaining battery.

### 6.1 Candidate Ranking

Before the decision loop, B2 ranks candidates in **descending order of expected information gain proxy**:

$$\text{rank score} = \text{importance\_weight} \times \text{uncertainty}$$

Higher-importance and higher-uncertainty candidates are evaluated first, so budget is spent where it matters most.

### 6.2 Per-Candidate Decision Tree (5 Branches)

For each candidate with uncertainty $u$, importance weight $w$, and battery fraction $f = E_{\text{remaining}} / E_{\text{initial}}$:

| Branch | Condition | Selected Action | Rationale |
|--------|-----------|-----------------|-----------|
| **1 — Accept** | $u < u_{\text{low}}$ | `NONE` (skip) | Detector is already confident enough; no verification value. |
| **2 — Recapture** | $u \ge u_{\text{high}}$ **AND** $w \ge w_{\text{high}}$ **AND** $f \ge f_{\text{min\_flight}}$ **AND** reserve feasible | `RECAPTURE` | High uncertainty + high importance justifies full UAV sortie. |
| **3 — Stronger Model** | RECAPTURE fails reserve, or $u_{\text{low}} \le u < u_{\text{high}}$ (moderate) | `STRONGER_MODEL` **if** reserve feasible | Compute-only verification; no flight cost; acceptable when recapture is blocked or uncertainty is moderate. |
| **4 — Human Review** | Energy too tight for `STRONGER_MODEL` **AND** `allow_human_review_fallback` is `True` | `HUMAN_REVIEW` | Minimal energy ($50\ \text{J}$ comms); conclusive resolution via analyst queue. |
| **5 — Return Home** | All actions infeasible | `RETURN_HOME` | Reserve guardrail forces mission abort. |

### 6.3 Configurable Thresholds (`B2AdaptiveComputationConfig`)

All thresholds are tagged **`ASSUMED`** — they are starting values, not calibrated from experiments.

| Parameter | Default Value | Meaning | Tag |
|-----------|---------------|---------|-----|
| `low_uncertainty_threshold` | `0.30` | Below this, no action is taken (candidate accepted). | `ASSUMED` |
| `high_uncertainty_threshold` | `0.65` | At or above this, recapture is considered if importance is high. | `ASSUMED` |
| `high_importance_threshold` | `4.0` | Minimum importance weight for triggering recapture. | `ASSUMED` |
| `min_battery_fraction_for_flight` | `0.35` | Minimum remaining battery fraction before flight actions are permitted. | `ASSUMED` |
| `allow_human_review_fallback` | `True` | Whether to escalate to human review when compute budget is tight. | `ASSUMED` |

### 6.4 Reserve Check Integration

Every action candidate (RECAPTURE, STRONGER_MODEL, HUMAN_REVIEW) is passed through the existing `ReturnReserveCalculator.is_feasible()` guardrail before being selected:

- **Flight actions** (`RECAPTURE`): post-action position is the **target candidate location** (drone will have flown there).
- **Non-flight actions** (`STRONGER_MODEL`, `HUMAN_REVIEW`): post-action position is the **current drone position** (no movement).
- If the check fails, the branch downgrades to the next cheaper action.

> [!IMPORTANT]
> The reserve guardrail is enforced unconditionally. No B2 path can override or bypass it. All energy margin values are `ASSUMED` and not certified safety guarantees.

### 6.5 Simulated Outcome Assumptions (all `SIMULATED`)

| Action | Uncertainty Reduction | Confidence Shift | Tag |
|--------|-----------------------|-----------------|-----|
| `RECAPTURE` | ×0.30 of original (≈70% cut) | Polarized toward ground truth | `SIMULATED` |
| `STRONGER_MODEL` | ×0.60 of original (≈40% cut) | Refined calibration | `SIMULATED` |
| `HUMAN_REVIEW` | Fixed $u' \le 0.05$ | Verified label assigned | `SIMULATED` |

---

## 7. Decision Ledger & Traceability

Every decision evaluated by ARES produces an immutable `DecisionRecord` containing:
- `timestamp`: ISO-8601 simulation timestamp.
- `candidate_id`: Identifier of candidate being evaluated.
- `policy_id`: Active policy (`B0`, `B1`, etc.).
- `action`: Evaluated action (`RECAPTURE`, `STRONGER_MODEL`, `HUMAN_REVIEW`, `RETURN_HOME`, `DEFER`).
- `action_energy_joules`: Total projected action cost in Joules.
- `action_energy_wh`: Display equivalent in Watt-hours.
- `battery_before_joules`: Battery state before action.
- `battery_after_joules`: Projected battery state after action.
- `required_reserve_joules`: Safe return reserve required from post-action location.
- `reserve_feasible`: Boolean gate result.
- `estimated_benefit`: Calculated mission utility of action.
- `reason`: Human-readable explanation of why the action was selected or rejected.
- `simulated_outcome`: Explicitly labeled `[SIMULATED]` execution feedback.
- `provenance`: `SIMULATED` tag.

---

## 8. Candidate State Machine

```
        [ SatQuery Detection Record ]
                     │
                     ▼
                 [ PENDING ]
                     │
          ┌──────────┴──────────┐
          │ (Reserve Feasible)   │ (Reserve Infeasible)
          ▼                      ▼
    [ INSPECTED ]          [ DEFERRED ]
          │                      │
          ▼                      ▼
  (Ledger Updated)       (Return Initiated)
```

1. **PENDING:** Ingested from SatQuery and assigned an importance weight.
2. **INSPECTED:** Action selected, validated by reserve guardrail, and executed in simulation.
3. **DEFERRED:** Reserve guardrail prohibited execution; preserved for potential future sortie.
4. **SKIPPED:** Evaluated as zero-utility or unviable under active policy.
