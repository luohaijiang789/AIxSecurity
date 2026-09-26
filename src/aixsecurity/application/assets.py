"""Asset registration is separate from preparation and scan execution."""
from aixsecurity.application.ports import CatalogPort
from aixsecurity.domain.assets import clean_text, normalize_registration


class AssetService:
    def __init__(self, catalog: CatalogPort):
        self.catalog = catalog

    def register(self, name: str, repositories: list[str], idempotency_key: str) -> dict:
        name, repositories, key = normalize_registration(name, repositories, idempotency_key)
        return self.catalog.register(name, repositories, key)

    def list(self) -> list[dict]:
        return self.catalog.list_projects()

    def get(self, project_id: str) -> dict:
        return self.catalog.get_project(clean_text(project_id, 'project_id'))
