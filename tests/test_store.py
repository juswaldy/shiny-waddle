import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from bible_reader import jobs
from bible_reader.models import Cancelled, ProjectConfig, ReaderError
from bible_reader.store import Store


def test_project_revisions_and_snapshot_isolation(tmp_path):
    store = Store(tmp_path)
    project = store.create_project(ProjectConfig())
    queued = store.queue("build", project["config"], project["id"], project["revision"])
    edited = ProjectConfig(name="Changed")
    updated = store.save_project(project["id"], 1, edited)
    assert updated["revision"] == 2
    with pytest.raises(ReaderError, match="another tab"):
        store.save_project(project["id"], 1, edited)
    assert Store(tmp_path).project(project["id"])["config"]["name"] == "Changed"
    assert store.job(queued["id"])["config"]["name"] == "Proverbs reader"


def test_atomic_claim_and_queued_cancellation(tmp_path):
    store = Store(tmp_path)
    queued = [store.queue("build", {}) for _ in range(8)]
    store.cancel(queued[0]["id"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed = [r for r in pool.map(lambda _: store.claim(), range(12)) if r]
    assert len(claimed) == 7
    assert len({r["id"] for r in claimed}) == 7
    assert store.job(queued[0]["id"])["status"] == "cancelled"
    store.recover()
    assert all(store.job(r["id"])["status"] == "interrupted" for r in claimed)


def test_newer_database_is_not_downgraded(tmp_path):
    Store(tmp_path)
    with sqlite3.connect(tmp_path / "reader.sqlite3") as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(ReaderError, match="newer"):
        Store(tmp_path)


@pytest.mark.parametrize(
    "outcome,status", [("ok", "succeeded"), ("error", "failed"), ("cancel", "cancelled")]
)
def test_worker_records_terminal_state(tmp_path, monkeypatch, outcome, status):
    store = Store(tmp_path)
    job = store.queue("build", ProjectConfig().model_dump())

    def fake_build(state, config, output, progress, cancelled):
        progress("Test stage")
        if outcome == "error":
            raise ReaderError("Actionable error")
        if outcome == "cancel":
            raise Cancelled("Cancelled")
        return {"artifacts": []}

    monkeypatch.setattr(jobs, "build", fake_build)
    jobs.run_worker(tmp_path, once=True)
    result = store.job(job["id"])
    assert result["status"] == status
    assert result["result"] == {"artifacts": []} if outcome == "ok" else result["error"]
