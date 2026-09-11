import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from aixsecurity.adapters.python_ast import PythonAstAnalyzer
from aixsecurity.application.audit import audit

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'input'
        self.source.mkdir()
        self.output = self.root/'report.json'

    def run_audit(self):
        return audit(self.source, PythonAstAnalyzer(), self.output)

    def test_candidate_and_hash(self):
        raw = b'eval(user_input)\n'
        (self.source/'a.py').write_bytes(raw)
        report = self.run_audit()
        self.assertEqual(report['findings'][0]['status'], 'candidate')
        self.assertEqual(report['findings'][0]['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertFalse(report['ai_enabled'])
        self.assertEqual(json.loads(self.output.read_text()), report)

    def test_clean(self):
        (self.source/'a.py').write_text('x = 1')
        self.assertEqual(self.run_audit()['findings'], [])

    def test_syntax_error_visible(self):
        (self.source/'a.py').write_text('def (')
        report = self.run_audit()
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['files_analyzed'], 0)

    def test_no_source_execution(self):
        marker = self.root/'executed'
        (self.source/'a.py').write_text(f'open({str(marker)!r}, "w").write("bad")')
        self.run_audit()
        self.assertFalse(marker.exists())

    def test_symlink_skip(self):
        external = self.root/'outside.py'
        external.write_text('eval(x)')
        (self.source/'linked.py').symlink_to(external)
        self.assertEqual(self.run_audit()['skipped'][0]['reason'], 'symlink')

    def test_size_limit(self):
        (self.source/'big.py').write_bytes(b'x'*1_000_001)
        self.assertEqual(self.run_audit()['skipped'][0]['reason'], 'size_limit')

    def test_output_inside_target_rejected(self):
        with self.assertRaises(ValueError):
            audit(self.source, PythonAstAnalyzer(), self.source/'report.json')

    def test_repeatable(self):
        (self.source/'a.py').write_text('exec(code)')
        self.assertEqual(self.run_audit(), self.run_audit())

    def test_excluded_directory(self):
        (self.source/'.venv').mkdir()
        (self.source/'.venv'/'a.py').write_text('eval(x)')
        self.assertEqual(self.run_audit()['files_analyzed'], 0)

    def test_encoding_failure(self):
        (self.source/'a.py').write_bytes(b'\xff')
        self.assertEqual(self.run_audit()['status'], 'partial')

if __name__ == '__main__':
    unittest.main()
