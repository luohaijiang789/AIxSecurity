"""Local run envelopes; timestamps never enter deterministic evidence reports."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class RunLedger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('''CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
            target TEXT NOT NULL, config TEXT NOT NULL, status TEXT NOT NULL,
            report TEXT, error TEXT)''')
        self.connection.commit()

    def close(self):
        self.connection.close()

    def start(self, target, config):
        run_id = uuid.uuid4().hex
        with self.connection:
            self.connection.execute(
                "INSERT INTO runs(id,started_at,target,config,status) VALUES(?,?,?,?,?)",
                (run_id, datetime.now(timezone.utc).isoformat(), str(target),
                 json.dumps(config, sort_keys=True), "running"))
        return run_id

    def finish(self, run_id, report=None, error=None):
        status = report["status"] if report is not None else "failed"
        with self.connection:
            self.connection.execute(
                "UPDATE runs SET finished_at=?,status=?,report=?,error=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), status,
                 json.dumps(report, ensure_ascii=False) if report is not None else None,
                 error, run_id))

    def list(self):
        return [dict(row) for row in self.connection.execute(
            "SELECT id,started_at,finished_at,target,status,error FROM runs ORDER BY started_at DESC")]

    def show(self, run_id):
        row = self.connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown run: {run_id}")
        result = dict(row)
        result["config"] = json.loads(result["config"])
        result["report"] = json.loads(result["report"]) if result["report"] else None
        return result
