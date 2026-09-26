"""Persistent asset registration; preparation remains queued until a worker runs.

A Catalog owns one thread-local SQLite connection. Registration and task creation
share one transaction; this adapter never fetches, builds, or publishes snapshots.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from aixsecurity.adapters.tasks import IdempotencyConflict, TaskStore
from aixsecurity.domain.assets import normalize_registration


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


class Catalog:
    def __init__(self, path: Path, *, read_only=False):
        self._tasks = None
        self.read_only = read_only
        if read_only:
            connection = None
            try:
                uri = Path(path).resolve().as_uri() + '?mode=ro'
                connection = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
                connection.row_factory = sqlite3.Row
                tables = {row['name'] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'tasks', 'catalog_projects', 'catalog_requests'} <= tables:
                    raise ValueError('Existing catalog database is required')
            except (sqlite3.Error, ValueError) as error:
                if connection is not None:
                    connection.close()
                raise ValueError('Existing catalog database is required') from error
            self.connection = connection
            return
        self._tasks = TaskStore(path)
        self.connection = self._tasks.connection
        try:
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('''CREATE TABLE IF NOT EXISTS catalog_projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                repositories TEXT NOT NULL,
                preparation_task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id),
                created_at REAL NOT NULL)''')
            self.connection.execute('''CREATE TABLE IF NOT EXISTS catalog_requests (
                scope TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                project_id TEXT NOT NULL REFERENCES catalog_projects(id),
                PRIMARY KEY(scope,idempotency_key))''')
        except BaseException:
            self.close()
            raise

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @staticmethod
    def _decode(row):
        return {
            'id': row['id'], 'name': row['name'],
            'repositories': json.loads(row['repositories']),
            'preparation_task_id': row['preparation_task_id'],
            'preparation_status': row['preparation_status'],
            # Task completion alone is not a validated, published asset snapshot.
            'current_snapshot_id': None,
        }

    def get_project(self, project_id):
        row = self.connection.execute('''SELECT p.*,t.status AS preparation_status
            FROM catalog_projects p JOIN tasks t ON t.id=p.preparation_task_id
            WHERE p.id=?''', (project_id,)).fetchone()
        if row is None:
            raise ValueError(f'Unknown project: {project_id}')
        return self._decode(row)

    def list_projects(self):
        rows = self.connection.execute('''SELECT p.*,t.status AS preparation_status
            FROM catalog_projects p JOIN tasks t ON t.id=p.preparation_task_id
            ORDER BY p.created_at,p.id''').fetchall()
        return [self._decode(row) for row in rows]

    def register(self, name: str, repositories: list[str], idempotency_key: str):
        if self.read_only:
            raise ValueError('Catalog is read-only')
        name, repositories, idempotency_key = normalize_registration(
            name, repositories, idempotency_key)
        request = {'name': name, 'repositories': repositories}
        encoded = _encode({'name': request['name'], 'repositories': request['repositories']})
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self._tasks.transaction():
            existing = self.connection.execute('''SELECT project_id,request_digest
                FROM catalog_requests WHERE scope=? AND idempotency_key=?''',
                ('catalog/register', idempotency_key)).fetchone()
            if existing is not None:
                if existing['request_digest'] != digest:
                    raise IdempotencyConflict('Idempotency key has a different registration')
                return self.get_project(existing['project_id'])
            project_id = uuid.uuid4().hex
            task = self._tasks.enqueue_in_transaction(
                'preparation',
                {'project_id': project_id, 'repositories': request['repositories']},
                f'catalog/register:{project_id}')
            task_id, now = task['id'], task['created_at']
            self.connection.execute('''INSERT INTO catalog_projects
                (id,name,repositories,preparation_task_id,created_at) VALUES(?,?,?,?,?)''',
                (project_id, request['name'], _encode(request['repositories']), task_id, now))
            self.connection.execute('''INSERT INTO catalog_requests
                (scope,idempotency_key,request_digest,project_id) VALUES(?,?,?,?)''',
                ('catalog/register', idempotency_key, digest, project_id))
            return self.get_project(project_id)
