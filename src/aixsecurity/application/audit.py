import hashlib
import json
import os
import tempfile
from pathlib import Path
from ..ports import Analyzer
from ..config import AuditConfig
import stat

EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__"}

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
    findings, manifest, skipped, excluded, unsupported = [], [], [], [], []
    bytes_read = 0
    files_seen = 0
    limit_reached = False
    walk_failed = False
    def walk_error(exc):
        nonlocal walk_failed
        walk_failed = True
        skipped.append({"path": os.path.relpath(exc.filename or target, target), "reason": type(exc).__name__})
    for directory, dirs, names in os.walk(target, followlinks=False, onerror=walk_error):
        kept = []
        for d in sorted(dirs):
            child = Path(directory) / d
            if d in EXCLUDED or child.is_symlink():
                excluded.append({"path": child.relative_to(target).as_posix(),
                                 "reason": "symlink" if child.is_symlink() else "directory_policy"})
            else:
                kept.append(d)
        dirs[:] = kept
        for name in sorted(names):
            path = Path(directory)/name
            rel = path.relative_to(target).as_posix()
            if files_seen >= config.max_files or bytes_read >= config.max_total_bytes:
                skipped.append({"path": rel, "reason": "scan_budget"})
                limit_reached = True
                break
            files_seen += 1
            if path.suffix != ".py":
                unsupported.append(rel)
                continue
            if path.is_symlink():
                skipped.append({"path": rel, "reason": "symlink"})
                continue
            try:
                if not stat.S_ISREG(path.stat().st_mode):
                    skipped.append({"path": rel, "reason": "not_regular_file"})
                    continue
                remaining = config.max_total_bytes - bytes_read
                with path.open("rb") as stream:
                    raw = stream.read(min(config.max_file_bytes + 1, remaining + 1))
                bytes_read += len(raw)
                if len(raw) > remaining:
                    skipped.append({"path": rel, "reason": "total_bytes_limit"})
                    limit_reached = True
                    break
                if len(raw) > config.max_file_bytes:
                    skipped.append({"path": rel, "reason": "size_limit"})
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                source = raw.decode("utf-8")
                findings.extend(f.to_dict() for f in analyzer.analyze(rel, source, digest))
                manifest.append({"path": rel, "sha256": digest})
            except (SyntaxError, UnicodeError, OSError) as exc:
                skipped.append({"path": rel, "reason": type(exc).__name__})
        if limit_reached:
            break
    report = {"schema_version": "2", "analyzer": analyzer.name,
        "status": "partial" if skipped else ("completed" if manifest else "no_supported_files"),
        "config": config.to_dict(),
        "coverage": {"files_seen": files_seen, "bytes_read": bytes_read,
            "traversal_complete": not limit_reached and not walk_failed,
            "unsupported_files": unsupported, "excluded_directories": excluded,
            "scope": "Python files outside excluded directories only"},
        "ai_enabled": False, "files_analyzed": len(manifest),
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
