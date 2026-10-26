from __future__ import annotations

import asyncio
import os
import secrets
import sys
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..book_helps import MAX_HELP_FILE_BYTES, BookHelps, load_book_helps, save_book_helps
from ..data_files import load_reader_data, validate_tex
from ..editorial import edit_decision, edit_decisions
from ..models import Decision, ProjectConfig, ReaderError, StrictModel, canonical_json
from ..service import doctor, inspect_project
from ..sources import book_artifact, catalog
from ..store import Store
from ..tex import font_path
from ..word_classes import WORD_CLASS_COLORS


class SaveProject(StrictModel):
    revision: int = Field(ge=1)
    config: ProjectConfig


class ImportSource(StrictModel):
    book: str


class DecisionEdit(StrictModel):
    anchor: str = Field(min_length=1, max_length=100)
    decision: Decision
    scope: Literal["occurrence", "book"] = "occurrence"


class EditDecision(DecisionEdit):
    revision: int = Field(ge=1)


class EditDecisionPage(StrictModel):
    revision: int = Field(ge=1)
    edits: list[DecisionEdit] = Field(min_length=1, max_length=200)


class LoadBookHelps(StrictModel):
    revision: int = Field(ge=1)
    helps: BookHelps


class UploadData(StrictModel):
    data: dict


class UploadTex(StrictModel):
    tex: str
    font: Literal["Ezra SIL", "SBL Hebrew"] = "Ezra SIL"


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
            if length and (not length.isdigit() or int(length) > MAX_HELP_FILE_BYTES):
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
        return templates.TemplateResponse(
            request=request, name="index.html", context={"csrf": token, "word_classes": WORD_CLASS_COLORS}
        )

    @app.get("/font/ezra.ttf")
    def font():
        return FileResponse(font_path("Ezra SIL"), media_type="font/ttf")

    @app.get("/font/greek.ttf")
    def greek_font():
        return FileResponse(font_path("Gentium Plus"), media_type="font/ttf")

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
            "attributions": info["attributions"]
            + info["greek"]["attributions"]
            + [n for layer in info["greek"]["layers"].values() for n in layer["attributions"]],
            "installed": [code for code in info["books"] if book_artifact(state, code)[0].is_file()],
            "lexicon": (state / "raw/TBESH.txt").is_file(),
            "greek_lexicon": (state / "raw/greek/TBESG.txt").is_file(),
            "greek_terms": info["greek"]["layers"],
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

    @app.get("/api/projects/{identity}/helps")
    def download_helps(identity: str, revision: int):
        project = store.project(identity)
        if revision != project["revision"]:
            raise ReaderError("Project changed in another tab. Reload before saving.")
        config = ProjectConfig.model_validate(project["config"])
        helps = save_book_helps(state, config)
        return JSONResponse(
            helps.model_dump(),
            headers={"Content-Disposition": f'attachment; filename="{config.book}-lexical-helps.json"'},
        )

    @app.post("/api/projects/{identity}/helps")
    def upload_helps(identity: str, value: LoadBookHelps):
        project = store.project(identity)
        if value.revision != project["revision"]:
            raise ReaderError("Project changed in another tab. Reload before saving.")
        config = load_book_helps(state, ProjectConfig.model_validate(project["config"]), value.helps)
        saved = store.save_project(identity, value.revision, config)
        return {"project": saved, "loaded": len(config.decisions)}

    @app.post("/api/projects/{identity}/decisions")
    def save_decision(identity: str, value: EditDecision):
        project = store.project(identity)
        if value.revision != project["revision"]:
            raise ReaderError("Project changed in another tab. Reload before saving.")
        config, report = edit_decision(
            state, ProjectConfig.model_validate(project["config"]), value.anchor, value.decision, value.scope
        )
        saved = store.save_project(identity, value.revision, config)
        return {"project": saved, **report}

    @app.post("/api/projects/{identity}/decisions/batch")
    def save_decision_page(identity: str, value: EditDecisionPage):
        project = store.project(identity)
        if value.revision != project["revision"]:
            raise ReaderError("Project changed in another tab. Reload before saving.")
        config, reports = edit_decisions(
            state,
            ProjectConfig.model_validate(project["config"]),
            [(edit.anchor, edit.decision, edit.scope) for edit in value.edits],
        )
        saved = store.save_project(identity, value.revision, config)
        applied = list(dict.fromkeys(anchor for report in reports for anchor in report["applied"]))
        skipped = {
            item["anchor"]: item
            for report in reports
            for item in report["skipped"]
            if item["anchor"] not in applied
        }
        return {"project": saved, "applied": applied, "skipped": list(skipped.values())}

    @app.post("/api/projects/{identity}/builds", status_code=202)
    def queue_build(identity: str):
        project = store.project(identity)
        return store.queue("build", project["config"], identity, project["revision"])

    @app.post("/api/projects/{identity}/data", status_code=202)
    def queue_data(identity: str):
        project = store.project(identity)
        return store.queue("data", project["config"], identity, project["revision"])

    @app.post("/api/projects/{identity}/transforms/data-to-tex", status_code=202)
    def queue_data_to_tex(identity: str, value: UploadData):
        store.project(identity)
        document = load_reader_data(value.data)
        return store.queue_file(
            "data-to-tex", canonical_json(document.json()), identity, config=document.config
        )

    @app.post("/api/projects/{identity}/transforms/tex-to-pdf", status_code=202)
    def queue_tex_to_pdf(identity: str, value: UploadTex):
        store.project(identity)
        return store.queue_file("tex-to-pdf", validate_tex(value.tex), identity, config={"font": value.font})

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
        diagnostic = job["status"] in {"failed", "interrupted"} and name in {
            "reader.log",
            "reader.console.log",
            "measure.log",
            "measure.console.log",
        }
        exported = job["status"] in {"succeeded", "failed"} and name in (job["result"] or {}).get(
            "artifacts", []
        )
        if not (diagnostic or exported):
            raise HTTPException(404, "Artifact not available")
        path = state / "builds" / job["id"] / name
        if path.resolve().parent != (state / "builds" / job["id"]).resolve() or not path.is_file():
            raise HTTPException(404, "Artifact not available")
        return FileResponse(
            path,
            filename=name if download else None,
            media_type="application/pdf" if name.endswith(".pdf") else "text/plain" if diagnostic else None,
        )

    return app
