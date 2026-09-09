import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
POLICIES = [
    ROOT / "src/plan_store/grade_policy.py",
]
GOAL_FIELDS = {
    "goal_id", "goal_role", "consumer_path", "directionality",
    "goal_contract_sha256", "goal_alignment_sha256", "intended_model_bindings",
}


def load_policy(path: Path):
    spec = importlib.util.spec_from_file_location(f"grade_policy_{path.parent.parent.name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GoalAlignmentGradePolicyTests(unittest.TestCase):
    def test_goal_alignment_fields_invalidate_gold_in_both_runtimes(self):
        for path in POLICIES:
            with self.subTest(path=path):
                policy = load_policy(path)
                self.assertTrue(GOAL_FIELDS.issubset(policy.GOLD_INVALIDATING_FIELDS))
                for field in GOAL_FIELDS:
                    changed = policy.invalidate_gold_for_mutation(
                        {"verification_grade": "GOLD", "gold_audit": {"status": "passed"}},
                        {field: "changed"},
                    )
                    self.assertIsNone(changed["verification_grade"])
                    self.assertIsNone(changed["gold_audit"])


if __name__ == "__main__":
    unittest.main()
