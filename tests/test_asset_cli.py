import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from aixsecurity.cli import main
from aixsecurity.composition import build_application
from aixsecurity.adapters.tasks import TaskStore


class AssetCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'platform.sqlite3'

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(['assets', '--database', str(self.db), *args])
        return code, out.getvalue(), err.getvalue()

    def test_register_reopen_list_and_claim_preparation(self):
        args = ('register', '--name', 'Java services', '--repo', 'https://example.com/org/a.git',
                '--repo', 'https://example.com/org/b.git', '--request-id', 'request-1')
        code, out, _ = self.invoke(*args)
        self.assertEqual(code, 0)
        project = json.loads(out)
        self.assertIsNone(project['current_snapshot_id'])
        self.assertEqual(project['preparation_status'], 'queued')
        self.assertEqual(json.loads(self.invoke(*args)[1])['id'], project['id'])
        self.assertEqual(len(json.loads(self.invoke('list')[1])), 1)
        self.assertEqual(json.loads(self.invoke('show', project['id'])[1])['id'], project['id'])
        store = TaskStore(self.db)
        try:
            self.assertIsNone(store.claim(kind='scan'))
            task = store.claim(kind='preparation')
            self.assertEqual(task['id'], project['preparation_task_id'])
            store.fail(task['id'], task['token'], 'No Java preparation adapter configured')
        finally:
            store.close()
        with build_application(self.db) as app:
            record = app.assets.get(project['id'])
            self.assertEqual(record['preparation_status'], 'failed')
            self.assertIsNone(record['current_snapshot_id'])

    def test_read_does_not_create_database(self):
        code, _, _ = self.invoke('list')
        self.assertEqual(code, 2)
        self.assertFalse(self.db.exists())

    def test_invalid_url_is_not_echoed_with_credentials(self):
        code, _, err = self.invoke('register', '--name', 'x', '--repo',
            'https://user:synthetic-secret@example.com/a.git', '--request-id', 'bad')
        self.assertEqual(code, 2)
        self.assertNotIn('synthetic-secret', err)

    def test_read_unrelated_database_does_not_create_catalog_tables(self):
        import sqlite3
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE unrelated(value TEXT)')
        code, _, _ = self.invoke('list')
        self.assertEqual(code, 2)
        with sqlite3.connect(self.db) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {'unrelated'})
