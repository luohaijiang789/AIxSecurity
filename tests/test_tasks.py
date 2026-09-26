import concurrent.futures
from pathlib import Path
import tempfile
import threading
import unittest

from aixsecurity.adapters.tasks import IdempotencyConflict, LeaseLost, TaskStore


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'tasks.sqlite3'
        self.now = 100.0
        self.store = TaskStore(self.path, clock=lambda: self.now)
        self.addCleanup(self.store.close)

    def enqueue(self, key='request', **kwargs):
        return self.store.enqueue('prepare', {'commit': 'abc'}, key, **kwargs)

    def test_composable_enqueue_requires_transaction(self):
        with self.assertRaisesRegex(RuntimeError, 'active transaction'):
            self.store.enqueue_in_transaction('prepare', {'commit': 'abc'}, 'x')
        self.assertEqual(self.store.connection.execute(
            'SELECT COUNT(*) FROM tasks').fetchone()[0], 0)

    def test_composable_enqueue_commits_and_reuses_standard_semantics(self):
        with self.store.transaction():
            task = self.store.enqueue_in_transaction('prepare', {'commit': 'abc'}, 'x')
            self.assertTrue(self.store.connection.in_transaction)
            again = self.store.enqueue_in_transaction('prepare', {'commit': 'abc'}, 'x')
            self.assertEqual(again['id'], task['id'])
        self.assertFalse(self.store.connection.in_transaction)
        self.assertEqual(self.store.enqueue('prepare', {'commit': 'abc'}, 'x')['id'], task['id'])
        with self.assertRaises(IdempotencyConflict):
            with self.store.transaction():
                self.store.enqueue_in_transaction('prepare', {'commit': 'different'}, 'x')
        self.assertEqual(self.store.get(task['id'])['payload'], {'commit': 'abc'})

    def test_external_transaction_rolls_back_composed_writes(self):
        self.store.connection.execute('CREATE TABLE application_marker (name TEXT)')
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            with self.store.transaction():
                self.store.connection.execute("INSERT INTO application_marker VALUES ('project')")
                self.store.enqueue_in_transaction('prepare', {'commit': 'abc'}, 'x')
                raise RuntimeError('injected')
        for table in ('tasks', 'application_marker'):
            self.assertEqual(self.store.connection.execute(
                f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
        self.assertFalse(self.store.connection.in_transaction)
        self.assertEqual(self.store.enqueue('prepare', {'commit': 'abc'}, 'x')['status'], 'queued')

    def test_idempotency_and_immutable_request(self):
        task = self.enqueue()
        self.assertEqual(self.enqueue()['id'], task['id'])
        with self.assertRaises(IdempotencyConflict):
            self.store.enqueue('prepare', {'commit': 'def'}, 'request')
        with self.assertRaises(IdempotencyConflict):
            self.enqueue(max_attempts=9)
        other = self.store.enqueue('scan', {'commit': 'abc'}, 'request')
        self.assertNotEqual(task['id'], other['id'])

    def test_canonical_payload_and_reopen(self):
        first = self.store.enqueue('prepare', {'a': 1, 'b': 2}, 'a')
        other = TaskStore(self.path)
        try:
            second = other.enqueue('prepare', {'b': 2, 'a': 1}, 'a')
            self.assertEqual(first['id'], second['id'])
        finally:
            other.close()

    def test_kind_filter_and_completion(self):
        self.enqueue()
        self.assertIsNone(self.store.claim(kind='scan'))
        claimed = self.store.claim(kind='prepare', lease_seconds=20)
        self.assertEqual(claimed['attempt'], 1)
        self.assertIsNone(self.store.claim())
        done = self.store.complete(claimed['id'], claimed['token'], {'artifact': 'digest'})
        self.assertEqual(done['result'], {'artifact': 'digest'})
        self.assertEqual(self.store.cancel(done['id'])['status'], 'completed')
        with self.assertRaises(LeaseLost):
            self.store.fail(done['id'], claimed['token'], 'late')

    def test_expiry_fences_all_writes_before_reclaim(self):
        self.enqueue()
        task = self.store.claim(lease_seconds=5)
        self.now = 105
        for operation in (
            lambda: self.store.heartbeat(task['id'], task['token']),
            lambda: self.store.complete(task['id'], task['token']),
            lambda: self.store.fail(task['id'], task['token'], 'late')):
            with self.assertRaises(LeaseLost):
                operation()

    def test_reclaim_fences_old_worker(self):
        self.enqueue()
        old = self.store.claim(lease_seconds=1)
        self.now += 2
        current = self.store.claim()
        self.assertEqual(current['id'], old['id'])
        self.assertEqual(current['attempt'], 2)
        self.assertNotEqual(current['token'], old['token'])
        for operation in (
            lambda: self.store.heartbeat(old['id'], old['token']),
            lambda: self.store.complete(old['id'], old['token']),
            lambda: self.store.fail(old['id'], old['token'], 'late')):
            with self.assertRaises(LeaseLost):
                operation()
        self.store.complete(current['id'], current['token'])

    def test_heartbeat_extends_live_lease(self):
        self.enqueue()
        task = self.store.claim(lease_seconds=5)
        self.now += 4
        updated = self.store.heartbeat(task['id'], task['token'], lease_seconds=8)
        self.assertEqual(updated['lease_until'], 112)
        self.now = 106
        self.assertEqual(self.store.reap_expired(), 0)
        self.store.complete(task['id'], task['token'])

    def test_bounded_attempts(self):
        task = self.enqueue(max_attempts=2)
        for attempt in (1, 2):
            claimed = self.store.claim(lease_seconds=1)
            self.assertEqual(claimed['attempt'], attempt)
            self.now += 2
        self.assertIsNone(self.store.claim())
        stopped = self.store.get(task['id'])
        self.assertEqual(stopped['status'], 'failed')
        self.assertEqual(stopped['error'], 'lease_expired')
        self.assertEqual(stopped['attempt'], 2)

    def test_reap_batch_limit(self):
        for index in range(3):
            self.enqueue(str(index))
            self.store.claim(lease_seconds=1)
        self.now += 2
        self.assertEqual(self.store.reap_expired(limit=2), 2)
        self.assertEqual(self.store.reap_expired(limit=2), 1)
        self.assertEqual(self.store.reap_expired(limit=2), 0)

    def test_cancel_queued_and_running(self):
        queued = self.enqueue('queued')
        self.assertEqual(self.store.cancel(queued['id'])['status'], 'cancelled')
        self.assertIsNone(self.store.claim())
        self.enqueue('running')
        running = self.store.claim()
        self.store.cancel(running['id'])
        for operation in (
            lambda: self.store.complete(running['id'], running['token']),
            lambda: self.store.heartbeat(running['id'], running['token']),
            lambda: self.store.fail(running['id'], running['token'], 'late')):
            with self.assertRaises(LeaseLost):
                operation()
        self.assertEqual(self.store.cancel(running['id'])['status'], 'cancelled')

    def test_failure_is_terminal(self):
        self.enqueue()
        task = self.store.claim()
        self.store.fail(task['id'], task['token'], 'missing JDK')
        self.assertEqual(self.store.cancel(task['id'])['status'], 'failed')
        self.now += 1000
        self.assertIsNone(self.store.claim())
        with self.assertRaises(LeaseLost):
            self.store.complete(task['id'], task['token'])

    def test_validation_and_missing_task(self):
        with self.assertRaises(ValueError):
            self.store.cancel('missing')
        with self.assertRaises(LeaseLost):
            self.store.complete('missing', 'token')
        for value in (0, -1, float('inf'), float('nan'), True):
            with self.assertRaises(ValueError):
                self.store.claim(lease_seconds=value)
        with self.assertRaises(ValueError):
            self.enqueue(max_attempts=0)
        with self.assertRaises(ValueError):
            self.store.enqueue('prepare', {'x': float('nan')}, 'nan')
        with self.assertRaises(ValueError):
            self.store.reap_expired(limit=0)

    def parallel(self, operation):
        barrier = threading.Barrier(2)
        def worker():
            store = TaskStore(self.path, clock=lambda: 100.0)
            try:
                barrier.wait(timeout=5)
                return operation(store)
            finally:
                store.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            return [future.result(timeout=15) for future in futures]

    def test_parallel_enqueue_uses_one_logical_task(self):
        tasks = self.parallel(lambda store: store.enqueue('prepare', {'commit': 'abc'}, 'request'))
        self.assertEqual(tasks[0]['id'], tasks[1]['id'])
        count = self.store.connection.execute('SELECT count(*) FROM tasks').fetchone()[0]
        self.assertEqual(count, 1)

    def test_parallel_claim_has_single_owner(self):
        self.enqueue()
        tasks = self.parallel(lambda store: store.claim())
        self.assertEqual(sum(task is not None for task in tasks), 1)

    def test_completion_cancel_race_has_one_terminal_outcome(self):
        self.enqueue()
        task = self.store.claim()
        barrier = threading.Barrier(2)
        def worker(cancel):
            store = TaskStore(self.path, clock=lambda: 100.0)
            try:
                barrier.wait(timeout=5)
                try:
                    return (store.cancel(task['id']) if cancel else
                            store.complete(task['id'], task['token']))['status']
                except LeaseLost:
                    return 'lease_lost'
            finally:
                store.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, value) for value in (True, False)]
            outcomes = [future.result(timeout=15) for future in futures]
        final = self.store.get(task['id'])['status']
        self.assertIn(final, ('cancelled', 'completed'))
        self.assertEqual(sorted(outcomes), ['cancelled', 'lease_lost'] if final == 'cancelled'
                         else ['completed', 'completed'])
