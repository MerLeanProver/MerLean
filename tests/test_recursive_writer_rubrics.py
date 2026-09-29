"""Rubric version compatibility; synthetic fixtures do not assess editorial quality."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper_writing_codex import recursive_writer as writer
from paper_writing_codex.versioning import sha256_file
from paper_writing_codex.workflow import init_compose


SAMPLE = r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:identity}
For every integer $n$, $n=n$.
\end{theorem}
\begin{proof}
Reflexivity proves the identity.
\end{proof}
\end{document}
"""


class RecursiveWriterRubricTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.tex"
        self.source.write_text(SAMPLE, encoding="utf-8")
        self.work = self.root / "run"
        self.output = self.root / "draft" / "paper.tex"
        self.state_path = self.work / "00-run-state.json"
        init_compose(self.output, self.work, workflow_version=2,
                     authoritative_sources=[self.source])
        self.output.write_text(SAMPLE, encoding="utf-8")

    def rubric_path(self, role):
        return self.work / "writer" / "rubrics" / f"{role}.json"

    def read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, path, value):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def set_baseline(self, baseline, *, revision=None, extension=False):
        for role, prefix in zip(writer.ROLES, ("F", "N", "D", "W")):
            value = {"role": role, "version": revision or baseline,
                     "checkpoints": [
                         {"id": f"{prefix}{index:02}", "severity": "required",
                          "acceptance": acceptance}
                         for index, acceptance in enumerate(writer.CHECKPOINTS_BY_VERSION[baseline][role], 1)
                     ]}
            if baseline != 1:
                value["defaults_version"] = baseline
            if extension:
                value["checkpoints"].append({"id": f"{prefix}99", "severity": "required",
                                             "acceptance": "Synthetic author-added obligation."})
            self.write(self.rubric_path(role), value)

    def freeze(self):
        claims = self.read(self.work / "writer" / "source-claims.json")["claims"]
        main = next(row["id"] for row in claims if row["kind"] == "statement")
        approval = self.root / "synthetic-approval.txt"
        approval.write_text("Synthetic fixture author approves the identity-only brief.", encoding="utf-8")
        self.write(self.work / "writer" / "brief.json", {
            "audience": "Elementary mathematics readers", "question": "How is the identity stated?",
            "contribution": "Explain the supplied identity.", "scope": "The supplied integer identity only.",
            "main_claim_ids": [main], "exclusions": ["new mathematics"],
            "approval_evidence": str(approval),
        })
        plan = self.root / "plan.json"
        self.write(plan, {
            "planner_id": "synthetic-planner", "writer_id": "synthetic-writer", "base_revision": None,
            "objective": "Explain the approved identity.", "outline": ["Identity and proof"],
            "claim_map": [{"claim_id": row["id"], "disposition": "retained",
                           "location": "Identity and proof", "reason": "Preserve source content",
                           "candidate_label": "thm:identity" if row["id"] == main else None}
                          for row in claims],
        })
        writer.record_plan(self.state_path, plan)
        writer.freeze_revision(self.state_path)

    def report(self, packet, name):
        value = {key: packet[key] for key in (
            "packet_id", "revision_id", "role", "review_kind", "reviewer_id", "bindings")}
        value.update(verdict="PASS", summary="Synthetic receipt test, not an editorial assessment.",
                     findings=[], coverage=[{
                         "checkpoint_id": checkpoint["id"], "status": "PASS",
                         "evidence": "Synthetic fixture explicitly accounts for this obligation.",
                     } for checkpoint in packet["rubric"]["checkpoints"]])
        if packet["role"] == "faithfulness":
            value["scope"] = packet["scope"]
            value["claim_reviews"] = [
                {"claim_id": row["id"], "status": "faithful",
                 "evidence": "Synthetic source-to-draft claim correspondence checked."}
                for row in packet["source_claims"]["claims"]
            ]
        path = self.root / name
        self.write(path, value)
        return path

    def test_new_runs_use_v4_without_changing_checkpoint_ids_or_counts(self):
        self.assertEqual(4, writer.DEFAULT_RUBRIC_VERSION)
        self.assertEqual(("faithfulness", "narrative", "notation", "wording"), writer.ROLES)
        self.assertEqual({1, 2, 3, 4}, set(writer.CHECKPOINTS_BY_VERSION))
        for role, prefix, count in zip(writer.ROLES, ("F", "N", "D", "W"), (8, 5, 5, 6)):
            with self.subTest(role=role):
                value = self.read(self.rubric_path(role))
                self.assertEqual((4, 4), (value["version"], value["defaults_version"]))
                self.assertEqual([f"{prefix}{index:02}" for index in range(1, count + 1)],
                                 [row["id"] for row in value["checkpoints"]])
                self.assertTrue(all(row["severity"] == "required" for row in value["checkpoints"]))
                self.assertEqual(list(writer.CHECKPOINTS[role]),
                                 [row["acceptance"] for row in value["checkpoints"]])
        self.assertEqual(set(writer.ROLES), set(writer._rubrics(self.work)))

    def test_v2_requires_locatable_definition_block_claim_and_statement_evidence(self):
        self.set_baseline(2)
        expected = {
            ("faithfulness", "F03"): ("every nontrivial numbered claim", "reader-visible proof",
                                       "precise external citation", "explicit internal proof pointer",
                                       "identified deduction", "missing justification", "weak discoverability",
                                       "do not reprove accepted source mathematics", "locatable justification route"),
            ("narrative", "N02"): ("purpose of supporting lemmas and technical blocks before",
                                    "one introduction may orient a whole block", "locates each substantial block"),
            ("narrative", "N03"): ("reader-visible interpretation", "reason for introduction",
                                    "before or immediately alongside", "locates these explanations"),
            ("notation", "D01"): ("what the quantity measures or concept means", "why it is introduced",
                                   "before or immediately alongside", "Do not require motivation for every routine symbol",
                                   "locates its interpretation and purpose"),
            ("wording", "W03"): ("formal statements focused on mathematical content", "adjacent prose",
                                  "preserve every hypothesis, quantifier and qualification", "locates statements checked"),
        }
        for (role, checkpoint_id), phrases in expected.items():
            value = self.read(self.rubric_path(role))
            acceptance = next(row["acceptance"] for row in value["checkpoints"] if row["id"] == checkpoint_id)
            with self.subTest(checkpoint=checkpoint_id):
                self.assertIn("PASS evidence", acceptance)
                for phrase in phrases:
                    self.assertIn(phrase, acceptance)

    def test_v3_changes_only_N02_N03_and_D01_from_v2(self):
        changed = set()
        for role in writer.ROLES:
            for index, (previous, current) in enumerate(zip(writer.V2_CHECKPOINTS[role],
                                                            writer.V3_CHECKPOINTS[role]), 1):
                if previous != current:
                    changed.add((role, index))
                else:
                    self.assertEqual(previous.encode("utf-8"), current.encode("utf-8"))
        self.assertEqual({("narrative", 2), ("narrative", 3), ("notation", 1)}, changed)

    def test_v3_requires_first_encounter_evidence_and_reader_impact(self):
        for role, index in (("narrative", 1), ("narrative", 2), ("notation", 0)):
            with self.subTest(role=role, index=index):
                acceptance = writer.V3_CHECKPOINTS[role][index]
                for phrase in (
                        "before or at entry", "later proofs, applications, or reviewer reconstruction",
                        "cannot supply missing introductory explanation", "PASS evidence",
                        "short exact introductory passage with its location", "the question it answers",
                        "explicit short inference from local context", "only later or reconstructed",
                        "reader must await later material", "reconstruct a nontrivial argument",
                        "unanswered question", "extra explanation is advisory", "stock phrase"):
                    self.assertIn(phrase, acceptance)
        for role, index in (("narrative", 2), ("notation", 0)):
            with self.subTest(definition_role=role):
                acceptance = writer.V3_CHECKPOINTS[role][index]
                for phrase in (
                        "intended purpose", "conceptual reason", "consequential, non-obvious branches",
                        "thresholds", "competing terms", "not a preliminary proof",
                        "derivation of every constant", "routine symbols", "standard formulas",
                        "transparent rewritings", "evident cases"):
                    self.assertIn(phrase, acceptance)
        for phrase in (
                "changes of mathematical object or argumentative purpose", "not merely section boundaries",
                "ingredients' roles and their connection", "generic announcement of useful tools",
                "eventual output is insufficient", "One introduction may orient a whole block"):
            self.assertIn(phrase, writer.V3_CHECKPOINTS["narrative"][1])

    def test_v4_changes_only_N02_from_v3(self):
        changed = set()
        for role in writer.ROLES:
            self.assertEqual(len(writer.V3_CHECKPOINTS[role]), len(writer.CHECKPOINTS[role]))
            for index, (previous, current) in enumerate(zip(writer.V3_CHECKPOINTS[role],
                                                            writer.CHECKPOINTS[role]), 1):
                if previous.encode("utf-8") != current.encode("utf-8"):
                    changed.add((role, index))
        self.assertEqual({("narrative", 2)}, changed)

    def test_v4_N02_requires_a_local_objective_not_merely_result_content(self):
        acceptance = writer.CHECKPOINTS["narrative"][1]
        for phrase in (
                "result content (what it computes)", "purpose (why it is needed now)",
                "changes of mathematical object or argumentative purpose",
                "why that family, comparison, or quantity is introduced",
                "already introduced question or next-step objective", "ingredient's contribution",
                "immediate connection", "objective cannot be invented from later applications",
                "Naming a count, bound, calculation, or tool",
                "paraphrasing the conclusion alone, is not purpose evidence",
                "reader must discover its intended use or choice from later material",
                "mathematics and retrospective connection are elementary",
                "explicit local goal plus a transparent inference", "forward theorem number",
                "Routine intermediate proof steps are not substantial detours",
                "One introduction may orient a whole block", "do not repeat a purpose",
                "before or at entry", "cannot supply missing introductory explanation",
                "short exact introductory passage with its location", "the question it answers",
                "explicit short inference from local context", "only later or reconstructed",
                "unanswered question and entry point", "extra explanation is advisory"):
            self.assertIn(phrase, acceptance)
        self.assertNotIn("reconstruct a nontrivial argument", acceptance)

    def test_narrative_role_keeps_v4_local_objective_and_proportionate_exemption(self):
        text = " ".join((ROOT / "roles" / "paper-narrative.md").read_text(encoding="utf-8").split())
        for phrase in (
                "Distinguish mathematical content from argumentative purpose",
                "already introduced question or next-step objective",
                "Do not infer the objective itself from a later application",
                "why this family, comparison, or quantity is introduced",
                "retrospective connection are elementary", "Routine intermediate steps",
                "quote the local evidence for its objective", "forward theorem number"):
            self.assertIn(phrase, text)

    def test_role_contracts_require_local_evidence_in_existing_coverage_fields(self):
        for role in ("narrative", "notation"):
            with self.subTest(role=role):
                text = " ".join((ROOT / "roles" / f"paper-{role}.md").read_text(encoding="utf-8").split())
                for phrase in ("First-encounter evidence", "short exact", "before/at entry",
                               "explicit short inference", "only later or reconstructed",
                               "existing coverage", "stock phrase", "advisory", "reader obstacle"):
                    self.assertIn(phrase, text)
                self.assertIn("no new report schema" if role == "narrative" else "without a new report schema", text)

    def test_historical_baseline_snapshots_are_exact_and_immutable(self):
        # Captured before each default upgrade, independent of current defaults.
        expected = {
            1: "9581c09098598c5bbf0441ad50745aa526565c168c090712e27349eb68be19bc",
            2: "9f76866929533cdf03b08c2a95e805a5db06b35e952154892cf5a67b6e603c95",
            3: "ad388ecd39f8f8682cdc8bff0444288531eb416d60c688b73015edfbff22251d",
        }
        self.assertIs(writer.LEGACY_CHECKPOINTS, writer.CHECKPOINTS_BY_VERSION[1])
        self.assertIs(writer.V2_CHECKPOINTS, writer.CHECKPOINTS_BY_VERSION[2])
        self.assertIs(writer.V3_CHECKPOINTS, writer.CHECKPOINTS_BY_VERSION[3])
        for baseline, digest in expected.items():
            with self.subTest(baseline=baseline):
                checkpoints = writer.CHECKPOINTS_BY_VERSION[baseline]
                encoded = json.dumps(dict(checkpoints), sort_keys=True, separators=(",", ":")).encode()
                self.assertEqual(digest, hashlib.sha256(encoded).hexdigest())
                with self.assertRaises(TypeError):
                    checkpoints["narrative"] = ()
                with self.assertRaises(TypeError):
                    checkpoints["narrative"][1] = "Changed historical requirement."
        with self.assertRaises(TypeError):
            writer.CHECKPOINTS_BY_VERSION[1] = writer.CHECKPOINTS

    def test_changed_defaults_keep_the_original_legacy_acceptance(self):
        expected = {
            ("faithfulness", 2): "Supply necessary definitions and results or precise appropriate citations.",
            ("narrative", 1): "Organize sections with visible purpose and logical transitions.",
            ("narrative", 2): "Explain central ideas adequately and give routine material proportionate space.",
            ("notation", 0): "Introduce only useful notation and explain its motivation.",
            ("wording", 2): "Remove unnecessary repetition without deleting scope or helpful reminders.",
        }
        for (role, index), acceptance in expected.items():
            with self.subTest(role=role, index=index):
                self.assertEqual(acceptance, writer.LEGACY_CHECKPOINTS[role][index])
                self.assertNotEqual(acceptance, writer.CHECKPOINTS[role][index])

    def test_saved_rubrics_and_author_extensions_remain_byte_identical(self):
        self.freeze()
        for baseline in (1, 2, 3, 4):
            for revision in (baseline, baseline + 1, 17):
                with self.subTest(baseline=baseline, author_revision=revision):
                    self.set_baseline(baseline, revision=revision, extension=revision != baseline)
                    before = {role: self.rubric_path(role).read_bytes() for role in writer.ROLES}
                    receipts = writer._rubrics(self.work)
                    audit = writer.audit_writing(self.state_path)
                    self.assertEqual([], audit["errors"], audit)
                    self.assertEqual("reviewing", audit["status"])
                    for role in writer.ROLES:
                        packet = writer.review_packet(self.state_path, role,
                                                      f"synthetic-{role}-v{baseline}-{revision}")
                        self.assertEqual(json.loads(before[role]), packet["rubric"])
                        if baseline == 1:
                            self.assertNotIn("defaults_version", packet["rubric"])
                        else:
                            self.assertEqual(baseline, packet["rubric"]["defaults_version"])
                        self.assertEqual(sha256_file(self.rubric_path(role)), receipts[role]["sha256"])
                        self.assertEqual(receipts[role]["sha256"], packet["bindings"]["rubric"])
                    self.assertEqual(before, {role: self.rubric_path(role).read_bytes() for role in writer.ROLES})

    def test_required_checkpoints_cannot_be_weakened_or_deleted_in_any_baseline(self):
        for baseline in (1, 2, 3, 4):
            for role in writer.ROLES:
                for index in range(len(writer.CHECKPOINTS_BY_VERSION[baseline][role])):
                    for change in ("delete", "acceptance", "severity"):
                        with self.subTest(baseline=baseline, role=role, checkpoint=index + 1, change=change):
                            self.set_baseline(baseline)
                            path = self.rubric_path(role)
                            value = self.read(path)
                            if change == "delete":
                                value["checkpoints"].pop(index)
                            else:
                                value["checkpoints"][index][change] = (
                                    "Synthetic weaker condition." if change == "acceptance" else "advisory")
                            self.write(path, value)
                            with self.assertRaisesRegex(ValueError, "default required checkpoints cannot be deleted or weakened"):
                                writer._rubrics(self.work)

    def test_explicit_baseline_change_stales_the_review_without_migrating_other_rubrics(self):
        self.set_baseline(2)
        self.freeze()
        packet = writer.review_packet(self.state_path, "notation", "synthetic-notation-reviewer")
        report = self.report(packet, "old-review.json")
        writer.record_review(self.state_path, report)
        self.assertNotIn("notation", writer.audit_writing(self.state_path)["pending_roles"])
        unchanged = {role: self.rubric_path(role).read_bytes() for role in writer.ROLES if role != "notation"}
        path = self.rubric_path("notation")
        rubric = self.read(path)
        rubric.update(version=3, defaults_version=3)
        for row, acceptance in zip(rubric["checkpoints"], writer.V3_CHECKPOINTS["notation"]):
            row["acceptance"] = acceptance
        self.write(path, rubric)
        audit = writer.audit_writing(self.state_path)
        self.assertEqual([], audit["errors"], audit)
        self.assertIn("notation", audit["pending_roles"])
        self.assertEqual(1, audit["reviewed_revisions"])
        with self.assertRaisesRegex(ValueError, "stale or mismatched"):
            writer.record_review(self.state_path, report)
        current = writer.review_packet(self.state_path, "notation", "synthetic-notation-reviewer")
        self.assertEqual(packet["bindings"]["manuscript"], current["bindings"]["manuscript"])
        self.assertNotEqual(packet["bindings"]["rubric"], current["bindings"]["rubric"])
        writer.record_review(self.state_path, self.report(current, "current-review.json"))
        self.assertNotIn("notation", writer.audit_writing(self.state_path)["pending_roles"])
        self.assertEqual(unchanged, {role: self.rubric_path(role).read_bytes() for role in unchanged})

    def test_v3_to_v4_N02_upgrade_stales_only_narrative_review(self):
        self.set_baseline(3)
        self.freeze()
        packets = {}
        reports = {}
        for role in writer.ROLES:
            packets[role] = writer.review_packet(self.state_path, role, f"synthetic-{role}-reviewer")
            reports[role] = self.report(packets[role], f"v3-{role}-review.json")
            writer.record_review(self.state_path, reports[role])
        self.assertEqual([], writer.audit_writing(self.state_path)["pending_roles"])
        unchanged = {role: self.rubric_path(role).read_bytes() for role in writer.ROLES
                     if role != "narrative"}
        path = self.rubric_path("narrative")
        rubric = self.read(path)
        rubric.update(version=4, defaults_version=4)
        rubric["checkpoints"][1]["acceptance"] = writer.CHECKPOINTS["narrative"][1]
        self.write(path, rubric)
        audit = writer.audit_writing(self.state_path)
        self.assertEqual([], audit["errors"], audit)
        self.assertEqual(["narrative"], audit["pending_roles"])
        self.assertEqual(unchanged, {role: self.rubric_path(role).read_bytes() for role in unchanged})
        with self.assertRaisesRegex(ValueError, "stale or mismatched"):
            writer.record_review(self.state_path, reports["narrative"])
        current = writer.review_packet(self.state_path, "narrative", "synthetic-narrative-reviewer")
        for binding, digest in packets["narrative"]["bindings"].items():
            if binding == "rubric":
                self.assertNotEqual(digest, current["bindings"][binding])
            else:
                self.assertEqual(digest, current["bindings"][binding])
        writer.record_review(self.state_path, self.report(current, "v4-narrative-review.json"))
        self.assertEqual([], writer.audit_writing(self.state_path)["pending_roles"])
        self.assertEqual(unchanged, {role: self.rubric_path(role).read_bytes() for role in unchanged})

    def test_unsupported_or_noninteger_defaults_version_is_rejected(self):
        for baseline in (0, 5, True, 1.0, "4", None):
            with self.subTest(defaults_version=baseline):
                path = self.rubric_path("faithfulness")
                value = self.read(path)
                value["defaults_version"] = baseline
                self.write(path, value)
                with self.assertRaisesRegex(ValueError, "unsupported faithfulness rubric defaults_version"):
                    writer._rubrics(self.work)


if __name__ == "__main__":
    unittest.main()
