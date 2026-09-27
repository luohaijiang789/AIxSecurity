"""Background preparation/scan worker; each task owns its store connection."""
import threading
import math
from pathlib import Path
from .platform import PlatformStore
from .tasks import LeaseLost, TaskStore
from .java import PreparationError


class PipelineWorker:
    def __init__(self, database, workdir, preparer, investigator, *, lease_seconds=3600, heartbeat_interval=30):
        self.database, self.workdir = database, Path(workdir).resolve()
        self.preparer,self.investigator=preparer,investigator
        if (isinstance(lease_seconds, bool) or isinstance(heartbeat_interval, bool)
                or not isinstance(lease_seconds, (int, float)) or not isinstance(heartbeat_interval, (int, float))
                or not math.isfinite(lease_seconds) or not math.isfinite(heartbeat_interval)
                or not 0 < heartbeat_interval < lease_seconds):
            raise ValueError('Heartbeat interval must be positive and shorter than the finite lease')
        self.lease_seconds, self.heartbeat_interval = lease_seconds, heartbeat_interval
        self.stop_event=threading.Event()

    def _renew(self, task, done, lost):
        # SQLite connections are thread-owned; never use the tick connection here.
        tasks = None
        try:
            tasks = TaskStore(self.database)
            while not done.wait(self.heartbeat_interval):
                if self.stop_event.is_set():
                    lost.set()
                    return
                tasks.heartbeat(task['id'], task['token'], lease_seconds=self.lease_seconds)
        except Exception:
            # Any renewal uncertainty is fail-closed; database fencing remains final.
            lost.set()
        finally:
            if tasks is not None:
                tasks.close()

    def _require_live(self, store, task, lost):
        if self.stop_event.is_set() or lost.is_set():
            raise LeaseLost('Worker stopped or task renewal was lost')
        store.tasks.heartbeat(task['id'], task['token'], lease_seconds=self.lease_seconds)

    def tick(self):
        if self.stop_event.is_set(): return False
        with PlatformStore(self.database) as store:
            task=store.tasks.claim(lease_seconds=self.lease_seconds)
            if not task: return False
            done, lost = threading.Event(), threading.Event()
            heartbeat = threading.Thread(target=self._renew, args=(task, done, lost),
                name='aixsecurity-lease-' + task['id'], daemon=True)
            heartbeat.start()
            try:
                self._require_live(store, task, lost)
                if task['kind']=='preparation':
                    repos=[]
                    for index,url in enumerate(task['payload']['repositories']):
                        self._require_live(store, task, lost)
                        attempt_dir = self.workdir/task['id']/f"attempt-{task['attempt']}-{task['token']}"
                        repo=self.preparer.prepare(url,attempt_dir/str(index))
                        repo['url']=url
                        repos.append(repo)
                    snapshot={'repositories':repos,'capabilities':sorted(set.intersection(*(set(r['capabilities']) for r in repos))),
                        'assets':[dict(a,repo_index=i) for i,r in enumerate(repos) for a in r['assets']],
                        'limitations':list(dict.fromkeys(x for r in repos for x in r.get('limitations',[])))}
                    self._require_live(store, task, lost)
                    store.publish(task['id'],task['token'],snapshot)
                elif task['kind']=='scan':
                    snapshot=store.snapshot(task['payload']['snapshot_id'])
                    report=self.investigator.run(snapshot)
                    report['snapshot_id']=task['payload']['snapshot_id']
                    report['plan']=task['payload']['plan']
                    self._require_live(store, task, lost)
                    store.tasks.complete(task['id'],task['token'],report)
                else:
                    store.tasks.fail(task['id'],task['token'],'Unsupported task kind')
            except Exception as error:
                # Known adapter messages are designed to exclude source/secrets.
                message=str(error)[:300] if isinstance(error,(ValueError,PreparationError)) else type(error).__name__
                try: store.tasks.fail(task['id'],task['token'],message)
                except LeaseLost: pass
            finally:
                done.set()
                heartbeat.join()
            return True

    def run(self):
        while not self.stop_event.is_set():
            try: worked=self.tick()
            except Exception: worked=False
            if not worked: self.stop_event.wait(1)
