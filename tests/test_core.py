import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from aixsecurity import __version__
from aixsecurity.cli import main
from aixsecurity.adapters.ledger import RunLedger


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'ledger.sqlite3'
        self.ledger = RunLedger(self.path)
        self.addCleanup(self.ledger.close)

    def invoke(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(list(args))
        return code, out.getvalue()

    def test_run_persists_after_reopen(self):
        run_id = self.ledger.start('fixture', {'language': 'java'})
        report = {'status': 'completed', 'findings': []}
        self.ledger.finish(run_id, report=report)
        other = RunLedger(self.path)
        try:
            run = other.show(run_id)
            self.assertEqual(run['report'], report)
            self.assertEqual(run['config'], {'language': 'java'})
            self.assertIsNotNone(run['finished_at'])
        finally:
            other.close()

    def test_failed_run(self):
        run_id = self.ledger.start('fixture', {})
        self.ledger.finish(run_id, error='build failed')
        run = self.ledger.show(run_id)
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['error'], 'build failed')
        self.assertIsNone(run['report'])

    def test_runs_list_and_show(self):
        run_id = self.ledger.start('fixture', {})
        code, text = self.invoke('runs', '--ledger', str(self.path), 'list')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)[0]['id'], run_id)
        code, text = self.invoke('runs', '--ledger', str(self.path), 'show', run_id)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)['status'], 'running')

    def test_unknown_run(self):
        code, _ = self.invoke('runs', '--ledger', str(self.path), 'show', 'missing')
        self.assertEqual(code, 2)

    def test_missing_ledger_is_not_created(self):
        path = self.path.parent/'missing.sqlite3'
        code, _ = self.invoke('runs', '--ledger', str(path), 'list')
        self.assertEqual(code, 2)
        self.assertFalse(path.exists())

    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            main(['--version'])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), __version__)

    def test_removed_python_audit_not_advertised(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            main(['--help'])
        self.assertNotIn('{audit', out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(['audit', 'examples/demo'])
        self.assertEqual(caught.exception.code, 2)
