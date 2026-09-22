import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aixsecurity.application.audit import audit
from aixsecurity.application.snapshot import collect, read_source, SourceChanged
from aixsecurity.adapters.python_ast import PythonAstAnalyzer
from aixsecurity.config import AuditConfig


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / 'input'
        self.target.mkdir()
        self.output = self.root / 'report.json'

    def run_audit(self, analyzer=None):
        return audit(self.target, analyzer or PythonAstAnalyzer(), self.output)

    def test_persisted_content_and_id(self):
        raw = b'eval(x)'
        (self.target/'a.py').write_bytes(raw)
        report = self.run_audit()
        store = self.root/'.aixsecurity-snapshots'/report['snapshot']['id']
        manifest = (store/'manifest.json').read_bytes()
        self.assertEqual(hashlib.sha256(manifest).hexdigest(), report['snapshot']['id'])
        self.assertEqual((store/hashlib.sha256(raw).hexdigest()).read_bytes(), raw)
        self.assertEqual(json.loads(manifest)['files'], report['manifest'])

    def test_parse_and_encoding_failures_have_hashes(self):
        for name, raw in [('a.py', b'def ('), ('b.py', b'\xff')]:
            (self.target/name).write_bytes(raw)
        report = self.run_audit()
        self.assertEqual(report['files_analyzed'], 0)
        self.assertEqual(len(report['manifest']), 2)
        self.assertTrue(all('sha256' in item for item in report['skipped']))

    def test_analysis_never_rereads_source(self):
        (self.target/'a.py').write_text('x=1')
        (self.target/'b.py').write_text('eval(x)')
        target = self.target
        class MutatingAnalyzer(PythonAstAnalyzer):
            def analyze(self, path, source, digest):
                (target/'b.py').write_text('x=2')
                return super().analyze(path, source, digest)
        report = self.run_audit(MutatingAnalyzer())
        self.assertEqual(report['findings'][0]['path'], 'b.py')
        self.assertEqual(report['findings'][0]['source_sha256'], hashlib.sha256(b'eval(x)').hexdigest())

    def test_change_after_capture_aborts(self):
        path = self.target/'a.py'
        path.write_text('x=1')
        def changing(path, limit):
            result = read_source(path, limit)
            path.write_text('longer=2')
            return result
        with patch('aixsecurity.application.snapshot.read_source', side_effect=changing):
            with self.assertRaises(SourceChanged):
                self.run_audit()
        self.assertFalse(self.output.exists())

    def test_change_during_read_aborts(self):
        path = self.target/'a.py'
        path.write_text('x=1')
        original = __import__('os').fstat
        calls = 0
        def changing(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                path.write_text('longer=2')
            return original(fd)
        with patch('aixsecurity.application.snapshot.os.fstat', side_effect=changing):
            with self.assertRaises(SourceChanged):
                read_source(path, 100)

    def test_corrupt_store_rejected(self):
        (self.target/'a.py').write_text('x=1')
        report = self.run_audit()
        store = self.root/'.aixsecurity-snapshots'/report['snapshot']['id']
        (store/report['manifest'][0]['sha256']).write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'integrity failure'):
            self.run_audit()

    def test_changed_content_changes_snapshot_id(self):
        path = self.target/'a.py'
        path.write_text('x=1')
        first = self.run_audit()['snapshot']['id']
        path.write_text('x=2')
        self.assertNotEqual(first, self.run_audit()['snapshot']['id'])

    def test_capture_returns_immutable_bytes(self):
        (self.target/'a.py').write_text('x=1')
        files, _, _ = collect(self.target, AuditConfig())
        self.assertIsInstance(files, tuple)
        self.assertIsInstance(files[0].content, bytes)
        with self.assertRaises(AttributeError):
            files[0].content = b'changed'
