"""Single-user platform persistence with transactional immutable snapshot publication."""
import hashlib
import json
import re
import time
import uuid
from .catalog import Catalog
from .tasks import TaskStore, LeaseLost, IdempotencyConflict
from ..domain.assets import clean_text


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


class PlatformStore:
    def __init__(self, path):
        self.catalog = Catalog(path)
        self.tasks = self.catalog._tasks
        self.db = self.catalog.connection
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS published_snapshots(
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES catalog_projects(id),
            data TEXT NOT NULL, created_at REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS platform_scans(
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES catalog_projects(id),
            snapshot_id TEXT NOT NULL REFERENCES published_snapshots(id),
            task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id), request_key TEXT UNIQUE NOT NULL,
            created_at REAL NOT NULL);
        ''')

    def close(self): self.catalog.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    def get_project(self, project_id):
        project = self.catalog.get_project(project_id)
        task = self.tasks.get(project['preparation_task_id'])
        row = self.db.execute('SELECT * FROM published_snapshots WHERE project_id=? ORDER BY created_at DESC LIMIT 1', (project_id,)).fetchone()
        project.update(task_status=task['status'], error=task['error'])
        if row:
            snapshot = json.loads(row['data'])
            project.update(current_snapshot_id=row['id'], preparation_status='READY',
                capabilities=snapshot['capabilities'], assets={'total':len(snapshot['assets']),'by_kind':{kind:sum(a.get('kind')==kind for a in snapshot['assets']) for kind in ('entry','source','sink','guard')},'sample':snapshot['assets'][:20]},
                commit=', '.join(r['commit'] for r in snapshot['repositories']),
                commits=[r['commit'] for r in snapshot['repositories']],
                limitations=snapshot['limitations'])
        elif task['status'] in ('failed','cancelled'):
            project['preparation_status'] = task['status'].upper()
        return project

    def list_projects(self):
        return [self.get_project(p['id']) for p in self.catalog.list_projects()]

    def publish(self, task_id, token, snapshot):
        """Called only after build+analysis; publication and task finish share a lock."""
        repositories = snapshot.get('repositories', [])
        required = {'java-ast','java-sqli-intraprocedural','maven-compile'}
        if not repositories:
            raise ValueError('Preparation repositories missing')
        for repo in repositories:
            if (not isinstance(repo.get('commit'), str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',repo['commit'])
                    or repo.get('build', {}).get('success') is not True
                    or repo.get('analysis_success') is not True
                    or not required <= set(repo.get('capabilities', []))
                    or not repo.get('tool_versions') or not isinstance(repo.get('source_manifest'),dict)):
                raise ValueError('Preparation build, analysis, or provenance gate failed')
            for candidate in repo.get('candidates', []):
                digest = repo['source_manifest'].get(candidate.get('path'))
                if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest):
                    raise ValueError('Candidate lacks source manifest hash')
        actual = set.intersection(*(set(r['capabilities']) for r in repositories))
        if set(snapshot.get('capabilities', [])) != actual or not required <= actual:
            raise ValueError('Snapshot capabilities do not match analyzer outputs')
        data = encoded(snapshot)
        snapshot_id = hashlib.sha256(data.encode()).hexdigest()
        with self.tasks.transaction():
            task = self.tasks.get(task_id)
            if task['kind'] != 'preparation' or task['status'] != 'running' or task['token'] != token or task['lease_until'] <= time.time():
                raise LeaseLost('Preparation lease expired')
            if [r.get('url') for r in repositories] != task['payload']['repositories']:
                raise ValueError('Prepared repository set does not match task')
            project_id = task['payload']['project_id']
            self.db.execute('INSERT INTO published_snapshots VALUES(?,?,?,?)', (snapshot_id, project_id, data, time.time()))
            self.db.execute("UPDATE tasks SET status='completed', result=?,token=NULL,lease_until=NULL WHERE id=?", (encoded({'snapshot_id':snapshot_id}),task_id))
        return snapshot_id

    def retry_preparation(self, project_id, idempotency_key):
        project_id=clean_text(project_id,'project_id')
        key='retry:'+clean_text(idempotency_key,'idempotency_key')
        with self.tasks.transaction():
            project=self.catalog.get_project(project_id)
            prior=self.db.execute("SELECT * FROM tasks WHERE kind='preparation' AND idempotency_key=?",(key,)).fetchone()
            if prior:
                if json.loads(prior['payload'])['project_id'] != project_id:
                    raise IdempotencyConflict('Retry key belongs to another project')
                return self.get_project(project_id)
            if project['preparation_status'] not in ('failed','cancelled'):
                raise ValueError('Only failed or cancelled preparation can be retried')
            task=self.tasks.enqueue_in_transaction('preparation',
                {'project_id':project_id,'repositories':project['repositories']},key)
            self.db.execute('UPDATE catalog_projects SET preparation_task_id=? WHERE id=?',(task['id'],project_id))
            return self.get_project(project_id)

    def create_scan(self, project_id, idempotency_key):
        project_id = clean_text(project_id,'project_id')
        key = clean_text(idempotency_key,'idempotency_key')
        with self.tasks.transaction():
            row = self.db.execute('SELECT * FROM platform_scans WHERE request_key=?', (key,)).fetchone()
            if row:
                if row['project_id'] != project_id: raise IdempotencyConflict('Scan key has different project')
                return self.get_scan(row['id'])
            project = self.get_project(project_id)
            if project['preparation_status'] != 'READY' or not project['current_snapshot_id']:
                raise ValueError('Select a READY asset before scanning')
            scan_id = uuid.uuid4().hex
            task = self.tasks.enqueue_in_transaction('scan', {'scan_id':scan_id,'project_id':project_id,
                'snapshot_id':project['current_snapshot_id'],'plan':'sqli-intraprocedural-v1'}, 'scan:'+key)
            self.db.execute('INSERT INTO platform_scans VALUES(?,?,?,?,?,?)',
                (scan_id,project_id,project['current_snapshot_id'],task['id'],key,time.time()))
            return self.get_scan(scan_id)

    def get_scan(self, scan_id):
        row = self.db.execute('SELECT * FROM platform_scans WHERE id=?',(scan_id,)).fetchone()
        if row is None: raise ValueError('Unknown scan')
        task = self.tasks.get(row['task_id'])
        return {'id':row['id'],'project_id':row['project_id'],'snapshot_id':row['snapshot_id'],
                'status':task['status'],'error':task['error'],'report':task['result']}

    def list_scans(self):
        return [self.get_scan(r['id']) for r in self.db.execute('SELECT id FROM platform_scans ORDER BY created_at DESC')]

    def snapshot(self, snapshot_id):
        row = self.db.execute('SELECT data FROM published_snapshots WHERE id=?',(snapshot_id,)).fetchone()
        if row is None: raise ValueError('Unknown snapshot')
        return json.loads(row['data'])
