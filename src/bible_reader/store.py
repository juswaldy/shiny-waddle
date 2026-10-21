"""Local persistence with optimistic project revisions and atomic job claims."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .models import ProjectConfig, ReaderError, canonical_json


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, state: Path):
        self.state = state.resolve()
        self.state.mkdir(parents=True, exist_ok=True)
        self.path = self.state / "reader.sqlite3"
        with self.connection() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] > 1:
                raise ReaderError(
                    "This state database was created by a newer reader version. Upgrade the app."
                )
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, config TEXT NOT NULL,
                    created TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, project_id TEXT,
                    project_revision INTEGER, config TEXT NOT NULL, status TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT '', error TEXT, result TEXT,
                    cancel INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, updated TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def decode(row):
        if row is None:
            raise ReaderError("Record not found")
        result = dict(row)
        result["config"] = json.loads(result["config"])
        if "result" in result and result["result"]:
            result["result"] = json.loads(result["result"])
        return result

    def projects(self):
        with self.connection() as db:
            return [self.decode(r) for r in db.execute("SELECT * FROM projects ORDER BY updated DESC")]

    def project(self, identity):
        with self.connection() as db:
            return self.decode(db.execute("SELECT * FROM projects WHERE id=?", (identity,)).fetchone())

    def create_project(self, config: ProjectConfig):
        identity = uuid.uuid4().hex
        with self.connection() as db:
            db.execute(
                "INSERT INTO projects VALUES (?,?,?,?,?)",
                (
                    identity,
                    1,
                    canonical_json(config.model_dump()),
                    now(),
                    now(),
                ),
            )
        return self.project(identity)

    def save_project(self, identity, revision, config: ProjectConfig):
        with self.connection() as db:
            cursor = db.execute(
                "UPDATE projects SET revision=revision+1, config=?, updated=? WHERE id=? AND revision=?",
                (canonical_json(config.model_dump()), now(), identity, revision),
            )
            if cursor.rowcount != 1:
                raise ReaderError("Project changed in another tab. Reload before saving.")
        return self.project(identity)

    def queue(self, kind, config, project_id=None, revision=None):
        identity = uuid.uuid4().hex
        with self.connection() as db:
            db.execute(
                "INSERT INTO jobs(id,kind,project_id,project_revision,config,status,created,updated) VALUES (?,?,?,?,?,?,?,?)",
                (identity, kind, project_id, revision, canonical_json(config), "queued", now(), now()),
            )
        return self.job(identity)

    def queue_file(self, kind: str, text: str, project_id: str, *, config=None):
        """Keep immutable uploads out of frequently polled job metadata."""
        inputs = self.state / "inputs"
        inputs.mkdir(exist_ok=True)
        filename = uuid.uuid4().hex
        path = inputs / filename
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text)
        try:
            return self.queue(kind, {**(config or {}), "input_file": filename}, project_id)
        except Exception:
            path.unlink()
            raise

    def job(self, identity):
        with self.connection() as db:
            return self.decode(db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone())

    def jobs(self):
        with self.connection() as db:
            return [self.decode(r) for r in db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 50")]

    def claim(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='running', updated=? WHERE id=?", (now(), row["id"]))
            return self.decode(row)

    def update_job(self, identity, *, status=None, stage=None, error=None, result=None):
        values = {"updated": now()}
        for key, value in {
            "status": status,
            "stage": stage,
            "error": error,
            "result": canonical_json(result) if result is not None else None,
        }.items():
            if value is not None:
                values[key] = value
        with self.connection() as db:
            db.execute(
                "UPDATE jobs SET " + ",".join(f"{key}=?" for key in values) + " WHERE id=?",
                (*values.values(), identity),
            )

    def cancel(self, identity):
        self.job(identity)
        with self.connection() as db:
            db.execute(
                "UPDATE jobs SET cancel=1, status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END, updated=? WHERE id=? AND status IN ('queued','running')",
                (now(), identity),
            )

    def recover(self):
        with self.connection() as db:
            db.execute(
                "UPDATE jobs SET status='interrupted', error='Worker stopped. Start a new build to retry.', updated=? WHERE status='running'",
                (now(),),
            )
