"""Worker lease/attempt tests using synthetic preparation, never remote code."""
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from aixsecurity.adapters.pipeline import PipelineWorker
from aixsecurity.adapters.platform import PlatformStore
from aixsecurity.adapters.tasks import TaskStore, LeaseLost
from test_platform import make_snapshot, URL


class PipelineLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/'platform.db'
        self.store = PlatformStore(self.db)
        self.addCleanup(self.store.close)
        self.project = self.store.catalog.register('Synthetic', [URL], 'register')
        self.paths = []

    def worker(self, action=None):
        paths = self.paths
        class Preparer:
            def prepare(inner, url, directory):
                paths.append(directory)
                if action: action()
                return deepcopy(make_snapshot()['repositories'][0])
        return PipelineWorker(self.db, Path(self.temp.name)/'jobs', Preparer(), None,
                              lease_seconds=1, heartbeat_interval=.05)

    def test_long_task_is_renewed_and_attempt_directory_is_unique(self):
        worker = self.worker(lambda: time.sleep(1.3))
        self.assertTrue(worker.tick())
        project = self.store.get_project(self.project['id'])
        self.assertEqual(project['preparation_status'], 'READY')
        self.assertTrue(self.paths[0].parent.name.startswith('attempt-1-'))

    def test_lost_renewal_never_publishes(self):
        worker = self.worker(lambda: time.sleep(.15))
        original = TaskStore.heartbeat
        count = [0]
        def renew(store, *args, **kwargs):
            count[0] += 1
            if count[0] > 2: raise LeaseLost('Synthetic renewal failure')
            return original(store, *args, **kwargs)
        with patch.object(TaskStore, 'heartbeat', renew):
            worker.tick()
        self.assertIsNone(self.store.get_project(self.project['id'])['current_snapshot_id'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM published_snapshots').fetchone()[0], 0)

    def test_stop_during_preparation_never_publishes(self):
        worker = self.worker(lambda: worker.stop_event.set())
        worker.tick()
        self.assertIsNone(self.store.get_project(self.project['id'])['current_snapshot_id'])
        self.assertFalse(worker.tick())

    def test_reclaimed_task_uses_new_attempt_directory(self):
        previous = self.store.tasks.claim(lease_seconds=1)
        self.store.db.execute('UPDATE tasks SET lease_until=0 WHERE id=?', (previous['id'],))
        worker = self.worker()
        worker.tick()
        self.assertTrue(self.paths[0].parent.name.startswith('attempt-2-'))
        self.assertNotIn(previous['token'], str(self.paths[0]))
        self.assertEqual(self.store.get_project(self.project['id'])['preparation_status'], 'READY')

    def test_invalid_heartbeat_configuration_rejected(self):
        for lease, interval in [(1,1), (0,1), (1,0), (1,float('nan'))]:
            with self.subTest(lease=lease, interval=interval), self.assertRaises(ValueError):
                PipelineWorker(self.db, self.temp.name, None, None,
                               lease_seconds=lease, heartbeat_interval=interval)
