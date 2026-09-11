from dataclasses import dataclass, asdict
from typing import Literal

@dataclass(frozen=True)
class Finding:
    rule_id: str
    path: str
    line: int
    message: str
    source_sha256: str
    status: Literal["candidate"] = "candidate"
    evidence_type: str = "static_syntax"

    def to_dict(self):
        return asdict(self)
