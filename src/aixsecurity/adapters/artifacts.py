"""Content-addressed immutable artifacts, not an asset readiness publisher."""
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile

_DIGEST = re.compile(r'^[0-9a-f]{64}$')


class ArtifactStore:
    """Trusted private local directory. Digest verification detects changed bytes.

    The caller owns database publication and reference-aware retention. This store
    never sets READY and does not permit user-supplied filesystem paths.
    Ancestor directories and same-UID processes must be trusted; this is not a
    hostile-filesystem sandbox. Build workers must not access this directory.
    """
    def __init__(self, root):
        root = Path(root).absolute()
        if any(p.is_symlink() for p in (root, *root.parents)):
            raise ValueError('Artifact root must not traverse symlinks')
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = root.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Artifact root must be owned by this user and not accessible by group/other")
        self.root = root

    def _path(self, digest):
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise ValueError('Expected SHA256 digest')
        if self.root.is_symlink():
            raise ValueError('Artifact root changed')
        return self.root / digest

    def get(self, digest):
        path = self._path(digest)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Artifact is not a regular file')
            data = stream.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Artifact integrity mismatch')
        return data

    def put(self, data):
        if not isinstance(data, bytes):
            raise TypeError('Artifact content must be bytes')
        digest = hashlib.sha256(data).hexdigest()
        destination = self._path(digest)
        fd, name = tempfile.mkstemp(prefix='.pending-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, 0o400)
            try:
                # Link publishes atomically and never overwrites existing bytes.
                os.link(name, destination)
            except FileExistsError:
                pass
            self.get(digest)
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            os.unlink(name)
        return digest
