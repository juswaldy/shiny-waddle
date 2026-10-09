from __future__ import annotations

import asyncio
import os
import secrets
import sys
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..models import ProjectConfig, ReaderError, StrictModel
from ..service import doctor, inspect_project
from ..sources import catalog
from ..store import Store
from ..tex import font_path


class SaveProject(StrictModel):
    revision: int = Field(ge=1)
    config: ProjectConfig


class ImportSource(StrictModel):
    book: str


def create_app(state: Path | None = None, *, start_worker=True):
    state = (state or Path(os.environ.get("READER_STATE", ".reader"))).resolve()
    store = Store(state)
    token = secrets.token_urlsafe(32)
    root = Path(str(files("bible_reader").joinpath("web")))

    @asynccontextmanager
    async def lifespan(app):
        worker = None
        if start_worker:
            worker = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "bible_reader", "--state", str(state), "worker"
            )
        try:
            yield
        finally:
            if worker and worker.returncode is None:
                worker.terminate()
                try:
                    await asyncio.wait_for(worker.wait(), timeout=10)
                except TimeoutError:
                    worker.kill()
                    await worker.wait()

    app = FastAPI(
        title="Original-language reader", version="0.2.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.state.store = store
    app.state.csrf_token = token
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver", "[::1]"])
    app.mount("/static", StaticFiles(directory=root / "static"), name="static")
    templates = Jinja2Templates(directory=root / "templates")

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not secrets.compare_digest(request.headers.get("x-reader-token", ""), token):
                return JSONResponse(
                    {"detail": "Reload the local reader page before making changes."}, status_code=403
                )
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > 2_000_000):
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; frame-src 'self'; object-src 'self'; frame-ancestors 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ReaderError)
    async def reader_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=409 if "another tab" in str(error) else 400)

    @app.get("/")
    def home(request: Request):
        if not store.projects():
            store.create_project(ProjectConfig())
        return templates.TemplateResponse(request=request, name="index.html", context={"csrf": token})

    @app.get("/font/ezra.ttf")
    def font():
        return FileResponse(font_path("Ezra SIL"), media_type="font/ttf")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.2.0"}

    @app.get("/api/doctor")
    def environment():
        return doctor(state)

    @app.get("/api/sources")
    def sources():
        info = catalog()
        return {
            "books": info["books"],
            "attributions": info["attributions"],
            "installed": [code for code in info["books"] if (state / "raw" / f"{code}.xml").is_file()],
            "lexicon": (state / "raw/TBESH.txt").is_file(),
            "revisions": {"oshb": info["oshb_revision"], "step": info["step_revision"]},
        }

    @app.post("/api/sources/import", status_code=202)
    def import_source(value: ImportSource):
        if value.book not in catalog()["books"]:
            raise ReaderError("Unsupported source book")
        return store.queue("import", {"book": value.book})

    @app.get("/api/projects")
    def projects():
        return store.projects()

    @app.post("/api/projects", status_code=201)
    def new_project(config: ProjectConfig):
        return store.create_project(config)

    @app.get("/api/projects/{identity}")
    def project(identity: str):
        return store.project(identity)

    @app.put("/api/projects/{identity}")
    def save_project(identity: str, value: SaveProject):
        return store.save_project(identity, value.revision, value.config)

    @app.get("/api/projects/{identity}/review")
    def review(identity: str):
        config = ProjectConfig.model_validate(store.project(identity)["config"])
        return inspect_project(state, config)

    @app.post("/api/projects/{identity}/builds", status_code=202)
    def queue_build(identity: str):
        project = store.project(identity)
        return store.queue("build", project["config"], identity, project["revision"])

    @app.get("/api/jobs")
    def jobs():
        return store.jobs()

    @app.get("/api/jobs/{identity}")
    def job(identity: str):
        return store.job(identity)

    @app.post("/api/jobs/{identity}/cancel")
    def cancel(identity: str):
        store.cancel(identity)
        return store.job(identity)

    @app.get("/api/jobs/{identity}/artifacts/{name}")
    def artifact(identity: str, name: str, download: bool = False):
        job = store.job(identity)
        if job["status"] != "succeeded" or name not in (job["result"] or {}).get("artifacts", []):
            raise HTTPException(404, "Artifact not available")
        path = state / "builds" / job["id"] / name
        if path.resolve().parent != (state / "builds" / job["id"]).resolve() or not path.is_file():
            raise HTTPException(404, "Artifact not available")
        return FileResponse(
            path,
            filename=name if download else None,
            media_type="application/pdf" if name.endswith(".pdf") else None,
        )

    return app
