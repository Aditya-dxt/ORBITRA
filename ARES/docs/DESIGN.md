# ARES Technical Design Document

**Status:** Research Prototype — Initial Architecture Foundation  
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
| **B2** | Adaptive Computation | Dynamically allocates computation depth (e.g., lightweight on-edge detector vs. high-capacity model) per candidate based on uncertainty and importance. | Planned |
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

### 3.2 Starting Assumptions ($k=2$, Importance Weights)
- **Kinematic Drag Exponent ($k = 2$):** Aerodynamic power scaling assumption where power relates quadratically to relative airspeed in transit calculations ($P \propto v^k$). Configurable starting assumption tagged `ASSUMED`.
- **Operational Importance Weights ($w \in \{1, 2, 4\}$):**
  - Low priority = $1.0$ (tagged `ASSUMED`)
  - Medium priority = $2.0$ (tagged `ASSUMED`)
  - High priority = $4.0$ (tagged `ASSUMED`)

### 3.3 Return-Reserve Guardrail Rule
To prevent drone loss, ARES enforces a mandatory safe-return reserve before committing to any action:
1. **Post-Action Position Evaluation:** The return trajectory energy $E_{\text{return}}$ must be evaluated from the **candidate's coordinates after the proposed action**, not from the initial launch origin or current position.
2. **Single Uncertainty Allowance ($\alpha_{\text{reserve}}$):** To prevent double-counting safety margins, a single reserve uncertainty multiplier (e.g., $\alpha = 0.20$ or $20\%$) is applied to nominal return energy.
3. **Explicit Wind Margin ($E_{\text{wind}}$):** Headwinds and adverse gusts are parameterized as a dedicated additive energy parameter $E_{\text{wind}}$ (in Joules), cleanly decoupled from distance uncertainty.

$$\text{Reserve Required: } E_{\text{reserve}}(\mathbf{x}_{\text{after}}) = (1 + \alpha_{\text{reserve}}) \cdot E_{\text{return\_nominal}}(\mathbf{x}_{\text{after}} \to \mathbf{x}_{\text{home}}) + E_{\text{wind}}$$

$$\text{Feasibility Gate: } E_{\text{remaining}} - E_{\text{action\_total}} \ge E_{\text{reserve}}(\mathbf{x}_{\text{after}})$$

If this inequality is violated, the action is marked **INFEASIBLE**, candidate status is marked **DEFERRED**, and the drone initiates immediate return to home base.

---

## 4. Decision Ledger & Traceability

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

## 5. Candidate State Machine

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
