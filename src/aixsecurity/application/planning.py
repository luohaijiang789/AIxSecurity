"""Validate an explicit selection without creating tasks or changing assets."""
from aixsecurity.domain.planning import ScanPlan, ScanSpec, Snapshot


class PlanningService:
    def create(self, plan: ScanPlan, snapshots: tuple[Snapshot, ...]) -> ScanSpec:
        return ScanSpec(plan=plan, snapshots=snapshots)
