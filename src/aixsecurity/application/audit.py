import json
import os
import tempfile
from pathlib import Path
from ..ports import Analyzer
from ..config import AuditConfig
from ..ports import WorkerFailure

from .snapshot import collect, persist_snapshot

def audit(target: Path, analyzer: Analyzer, output: Path, config: AuditConfig | None = None):
    config = config or AuditConfig()
    if analyzer.name != config.analyzer:
        raise ValueError("Analyzer does not match configuration")
    target = target.resolve(strict=True)
    if not target.is_dir():
        raise ValueError("Target must be a directory")
    output = output.resolve()
    if output == target or target in output.parents:
        raise ValueError("Output must be outside the target directory")
    sources, skipped, coverage = collect(target, config)
    snapshot_root = output.parent / ".aixsecurity-snapshots"
    if snapshot_root.resolve() == target or target in snapshot_root.resolve().parents:
        raise ValueError("Snapshot store must be outside target")
    if output == snapshot_root:
        raise ValueError("Output conflicts with snapshot store")
    snapshot_id = persist_snapshot(snapshot_root, sources, skipped, coverage)
    findings = []
    analyzed = 0
    for source in sources:
        try:
            text = source.content.decode("utf-8")
            findings.extend(f.to_dict() for f in analyzer.analyze(source.path, text, source.sha256))
            analyzed += 1
        except WorkerFailure as exc:
            skipped.append({"path": source.path, "reason": exc.reason, "sha256": source.sha256})
        except (SyntaxError, UnicodeError) as exc:
            skipped.append({"path": source.path, "reason": type(exc).__name__, "sha256": source.sha256})
    manifest = [source.manifest() for source in sources]
    report = {"schema_version": "3", "analyzer": analyzer.name,
        "status": "partial" if skipped else ("completed" if analyzed else "no_supported_files"),
        "config": config.to_dict(),
        "execution_mode": getattr(analyzer, "execution_mode", "in_process"),
        "coverage": coverage,
        "snapshot": {"id": snapshot_id, "schema_version": "1", "files_captured": len(sources)},
        "ai_enabled": False, "files_analyzed": analyzed,
        "manifest": manifest, "findings": findings, "skipped": skipped,
        "limitations": ["Python syntax candidates only; no taint, reachability or runtime proof.",
            "Zero candidates does not mean secure. Use immutable trusted snapshots."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix=".report-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return report
