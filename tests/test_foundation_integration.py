"""Offline storage boundary tests, not Java preparation or READY publication."""
from pathlib import Path
import tempfile
import unittest
from aixsecurity.adapters.artifacts import ArtifactStore
from aixsecurity.adapters.tasks import TaskStore, LeaseLost


class FoundationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.now = 100.0
        self.tasks = TaskStore(self.root / 'tasks.sqlite3', clock=lambda: self.now)
        self.addCleanup(self.tasks.close)
        self.artifacts = ArtifactStore(self.root / 'artifacts')

    def test_completed_result_survives_reopen_and_artifact_verifies(self):
        queued = self.tasks.enqueue('preparation', {'commit': 'a'*40}, 'request-1')
        attempt = self.tasks.claim(lease_seconds=10)
        digest = self.artifacts.put(b'{"fixture":true,"ready":false}')
        self.tasks.complete(queued['id'], attempt['token'], {'manifest_digest': digest})
        reopened = TaskStore(self.root / 'tasks.sqlite3')
        try:
            record = reopened.get(queued['id'])
            self.assertEqual(record['status'], 'completed')
            self.assertEqual(self.artifacts.get(record['result']['manifest_digest']),
                             b'{"fixture":true,"ready":false}')
        finally:
            reopened.close()

    def test_expired_attempt_can_leave_orphan_but_cannot_publish_result(self):
        queued = self.tasks.enqueue('preparation', {}, 'request-2')
        old = self.tasks.claim(lease_seconds=1)
        self.now += 2
        current = self.tasks.claim(lease_seconds=10)
        digest = self.artifacts.put(b'old attempt artifact')
        with self.assertRaises(LeaseLost):
            self.tasks.complete(queued['id'], old['token'], {'manifest_digest': digest})
        record = self.tasks.get(queued['id'])
        self.assertIsNone(record['result'])
        self.assertEqual(record['token'], current['token'])
        # Filesystem and SQLite are not one transaction: orphan cleanup is future work.
        self.assertEqual(self.artifacts.get(digest), b'old attempt artifact')

    def test_cancel_fences_result_without_removing_shared_artifacts(self):
        queued = self.tasks.enqueue('scan', {'snapshot': 'fixture-only'}, 'request-3')
        attempt = self.tasks.claim()
        digest = self.artifacts.put(b'shared baseline')
        self.tasks.cancel(queued['id'])
        with self.assertRaises(LeaseLost):
            self.tasks.complete(queued['id'], attempt['token'], {'report': digest})
        self.assertEqual(self.artifacts.get(digest), b'shared baseline')
