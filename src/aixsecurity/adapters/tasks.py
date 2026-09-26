"""Single-host durable tasks with idempotency, bounded retries and lease fencing.

Each thread/worker owns a TaskStore connection. A cancellation fences database
writes immediately; the executor must separately stop its subprocesses. This is
not an artifact publisher and does not make filesystem writes transactional.
"""
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid


class IdempotencyConflict(ValueError):
    """A key already belongs to a different request."""


class LeaseLost(ValueError):
    """The task is no longer running under this live attempt token."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _lease(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("lease_seconds must be positive and finite")
    if not math.isfinite(value) or value <= 0:
        raise ValueError("lease_seconds must be positive and finite")
    return value


class TaskStore:
    def __init__(self, path: Path, *, clock=time.time):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.connection = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
            payload_digest TEXT NOT NULL, idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN
                ('queued','running','completed','failed','cancelled')),
            attempt INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
            token TEXT, lease_until REAL, result TEXT, error TEXT,
            created_at REAL NOT NULL, updated_at REAL NOT NULL,
            UNIQUE(kind, idempotency_key))''')
        self.connection.execute(
            'CREATE INDEX IF NOT EXISTS tasks_claim ON tasks(status, created_at)')

    def close(self):
        self.connection.close()

    @contextmanager
    def transaction(self):
        """Own an immediate transaction for atomic task and application writes.

        Nested transactions are not supported. Use enqueue_in_transaction when
        composing task creation with other writes on this connection.
        """
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield self
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def _transaction(self):
        """Compatibility alias for existing internal callers."""
        return self.transaction()

    @staticmethod
    def _decode(row):
        task = dict(row)
        task['payload'] = json.loads(task['payload'])
        task['result'] = json.loads(task['result']) if task['result'] is not None else None
        return task

    def get(self, task_id):
        row = self.connection.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise ValueError(f'Unknown task: {task_id}')
        return self._decode(row)

    def enqueue(self, kind, payload, idempotency_key, *, max_attempts=3):
        """Return task dict; same kind/key/request returns the original task.

        Keys are scoped by kind. max_attempts is immutable request configuration:
        changing it with an existing key also raises IdempotencyConflict.
        """
        with self.transaction():
            return self.enqueue_in_transaction(
                kind, payload, idempotency_key, max_attempts=max_attempts)

    def enqueue_in_transaction(self, kind, payload, idempotency_key, *, max_attempts=3):
        """Enqueue without committing; caller must own an active transaction.

        Uses exactly the same validation and idempotency semantics as enqueue.
        The caller is responsible for rolling back its transaction on failure.
        """
        if not self.connection.in_transaction:
            raise RuntimeError('enqueue_in_transaction requires an active transaction')
        _text(kind, 'kind')
        _text(idempotency_key, 'idempotency_key')
        _positive_int(max_attempts, 'max_attempts')
        encoded = _json(payload)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        existing = self.connection.execute(
            'SELECT * FROM tasks WHERE kind=? AND idempotency_key=?',
            (kind, idempotency_key)).fetchone()
        if existing:
            if existing['payload_digest'] != digest or existing['max_attempts'] != max_attempts:
                raise IdempotencyConflict('Idempotency key has a different request')
            return self._decode(existing)
        task_id = uuid.uuid4().hex
        now = self.clock()
        self.connection.execute('''INSERT INTO tasks
            (id,kind,payload,payload_digest,idempotency_key,status,max_attempts,created_at,updated_at)
            VALUES(?,?,?,?,?,'queued',?,?,?)''',
            (task_id, kind, encoded, digest, idempotency_key, max_attempts, now, now))
        return self.get(task_id)

    def _reap(self, now, limit):
        rows = self.connection.execute('''SELECT id,attempt,max_attempts FROM tasks
            WHERE status='running' AND lease_until<=? ORDER BY lease_until,id LIMIT ?''',
            (now, limit)).fetchall()
        for row in rows:
            status = 'failed' if row['attempt'] >= row['max_attempts'] else 'queued'
            self.connection.execute('''UPDATE tasks SET status=?,token=NULL,lease_until=NULL,
                error='lease_expired',updated_at=? WHERE id=?''', (status, now, row['id']))
        return len(rows)

    def reap_expired(self, *, limit=100):
        """Recover at most limit expired attempts; max_attempts bounds retries."""
        _positive_int(limit, 'limit')
        with self._transaction():
            return self._reap(self.clock(), limit)

    def claim(self, *, kind=None, lease_seconds=60):
        """Atomically claim one task, or return None. Token changes every attempt."""
        _lease(lease_seconds)
        if kind is not None:
            _text(kind, 'kind')
        with self._transaction():
            now = self.clock()
            self._reap(now, 100)
            row = self.connection.execute('''SELECT id FROM tasks
                WHERE status='queued' AND (? IS NULL OR kind=?)
                ORDER BY created_at,rowid LIMIT 1''', (kind, kind)).fetchone()
            if row is None:
                return None
            self.connection.execute('''UPDATE tasks SET status='running',attempt=attempt+1,
                token=?,lease_until=?,updated_at=? WHERE id=?''',
                (uuid.uuid4().hex, now + lease_seconds, now, row['id']))
            return self.get(row['id'])

    def _live_update(self, task_id, token, fields, values):
        _text(token, 'token')
        with self._transaction():
            now = self.clock()
            cursor = self.connection.execute(f'''UPDATE tasks SET {fields},updated_at=?
                WHERE id=? AND status='running' AND token=? AND lease_until>?''',
                (*values, now, task_id, token, now))
            if cursor.rowcount != 1:
                raise LeaseLost('Task does not have this live attempt lease')
            return self.get(task_id)

    def heartbeat(self, task_id, token, *, lease_seconds=60):
        _lease(lease_seconds)
        # Compute the new deadline while holding the transaction lock, not before
        # waiting for another writer. The common updater accepts only fixed SQL.
        _text(token, 'token')
        with self._transaction():
            now = self.clock()
            cursor = self.connection.execute('''UPDATE tasks SET lease_until=?,updated_at=?
                WHERE id=? AND status='running' AND token=? AND lease_until>?''',
                (now + lease_seconds, now, task_id, token, now))
            if cursor.rowcount != 1:
                raise LeaseLost('Task does not have this live attempt lease')
            return self.get(task_id)

    def complete(self, task_id, token, result=None):
        return self._live_update(task_id, token,
            "status='completed',result=?,error=NULL,token=NULL,lease_until=NULL", (_json(result),))

    def fail(self, task_id, token, error):
        """Explicit failure is terminal; only abandoned leases auto-retry."""
        return self._live_update(task_id, token,
            "status='failed',error=?,token=NULL,lease_until=NULL", (_text(error, 'error'),))

    def cancel(self, task_id):
        """Fence queued/running work; retain a pre-existing terminal outcome."""
        with self._transaction():
            task = self.get(task_id)
            if task['status'] in ('queued', 'running'):
                self.connection.execute('''UPDATE tasks SET status='cancelled',token=NULL,
                    lease_until=NULL,updated_at=? WHERE id=?''', (self.clock(), task_id))
            return self.get(task_id)
