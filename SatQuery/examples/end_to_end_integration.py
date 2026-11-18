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
import numpy as np

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
    EvidenceRecord,
    ImportanceTier,
)
from ares.energy.units import joules_to_wh
from ares.energy.model import DroneEnergyModel
from ares.energy.reserve import ReturnReserveCalculator
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.policies.b0_fixed_pass import B0FixedPassPolicy
from ares.policies.b1_uncertainty_first import B1UncertaintyFirstPolicy
from ares.policies.b2_adaptive_computation import B2AdaptiveComputationPolicy
from ares.policies.b3_joint_policy import B3JointPolicy, B3JointPolicyConfig
from ares.policies.b4_greedy_benefit_per_energy import B4GreedyBenefitPerEnergyPolicy
from ares.simulation.simulator import MissionSimulationConfig, MissionSimulator


def get_policy_instance(policy_id: str, include_human_review: bool = True):
    """Factory for selecting ARES policy."""
    pid = policy_id.upper()
    if pid == "B0":
        return B0FixedPassPolicy()
    elif pid == "B1":
        return B1UncertaintyFirstPolicy()
    elif pid == "B2":
        return B2AdaptiveComputationPolicy()
    elif pid == "B3":
        if not include_human_review:
            config = B3JointPolicyConfig(
                allow_human_review=ProvenanceValue(
                    value=False,
                    provenance=DataProvenance.ASSUMED,
                    notes="Disabled to test physical flight recapture and return reserve",
                )
            )
            return B3JointPolicy(config=config)
        return B3JointPolicy()
    elif pid == "B4":
        return B4GreedyBenefitPerEnergyPolicy()
    else:
        raise ValueError(f"Unknown policy '{policy_id}'. Available: B0, B1, B2, B3, B4")


def run_integration(
    candidates_json_path: Optional[str] = None,
    policy_name: str = "B3",
    battery_wh: float = 20.83,  # 75,000 J
    export_report_path: Optional[str] = None,
    include_human_review: bool = True,
) -> Dict:
    """Execute end-to-end integration run."""
    print("=" * 80)
    print("🛰️  ORBITRA JOINT INTEGRATION: SatQuery (Vision) -> ARES (Decision & Energy)")
    print("=" * 80)
    print("📋 [Demonstration Architecture Scope]")
    print("   • Schema Interface:      SatQueryCandidateRecord (v1.0.0-provisional)")
    print("   • Candidate Management:  AresCandidateState with decoupled importance & energy guards")
    print("   • Vision Re-Inference:   Live patch inference on resolved candidate source imagery")
    print("   • Energy Accounting:     ARES discrete-event ledger with 1,450 J STRONGER_MODEL billing")
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

    # Check SatQuery vision engine status
    from SatQuery.satquery.vision.deep_detector import DeepSiameseChangeDetector
    deep_det = DeepSiameseChangeDetector()
    model_info = deep_det.get_model_info()
    print(f"\n🤖 [SatQuery Vision Model Engine]")
    print(f"   • Active Execution Mode: {model_info['mode']}")
    print(f"   • Status: {model_info['execution_description']}")
    print(f"   • Neural Checkpoint Found: {model_info['checkpoint_found']}")

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
    policy = get_policy_instance(policy_name, include_human_review=include_human_review)

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

    # 7. STRONGER_MODEL Verification: Detector Inference & ARES Simulated Outcome
    stronger_decisions = [r for r in decision_entries if r["action"] == "STRONGER_MODEL"]
    if stronger_decisions:
        print("\n" + "=" * 95)
        print("🧠 STRONGER_MODEL DISPATCH: SatQuery Vision Re-Inference & ARES Outcome")
        print("=" * 95)
        print(f"   • Active Vision Detector: {deep_det.describe_execution_mode()}")
        print(f"   • ARES Action Cost Rule:  1,450.0 J (1,200 J edge compute + 250 J offload comms) [ASSUMED]")
        print(f"   • ARES Policy Assumption: 40% uncertainty reduction (u_post = u_pre * 0.60) [SIMULATED]")

        from SatQuery.satquery.data.image_resolver import ImagePairResolver
        from SatQuery.satquery.vision.calibration import binary_entropy_uncertainty

        resolver = ImagePairResolver()

        for sd in stronger_decisions:
            cid = sd["candidate_id"]
            c_obj = next((c for c in candidate_states if c.detection.candidate_id == cid), None)
            if c_obj:
                u_orig = c_obj.detection.uncertainty
                conf_orig = c_obj.detection.confidence
                bbox = c_obj.detection.region.bbox_pixels
                pair_id = c_obj.detection.image_pair_id

                print(f"\n   ✓ Candidate '{cid}' [Action: STRONGER_MODEL]:")
                print(f"       [SatQuery Input State]       Confidence={conf_orig:.3f}, Uncertainty={u_orig:.3f}, BBox={bbox}, ImagePair='{pair_id}'")

                # Resolve source imagery for candidate's image_pair_id
                resolved = resolver.resolve(pair_id)
                print(f"       [Source Imagery Resolution]  Source='{resolved.source_type}' | Synthetic={resolved.is_synthetic}")
                print(f"                                    {resolved.description}")

                # Real patch crop inference
                recomputed_conf = None
                recomputed_unc = None
                delta_u_measured = None

                if bbox and len(bbox) == 4:
                    h, w = resolved.img_pre.shape[:2]
                    x1, y1, x2, y2 = bbox
                    xmin = max(0, min(x1, x2))
                    xmax = min(w, max(x1, x2))
                    ymin = max(0, min(y1, y2))
                    ymax = min(h, max(y1, y2))

                    crop_pre = resolved.img_pre[ymin:ymax, xmin:xmax]
                    crop_post = resolved.img_post[ymin:ymax, xmin:xmax]

                    if crop_pre.size > 0 and crop_post.size > 0:
                        crop_heatmap, crop_mask = deep_det.detect_changes(crop_pre, crop_post)
                        crop_score = float(np.mean(crop_heatmap))
                        recomputed_conf = float(deep_det.calibrator.predict_probability(crop_score))
                        recomputed_unc = binary_entropy_uncertainty(recomputed_conf)
                        delta_u_measured = round(u_orig - recomputed_unc, 4)

                        print(f"       [SatQuery Patch Inference]   Executed on crop {crop_pre.shape[:2]} via '{deep_det.mode}':")
                        print(f"                                    Re-computed Confidence={recomputed_conf:.3f}, Re-computed Uncertainty={recomputed_unc:.3f}")

                        # Mutate candidate state to reflect measured closed-loop detector inference
                        c_obj.detection.confidence = round(recomputed_conf, 4)
                        c_obj.detection.uncertainty = round(recomputed_unc, 4)
                        c_obj.evidence_history.append(
                            EvidenceRecord(
                                action=ActionType.STRONGER_MODEL,
                                timestamp=c_obj.detection.timestamp,
                                energy_spent_joules=1450.0,
                                simulated_outcome=(
                                    f"[MEASURED] Patch re-inference on {resolved.source_type}: "
                                    f"conf={recomputed_conf:.3f}, uncert={recomputed_unc:.3f} (Δu={delta_u_measured:+.3f})"
                                ),
                                notes=f"Resolved via {resolved.description}",
                            )
                        )
                        print(f"       [Candidate State Update]     Mutated candidate state: conf={conf_orig:.3f}->{recomputed_conf:.3f}, uncert={u_orig:.3f}->{recomputed_unc:.3f} (Δu={delta_u_measured:+.3f})")

                        # Update final candidate summary row
                        for row in final_candidate_rows:
                            if row["candidate_id"] == cid:
                                row["recomputed_confidence"] = round(recomputed_conf, 4)
                                row["recomputed_uncertainty"] = round(recomputed_unc, 4)
                                row["measured_delta_uncertainty"] = delta_u_measured
                                row["imagery_source"] = resolved.source_type
                                row["ares_assumed_reduction"] = "40% (u * 0.60)"
                                row["ares_energy_billed_joules"] = 1450.0
                    else:
                        print(f"       [SatQuery Patch Inference]   WARNING: BBox [{xmin}, {ymin}, {xmax}, {ymax}] out of bounds for image shape ({h}, {w})")

                # ARES offline baseline comparison
                u_simulated = round(u_orig * 0.60, 3)
                print(f"       [ARES Offline Baseline]      ARES benchmark simulated outcome: uncertainty reduced from {u_orig:.3f} to {u_simulated:.3f} (40% theoretical reduction) [SIMULATED]")
                print(f"       [ARES Energy Accounting]     1,450.0 J (0.403 Wh) billed [Zero flight energy consumed]")
        print("=" * 95)

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
    parser.add_argument("--policy", type=str, default="B3", choices=["B0", "B1", "B2", "B3", "B4"])
    parser.add_argument("--battery_wh", type=float, default=20.83)
    parser.add_argument("--output_report", type=str, default=os.path.join(REPO_ROOT, "SatQuery", "exports", "mission_decision_report.json"))
    parser.add_argument("--no-human-review", action="store_true", help="Exclude HUMAN_REVIEW from action space, forcing flight/model triage")
    parser.add_argument("--model", type=str, default="deep_siamese", choices=["deep_siamese", "baseline"])
    parser.add_argument("--regenerate", action="store_true", help="Regenerate candidates using specified model before running ARES")
    args = parser.parse_args()

    candidates_path = args.candidates
    if args.regenerate or not os.path.exists(candidates_path):
        from SatQuery.satquery.pipeline import SatQueryPipeline
        from SatQuery.satquery.data.synthetic_sample_data import generate_benchmark_pair
        print(f"Generating candidates using {args.model.upper()}...")
        p = SatQueryPipeline(model_type=args.model)
        pre, post, gt_mask, gt_boxes = generate_benchmark_pair("levir")
        res = p.process_pair(pre, post, image_pair_id="pair_benchmark_live", ground_truth_mask=gt_mask, ground_truth_boxes=gt_boxes)
        p.export_candidates_to_json(res["candidates"], candidates_path)

    run_integration(
        candidates_json_path=candidates_path,
        policy_name=args.policy,
        battery_wh=args.battery_wh,
        export_report_path=args.output_report,
        include_human_review=not args.no_human_review,
    )
