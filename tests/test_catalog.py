import concurrent.futures
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from aixsecurity.adapters.catalog import Catalog
from aixsecurity.adapters.tasks import IdempotencyConflict, TaskStore


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'catalog.sqlite3'
        self.catalog = Catalog(self.path)
        self.addCleanup(self.catalog.close)
        self.repositories = ['https://github.com/example/orders.git',
                             'https://github.com/example/users.git']

    def register(self, key='request'):
        return self.catalog.register('Services', self.repositories, key)

    def test_registration_creates_one_queued_task_and_no_snapshot(self):
        project = self.register()
        self.assertEqual(project['name'], 'Services')
        self.assertEqual(project['repositories'], self.repositories)
        self.assertEqual(project['preparation_status'], 'queued')
        self.assertIsNone(project['current_snapshot_id'])
        self.assertEqual(self.catalog.list_projects(), [project])
        store = TaskStore(self.path)
        self.addCleanup(store.close)
        task = store.get(project['preparation_task_id'])
        self.assertEqual(task['kind'], 'preparation')
        self.assertEqual(task['payload'], {'project_id': project['id'],
                                           'repositories': self.repositories})
        self.assertEqual(task['status'], 'queued')
        self.assertIsNone(store.claim(kind='scan'))
        # Same schema and digest convention: ordinary TaskStore replay works.
        self.assertEqual(store.enqueue(task['kind'], task['payload'],
                                       task['idempotency_key'])['id'], task['id'])

    def test_idempotency_survives_reopen_and_conflicts(self):
        first = self.register()
        with Catalog(self.path) as reopened:
            self.assertEqual(reopened.register('Services', self.repositories, 'request'), first)
            self.assertEqual(reopened.get_project(first['id']), first)
            with self.assertRaises(IdempotencyConflict):
                reopened.register('Other', self.repositories, 'request')
            with self.assertRaises(IdempotencyConflict):
                reopened.register('Services', self.repositories[:1], 'request')
        self.assertEqual(len(self.catalog.list_projects()), 1)

    def test_distinct_keys_make_distinct_registrations(self):
        first, second = self.register('a'), self.register('b')
        self.assertNotEqual(first['id'], second['id'])
        self.assertNotEqual(first['preparation_task_id'], second['preparation_task_id'])
        self.assertEqual(len(self.catalog.list_projects()), 2)

    def test_task_status_is_live_but_completion_does_not_fabricate_ready(self):
        project = self.register()
        store = TaskStore(self.path)
        self.addCleanup(store.close)
        task = store.claim(kind='preparation')
        self.assertEqual(self.catalog.get_project(project['id'])['preparation_status'], 'running')
        store.complete(task['id'], task['token'], {'snapshot_id': 'unverified'})
        refreshed = self.catalog.get_project(project['id'])
        self.assertEqual(refreshed['preparation_status'], 'completed')
        self.assertIsNone(refreshed['current_snapshot_id'])

    def test_insertion_failure_rolls_back_task_project_and_key(self):
        self.catalog.connection.execute('''CREATE TRIGGER fail_registration
            BEFORE INSERT ON catalog_requests BEGIN
            SELECT RAISE(ABORT, 'injected failure'); END''')
        with self.assertRaises(sqlite3.IntegrityError):
            self.register()
        for table in ('catalog_projects', 'catalog_requests', 'tasks'):
            self.assertEqual(self.catalog.connection.execute(
                f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
        self.catalog.connection.execute('DROP TRIGGER fail_registration')
        self.assertEqual(self.register()['preparation_status'], 'queued')

    def test_concurrent_identical_registration_is_exactly_once(self):
        barrier = threading.Barrier(6)
        def register(_):
            with Catalog(self.path) as catalog:
                barrier.wait(timeout=10)
                return catalog.register('Services', self.repositories, 'concurrent')
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            projects = list(executor.map(register, range(6)))
        self.assertEqual(len({p['id'] for p in projects}), 1)
        self.assertEqual(self.catalog.connection.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 1)
        self.assertEqual(len(self.catalog.list_projects()), 1)

    def test_concurrent_conflicting_requests_commit_only_one(self):
        barrier = threading.Barrier(2)
        def register(name):
            with Catalog(self.path) as catalog:
                barrier.wait(timeout=10)
                try:
                    return catalog.register(name, self.repositories, 'same-key')['id']
                except IdempotencyConflict:
                    return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(register, ['One', 'Two']))
        self.assertEqual(results.count('conflict'), 1)
        self.assertEqual(len(self.catalog.list_projects()), 1)
        self.assertEqual(self.catalog.connection.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 1)

    def test_invalid_requests_write_nothing(self):
        for name, repositories, key in [('', self.repositories, 'key'),
                                         ('x', [], 'key'), ('x', self.repositories, ''),
                                         ('x', ['file:///tmp/repo'], 'key'),
                                         ('x', ['https://localhost/repo'], 'key')]:
            with self.subTest(name=name, repositories=repositories, key=key):
                with self.assertRaises(ValueError):
                    self.catalog.register(name, repositories, key)
        self.assertEqual(self.catalog.list_projects(), [])
        self.assertEqual(self.catalog.connection.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 0)

    def test_read_only_missing_database_does_not_create_file(self):
        path = Path(self.temp.name) / 'missing' / 'assets.sqlite3'
        with self.assertRaisesRegex(ValueError, 'Existing catalog database is required'):
            Catalog(path, read_only=True)
        self.assertFalse(path.exists())
        self.assertFalse(path.parent.exists())

    def test_read_only_unrelated_database_does_not_change_schema(self):
        path = Path(self.temp.name) / 'unrelated.sqlite3'
        connection = sqlite3.connect(path)
        connection.execute('CREATE TABLE unrelated (id INTEGER)')
        connection.commit()
        connection.close()
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Existing catalog database is required'):
            Catalog(path, read_only=True)
        self.assertEqual(path.read_bytes(), before)
        connection = sqlite3.connect(path)
        self.addCleanup(connection.close)
        self.assertEqual(connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [('unrelated',)])

    def test_read_only_catalog_reads_and_rejects_writes(self):
        project = self.register()
        before = self.path.read_bytes()
        with Catalog(self.path, read_only=True) as catalog:
            self.assertEqual(catalog.list_projects(), [project])
            self.assertEqual(catalog.get_project(project['id']), project)
            with self.assertRaisesRegex(ValueError, 'read-only'):
                catalog.register('Other', self.repositories, 'other')
            with self.assertRaises(sqlite3.OperationalError):
                catalog.connection.execute('CREATE TABLE forbidden (id INTEGER)')
        self.assertEqual(self.path.read_bytes(), before)

    def test_unknown_project_is_explicit(self):
        with self.assertRaisesRegex(ValueError, 'Unknown project'):
            self.catalog.get_project('missing')


if __name__ == '__main__':
    unittest.main()
