"""Immutable scan selection contracts, not an executor or readiness producer."""
from __future__ import annotations

from dataclasses import dataclass
import re

from aixsecurity.domain.assets import clean_text

SQLI_CAPABILITIES = frozenset({'java_source', 'entrypoints', 'dataflow', 'sql_sinks'})


@dataclass(frozen=True)
class Snapshot:
    repo_id: str
    commit: str
    snapshot_id: str
    readiness: str
    capabilities: frozenset[str]

    def __post_init__(self):
        for field in ('repo_id', 'snapshot_id'):
            value = getattr(self, field)
            if clean_text(value, field) != value:
                raise ValueError(f'{field} must be normalized')
        if not isinstance(self.commit, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', self.commit):
            raise ValueError('commit must be a complete immutable Git object ID')
        if self.readiness not in ('READY', 'PARTIAL', 'FAILED', 'PREPARING'):
            raise ValueError('unknown snapshot readiness')
        if not isinstance(self.capabilities, frozenset):
            raise ValueError('capabilities must be an immutable frozenset')
        for capability in self.capabilities:
            if clean_text(capability, 'capability') != capability:
                raise ValueError('capabilities must be normalized')


@dataclass(frozen=True)
class ScanPlan:
    mode: str = 'specialized'
    focus: str = 'sqli'

    def __post_init__(self):
        if self.mode != 'specialized' or self.focus != 'sqli':
            raise ValueError('only specialized SQLi selection is currently defined; no silent mode substitution')

    @property
    def required_capabilities(self) -> frozenset[str]:
        return SQLI_CAPABILITIES


@dataclass(frozen=True)
class ScanSpec:
    plan: ScanPlan
    snapshots: tuple[Snapshot, ...]

    def __post_init__(self):
        if not isinstance(self.plan, ScanPlan):
            raise ValueError('plan must be ScanPlan')
        if not isinstance(self.snapshots, tuple) or not self.snapshots:
            raise ValueError('snapshots must be a non-empty immutable tuple')
        if not all(isinstance(s, Snapshot) for s in self.snapshots):
            raise ValueError('snapshots must contain Snapshot values')
        if len({s.repo_id for s in self.snapshots}) != len(self.snapshots):
            raise ValueError('each repository must have exactly one selected snapshot')
        if len({s.snapshot_id for s in self.snapshots}) != len(self.snapshots):
            raise ValueError('duplicate snapshot ID')
        for snapshot in self.snapshots:
            if snapshot.readiness != 'READY':
                raise ValueError('every selected snapshot must be READY')
            missing = self.plan.required_capabilities - snapshot.capabilities
            if missing:
                raise ValueError(f'missing capabilities for {snapshot.repo_id}: {", ".join(sorted(missing))}')
