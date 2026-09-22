"""Strict, versioned runtime configuration (stdlib only)."""
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditConfig:
    schema_version: str = "1"
    analyzer: str = "python-ast-demo-v1"
    ai_enabled: bool = False
    max_file_bytes: int = 1_000_000
    max_total_bytes: int = 20_000_000
    max_files: int = 10_000

    def __post_init__(self):
        if self.schema_version != "1" or self.analyzer != "python-ast-demo-v1":
            raise ValueError("Unsupported configuration version or analyzer")
        if self.ai_enabled is not False:
            raise ValueError("AI provider is not implemented")
        for key in ("max_file_bytes", "max_total_bytes", "max_files"):
            value = getattr(self, key)
            if type(value) is not int or value < 1:
                raise ValueError(f"{key} must be a positive integer")

    def to_dict(self):
        return asdict(self)


def load_config(path: Path | None = None) -> AuditConfig:
    if path is None:
        return AuditConfig()
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate configuration key: {key}")
            result[key] = value
        return result
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    if not isinstance(data, dict):
        raise ValueError("Configuration must be an object")
    unknown = set(data) - set(AuditConfig.__dataclass_fields__)
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    return AuditConfig(**data)
