"""Synthetic persistence/worker tests. No Git, Docker, network, or model calls."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from aixsecurity.adapters.platform import PlatformStore
from aixsecurity.adapters.pipeline import PipelineWorker
from aixsecurity.adapters.tasks import IdempotencyConflict, LeaseLost


URL = 'https://github.com/example/synthetic.git'


def make_snapshot():
    return {'repositories': [{'url': URL, 'commit': 'a' * 40, 'repo_path': '/synthetic/not-read',
        'build': {'success': True, 'status': 'completed'}, 'assets': [], 'candidates': [],
        'tool_versions': {'semgrep': 'synthetic'}, 'analysis_success': True,
        'source_manifest': {'Demo.java': 'b' * 64},
        'capabilities': ['java-ast', 'java-sqli-intraprocedural', 'maven-compile'],
        'limitations': ['Synthetic test input only']}],
        'capabilities': ['java-ast', 'java-sqli-intraprocedural', 'maven-compile'],
        'assets': [], 'limitations': ['Synthetic test input only']}


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'platform.sqlite3'
        self.store = PlatformStore(self.db)
        self.addCleanup(self.store.close)
        self.project = self.store.catalog.register('Synthetic project', [URL], 'registration')

    def publish(self):
        task = self.store.tasks.claim(kind='preparation')
        return self.store.publish(task['id'], task['token'], make_snapshot())

    def test_unready_project_cannot_scan_and_registration_does_not_scan(self):
        self.assertEqual(self.store.list_scans(), [])
        self.assertIsNone(self.store.tasks.claim(kind='scan'))
        with self.assertRaisesRegex(ValueError, 'READY'):
            self.store.create_scan(self.project['id'], 'scan-request')
        self.assertEqual(self.store.list_scans(), [])

    def test_publication_is_ready_but_does_not_auto_create_scan(self):
        snapshot_id = self.publish()
        project = self.store.get_project(self.project['id'])
        self.assertEqual(project['preparation_status'], 'READY')
        self.assertEqual(project['current_snapshot_id'], snapshot_id)
        self.assertEqual(project['task_status'], 'completed')
        self.assertEqual(self.store.list_scans(), [])
        self.assertIsNone(self.store.tasks.claim(kind='scan'))

    def test_expired_and_wrong_token_cannot_publish(self):
        task = self.store.tasks.claim(kind='preparation')
        with self.assertRaises(LeaseLost):
            self.store.publish(task['id'], 'wrong-token', make_snapshot())
        self.store.db.execute('UPDATE tasks SET lease_until=0 WHERE id=?', (task['id'],))
        with self.assertRaises(LeaseLost):
            self.store.publish(task['id'], task['token'], make_snapshot())
        self.assertIsNone(self.store.get_project(self.project['id'])['current_snapshot_id'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM published_snapshots').fetchone()[0], 0)

    def test_scan_idempotency_pins_snapshot_and_conflicts_across_projects(self):
        snapshot_id = self.publish()
        first = self.store.create_scan(self.project['id'], 'scan-request')
        replay = self.store.create_scan(self.project['id'], 'scan-request')
        self.assertEqual(first['id'], replay['id'])
        self.assertEqual(first['snapshot_id'], snapshot_id)
        other = self.store.catalog.register('Other', [URL], 'other')
        with self.assertRaises(IdempotencyConflict):
            self.store.create_scan(other['id'], 'scan-request')
        self.assertEqual(len(self.store.list_scans()), 1)

    def test_failed_build_or_missing_capability_rejected(self):
        task = self.store.tasks.claim(kind='preparation')
        bad = make_snapshot(); bad['repositories'][0]['build']['success'] = False
        missing = make_snapshot(); missing['capabilities'] = []
        for data in (bad, missing):
            with self.assertRaises(ValueError):
                self.store.publish(task['id'], task['token'], data)
        self.assertIsNone(self.store.get_project(self.project['id'])['current_snapshot_id'])

    def test_incomplete_analysis_or_inconsistent_repository_rejected(self):
        task = self.store.tasks.claim(kind='preparation')
        cases = []
        for key, value in [('commit', 'main'), ('url', 'https://github.com/example/other.git'),
                           ('analysis_success', False), ('tool_versions', {}),
                           ('capabilities', ['maven-compile'])]:
            data = make_snapshot(); data['repositories'][0][key] = value; cases.append(data)
        data = make_snapshot(); data['repositories'][0]['build']['success'] = 'true'; cases.append(data)
        data = make_snapshot(); data['repositories'][0]['candidates'] = [{'path': 'Missing.java'}]; cases.append(data)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.store.publish(task['id'], task['token'], data)
        self.assertIsNone(self.store.get_project(self.project['id'])['current_snapshot_id'])

    def test_worker_preparation_does_not_call_investigator(self):
        class Preparer:
            def prepare(self, url, path):
                return deepcopy(make_snapshot()['repositories'][0])
        class Investigator:
            def run(self, snapshot):
                raise AssertionError('Preparation must not invoke investigation')
        worker = PipelineWorker(self.db, Path(self.temp.name)/'work', Preparer(), Investigator())
        self.assertTrue(worker.tick())
        self.assertEqual(self.store.get_project(self.project['id'])['preparation_status'], 'READY')
        self.assertEqual(self.store.list_scans(), [])
        self.assertFalse(worker.tick())


if __name__ == '__main__':
    unittest.main()

    def test_retry_failed_preparation_is_explicit_and_idempotent(self):
        task=self.store.tasks.claim(kind='preparation')
        self.store.tasks.fail(task['id'],task['token'],'build failed')
        retried=self.store.retry_preparation(self.project['id'],'retry-1')
        self.assertEqual(retried['preparation_status'],'queued')
        self.assertNotEqual(retried['preparation_task_id'],task['id'])
        replay=self.store.retry_preparation(self.project['id'],'retry-1')
        self.assertEqual(replay['preparation_task_id'],retried['preparation_task_id'])
        with self.assertRaises(ValueError):self.store.retry_preparation(self.project['id'],'retry-2')
        self.assertEqual(self.store.list_scans(),[])
