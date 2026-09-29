"""Recursive writing contracts, provenance, review ordering, and recovery.

All approval/review text in these tests is synthetic test evidence, never a
mathematical certification or a substitute for the separately run agent evals.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper_writing_codex import recursive_writer as writer
from paper_writing_codex.versioning import sha256_file
from paper_writing_codex.workflow import init_compose, init_refine, mark_gate


SAMPLE = r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\section{Introduction}
We explain why an identity remains valid on the stated domain.
\begin{theorem}\label{thm:identity}
For every nonnegative integer $n$, one has $n=n$.
\end{theorem}
\begin{proof}\label{proof:identity}
This follows by reflexivity on the stated domain.
\end{proof}
\end{document}
"""


class RecursiveWriterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "notes" / "source.tex"
        self.source.parent.mkdir()
        self.source.write_text(SAMPLE, encoding="utf-8")
        self.work = self.root / "run"
        self.output = self.root / "draft" / "paper.tex"
        self.state_path = self.work / "00-run-state.json"
        self.counter = 0

    def read(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))

    def write(self, path, value):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        return path

    def state(self):
        return self.read(self.state_path)

    def start(self, *, refine=False, limit=5, approve=True):
        before = self.source.read_bytes()
        if refine:
            state = init_refine(self.source, self.work, workflow_version=2,
                                max_review_rounds=limit)
            self.output = Path(state["output"])
        else:
            state = init_compose(self.output, self.work, workflow_version=2,
                                 authoritative_sources=[self.source], max_review_rounds=limit)
            self.output.write_text(SAMPLE, encoding="utf-8")
        self.assertEqual(before, self.source.read_bytes())
        self.claims = self.read(self.work / "writer" / "source-claims.json")["claims"]
        self.main_id = next(row["id"] for row in self.claims if row["kind"] == "statement")
        if approve:
            self.approve()
        return state

    def approve(self):
        approval = self.root / "synthetic-author-approval.txt"
        approval.write_text("SYNTHETIC TEST AUTHOR: approve precisely the identity-only writing brief.",
                            encoding="utf-8")
        self.write(self.work / "writer" / "brief.json", {
            "audience": "Readers of elementary discrete mathematics",
            "question": "How can this elementary identity be stated precisely?",
            "contribution": "One self-contained explanation of the stated identity.",
            "scope": "The nonnegative-integer identity in the immutable source; no new mathematics.",
            "main_claim_ids": [self.main_id], "exclusions": ["new claims", "novelty certification"],
            "approval_evidence": str(approval),
        })

    def plan(self, **changes):
        state = self.state()
        revisions = state["writer"]["revisions"]
        current = revisions[-1] if revisions else None
        findings = set()
        if current:
            for record in current["reviews"]:
                report = self.read(record["receipt"]["path"])
                findings.update(f["id"] for f in report.get("findings", []) if f["severity"] == "required")
        value = {
            "planner_id": "synthetic-planner", "writer_id": "synthetic-writer",
            "base_revision": current["id"] if current else None,
            "objective": "Faithfully explain the approved identity and address documented repairs.",
            "outline": ["Motivation", "Main identity and its proof"],
            "claim_map": [{"claim_id": row["id"], "disposition": "retained",
                           "location": "Main identity section",
                           "reason": "Preserve all approved source mathematics",
                           "candidate_label": "thm:identity" if row["id"] == self.main_id else "proof:identity"}
                          for row in self.claims],
            "repairs": [{"finding_id": identity, "action": "Repair and independently recheck",
                         "reason": "Keep the documented obligation required"}
                        for identity in sorted(findings)],
        }
        value.update(changes)
        self.counter += 1
        return self.write(self.root / f"plan-{self.counter}.json", value)

    def freeze(self, **plan_changes):
        writer.record_plan(self.state_path, self.plan(**plan_changes))
        return writer.freeze_revision(self.state_path)

    def report(self, role, verdict="PASS", *, reviewer=None, finding_id=None, packet=None):
        if packet is None:
            packet = writer.review_packet(self.state_path, role, reviewer or f"synthetic-{role}-reviewer")
        value = {key: copy.deepcopy(packet[key]) for key in
                 ("packet_id", "revision_id", "role", "review_kind", "reviewer_id", "bindings")}
        if "review_track" in packet:
            value["review_track"] = packet["review_track"]
        value.update(verdict=verdict, summary="Synthetic fixture evidence; not a real mathematical review.",
                     findings=[], coverage=[{"checkpoint_id": checkpoint["id"], "status": "PASS",
                                             "evidence": "Synthetic fixture checks this obligation explicitly."}
                                            for checkpoint in packet["rubric"]["checkpoints"]])
        if packet.get("unresolved_findings"):
            value["previous_findings"] = {
                finding["id"]: {"status": "resolved" if verdict == "PASS" else "retained",
                                "evidence": "Synthetic review explicitly accounts for the prior obligation."}
                for finding in packet["unresolved_findings"]
            }
        if verdict == "FAIL":
            value["findings"] = [{"id": finding_id or f"{role}-required",
                                  "severity": "required", "location": "Main identity section",
                                  "evidence": "The synthetic fixture deliberately marks an unresolved requirement.",
                                  "resolution": "Repair the indicated requirement and have it independently rechecked."}]
            value["coverage"][0]["status"] = "FAIL"
        if packet["role"] == "faithfulness":
            value["scope"] = packet["scope"]
            value["claim_reviews"] = [
                {"claim_id": row["id"], "status": "faithful" if verdict == "PASS" else "unresolved",
                 "evidence": "Synthetic source-to-draft claim correspondence checked."}
                for row in packet["source_claims"]["claims"]
            ]
        if role == "layout":
            value.update(pdf_sha256=packet["build"]["pdf_sha256"], pages_inspected=[1])
        self.counter += 1
        return self.write(self.root / f"review-{self.counter}.json", value)

    def reviews(self, *, fail_role=None):
        revision = self.state()["writer"]["revisions"][-1]
        for role in writer.ROLES:
            verdict = "FAIL" if role == fail_role else "PASS"
            writer.record_review(self.state_path, self.report(role, verdict))
            if role == "faithfulness" and revision["two_faithfulness"]:
                writer.record_review(self.state_path, self.report("faithfulness-secondary", verdict,
                                     reviewer="synthetic-faithfulness-second"))

    def edit(self, text="Additional explanation of the already approved identity."):
        content = self.output.read_text(encoding="utf-8")
        self.output.write_text(content.replace("\\end{document}", text + "\n\\end{document}"),
                               encoding="utf-8")

    def mock_build(self, *, pages=1):
        def compile_tex(tex, timeout, retain_dir):
            retain_dir.mkdir(parents=True, exist_ok=False)
            pdf = retain_dir / "paper.pdf"
            pdf.write_bytes(b"Synthetic PDF fixture for receipt testing only")
            log = retain_dir / "paper.log"
            log.write_text("Synthetic clean build.", encoding="utf-8")
            return {"pass": True, "pdf_pages": pages, "pdf_sha256": sha256_file(pdf),
                    "retained_pdf": str(pdf), "retained_log": str(log),
                    "log_sha256": sha256_file(log), "warnings": [], "project_changes": []}
        with patch("paper_writing_codex.cli._compile_tex", side_effect=compile_tex):
            return writer.compile_revision(self.state_path)

    def finish(self):
        self.mock_build()
        writer.record_review(self.state_path, self.report("layout"))
        return writer.audit_writing(self.state_path, require_complete=True)

    def test_notes_only_initialization_is_ungraded_and_preserves_source_bytes(self):
        state = self.start()
        self.assertEqual(2, state["schema_version"])
        self.assertEqual(5, state["writer"]["max_review_rounds"])
        self.assertTrue(all(row["proof_status"] == "accepted_source_not_independently_verified"
                            and row["grade_metadata"] is None for row in self.claims))
        self.assertEqual([], state["writer"]["revisions"])

    def test_plan_needs_author_approval_and_full_source_claim_map(self):
        self.start(approve=False)
        with self.assertRaisesRegex(ValueError, "approved brief"):
            writer.record_plan(self.state_path, self.plan())
        self.approve()
        incomplete_plan = self.plan()
        incomplete = self.read(incomplete_plan)
        incomplete["claim_map"] = incomplete["claim_map"][:1]
        self.write(incomplete_plan, incomplete)
        with self.assertRaisesRegex(ValueError, "every source claim"):
            writer.record_plan(self.state_path, incomplete_plan)
        writer.record_plan(self.state_path, self.plan())
        self.assertTrue(self.state()["writer"]["contract"])

    def test_one_main_result_can_complete_without_shortening(self):
        self.start()
        self.edit("This added explanation is useful and deliberately makes the manuscript longer.")
        self.freeze()
        self.reviews()
        report = self.finish()
        self.assertTrue(report["pass"], report)
        self.assertEqual("complete", report["status"])
        self.assertGreater(self.output.stat().st_size, self.source.stat().st_size)

    def test_faithful_main_statement_reformulation_preserves_the_source_contract(self):
        self.start(refine=True)
        source_bytes = self.source.read_bytes()
        self.output.write_text(SAMPLE.replace("one has $n=n$", "the difference $n-n$ equals zero"),
                               encoding="utf-8")
        self.freeze()
        packet = writer.review_packet(self.state_path, "faithfulness", "reformulation-checker")
        main = next(row for row in packet["source_claims"]["claims"] if row["id"] == self.main_id)
        self.assertIn("nonnegative integer", main["statement"])
        self.assertIn("$n=n$", main["statement"])
        self.reviews()
        report = self.finish()
        self.assertTrue(report["pass"], report)
        self.assertEqual(source_bytes, self.source.read_bytes())

    def test_comprehensive_faithfulness_cannot_inherit_unreviewed_claim_coverage(self):
        self.start()
        self.freeze()
        path = self.report("faithfulness")
        value = self.read(path)
        value["claim_reviews"][0]["status"] = "inherited"
        self.write(path, value)
        with self.assertRaisesRegex(ValueError, "comprehensive review cannot inherit"):
            writer.record_review(self.state_path, path)

    def test_refinement_second_track_cannot_reuse_primary_invocation(self):
        self.start(refine=True)
        self.freeze()
        writer.record_review(self.state_path, self.report("faithfulness", reviewer="one-invocation"))
        with self.assertRaisesRegex(ValueError, "separate independent invocations"):
            writer.record_review(self.state_path, self.report("faithfulness-secondary", reviewer="one-invocation"))

    def test_interruption_resume_and_audit_are_read_only(self):
        self.start()
        self.freeze()
        writer.record_review(self.state_path, self.report("narrative"))
        before = {str(path.relative_to(self.work)): path.read_bytes()
                  for path in self.work.rglob("*") if path.is_file()}
        with patch("paper_writing_codex.cli._compile_tex", side_effect=AssertionError("read-only compiled")):
            first = writer.resume_writing(self.state_path)
            second = writer.audit_writing(self.state_path)
        after = {str(path.relative_to(self.work)): path.read_bytes()
                 for path in self.work.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual("reviewing", first["status"])
        self.assertEqual({"faithfulness", "notation", "wording"}, set(second["pending_roles"]))

    def test_first_failure_does_not_allow_replanning_before_other_roles_finish(self):
        self.start()
        self.freeze()
        writer.record_review(self.state_path, self.report("narrative", "FAIL"))
        with self.assertRaisesRegex(ValueError, "all scheduled reviews"):
            writer.record_plan(self.state_path, self.plan())
        for role in ("faithfulness", "notation", "wording"):
            writer.record_review(self.state_path, self.report(role))
        with self.assertRaisesRegex(ValueError, "every required finding"):
            writer.record_plan(self.state_path, self.plan(repairs=[]))
        writer.record_plan(self.state_path, self.plan())

    def test_review_invocations_are_independent_and_role_separated(self):
        self.start()
        self.freeze()
        for identity in ("synthetic-planner", "synthetic-writer"):
            with self.assertRaisesRegex(ValueError, "independent"):
                writer.review_packet(self.state_path, "faithfulness", identity)
        writer.record_review(self.state_path, self.report("narrative", reviewer="same-invocation"))
        with self.assertRaisesRegex(ValueError, "separate independent invocations"):
            writer.record_review(self.state_path, self.report("wording", reviewer="same-invocation"))

    def test_refinement_requires_two_distinct_faithfulness_reviews(self):
        self.start(refine=True)
        self.freeze()
        for role in writer.ROLES:
            writer.record_review(self.state_path, self.report(role))
        self.assertIn("faithfulness", writer.audit_writing(self.state_path)["pending_roles"])
        writer.record_review(self.state_path, self.report("faithfulness"))
        self.assertIn("faithfulness", writer.audit_writing(self.state_path)["pending_roles"])
        writer.record_review(self.state_path, self.report("faithfulness-secondary", reviewer="second-independent-invocation"))
        self.assertNotIn("faithfulness", writer.audit_writing(self.state_path)["pending_roles"])

    def test_forged_or_stale_report_packet_is_rejected(self):
        self.start()
        self.freeze()
        report_path = self.report("notation")
        report = self.read(report_path)
        report["bindings"]["manuscript"] = "0" * 64
        self.write(report_path, report)
        with self.assertRaisesRegex(ValueError, "stale or mismatched"):
            writer.record_review(self.state_path, report_path)

    def test_archived_report_tampering_blocks_audit(self):
        self.start()
        self.freeze()
        receipt = writer.record_review(self.state_path, self.report("wording"))["receipt"]
        path = Path(receipt["path"])
        path.write_bytes(path.read_bytes() + b"\n")
        report = writer.audit_writing(self.state_path)
        self.assertFalse(report["pass"])
        self.assertIn("evidence changed", " ".join(report["errors"]))

    def test_rubric_change_invalidates_only_that_role_without_new_manuscript_round(self):
        self.start()
        self.freeze()
        self.reviews()
        path = self.work / "writer" / "rubrics" / "notation.json"
        rubric = self.read(path)
        rubric["version"] = 2
        rubric["checkpoints"].append({"id": "D99", "severity": "required",
                                      "acceptance": "A new synthetic notation checkpoint."})
        self.write(path, rubric)
        report = writer.audit_writing(self.state_path)
        self.assertEqual(["notation"], report["pending_roles"])
        writer.record_review(self.state_path, self.report("notation", reviewer="updated-notation-invocation"))
        report = writer.audit_writing(self.state_path)
        self.assertEqual([], report["pending_roles"])
        self.assertEqual(1, report["reviewed_revisions"])

    def test_cumulative_faithfulness_diff_survives_a_failed_intermediate_revision(self):
        self.start()
        self.freeze()
        self.reviews()
        self.edit("Revision two retains a detail to check later.")
        self.freeze()
        self.reviews(fail_role="faithfulness")
        self.edit("Revision three repairs the reported defect.")
        self.freeze()
        packet = writer.review_packet(self.state_path, "faithfulness", "third-revision-invocation")
        self.assertEqual("r001", packet["last_pass_revision"])
        self.assertEqual("r002", packet["previous_report"]["revision_id"])
        self.assertTrue(packet["cumulative_diff"])
        self.assertEqual("incremental", packet["scope"])

    def test_all_new_revision_roles_are_required_and_old_report_cannot_be_reused(self):
        self.start()
        self.freeze()
        old = self.report("wording")
        self.reviews()
        self.edit()
        self.freeze()
        self.assertEqual(set(writer.ROLES), set(writer.audit_writing(self.state_path)["pending_roles"]))
        with self.assertRaisesRegex(ValueError, "stale or mismatched"):
            writer.record_review(self.state_path, old)

    def test_five_revisions_then_explicit_extension_preserves_history(self):
        self.start()
        for revision in range(5):
            if revision:
                self.edit(f"Synthetic repair revision {revision + 1}.")
            self.freeze()
            self.reviews(fail_role="narrative")
        report = writer.audit_writing(self.state_path)
        self.assertEqual("limit_pause", report["status"])
        self.assertEqual(5, report["reviewed_revisions"])
        writer.record_plan(self.state_path, self.plan())
        with self.assertRaisesRegex(ValueError, "limit reached"):
            writer.freeze_revision(self.state_path)
        approval = self.root / "synthetic-extension.txt"
        approval.write_text("SYNTHETIC TEST AUTHOR: authorize two additional reviewed revisions.", encoding="utf-8")
        extended = writer.continue_writing(self.state_path, approval, 2)
        self.assertEqual({"max_review_rounds": 7, "reviewed_revisions": 5}, extended)
        with self.assertRaisesRegex(ValueError, "already been consumed"):
            writer.continue_writing(self.state_path, approval, 2)
        self.edit("The specifically authorized sixth revision.")
        sixth = writer.freeze_revision(self.state_path)
        self.assertEqual("r006", sixth["id"])

    def test_fifth_revision_can_finish_without_extension(self):
        self.start()
        for revision in range(5):
            if revision:
                self.edit(f"Synthetic repair revision {revision + 1}.")
            self.freeze()
            self.reviews(fail_role="narrative" if revision < 4 else None)
        result = self.finish()
        self.assertTrue(result["pass"], result)
        self.assertEqual("complete", result["status"])
        self.assertEqual(5, result["reviewed_revisions"])

    def test_source_drift_and_brief_drift_block_instead_of_refreshing(self):
        self.start()
        self.freeze()
        original = self.source.read_bytes()
        self.source.write_bytes(original + b"\n% changed authority\n")
        self.assertFalse(writer.audit_writing(self.state_path)["pass"])
        self.source.write_bytes(original)
        brief_path = self.work / "writer" / "brief.json"
        brief = self.read(brief_path)
        brief["scope"] = "A stronger unapproved scope"
        self.write(brief_path, brief)
        self.assertFalse(writer.audit_writing(self.state_path)["pass"])

    def test_changed_macro_with_unchanged_root_forces_comprehensive_review(self):
        self.start()
        macros = self.output.parent / "macros.tex"
        macros.write_text("\\newcommand{\\identitydomain}{nonnegative integers}\n", encoding="utf-8")
        self.output.write_text(SAMPLE.replace("\\begin{document}", "\\input{macros}\n\\begin{document}"),
                               encoding="utf-8")
        self.freeze()
        self.reviews()
        original = self.output.read_bytes()
        macros.write_text("\\newcommand{\\identitydomain}{integers}\n", encoding="utf-8")
        self.freeze()
        packet = writer.review_packet(self.state_path, "faithfulness", "macro-recheck")
        self.assertEqual(original, self.output.read_bytes())
        self.assertEqual("comprehensive", packet["scope"])

    def test_gate_evidence_cannot_bypass_reviews_or_build(self):
        self.start()
        self.freeze()
        with self.assertRaisesRegex(ValueError, "cannot pass final"):
            mark_gate(self.state_path, "final", "pass", ["Trust this free-form claim"])
        self.reviews()
        with self.assertRaisesRegex(ValueError, "cannot pass final"):
            mark_gate(self.state_path, "final", "pass", ["All content reviewers passed"])
        self.finish()
        state = mark_gate(self.state_path, "final", "pass", ["Current receipt-bound writing audit"])
        self.assertEqual("pass", state["gates"]["final"]["status"])

    def test_build_pdf_tampering_invalidates_completion(self):
        self.start()
        self.freeze()
        self.reviews()
        self.assertTrue(self.finish()["pass"])
        revision = self.state()["writer"]["revisions"][-1]
        build = self.read(revision["builds"][-1]["path"])
        Path(build["retained_pdf"]).write_bytes(b"substituted PDF")
        self.assertFalse(writer.audit_writing(self.state_path, require_complete=True)["pass"])

    def test_build_log_tampering_blocks_layout_and_completion(self):
        self.start()
        self.freeze()
        self.reviews()
        self.assertTrue(self.finish()["pass"])
        revision = self.state()["writer"]["revisions"][-1]
        build = self.read(revision["builds"][-1]["path"])
        Path(build["retained_log"]).write_bytes(b"substituted compilation log")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            writer.review_packet(self.state_path, "layout", "new-layout-reviewer")
        self.assertFalse(writer.audit_writing(self.state_path, require_complete=True)["pass"])

    def test_layout_pass_requires_every_pdf_page_without_fabricated_or_duplicate_pages(self):
        self.start()
        self.freeze()
        self.reviews()
        self.mock_build(pages=2)
        for inspected in ([1], [1, 3], [1, 1, 2], [True, 2], "all"):
            with self.subTest(inspected=inspected):
                path = self.report("layout")
                report = self.read(path)
                report["pages_inspected"] = inspected
                self.write(path, report)
                with self.assertRaisesRegex(ValueError, "page"):
                    writer.record_review(self.state_path, path)
        path = self.report("layout")
        report = self.read(path)
        report["pages_inspected"] = [1, 2]
        self.write(path, report)
        writer.record_review(self.state_path, path)
        self.assertTrue(writer.audit_writing(self.state_path, require_complete=True)["pass"])

    def test_missing_pdf_page_count_cannot_authorize_release(self):
        self.start()
        self.freeze()
        self.reviews()
        self.mock_build(pages=None)
        with self.assertRaisesRegex(ValueError, "page count"):
            writer.review_packet(self.state_path, "layout", "new-layout-reviewer")
        self.assertFalse(writer.audit_writing(self.state_path, require_complete=True)["pass"])

    def test_same_revision_required_failure_needs_resolution_evidence(self):
        self.start()
        self.freeze()
        writer.record_review(self.state_path, self.report("narrative", "FAIL"))
        path = self.report("narrative", "PASS")
        report = self.read(path)
        report.pop("previous_findings", None)
        self.write(path, report)
        with self.assertRaisesRegex(ValueError, "previous|required|resolve"):
            writer.record_review(self.state_path, path)

    def test_only_a_complete_passing_faithfulness_role_can_supply_baseline(self):
        self.start(refine=True)
        self.freeze()
        writer.record_review(self.state_path, self.report("faithfulness"))
        writer.record_review(self.state_path, self.report("faithfulness-secondary", "FAIL", reviewer="second-independent"))
        for role in ("narrative", "notation", "wording"):
            writer.record_review(self.state_path, self.report(role))
        self.edit()
        self.freeze()
        packet = writer.review_packet(self.state_path, "faithfulness", "new-independent")
        self.assertIsNone(packet["last_pass_revision"])
        self.assertEqual("comprehensive", packet["scope"])

    def test_unchanged_freeze_rejection_does_not_poison_next_revision_path(self):
        self.start()
        self.freeze()
        self.reviews()
        writer.record_plan(self.state_path, self.plan())
        with self.assertRaisesRegex(ValueError, "unchanged"):
            writer.freeze_revision(self.state_path)
        self.edit()
        revision = writer.freeze_revision(self.state_path)
        self.assertEqual("r002", revision["id"])

    def test_each_faithfulness_track_receives_its_own_prior_findings(self):
        self.start(refine=True)
        self.freeze()
        writer.record_review(self.state_path, self.report("faithfulness", "FAIL", finding_id="primary-problem"))
        writer.record_review(self.state_path, self.report("faithfulness-secondary", "FAIL", finding_id="secondary-problem"))
        for role in ("narrative", "notation", "wording"):
            writer.record_review(self.state_path, self.report(role))
        self.edit()
        self.freeze()
        primary = writer.review_packet(self.state_path, "faithfulness", "primary-new-invocation")
        secondary = writer.review_packet(self.state_path, "faithfulness-secondary", "secondary-new-invocation")
        self.assertEqual(["primary-problem"], [row["id"] for row in primary["previous_report"]["findings"]])
        self.assertEqual(["secondary-problem"], [row["id"] for row in secondary["previous_report"]["findings"]])
        self.assertEqual("faithfulness", secondary["role"])
        self.assertEqual("secondary", secondary["review_track"])

    def test_failed_recursive_initialization_cannot_resume_as_legacy(self):
        with self.assertRaisesRegex(ValueError, "requires --source"):
            init_compose(self.output, self.work, workflow_version=2)
        state = self.state()
        self.assertEqual(2, state["schema_version"])
        self.assertEqual("incomplete", state["writer_initialization"])
        result = writer.resume_writing(self.state_path)
        self.assertFalse(result["pass"])
        self.assertEqual("blocked", result["status"])

    def test_layout_packet_is_not_staled_by_its_separate_content_report(self):
        self.start()
        self.freeze()
        self.mock_build()
        packet = writer.review_packet(self.state_path, "layout", "same-wording-invocation")
        content = self.report("wording", reviewer="same-wording-invocation")
        writer.record_review(self.state_path, content)
        layout = self.report("layout", packet=packet)
        writer.record_review(self.state_path, layout)
        self.assertEqual(1, len(self.state()["writer"]["revisions"][-1]["layouts"]))

    def test_frozen_revision_records_coordinator_writer_acceptance(self):
        self.start()
        revision = self.freeze(mathematical_change_account="Synthetic account: same identity, more explanation.")
        receipt = revision["writer_task_receipt"]
        self.assertEqual(revision["snapshot"]["digest"], receipt["accepted_manuscript_sha256"])
        self.assertIsNone(receipt["base_revision"])
        self.assertEqual("synthetic-writer", receipt["writer_id"])

    def test_failed_review_cannot_drop_an_earlier_unresolved_required_finding(self):
        self.start()
        self.freeze()
        self.reviews(fail_role="narrative")
        self.edit()
        self.freeze()
        path = self.report("narrative", "FAIL", finding_id="different-new-defect")
        # The old finding is only marked persisting in previous_findings. It must
        # remain in the required finding set seen by the next round too.
        with self.assertRaisesRegex(ValueError, "carried forward"):
            writer.record_review(self.state_path, path)
        value = self.read(path)
        value["findings"].append({"id": "narrative-required", "severity": "required",
                                  "location": "Original defective passage", "evidence": "Still unresolved",
                                  "resolution": "Repair and independently recheck the old requirement"})
        self.write(path, value)
        writer.record_review(self.state_path, path)

    def test_layout_failure_requires_disposition_on_same_pdf_retry(self):
        self.start()
        self.freeze()
        self.reviews()
        self.mock_build()
        writer.record_review(self.state_path, self.report("layout", "FAIL", finding_id="layout-clipped"))
        self.assertFalse(writer.audit_writing(self.state_path, require_complete=True)["pass"])
        path = self.report("layout")
        value = self.read(path)
        value.pop("previous_findings")
        self.write(path, value)
        with self.assertRaisesRegex(ValueError, "previous required"):
            writer.record_review(self.state_path, path)
        writer.record_review(self.state_path, self.report("layout"))
        self.assertEqual("complete", writer.audit_writing(self.state_path, require_complete=True)["status"])

    def test_multiple_reviewer_branches_cannot_hide_old_required_findings(self):
        self.start()
        self.freeze()
        self.reviews(fail_role="narrative")
        writer.record_review(self.state_path, self.report("narrative", reviewer="second-narrative"))
        self.edit()
        self.freeze()
        packet = writer.review_packet(self.state_path, "narrative", "third-narrative")
        self.assertEqual("PASS", packet["previous_report"]["verdict"])
        self.assertEqual(["narrative-required"], [f["id"] for f in packet["unresolved_findings"]])
        path = self.report("narrative", packet=packet)
        value = self.read(path)
        value.pop("previous_findings")
        self.write(path, value)
        with self.assertRaisesRegex(ValueError, "previous required"):
            writer.record_review(self.state_path, path)

    def test_another_layout_invocation_cannot_silently_override_a_failure(self):
        self.start()
        self.freeze()
        self.reviews()
        self.mock_build()
        writer.record_review(self.state_path, self.report("layout", "FAIL"))
        writer.record_review(self.state_path, self.report("layout", reviewer="independent-layout-b"))
        report = writer.audit_writing(self.state_path, require_complete=True)
        self.assertFalse(report["pass"])
        self.assertEqual("needs_revision", report["status"])

    def test_cannot_resolve_another_current_reviewers_unseen_finding(self):
        self.start()
        self.freeze()
        writer.record_review(self.state_path, self.report("narrative", "FAIL"))
        path = self.report("narrative", reviewer="other-narrative")
        value = self.read(path)
        value["previous_findings"] = {"narrative-required": {"status": "resolved", "evidence": "not in this packet"}}
        self.write(path, value)
        with self.assertRaisesRegex(ValueError, "absent from its packet"):
            writer.record_review(self.state_path, path)


if __name__ == "__main__":
    unittest.main()
