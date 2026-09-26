import os
import hashlib
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from aixsecurity.adapters.artifacts import ArtifactStore


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ArtifactStore(Path(self.temp.name).resolve() / 'artifacts')

    def test_roundtrip_dedup_and_reopen(self):
        digest = self.store.put(b'evidence')
        self.assertEqual(self.store.put(b'evidence'), digest)
        self.assertEqual(ArtifactStore(self.store.root).get(digest), b'evidence')
        self.assertEqual(len(list(self.store.root.iterdir())), 1)

    def test_concurrent_identical_publication(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            refs = list(pool.map(self.store.put, [b'same'] * 8))
        self.assertEqual(len(set(refs)), 1)
        self.assertEqual(self.store.get(refs[0]), b'same')

    def test_path_traversal_rejected(self):
        for ref in ['../secret', '/etc/passwd', 'a'*63, 'G'*64]:
            with self.assertRaises(ValueError): self.store.get(ref)

    def test_tampered_content_never_overwritten(self):
        digest = self.store.put(b'original')
        path = self.store.root / digest
        path.chmod(0o600); path.write_bytes(b'tampered')
        with self.assertRaises(ValueError): self.store.get(digest)
        with self.assertRaises(ValueError): self.store.put(b'original')
        self.assertEqual(path.read_bytes(), b'tampered')
        self.assertFalse(list(self.store.root.glob('.pending-*')))

    def test_symlink_artifact_rejected(self):
        target = self.store.root.parent / 'outside'
        target.write_bytes(b'outside')
        digest = hashlib.sha256(b'outside').hexdigest()
        (self.store.root / digest).symlink_to(target)
        with self.assertRaises(OSError): self.store.get(digest)
        with self.assertRaises(OSError): self.store.put(b'outside')

    def test_symlink_root_rejected(self):
        link = self.store.root.parent / 'link'; link.symlink_to(self.store.root)
        with self.assertRaises(ValueError): ArtifactStore(link)

    def test_fifo_is_rejected_without_blocking(self):
        digest = 'a' * 64
        os.mkfifo(self.store.root / digest)
        with self.assertRaises(ValueError): self.store.get(digest)

    def test_existing_writable_shared_root_rejected(self):
        self.store.root.chmod(0o777)
        try:
            with self.assertRaises(ValueError): ArtifactStore(self.store.root)
        finally:
            self.store.root.chmod(0o700)

    def test_existing_readable_shared_root_rejected(self):
        self.store.root.chmod(0o755)
        try:
            with self.assertRaises(ValueError): ArtifactStore(self.store.root)
        finally:
            self.store.root.chmod(0o700)
