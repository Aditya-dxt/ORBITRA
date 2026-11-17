"""Tests for reproducible matched-budget policy experiments."""

import unittest

from ares.simulation.benchmark import generate_scenario, run_comparison


class TestPolicyBenchmark(unittest.TestCase):
    def test_scenario_generation_is_deterministic_and_independent(self):
        first = generate_scenario(seed=17, candidate_count=4)
        second = generate_scenario(seed=17, candidate_count=4)

        self.assertEqual(
            [candidate.model_dump() for candidate in first],
            [candidate.model_dump() for candidate in second],
        )
        self.assertIsNot(first[0], second[0])
        self.assertTrue(all("[SYNTHETIC EXAMPLE]" in c.detection.predicted_change for c in first))

    def test_matched_runs_include_all_policies_and_b3_ablation(self):
        result = run_comparison(
            budgets_wh=(12.0,),
            scenario_seeds=(3, 7),
            candidate_count=4,
        )

        expected_variants = {"B0", "B1", "B2", "B3", "B4", "B3_no_human_review"}
        self.assertEqual(set(result["policy_variants"]), expected_variants)
        self.assertEqual(len(result["runs"]), 12)
        self.assertEqual(len(result["summary"]), 6)
        self.assertTrue(all(row["safe_return"] for row in result["runs"]))
        self.assertTrue(all(row["provenance"] == "SIMULATED" for row in result["runs"]))
        self.assertTrue(all(row["parameters_provenance"] == "ASSUMED" for row in result["runs"]))
        self.assertTrue(
            all(row["human_review_count"] == 0 for row in result["runs"] if row["policy"] == "B3_no_human_review")
        )

    def test_benchmark_is_repeatable_for_fixed_inputs(self):
        kwargs = {"budgets_wh": (8.0, 20.0), "scenario_seeds": (2,), "candidate_count": 3}
        self.assertEqual(run_comparison(**kwargs), run_comparison(**kwargs))


if __name__ == "__main__":
    unittest.main()
