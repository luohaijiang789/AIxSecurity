"""Capture before analysis; immutable byte objects, with observable-change checks."""
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from ..config import AuditConfig

EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__"}


class SourceChanged(ValueError):
    pass


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str
    content: bytes

    def manifest(self):
        return {"path": self.path, "sha256": self.sha256, "size": len(self.content)}


def signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_source(path, limit):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise OSError("Not a regular file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or signature(before) != signature(opened):
            raise SourceChanged(f"Source changed before read: {path.name}")
        raw = stream.read(limit)
        after = os.fstat(stream.fileno())
    try:
        current = path.lstat()
    except OSError as exc:
        raise SourceChanged(f"Source disappeared during read: {path.name}") from exc
    if signature(opened) != signature(after) or signature(after) != signature(current):
        raise SourceChanged(f"Source changed during read: {path.name}")
    return raw, signature(after)


def collect(target: Path, config: AuditConfig):
    sources, skipped, excluded, unsupported = [], [], [], []
    stamps = {}
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
                raw, stamp = read_source(path, min(config.max_file_bytes + 1, config.max_total_bytes - bytes_read + 1))
                remaining = config.max_total_bytes - bytes_read
                bytes_read += len(raw)
                if len(raw) > remaining:
                    skipped.append({"path": rel, "reason": "total_bytes_limit"})
                    limit_reached = True
                    break
                if len(raw) > config.max_file_bytes:
                    skipped.append({"path": rel, "reason": "size_limit"})
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                sources.append(SourceFile(rel, digest, raw))
                stamps[rel] = stamp
            except OSError as exc:
                skipped.append({"path": rel, "reason": type(exc).__name__})
        if limit_reached:
            break

    for source in sources:
        try:
            current = signature((target / source.path).lstat())
        except OSError as exc:
            raise SourceChanged(f"Source disappeared after capture: {source.path}") from exc
        if current != stamps[source.path]:
            raise SourceChanged(f"Source changed after capture: {source.path}")
    coverage = {"files_seen": files_seen, "bytes_read": bytes_read,
        "traversal_complete": not limit_reached and not walk_failed,
        "unsupported_files": unsupported, "excluded_directories": excluded,
        "scope": "Python files outside excluded directories only"}
    return tuple(sources), skipped, coverage


def persist_snapshot(root: Path, sources, skipped, coverage):
    """Content addressed artifacts; existing bytes must match, never overwrite."""
    manifest = {"schema_version": "1", "files": [s.manifest() for s in sources],
                "skipped": skipped, "coverage": coverage}
    raw = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    snapshot_id = hashlib.sha256(raw).hexdigest()
    destination = root / snapshot_id
    if root.is_symlink() or destination.is_symlink():
        raise ValueError("Snapshot directory must not be a symlink")
    destination.mkdir(parents=True, exist_ok=True)
    def put(path, data):
        fd, temporary = tempfile.mkstemp(dir=destination, prefix=".capture-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.is_symlink() or path.read_bytes() != data:
                    raise ValueError(f"Snapshot artifact integrity failure: {path.name}")
        finally:
            os.unlink(temporary)
    for source in sources:
        put(destination / source.sha256, source.content)
    # Manifest is published last; a partial directory has no completion marker.
    put(destination / "manifest.json", raw)
    return snapshot_id
