"""Composition root: the only delivery-to-infrastructure wiring location.

No network, database, or model is opened at import time. Lifetimes are explicit;
future HTTP handlers create one application per request/worker, not a shared
SQLite connection. Domain and application modules never import this module.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from .application.assets import AssetService
from .application.planning import PlanningService
from .adapters.catalog import Catalog
from .adapters.ledger import RunLedger
from .adapters.model import LocalModelClient, ModelError, load_config
from .doctor import inspect_environment


@dataclass
class Application:
    assets: AssetService
    planning: PlanningService
    _close: Callable[[], None] = field(repr=False)

    def close(self):
        self._close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def build_application(database: Path, *, read_only=False) -> Application:
    catalog = Catalog(database, read_only=read_only)
    return Application(AssetService(catalog), PlanningService(), catalog.close)


def read_legacy_runs(path: Path, run_id=None):
    if not path.is_file():
        raise ValueError('Ledger does not exist')
    ledger = RunLedger(path)
    try:
        return ledger.list() if run_id is None else ledger.show(run_id)
    finally:
        ledger.close()


def check_environment(env_file: Path, defer_model=False):
    model_env = None
    if not defer_model and env_file.exists():
        config = load_config(env_file)
        model_env = {'AIXSECURITY_MODEL_BASE_URL': config.base_url,
                     'AIXSECURITY_MODEL_NAME': config.model,
                     'AIXSECURITY_MODEL_API_KEY': config.api_key}
    return inspect_environment(defer_model=defer_model, environ=model_env)


def check_model(env_file: Path):
    return LocalModelClient(load_config(env_file)).smoke_test()
