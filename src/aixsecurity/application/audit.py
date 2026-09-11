import hashlib
import json
import os
import tempfile
from pathlib import Path
from ..ports import Analyzer

EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__"}
MAX_BYTES = 1_000_000

def audit(target: Path, analyzer: Analyzer, output: Path):
    target = target.resolve(strict=True)
    if not target.is_dir():
        raise ValueError("Target must be a directory")
    output = output.resolve()
    if output == target or target in output.parents:
        raise ValueError("Output must be outside the target directory")
    findings, manifest, skipped = [], [], []
    for directory, dirs, names in os.walk(target, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not (Path(directory)/d).is_symlink())
        for name in sorted(names):
            path = Path(directory)/name
            if path.suffix != ".py":
                continue
            rel = path.relative_to(target).as_posix()
            if path.is_symlink():
                skipped.append({"path": rel, "reason": "symlink"})
                continue
            try:
                with path.open("rb") as stream:
                    raw = stream.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    skipped.append({"path": rel, "reason": "size_limit"})
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                source = raw.decode("utf-8")
                findings.extend(f.to_dict() for f in analyzer.analyze(rel, source, digest))
                manifest.append({"path": rel, "sha256": digest})
            except (SyntaxError, UnicodeError, OSError) as exc:
                skipped.append({"path": rel, "reason": type(exc).__name__})
    report = {"schema_version": "1", "analyzer": analyzer.name,
        "status": "partial" if skipped else "completed",
        "ai_enabled": False, "files_analyzed": len(manifest),
        "manifest": manifest, "findings": findings, "skipped": skipped,
        "limitations": ["Python syntax candidates only; no taint, reachability or runtime proof.",
            "Zero candidates does not mean secure. Use immutable trusted snapshots."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix=".report-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return report
