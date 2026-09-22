import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aixsecurity.adapters.isolated import IsolatedPythonAnalyzer
from aixsecurity.adapters.python_ast import PythonAstAnalyzer
from aixsecurity.application.audit import audit
from aixsecurity.config import AuditConfig
from aixsecurity.ports import WorkerFailure


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = IsolatedPythonAnalyzer(5)
        self.digest = hashlib.sha256(b'eval(x)').hexdigest()

    def test_real_worker_matches_direct(self):
        expected = PythonAstAnalyzer().analyze('a.py', 'eval(x)', self.digest)
        self.assertEqual(self.analyzer.analyze('a.py', 'eval(x)', self.digest), expected)

    def test_real_worker_syntax_failure(self):
        with self.assertRaisesRegex(WorkerFailure, 'SyntaxError'):
            self.analyzer.analyze('a.py', 'def (', self.digest)

    def test_real_timeout_child_reaped(self):
        original = subprocess.run
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp)/'pid'
            code = f"import os,time;open({str(pid_file)!r},'w').write(str(os.getpid()));time.sleep(30)"
            def slow(command, **kwargs):
                return original([sys.executable, '-I', '-c', code], **kwargs)
            with patch('aixsecurity.adapters.isolated.subprocess.run', side_effect=slow):
                with self.assertRaisesRegex(WorkerFailure, 'WorkerTimeout'):
                    IsolatedPythonAnalyzer(1).analyze('a.py', 'eval(x)', self.digest)
            self.assertTrue(pid_file.exists())
            if os.name == 'posix':
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pid_file.read_text()), 0)

    def test_real_crash(self):
        original = subprocess.run
        def crash(command, **kwargs):
            return original([sys.executable, '-I', '-c', 'import os;os._exit(9)'], **kwargs)
        with patch('aixsecurity.adapters.isolated.subprocess.run', side_effect=crash):
            with self.assertRaisesRegex(WorkerFailure, 'WorkerCrash'):
                self.analyzer.analyze('a.py', '', self.digest)

    def test_invalid_protocol_and_evidence(self):
        bad = PythonAstAnalyzer().analyze('wrong.py', 'eval(x)', self.digest)[0].to_dict()
        for payload in ['not json', '[]', '{"error":"Unknown"}', json.dumps({'findings':[bad]})]:
            result = subprocess.CompletedProcess([], 0, payload, '')
            with patch('aixsecurity.adapters.isolated.subprocess.run', return_value=result):
                with self.assertRaisesRegex(WorkerFailure, 'WorkerProtocolError'):
                    self.analyzer.analyze('a.py', 'eval(x)', self.digest)

    def test_failure_continues_next_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);target=root/'input';target.mkdir()
            (target/'a.py').write_text('eval(x)');(target/'b.py').write_text('eval(x)')
            original = self.analyzer.analyze
            def fail_first(path, source, digest):
                if path == 'a.py': raise WorkerFailure('WorkerTimeout')
                return original(path, source, digest)
            with patch.object(self.analyzer, 'analyze', side_effect=fail_first):
                report = audit(target, self.analyzer, root/'report.json')
            self.assertEqual(report['status'], 'partial')
            self.assertEqual(report['files_analyzed'], 1)
            self.assertEqual(report['skipped'][0]['reason'], 'WorkerTimeout')
            self.assertEqual(report['findings'][0]['path'], 'b.py')

    def test_timeout_config_validation(self):
        for value in [0, -1, True, 1.5, '10']:
            with self.assertRaises(ValueError):AuditConfig(worker_timeout_seconds=value)

    def test_target_code_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp)/'marker'
            self.analyzer.analyze('a.py', f'open({str(marker)!r}, "w").write("bad")', self.digest)
            self.assertFalse(marker.exists())
