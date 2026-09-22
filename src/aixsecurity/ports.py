"""Dependency boundaries: adapters implement these protocols."""
from typing import Protocol
from .domain.models import Finding

class Analyzer(Protocol):
    name: str
    def analyze(self, path: str, source: str, digest: str) -> list[Finding]: ...

class HypothesisProvider(Protocol):
    # Model output is a hypothesis, never a confirmed vulnerability.
    def propose(self, evidence: list[dict]) -> list[dict]: ...

class WorkerFailure(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason
