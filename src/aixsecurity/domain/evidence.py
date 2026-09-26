"""Fail-closed SQLi evidence gate; does not discover or verify Java vulnerabilities.

Artifact bytes authenticate references, not the truth of their contents. ReviewRecord
is a receipt from a separately executed reviewer, not evidence that this module ran
one. Only trusted adapters should construct these objects in a deployed service.
Runtime verification is deliberately unsupported until an execution adapter exists.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re
from typing import Mapping


CONDITIONS = frozenset({
    "attacker_control", "propagation", "sql_structure_influence",
    "sink_reachable", "no_effective_guard",
})
STANCES = frozenset({"supported", "counter", "missing"})


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _digest(value: str, field: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{field} must be lowercase SHA-256")


@dataclass(frozen=True)
class SourceRef:
    repo_id: str
    commit: str
    path: str
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        _text(self.repo_id, "repo_id")
        if not isinstance(self.commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.commit):
            raise ValueError("commit must be a complete immutable Git object ID")
        _text(self.path, "path")
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts or "\\" in self.path or str(path) != self.path or self.path == ".":
            raise ValueError("path must be a normalized repository-relative path")
        if type(self.start_line) is not int or type(self.end_line) is not int or not 1 <= self.start_line <= self.end_line:
            raise ValueError("source line range must be positive and ordered")


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    branch_id: str
    condition: str
    stance: str
    source: SourceRef
    artifact_digest: str
    producer: str
    producer_version: str
    explanation: str
    kind: str = "static_analysis"

    def __post_init__(self) -> None:
        for field in ("evidence_id", "branch_id", "producer", "producer_version", "explanation"):
            _text(getattr(self, field), field)
        if not isinstance(self.source, SourceRef):
            raise ValueError("source must be SourceRef")
        if self.condition not in CONDITIONS or self.stance not in STANCES:
            raise ValueError("unknown condition or stance")
        _digest(self.artifact_digest, "artifact_digest")
        if self.kind not in {"static_analysis", "source_observation", "tool_hit"}:
            raise ValueError("unsupported evidence kind; runtime proof requires a future adapter")


@dataclass(frozen=True)
class SqliCase:
    case_id: str
    revision: int
    snapshot_id: str
    repo_id: str
    commit: str
    branch_id: str
    investigator_id: str
    evidence: tuple[Evidence, ...]

    def __post_init__(self) -> None:
        for field in ("case_id", "snapshot_id", "repo_id", "branch_id", "investigator_id"):
            _text(getattr(self, field), field)
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("revision must be a positive integer")
        if not isinstance(self.commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.commit):
            raise ValueError("case commit must be complete")
        if not isinstance(self.evidence, tuple) or not all(isinstance(e, Evidence) for e in self.evidence):
            raise ValueError("evidence must be an immutable tuple of Evidence")
        if len({e.evidence_id for e in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate evidence ID")
        for item in self.evidence:
            if (item.source.repo_id, item.source.commit, item.branch_id) != (self.repo_id, self.commit, self.branch_id):
                raise ValueError("evidence repo, commit or branch does not match case")

    @property
    def digest(self) -> str:
        """Bind a review to the full case revision, including every evidence claim."""
        return sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ReviewAssessment:
    condition: str
    stance: str
    evidence_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.condition not in CONDITIONS or self.stance not in STANCES:
            raise ValueError("unknown reviewer condition or stance")
        _text(self.reason, "review reason")
        if not isinstance(self.evidence_ids, tuple) or not all(isinstance(i, str) for i in self.evidence_ids):
            raise ValueError("assessment references must be a tuple of strings")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("duplicate assessment reference")
        if self.stance != "missing" and not self.evidence_ids:
            raise ValueError("review assertion requires evidence references")


@dataclass(frozen=True)
class ReviewRecord:
    case_digest: str
    reviewer_id: str
    review_id: str
    evidence_ids: tuple[str, ...]
    artifact_digest: str
    method: str = "static_review"
    execution_status: str = "incomplete"
    assessments: tuple[ReviewAssessment, ...] = ()

    def __post_init__(self) -> None:
        _digest(self.case_digest, "case_digest")
        _digest(self.artifact_digest, "artifact_digest")
        _text(self.reviewer_id, "reviewer_id")
        _text(self.review_id, "review_id")
        if not isinstance(self.evidence_ids, tuple) or not all(isinstance(i, str) for i in self.evidence_ids):
            raise ValueError("review evidence_ids must be a tuple of strings")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("duplicate reviewed evidence ID")
        if self.execution_status not in {"completed", "failed", "incomplete"}:
            raise ValueError("unknown review execution status")
        if not isinstance(self.assessments, tuple) or not all(isinstance(a, ReviewAssessment) for a in self.assessments):
            raise ValueError("assessments must be immutable ReviewAssessment records")
        if len({a.condition for a in self.assessments}) != len(self.assessments):
            raise ValueError("duplicate reviewer condition")
        if self.method != "static_review":
            raise ValueError("runtime_verified is unsupported; a receipt cannot prove execution")


@dataclass(frozen=True)
class Verdict:
    status: str
    verification_method: str
    case_digest: str
    reasons: tuple[str, ...]
    missing_conditions: tuple[str, ...] = ()
    # This gate verifies record consistency, never independent real-world truth.
    assurance: str = "application_contract_only"


def _check_artifact(digest: str, artifacts: Mapping[str, bytes]) -> None:
    data = artifacts.get(digest)
    if not isinstance(data, bytes) or not data or sha256(data).hexdigest() != digest:
        raise ValueError("artifact absent, empty or hash mismatch")


def evaluate_sqli(case: SqliCase, review: ReviewRecord | None,
                  artifacts: Mapping[str, bytes]) -> Verdict:
    """Assess ONE SQLi path branch from externally supplied evidence and review.

    supported/counter concern a named necessary condition, not generic confidence.
    missing records a known gap and overrides support for that condition. A bare
    tool hit never establishes a condition. No runtime_verified result is emitted.
    Invalid provenance raises ValueError; incomplete evidence stays suspicious.
    """
    if not isinstance(case, SqliCase):
        raise ValueError("case must be SqliCase")
    for evidence in case.evidence:
        _check_artifact(evidence.artifact_digest, artifacts)
    if review is None:
        return Verdict("suspicious", "unreviewed", case.digest, ("independent review record missing",))
    if not isinstance(review, ReviewRecord):
        raise ValueError("review must be ReviewRecord, not a verification boolean")
    _check_artifact(review.artifact_digest, artifacts)
    if review.case_digest != case.digest:
        raise ValueError("stale or mismatched review")
    if review.reviewer_id == case.investigator_id:
        raise ValueError("reviewer must differ from investigator")
    if set(review.evidence_ids) != {e.evidence_id for e in case.evidence}:
        raise ValueError("review must reference the complete evidence set")

    if review.execution_status != "completed":
        return Verdict("suspicious", "unreviewed", case.digest,
                       (f"review execution {review.execution_status}",))
    assessed = {a.condition: a for a in review.assessments}
    if set(assessed) != CONDITIONS:
        return Verdict("suspicious", "unreviewed", case.digest,
                       ("reviewer has not assessed every prerequisite",), tuple(sorted(CONDITIONS - set(assessed))))
    by_id = {e.evidence_id: e for e in case.evidence}
    for assessment in review.assessments:
        for ref in assessment.evidence_ids:
            if ref not in by_id or by_id[ref].condition != assessment.condition:
                raise ValueError("review assessment refers to absent or unrelated evidence")

    states = {condition: set() for condition in CONDITIONS}
    for evidence in case.evidence:
        if evidence.kind != "tool_hit":
            states[evidence.condition].add(evidence.stance)
    conflicts = sorted(key for key, value in states.items() if {"supported", "counter"} <= value)
    if conflicts:
        return Verdict("suspicious", "static_review", case.digest,
                       tuple(f"conflicting evidence: {key}" for key in conflicts))
    gaps = tuple(sorted(key for key, value in states.items() if not value or "missing" in value))
    # A documented gap blocks a final result until resolved or split into a
    # separate branch; a negative on another condition must not hide that gap.
    if gaps:
        return Verdict("suspicious", "static_review", case.digest, ("necessary evidence incomplete",), gaps)
    reviewer_gaps = tuple(sorted(key for key, value in assessed.items() if value.stance == "missing"))
    if reviewer_gaps:
        return Verdict("suspicious", "static_review", case.digest,
                       ("reviewer requires additional evidence",), reviewer_gaps)
    disagreement = tuple(sorted(key for key, value in assessed.items() if value.stance not in states[key]))
    if disagreement:
        return Verdict("suspicious", "static_review", case.digest,
                       tuple(f"investigation/review disagreement: {key}" for key in disagreement))
    disproven = sorted(key for key, value in states.items() if "counter" in value)
    if disproven:
        return Verdict("rejected", "static_review", case.digest,
                       tuple(f"necessary condition disproven: {key}" for key in disproven))
    return Verdict("confirmed", "static_review", case.digest,
                   ("all SQLi prerequisites supported by reviewed static evidence records",))
