"""One durable local worker. Builds are isolated from request handling."""

from __future__ import annotations

import fcntl
import time
from pathlib import Path

from .models import Cancelled, ProjectConfig
from .service import build
from .sources import import_sources
from .store import Store


def run_worker(state: Path, *, once=False, stopped=lambda: False):
    store = Store(state)
    with (state / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        store.recover()
        while not stopped():
            job = store.claim()
            if job is None:
                if once:
                    return
                time.sleep(0.25)
                continue
            identity = job["id"]

            def cancelled(identity=identity):
                return stopped() or bool(store.job(identity)["cancel"])

            def progress(stage, identity=identity):
                store.update_job(identity, stage=stage)

            try:
                if cancelled():
                    raise Cancelled("Cancelled before starting")
                if job["kind"] == "import":
                    result = import_sources(state, job["config"]["book"], progress, cancelled)
                else:
                    config = ProjectConfig.model_validate(job["config"])
                    result = build(state, config, state / "builds" / identity, progress, cancelled)
                if cancelled():
                    raise Cancelled("Cancelled")
                store.update_job(identity, status="succeeded", stage="Ready", result=result)
            except Cancelled as error:
                store.update_job(identity, status="cancelled", error=str(error))
            except Exception as error:
                store.update_job(identity, status="cancelled" if cancelled() else "failed", error=str(error))
            if once:
                return
