"""Malformed review dispositions fail closed without rewriting historical evidence."""
import unittest
from pathlib import Path

import test_recursive_writer as fixtures

writer = fixtures.writer


class RecursiveReviewSchemaTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RecursiveWriterTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.start()
        self.fixture.freeze()

    def assert_rejected_unchanged(self, report, pattern):
        fixture = self.fixture
        path = fixture.write(fixture.root / "malformed-review.json", report)
        before = {p.relative_to(fixture.work): p.read_bytes()
                  for p in fixture.work.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(ValueError, pattern):
            writer.record_review(fixture.state_path, path)
        after = {p.relative_to(fixture.work): p.read_bytes()
                 for p in fixture.work.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_previous_findings_wrong_types_rejected_without_state_or_archive_changes(self):
        fixture = self.fixture
        report = fixture.read(fixture.report("faithfulness"))
        for value in ([], ["old"], "", "old", None, False, 0):
            with self.subTest(value=value):
                report["previous_findings"] = value
                self.assert_rejected_unchanged(report, "previous_findings must be a JSON object")

    def test_empty_object_is_accepted(self):
        fixture = self.fixture
        path = fixture.report("faithfulness")
        report = fixture.read(path)
        report["previous_findings"] = {}
        fixture.write(path, report)
        record = writer.record_review(fixture.state_path, path)
        self.assertEqual({}, fixture.read(record["receipt"]["path"])["previous_findings"])
        self.assertTrue(writer.audit_writing(fixture.state_path)["pass"])

    def test_all_dispositions_require_valid_shape_including_advisory_findings(self):
        fixture = self.fixture
        path = fixture.report("faithfulness")
        report = fixture.read(path)
        report["findings"] = [{"id": "advice", "severity": "advisory", "location": "Introduction",
                               "evidence": "Synthetic optional improvement.", "resolution": "Optional."}]
        fixture.write(path, report)
        writer.record_review(fixture.state_path, path)
        retry = fixture.read(fixture.report("faithfulness"))
        for value in ([], None, "resolved", {}, {"status": []},
                      {"status": "resolved", "evidence": []},
                      {"status": "resolved", "evidence": True},
                      {"status": "resolved", "evidence": " "}):
            with self.subTest(value=value):
                retry["previous_findings"] = {"advice": value}
                self.assert_rejected_unchanged(retry, "prior finding disposition")

    def test_malformed_historical_receipt_blocks_audit_resume_and_preserves_findings(self):
        fixture = self.fixture
        original = writer.record_review(fixture.state_path,
                                        fixture.report("faithfulness", "FAIL", finding_id="still-required"))
        original_bytes = Path(original["receipt"]["path"]).read_bytes()
        retry_path = fixture.report("faithfulness")
        retry = fixture.read(retry_path)
        # Model an artifact accepted by an older runtime, with a coherent receipt.
        for malformed in ([], {"still-required": []},
                          {"still-required": {"status": "resolved", "evidence": True}}):
            with self.subTest(malformed=malformed):
                retry["previous_findings"] = malformed
                fixture.write(retry_path, retry)
                state = fixture.state()
                state["writer"]["revisions"][-1]["reviews"] = [original, {
                    "receipt": writer._receipt(retry_path), "packet": original["packet"]}]
                fixture.write(fixture.state_path, state)
                before = fixture.state_path.read_bytes()
                for audit in (writer.audit_writing, writer.resume_writing):
                    result = audit(fixture.state_path)
                    self.assertFalse(result["pass"], result)
                    self.assertEqual("blocked", result["status"])
                    self.assertIn("finding", " ".join(result["errors"]))
                with self.assertRaisesRegex(ValueError, "finding"):
                    writer.review_packet(fixture.state_path, "faithfulness", "synthetic-faithfulness-reviewer")
                self.assertEqual(before, fixture.state_path.read_bytes())
                self.assertEqual(original_bytes, Path(original["receipt"]["path"]).read_bytes())
                self.assertEqual("still-required", fixture.read(original["receipt"]["path"])["findings"][0]["id"])


if __name__ == "__main__":
    unittest.main()
