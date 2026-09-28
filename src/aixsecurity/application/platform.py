"""UI use cases, separate automatic preparation from explicit scan submission."""
from typing import Protocol
from .assets import AssetService
from ..domain.profiles import DEFAULT_PROFILE, list_profiles


class PlatformPort(Protocol):
    def close(self) -> None: ...
    def list_projects(self) -> list[dict]: ...
    def get_project(self, project_id: str) -> dict: ...
    def retry_preparation(self, project_id: str, idempotency_key: str) -> dict: ...
    def create_scan(self, project_id: str, idempotency_key: str, profile_id: str = DEFAULT_PROFILE, expected_snapshot_id: str | None = None) -> dict: ...
    def list_scans(self) -> list[dict]: ...
    def get_scan(self, scan_id: str) -> dict: ...


class PlatformService:
    def __init__(self, assets: AssetService, platform: PlatformPort):
        self.assets, self.platform = assets, platform

    def register(self, body: dict):
        return self.assets.register(body['name'], body['repositories'], body['idempotency_key'])

    def create_scan(self, body: dict):
        return self.platform.create_scan(body['project_id'], body['idempotency_key'], body.get('profile_id', DEFAULT_PROFILE), body.get('expected_snapshot_id'))

    def profiles(self):
        return list_profiles()
