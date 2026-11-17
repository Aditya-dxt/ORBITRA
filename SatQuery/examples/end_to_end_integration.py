"""End-to-end integration example connecting SatQuery and ARES.

Demonstrates:
1. Loading SatQuery exported candidate records (or generating live candidates)
2. Validating against the agreed SatQueryCandidateRecord schema (v1.0.0-provisional)
3. Ingesting into ARES candidate state manager (AresCandidateState)
4. Decorating with decoupled mission importance scoring
5. Applying ARES policies (B0, B1, B2, or B3) under defined energy budget and return reserve
6. Logging action, reason, estimated benefit, energy cost, and feasibility
7. Rendering an explainable mission dashboard and exporting structured report
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

# Add workspace root to sys.path to resolve ARES and SatQuery packages
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

ARES_ROOT = os.path.join(REPO_ROOT, "ARES")
if ARES_ROOT not in sys.path:
    sys.path.insert(0, ARES_ROOT)

from SatQuery.satquery.schemas.candidate_record import SatQueryCandidateRecord
from SatQuery.satquery.pipeline import run_pipeline_demo

# ARES imports
from ares.schemas.satquery_record import SatQueryCandidateRecord as AresCandidateRecord
from ares.schemas.candidate_state import (
    ActionType,
    AresCandidateState,
    CandidateStatus,
    ImportanceTier,
)
from ares.energy.units import joules_to_wh
from ares.energy.model import DroneEnergyModel
from ares.energy.reserve import ReturnReserveCalculator
from ares.policies.b0_fixed_pass import B0FixedPassPolicy
from ares.policies.b1_uncertainty_first import B1UncertaintyFirstPolicy
from ares.policies.b2_adaptive_computation import B2AdaptiveComputationPolicy
from ares.policies.b3_joint_policy import B3JointPolicy
from ares.simulation.simulator import MissionSimulationConfig, MissionSimulator


def get_policy_instance(policy_id: str):
    """Factory for selecting ARES policy."""
    pid = policy_id.upper()
    if pid == "B0":
        return B0FixedPassPolicy()
    elif pid == "B1":
        return B1UncertaintyFirstPolicy()
    elif pid == "B2":
        return B2AdaptiveComputationPolicy()
    elif pid == "B3":
        return B3JointPolicy()
    else:
        raise ValueError(f"Unknown policy '{policy_id}'. Available: B0, B1, B2, B3")


def run_integration(
    candidates_json_path: Optional[str] = None,
    policy_name: str = "B3",
    battery_wh: float = 20.83,  # 75,000 J
    export_report_path: Optional[str] = None,
) -> Dict:
    """Execute end-to-end integration run."""
    print("=" * 80)
    print("🛰️  ORBITRA JOINT INTEGRATION: SatQuery (Vision) -> ARES (Decision & Energy)")
    print("=" * 80)

    # 1. Load or Generate SatQuery Records
    if candidates_json_path and os.path.exists(candidates_json_path):
        print(f"\n📂 [Stage 1] Loading SatQuery candidates from: {candidates_json_path}")
        with open(candidates_json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    else:
        print("\n⚙️  [Stage 1] Running SatQuery pipeline to generate live candidate change records...")
        temp_export = os.path.join(REPO_ROOT, "SatQuery", "exports", "sample_candidates.json")
        res = run_pipeline_demo(output_json=temp_export)
        with open(temp_export, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

    print(f"   Loaded {len(raw_data)} candidate records from SatQuery.")

    # 2. Validate Against Interface Schema
    print("\n🔍 [Stage 2] Validating records against schema contract (v1.0.0-provisional)...")
    validated_records = []
    for item in raw_data:
        # Validate through SatQuery schema
        sq_rec = SatQueryCandidateRecord(**item)
        # Validate through ARES schema
        ares_rec = AresCandidateRecord(**item)
        validated_records.append((sq_rec, ares_rec))

    print(f"   ✓ All {len(validated_records)} records strictly validated by both SatQuery and ARES.")

    # 3. Import and Ingest into ARES Candidate States
    print("\n📦 [Stage 3] Importing into ARES Candidate State Manager...")
    candidate_states: List[AresCandidateState] = []
    for sq_rec, ares_rec in validated_records:
        state = AresCandidateState(detection=ares_rec)
        # Decorate with mission importance based on predicted change category
        change_type = sq_rec.predicted_change.lower()
        if "construction" in change_type or "road" in change_type:
            tier = ImportanceTier.HIGH
        elif "clearing" in change_type or "deforestation" in change_type:
            tier = ImportanceTier.MEDIUM
        else:
            tier = ImportanceTier.LOW
        state.set_importance(tier)

        candidate_states.append(state)
        print(
            f"   • Candidate {sq_rec.candidate_id}: Class='{sq_rec.predicted_change}', "
            f"Conf={sq_rec.confidence:.3f}, Uncert={sq_rec.uncertainty:.3f}, "
            f"Local=[x={sq_rec.region.local_grid.x_meters:.1f}m, y={sq_rec.region.local_grid.y_meters:.1f}m], "
            f"Assigned Importance={state.importance_weight.value:.1f} [{tier.name}]"
        )

    # 4. Configure Mission Energy & Reserve Filter
    battery_joules = battery_wh * 3600.0
    config = MissionSimulationConfig(initial_battery_joules=battery_joules)
    simulator = MissionSimulator(config=config)
    policy = get_policy_instance(policy_name)

    print(f"\n⚡ [Stage 4] Applying ARES Policy {policy_name} ({policy.policy_name})...")
    print(f"   Initial Energy Budget: {battery_wh:.2f} Wh ({battery_joules:,.0f} Joules)")
    print(f"   Return Reserve Rule: Enforced from candidate post-action position back to home base.")

    # 5. Run Mission Simulation
    report = simulator.run_mission(policy=policy, candidates=candidate_states)

    # 6. Display Explainable Decision Dashboard
    print("\n" + "=" * 80)
    print(f"📊 ARES EXPLAINABLE DECISION LOG ({report.policy_name})")
    print("=" * 80)
    print(f"{'Step':<5} | {'Candidate ID':<22} | {'Action':<15} | {'Cost (Wh)':<10} | {'Reserve Feasible':<17} | {'Reason'}")
    print("-" * 110)

    decision_entries = []
    for idx, rec in enumerate(simulator.ledger.records, start=1):
        cand_id = rec.candidate_id or "HOME / SYSTEM"
        action_name = rec.selected_action.value if hasattr(rec.selected_action, "value") else str(rec.selected_action)
        cost_wh = rec.action_energy_wh
        feasible = str(rec.reserve_feasible)
        reason = rec.reason

        print(f"{idx:<5} | {cand_id:<22} | {action_name:<15} | {cost_wh:<10.3f} | {feasible:<17} | {reason}")
        decision_entries.append({
            "step": idx,
            "candidate_id": cand_id,
            "action": action_name,
            "cost_wh": cost_wh,
            "reserve_feasible": rec.reserve_feasible,
            "reason": reason,
        })

    print("-" * 110)
    print(f"Safe Return Completed:  {report.safe_return_completed}")
    print(f"Initial Battery:        {report.initial_battery_wh:.2f} Wh ({report.initial_battery_joules:,.0f} J)")
    print(f"Energy Spent Actions:   {report.total_energy_spent_actions_wh:.2f} Wh ({report.total_energy_spent_actions_joules:,.0f} J)")
    print(f"Return Flight Energy:   {report.return_flight_energy_wh:.2f} Wh ({report.return_flight_energy_joules:,.0f} J)")
    print(f"Final Battery Reserve:  {report.final_battery_wh:.2f} Wh ({report.final_battery_joules:,.0f} J)")
    print(f"Candidates Summary:     {report.candidates_inspected} Inspected, {report.candidates_deferred} Deferred, {report.candidates_skipped} Skipped")

    # 7. Final Candidate Verification Status
    print("\n" + "=" * 80)
    print("🏁 FINAL CANDIDATE VERIFICATION STATUS & DECISION OUTCOMES")
    print("=" * 80)
    print(f"{'Candidate ID':<22} | {'Change Type':<25} | {'Confidence':<12} | {'Uncertainty':<12} | {'Action Selected':<15}")
    print("-" * 95)
    final_candidate_rows = []
    
    # Map ledger decisions by candidate_id
    decisions_by_cand = {r.candidate_id: r for r in simulator.ledger.records if r.candidate_id}

    for cand in candidate_states:
        cid = cand.detection.candidate_id
        pred_change = cand.detection.predicted_change
        conf = cand.detection.confidence
        unc = cand.detection.uncertainty
        
        ledger_entry = decisions_by_cand.get(cid)
        action_name = ledger_entry.selected_action.value if ledger_entry else "UNPROCESSED"
        
        print(f"{cid:<22} | {pred_change:<25} | {conf:<12.3f} | {unc:<12.3f} | {action_name:<15}")
        final_candidate_rows.append({
            "candidate_id": cid,
            "predicted_change": pred_change,
            "confidence": conf,
            "uncertainty": unc,
            "action_selected": action_name,
        })
    print("-" * 95)

    # 8. Export Report
    if export_report_path:
        os.makedirs(os.path.dirname(os.path.abspath(export_report_path)), exist_ok=True)
        report_data = {
            "mission_summary": report.model_dump(),
            "decisions": decision_entries,
            "candidates": final_candidate_rows,
        }
        with open(export_report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        print(f"\n📄 Saved full mission report to: {export_report_path}")

    return {
        "report": report,
        "decisions": decision_entries,
        "final_candidates": final_candidate_rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ORBITRA SatQuery -> ARES Integration Example")
    parser.add_argument("--candidates", type=str, default=os.path.join(REPO_ROOT, "SatQuery", "exports", "sample_candidates.json"))
    parser.add_argument("--policy", type=str, default="B3", choices=["B0", "B1", "B2", "B3"])
    parser.add_argument("--battery_wh", type=float, default=20.83)
    parser.add_argument("--output_report", type=str, default=os.path.join(REPO_ROOT, "SatQuery", "exports", "mission_decision_report.json"))
    args = parser.parse_args()

    run_integration(
        candidates_json_path=args.candidates,
        policy_name=args.policy,
        battery_wh=args.battery_wh,
        export_report_path=args.output_report,
    )
