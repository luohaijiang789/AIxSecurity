from dataclasses import dataclass, asdict
from typing import Literal
import hashlib
import json

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
        result = asdict(self)
        identity = [self.rule_id, self.path, self.line, self.source_sha256, self.evidence_type]
        result["fingerprint"] = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return result
