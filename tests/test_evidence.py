"""Synthetic evidence-contract tests; no Java, model or runtime detection."""
from dataclasses import replace
from hashlib import sha256
import unittest

from aixsecurity.domain.evidence import (
    CONDITIONS, Evidence, ReviewAssessment, ReviewRecord, SourceRef, SqliCase, evaluate_sqli,
)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = {}
        self.source = SourceRef("java-fixture", "a" * 40, "src/Controller.java", 12, 18)
        self.evidence = tuple(
            Evidence(condition, "request-query", condition, "supported", self.source,
                     self.artifact(f"synthetic record for {condition}"), "fixture", "1", "Fixture assumption, not actual analysis")
            for condition in sorted(CONDITIONS)
        )
        self.case = SqliCase("case-1", 1, "snapshot-1", "java-fixture", "a" * 40,
                             "request-query", "investigator-1", self.evidence)

    def artifact(self, text):
        data = text.encode()
        digest = sha256(data).hexdigest()
        self.artifacts[digest] = data
        return digest

    def review(self, case):
        return ReviewRecord(case.digest, "reviewer-2", "review-1",
                            tuple(e.evidence_id for e in case.evidence),
                            self.artifact("Synthetic independent-review receipt, not a model invocation"),
                            execution_status="completed",
                            assessments=tuple(ReviewAssessment(
                                condition,
                                next((e.stance for e in case.evidence if e.condition == condition), "missing"),
                                tuple(e.evidence_id for e in case.evidence if e.condition == condition),
                                "Synthetic reviewer assessment; no actual reviewer was executed")
                                for condition in sorted(CONDITIONS)))

    def evaluate(self, case=None):
        case = case or self.case
        return evaluate_sqli(case, self.review(case), self.artifacts)

    def test_complete_records_pass_static_gate_not_runtime_detection(self):
        result = self.evaluate()
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.verification_method, "static_review")
        self.assertEqual(result.assurance, "application_contract_only")

    def test_effective_parameter_binding_counterexample(self):
        records = tuple(replace(e, stance="counter", explanation="Untrusted values only reach bound placeholders; no SQL structure interpolation")
                        if e.condition in {"sql_structure_influence", "no_effective_guard"} else e
                        for e in self.evidence)
        self.assertEqual(self.evaluate(replace(self.case, evidence=records)).status, "rejected")

    def test_missing_control_path_or_guard_is_suspicious(self):
        for condition in ("attacker_control", "propagation", "no_effective_guard"):
            with self.subTest(condition=condition):
                records = tuple(replace(e, stance="missing") if e.condition == condition else e for e in self.evidence)
                result = self.evaluate(replace(self.case, evidence=records))
                self.assertEqual(result.status, "suspicious")
                self.assertIn(condition, result.missing_conditions)

    def test_bare_tool_hits_never_confirm(self):
        case = replace(self.case, evidence=tuple(replace(e, kind="tool_hit") for e in self.evidence))
        self.assertEqual(self.evaluate(case).status, "suspicious")

    def test_conflicting_evidence_is_suspicious(self):
        opposite = replace(self.evidence[0], evidence_id="counter-1", stance="counter")
        case = replace(self.case, evidence=self.evidence + (opposite,))
        self.assertEqual(self.evaluate(case).status, "suspicious")

    def test_mismatched_repo_commit_or_branch_rejected(self):
        for changes in ({"repo_id": "other"}, {"commit": "b" * 40}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.case, evidence=(replace(self.evidence[0], source=replace(self.source, **changes)),))
        with self.assertRaises(ValueError):
            replace(self.case, evidence=(replace(self.evidence[0], branch_id="another-input"),))

    def test_source_ref_rejects_mutable_refs_invalid_lines_and_paths(self):
        for changes in ({"commit": "main"}, {"commit": "a" * 7}, {"start_line": 0},
                        {"start_line": True}, {"end_line": 1}, {"path": "../other"},
                        {"path": "/tmp/file"}, {"path": "./src/File.java"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.source, **changes)

    def test_no_review_and_boolean_are_not_independent_review(self):
        self.assertEqual(evaluate_sqli(self.case, None, self.artifacts).status, "suspicious")
        with self.assertRaises(ValueError):
            evaluate_sqli(self.case, True, self.artifacts)
        with self.assertRaises(ValueError):
            evaluate_sqli(self.case, replace(self.review(self.case), reviewer_id="investigator-1"), self.artifacts)

    def test_stale_review_rejected_after_case_or_evidence_change(self):
        review = self.review(self.case)
        for changed in (replace(self.case, revision=2), replace(self.case, snapshot_id="snapshot-2"),
                        replace(self.case, evidence=self.evidence[:-1])):
            with self.subTest(changed=changed.digest), self.assertRaises(ValueError):
                evaluate_sqli(changed, review, self.artifacts)

    def test_review_must_include_every_evidence_reference(self):
        review = replace(self.review(self.case), evidence_ids=())
        with self.assertRaises(ValueError):
            evaluate_sqli(self.case, review, self.artifacts)

    def test_artifact_hash_mismatch_and_missing_bytes_rejected(self):
        review = self.review(self.case)
        digest = self.evidence[0].artifact_digest
        for artifacts in ({}, {**self.artifacts, digest: b"tampered"}):
            with self.subTest(artifacts=len(artifacts)), self.assertRaises(ValueError):
                evaluate_sqli(self.case, review, artifacts)

    def test_runtime_claim_cannot_be_fabricated_with_receipt(self):
        with self.assertRaises(ValueError):
            replace(self.review(self.case), method="runtime_verified")
        with self.assertRaises(ValueError):
            replace(self.evidence[0], kind="runtime_execution")

    def test_gap_not_hidden_by_counter_on_other_condition(self):
        records = tuple(replace(e, stance="counter") if e.condition == "no_effective_guard"
                        else replace(e, stance="missing") if e.condition == "propagation"
                        else e for e in self.evidence)
        self.assertEqual(self.evaluate(replace(self.case, evidence=records)).status, "suspicious")

    def test_failed_incomplete_and_no_condition_review_never_confirm(self):
        review = self.review(self.case)
        for changed in (replace(review, execution_status="failed"),
                        replace(review, execution_status="incomplete"),
                        replace(review, assessments=())):
            with self.subTest(status=changed.execution_status):
                result = evaluate_sqli(self.case, changed, self.artifacts)
                self.assertEqual(result.status, "suspicious")
                self.assertEqual(result.verification_method, "unreviewed")

    def test_reviewer_disagreement_and_missing_are_not_ignored(self):
        review = self.review(self.case)
        for stance in ("counter", "missing"):
            changed = replace(review, assessments=(replace(review.assessments[0], stance=stance),) + review.assessments[1:])
            self.assertEqual(evaluate_sqli(self.case, changed, self.artifacts).status, "suspicious")

    def test_reviewer_cannot_cite_another_conditions_evidence(self):
        review = self.review(self.case)
        changed = replace(review, assessments=(replace(review.assessments[0], evidence_ids=(self.evidence[1].evidence_id,)),) + review.assessments[1:])
        with self.assertRaises(ValueError):
            evaluate_sqli(self.case, changed, self.artifacts)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            replace(self.case, evidence=self.evidence + (self.evidence[0],))


if __name__ == "__main__":
    unittest.main()
