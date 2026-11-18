"""Reproducible matched-budget comparisons for ARES policies.

All generated candidates, action outcomes, and energy values are synthetic or
assumed. The common outcome metric is computed with ActionOutcomeSimulator so
policy-specific ranking scores do not become the cross-policy score.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Sequence

from pydantic import BaseModel

from ares.actions.models import ActionOutcomeSimulator
from ares.policies.b3_joint_policy import B3JointPolicy, B3JointPolicyConfig
from ares.policies.registry import get_policy
from ares.schemas.candidate_state import ActionType, AresCandidateState
from ares.schemas.provenance import DataProvenance, ProvenanceValue
from ares.schemas.satquery_record import (
    LocalGridCoordinates,
    RegionGeometry,
    SatQueryCandidateRecord,
)
from ares.simulation.simulator import MissionSimulationConfig, MissionSimulator


DEFAULT_BUDGETS_WH = (8.0, 12.0, 20.0, 30.0, 50.0)
POLICY_IDS = ("B0", "B1", "B2", "B3", "B4")
CHANGE_CLASSES = (
    ("ordinary_land", 1.0),
    ("new_construction", 1.0),
    ("vegetation_clearance", 2.0),
    ("road_obstruction", 2.0),
    ("industrial_spill", 4.0),
    ("critical_infrastructure", 4.0),
)


def _binary_entropy(probability: float) -> float:
    if probability in (0.0, 1.0):
        return 0.0
    return -(
        probability * math.log2(probability)
        + (1.0 - probability) * math.log2(1.0 - probability)
    )


def generate_scenario(seed: int, candidate_count: int = 8) -> List[AresCandidateState]:
    """Builds one deterministic, synthetic candidate set for every policy to share."""
    if candidate_count < 1:
        raise ValueError("candidate_count must be at least 1")

    rng = random.Random(seed)
    candidates: List[AresCandidateState] = []
    for index in range(candidate_count):
        confidence = round(rng.uniform(0.51, 0.99), 6)
        change_class, importance = rng.choice(CHANGE_CLASSES)
        x_meters = round(rng.uniform(100.0, 4_000.0), 1)
        y_meters = round(rng.uniform(100.0, 4_000.0), 1)
        detection = SatQueryCandidateRecord(
            schema_version="v1.0.0",
            candidate_id=f"cand_benchmark_{seed:04d}_{index + 1:03d}",
            image_pair_id=f"pair_synthetic_benchmark_{seed:04d}",
            timestamp="2026-11-17T00:00:00Z",
            predicted_change=f"[SYNTHETIC EXAMPLE] {change_class}",
            confidence=confidence,
            uncertainty=round(_binary_entropy(confidence), 6),
            region=RegionGeometry(
                crs="local_meter_grid",
                local_grid=LocalGridCoordinates(
                    x_meters=x_meters,
                    y_meters=y_meters,
                    z_meters=50.0,
                ),
            ),
        )
        candidates.append(
            AresCandidateState(
                detection=detection,
                importance_weight=ProvenanceValue[float](
                    value=importance,
                    provenance=DataProvenance.ASSUMED,
                    notes="Synthetic benchmark category-to-importance mapping.",
                ),
            )
        )
    return candidates


def _policy_variants() -> List[tuple[str, Callable[[], Any]]]:
    variants: List[tuple[str, Callable[[], Any]]] = [
        (policy_id, lambda policy_id=policy_id: get_policy(policy_id))
        for policy_id in POLICY_IDS
    ]
    no_human_review = B3JointPolicyConfig(
        allow_human_review=ProvenanceValue[bool](
            value=False,
            provenance=DataProvenance.ASSUMED,
            notes="Ablation: exclude human review from B3's action set.",
        )
    )
    variants.append(("B3_no_human_review", lambda: B3JointPolicy(no_human_review)))
    return variants


def _weighted_uncertainty_reduction(
    candidates: Sequence[AresCandidateState], actions: Iterable[Any]
) -> float:
    by_id = {candidate.detection.candidate_id: candidate for candidate in candidates}
    outcome_simulator = ActionOutcomeSimulator()
    total = 0.0
    actionable = {ActionType.RECAPTURE, ActionType.STRONGER_MODEL, ActionType.HUMAN_REVIEW}
    for record in actions:
        if record.selected_action not in actionable:
            continue
        candidate = by_id.get(record.candidate_id)
        if candidate is None:
            continue
        outcome = outcome_simulator.simulate_outcome(record.selected_action, candidate)
        weight = float(candidate.importance_weight.value)
        total += weight * max(0.0, outcome.prior_uncertainty - outcome.post_uncertainty)
    return round(total, 6)


def run_one(
    policy_label: str,
    policy_factory: Callable[[], Any],
    scenario_seed: int,
    candidate_count: int,
    budget_joules: float,
) -> Dict[str, Any]:
    candidates = generate_scenario(scenario_seed, candidate_count)
    simulator = MissionSimulator(
        config=MissionSimulationConfig(initial_battery_joules=budget_joules)
    )
    report = simulator.run_mission(policy_factory(), candidates)
    records = [
        record for record in simulator.ledger.records
        if record.candidate_id != "MISSION_RETURN"
    ]
    action_counts: Dict[str, int] = {}
    for record in records:
        if record.selected_action in (ActionType.RECAPTURE, ActionType.STRONGER_MODEL, ActionType.HUMAN_REVIEW):
            key = record.selected_action.value
            action_counts[key] = action_counts.get(key, 0) + 1

    weighted_reduction = _weighted_uncertainty_reduction(candidates, records)
    total_energy = report.total_energy_spent_actions_joules + report.return_flight_energy_joules
    reserve_triggers = sum(not record.reserve_feasible for record in records)
    return {
        "provenance": "SIMULATED",
        "parameters_provenance": "ASSUMED",
        "policy": policy_label,
        "scenario_seed": scenario_seed,
        "candidate_count": candidate_count,
        "budget_joules": round(budget_joules, 1),
        "budget_wh": round(budget_joules / 3600.0, 3),
        "inspected": report.candidates_inspected,
        "deferred": report.candidates_deferred,
        "skipped": report.candidates_skipped,
        "recapture_count": action_counts.get(ActionType.RECAPTURE.value, 0),
        "stronger_model_count": action_counts.get(ActionType.STRONGER_MODEL.value, 0),
        "human_review_count": action_counts.get(ActionType.HUMAN_REVIEW.value, 0),
        "reserve_guardrail_triggers": reserve_triggers,
        "safe_return": report.safe_return_completed,
        "action_energy_joules": round(report.total_energy_spent_actions_joules, 1),
        "return_energy_joules": round(report.return_flight_energy_joules, 1),
        "total_mission_energy_joules": round(total_energy, 1),
        "final_battery_joules": report.final_battery_joules,
        "budget_utilization": round(total_energy / budget_joules, 6),
        "weighted_uncertainty_reduction": weighted_reduction,
        "weighted_reduction_per_mission_joule": (
            round(weighted_reduction / total_energy, 8) if total_energy > 0 else None
        ),
    }


def _mean_and_sd(values: Sequence[float]) -> Dict[str, float]:
    return {
        "mean": round(statistics.mean(values), 6),
        "population_sd": round(statistics.pstdev(values), 6),
    }


def aggregate_runs(runs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Summarizes replicate runs for each matched budget and policy variant."""
    grouped: Dict[tuple[str, float], List[Dict[str, Any]]] = {}
    for run in runs:
        grouped.setdefault((run["policy"], run["budget_joules"]), []).append(run)

    summary: List[Dict[str, Any]] = []
    numeric_metrics = (
        "inspected", "deferred", "skipped", "recapture_count",
        "stronger_model_count", "human_review_count", "reserve_guardrail_triggers",
        "action_energy_joules", "return_energy_joules", "total_mission_energy_joules",
        "final_battery_joules", "budget_utilization", "weighted_uncertainty_reduction",
    )
    for (policy, budget_joules), group in sorted(grouped.items()):
        summary_item: Dict[str, Any] = {
            "policy": policy,
            "budget_joules": budget_joules,
            "budget_wh": round(budget_joules / 3600.0, 3),
            "replicates": len(group),
            "safe_return_rate": round(sum(run["safe_return"] for run in group) / len(group), 6),
        }
        for metric in numeric_metrics:
            summary_item[metric] = _mean_and_sd([float(run[metric]) for run in group])
        efficiencies = [
            run["weighted_reduction_per_mission_joule"]
            for run in group
            if run["weighted_reduction_per_mission_joule"] is not None
        ]
        summary_item["weighted_reduction_per_mission_joule"] = (
            _mean_and_sd([float(value) for value in efficiencies]) if efficiencies else None
        )
        summary.append(summary_item)
    return summary


def run_comparison(
    budgets_wh: Sequence[float] = DEFAULT_BUDGETS_WH,
    scenario_seeds: Sequence[int] = tuple(range(20)),
    candidate_count: int = 8,
) -> Dict[str, Any]:
    """Runs all B0-B4 policies and a B3 human-review ablation on matched inputs."""
    if not budgets_wh or any(budget <= 0 for budget in budgets_wh):
        raise ValueError("budgets_wh must contain positive values")
    if not scenario_seeds:
        raise ValueError("scenario_seeds must not be empty")

    variants = _policy_variants()
    runs = [
        run_one(label, factory, seed, candidate_count, float(budget_wh) * 3600.0)
        for seed in scenario_seeds
        for budget_wh in budgets_wh
        for label, factory in variants
    ]
    return {
        "experiment": "ARES matched-budget policy comparison",
        "provenance": "SIMULATED",
        "parameter_status": "ASSUMED",
        "policy_variants": [label for label, _ in variants],
        "budgets_wh": [float(value) for value in budgets_wh],
        "scenario_seeds": list(scenario_seeds),
        "candidate_count_per_scenario": candidate_count,
        "metric_definitions": {
            "weighted_uncertainty_reduction": "Sum over acted candidates of importance_weight × (prior uncertainty − deterministic simulated post-action uncertainty).",
            "total_mission_energy_joules": "Executed verification action energy plus return-flight energy; does not include unmodeled human labor or wall-clock latency.",
            "safe_return_rate": "Fraction of replicate simulations whose return flight completed with nonnegative modeled battery.",
            "B3_no_human_review": "Ablation that removes HUMAN_REVIEW from B3's feasible action set; all other assumptions remain unchanged.",
        },
        "runs": runs,
        "summary": aggregate_runs(runs),
    }


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=int, default=20, help="Number of deterministic synthetic scenarios (default: 20).")
    parser.add_argument("--candidates", type=int, default=8, help="Candidates per scenario (default: 8).")
    parser.add_argument(
        "--budgets-wh", type=float, nargs="+", default=list(DEFAULT_BUDGETS_WH),
        help="Matched battery budgets in Wh (default: 8 12 20 30 50).",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[2] / "outputs" / "policy_comparison.json",
        help="JSON output path (default: ARES/outputs/policy_comparison.json).",
    )
    args = parser.parse_args(argv)
    if args.scenarios < 1:
        parser.error("--scenarios must be at least 1")
    if args.candidates < 1:
        parser.error("--candidates must be at least 1")
    if any(value <= 0 for value in args.budgets_wh):
        parser.error("--budgets-wh values must be positive")

    result = run_comparison(
        budgets_wh=args.budgets_wh,
        scenario_seeds=tuple(range(args.scenarios)),
        candidate_count=args.candidates,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"[SIMULATED] Wrote {len(result['runs'])} matched runs to {args.output}")
    print("Policy comparison summary (mean weighted uncertainty reduction; safe-return rate):")
    for row in result["summary"]:
        reduction = row["weighted_uncertainty_reduction"]["mean"]
        print(
            f"  {row['policy']:20s} {row['budget_wh']:>6.1f} Wh  "
            f"reduction={reduction:>8.3f}  safe-return={row['safe_return_rate']:.1%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
