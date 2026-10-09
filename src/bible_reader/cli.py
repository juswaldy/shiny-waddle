"""Local application and batch workflows."""

import argparse
import json
import os
import signal
import threading
import tomllib
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from .models import ProjectConfig, ReaderError
from .service import build, doctor, inspect_project, write_json
from .sources import catalog, import_sources


def load_config(path: Path | None, passage=None):
    if path:
        data = tomllib.loads(path.read_text()) if path.suffix == ".toml" else json.loads(path.read_text())
    else:
        data = ProjectConfig().model_dump()
    if passage:
        data["passage"] = passage
    return ProjectConfig.model_validate(data)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Original-language Bible reader — sources, lexical review, LaTeX, PDF"
    )
    parser.add_argument("--state", type=Path, default=Path(os.environ.get("READER_STATE", ".reader")))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check TeX, fonts, and verified sources")
    init = commands.add_parser("init", help="Write a default project JSON file")
    init.add_argument("--project", type=Path, default=Path("reader.json"))
    sources = commands.add_parser("sources", help="Install or list pinned source artifacts")
    source_commands = sources.add_subparsers(dest="source_command", required=True)
    source_commands.add_parser("list")
    imp = source_commands.add_parser("import")
    imp.add_argument("--book", choices=list(catalog()["books"]), default="Prov")
    imp.add_argument("--all", action="store_true")
    for name in ("inspect", "align", "build"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--project", type=Path)
        cmd.add_argument("--passage")
        if name == "build":
            cmd.add_argument("--output", type=Path)
            cmd.add_argument("--emit", choices=["pdf", "tex"], default="pdf")
        else:
            cmd.add_argument("--report", type=Path)
    serve = commands.add_parser("serve", help="Open the local browser application")
    serve.add_argument("--host", choices=["127.0.0.1", "localhost"], default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    worker = commands.add_parser("worker", help=argparse.SUPPRESS)
    worker.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    state = args.state.resolve()
    try:
        if args.command == "doctor":
            result = doctor(state)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ready"] else 2
        if args.command == "init":
            if args.project.exists():
                raise ReaderError("Project file already exists")
            write_json(args.project, ProjectConfig().model_dump())
            print(f"Created {args.project}")
        elif args.command == "sources":
            if args.source_command == "list":
                info = catalog()
                print(
                    json.dumps(
                        {
                            "books": list(info["books"]),
                            "text_revision": info["oshb_revision"],
                            "lexicon_revision": info["step_revision"],
                        },
                        indent=2,
                    )
                )
            else:
                for book in catalog()["books"] if args.all else [args.book]:
                    print(json.dumps(import_sources(state, book, print), ensure_ascii=False))
        elif args.command in {"inspect", "align", "build"}:
            config = load_config(args.project, args.passage)
            if args.command == "build":
                output = args.output or Path("build") / datetime.now().strftime("reader-%Y%m%d-%H%M%S-%f")
                result = build(state, config, output, print, emit=args.emit)
            else:
                result = inspect_project(state, config)
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    write_json(args.report, result)
                    print(f"Wrote {args.report}")
                    return 0
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "serve":
            import uvicorn

            from .web.app import create_app

            print(f"Reader: http://{args.host}:{args.port}", flush=True)
            uvicorn.run(create_app(state), host=args.host, port=args.port)
        elif args.command == "worker":
            from .jobs import run_worker

            stopped = threading.Event()
            signal.signal(signal.SIGTERM, lambda *_: stopped.set())
            signal.signal(signal.SIGINT, lambda *_: stopped.set())
            run_worker(state, once=args.once, stopped=stopped.is_set)
    except (ReaderError, ValidationError, OSError, ValueError) as error:
        parser.exit(1, f"bible-reader: {error}\n")
    return 0
