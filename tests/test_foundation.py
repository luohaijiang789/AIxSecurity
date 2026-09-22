import contextlib
import io
import json
import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from aixsecurity.cli import main
from aixsecurity.config import AuditConfig, load_config
from aixsecurity.application.audit import audit
from aixsecurity.adapters.python_ast import PythonAstAnalyzer
from aixsecurity.adapters.ledger import RunLedger


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "report.json"
        self.ledger = self.root / "ledger.sqlite3"

    def scan(self, config=None):
        return audit(self.source, PythonAstAnalyzer(), self.output, config)

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = main(list(args))
        return status, out.getvalue()

    def test_config_validation(self):
        for data in [{"typo": 1}, {"max_files": True}, {"max_file_bytes": 0},
                     {"ai_enabled": 1}, {"schema_version": 1}, {"analyzer": "unknown"}, []]:
            path = self.root / "config.json"
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                load_config(path)
        path.write_text('{"max_files":1,"max_files":2}')
        with self.assertRaises(ValueError):
            load_config(path)

    def test_no_supported_files(self):
        (self.source / "a.js").write_text("eval(x)")
        report = self.scan()
        self.assertEqual(report["status"], "no_supported_files")
        self.assertEqual(report["coverage"]["unsupported_files"], ["a.js"])

    def test_coverage_excluded_directory(self):
        (self.source / ".git").mkdir()
        self.assertEqual(self.scan()["coverage"]["excluded_directories"],
                         [{"path": ".git", "reason": "directory_policy"}])

    def test_fingerprint_determinism_and_change(self):
        path = self.source / "a.py"
        path.write_text("eval(x)")
        first = self.scan()["findings"][0]["fingerprint"]
        self.assertEqual(first, self.scan()["findings"][0]["fingerprint"])
        path.write_text("eval(y)")
        self.assertNotEqual(first, self.scan()["findings"][0]["fingerprint"])

    def test_file_budget(self):
        for name in ("a.py", "b.py"):
            (self.source / name).write_text("x=1")
        report = self.scan(AuditConfig(max_files=1))
        self.assertEqual(report["files_analyzed"], 1)
        self.assertEqual(report["status"], "partial")
        self.assertFalse(report["coverage"]["traversal_complete"])

    def test_byte_budget(self):
        (self.source / "a.py").write_text("x=1")
        report = self.scan(AuditConfig(max_total_bytes=2))
        self.assertEqual(report["skipped"][0]["reason"], "total_bytes_limit")
        self.assertLessEqual(report["coverage"]["bytes_read"], 3)

    def test_config_effective_in_cli_and_ledger(self):
        (self.source / "a.py").write_text("eval(x)")
        config = self.root / "config.json"
        config.write_text('{"max_file_bytes":2}')
        status, text = self.cli("audit", str(self.source), "--output", str(self.output),
                                "--ledger", str(self.ledger), "--config", str(config))
        self.assertEqual(status, 3)
        run_id = json.loads(text)["run_id"]
        status, text = self.cli("runs", "--ledger", str(self.ledger), "show", run_id)
        self.assertEqual(status, 0)
        run = json.loads(text)
        self.assertEqual(run["config"]["max_file_bytes"], 2)
        self.assertEqual(run["status"], "partial")
        self.assertEqual(run["report"], json.loads(self.output.read_text()))
        status, text = self.cli("runs", "--ledger", str(self.ledger), "list")
        self.assertEqual(len(json.loads(text)), 1)

    def test_failed_run_is_persistent(self):
        with patch("aixsecurity.cli.audit", side_effect=OSError("test failure")):
            status, _ = self.cli("audit", str(self.source), "--output", str(self.output),
                                  "--ledger", str(self.ledger))
        self.assertEqual(status, 2)
        ledger = RunLedger(self.ledger)
        self.addCleanup(ledger.close)
        self.assertEqual(ledger.list()[0]["status"], "failed")
        self.assertIn("test failure", ledger.list()[0]["error"])

    def test_ledger_inside_source_rejected_without_mutation(self):
        path = self.source / "ledger.sqlite3"
        status, _ = self.cli("audit", str(self.source), "--output", str(self.output), "--ledger", str(path))
        self.assertEqual(status, 2)
        self.assertFalse(path.exists())

    def test_output_ledger_collision(self):
        status, _ = self.cli("audit", str(self.source), "--output", str(self.ledger), "--ledger", str(self.ledger))
        self.assertEqual(status, 2)
        self.assertFalse(self.ledger.exists())

    def test_no_input_cli_exit(self):
        status, text = self.cli("audit", str(self.source), "--output", str(self.output), "--ledger", str(self.ledger))
        self.assertEqual(status, 3)
        self.assertEqual(json.loads(text)["status"], "no_supported_files")

    def test_interrupted_run(self):
        with patch("aixsecurity.cli.audit", side_effect=KeyboardInterrupt):
            status, _ = self.cli("audit", str(self.source), "--output", str(self.output), "--ledger", str(self.ledger))
        self.assertEqual(status, 130)
        ledger = RunLedger(self.ledger)
        self.addCleanup(ledger.close)
        self.assertEqual(ledger.list()[0]["error"], "Interrupted by user")

    def test_interrupt_exit_survives_ledger_failure(self):
        with patch("aixsecurity.cli.audit", side_effect=KeyboardInterrupt), \
             patch("aixsecurity.cli.RunLedger.finish", side_effect=sqlite3.OperationalError("disk full")):
            status, _ = self.cli("audit", str(self.source), "--output", str(self.output), "--ledger", str(self.ledger))
        self.assertEqual(status, 130)

    def test_version_matches_package(self):
        from aixsecurity import __version__
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            main(["--version"])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), __version__)

    def test_report_roundtrips_unicode(self):
        (self.source / "示例.py").write_text("eval(x)", encoding="utf-8")
        report = self.scan()
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8")), report)
        self.assertEqual(report["findings"][0]["path"], "示例.py")
