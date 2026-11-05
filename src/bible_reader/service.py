"""Application use cases shared by the CLI and local web worker."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import zipfile
from collections import Counter
from importlib.resources import files
from pathlib import Path

from .citations import citation_needs_greek, citation_notes
from .data_files import load_reader_data, validate_tex
from .editorial import READY_HELP_STATUSES, build_document, require_resolved
from .models import ProjectConfig, ReaderError, digest
from .sources import book_artifact, catalog, read_verified
from .tex import (
    Compiler,
    engine_path,
    final_tex,
    font_path,
    paginate,
    preamble,
    verify_compilation,
    verify_pdf,
)


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def prepare_output(output: Path) -> Path:
    output = output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ReaderError("Output directory is not empty. Choose a new build directory.")
    output.mkdir(parents=True, exist_ok=True)
    return output


def bundle_artifacts(output: Path, artifacts: list[str]):
    with zipfile.ZipFile(output / "reader-bundle.zip", "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in artifacts:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            bundle.writestr(entry, (output / name).read_bytes())
    artifacts.append("reader-bundle.zip")


def check_pdf(output: Path, log: str, *, document=None, plans=None):
    """Retain completed output and diagnostics even when PDF validation fails."""
    errors = []
    try:
        checks = (
            verify_compilation(output / "reader.pdf", log, errors=errors)
            if document is None
            else verify_pdf(output / "reader.pdf", plans, document, log, errors=errors)
        )
    except ReaderError as error:
        errors.append(str(error))
        checks = {"validation_completed": False}
    return {**checks, "errors": errors}


def build_from_data(
    state: Path, value: dict, output: Path, progress=lambda _: None, cancelled=lambda: False, *, emit="tex"
):
    document = load_reader_data(value)
    return build(
        state,
        ProjectConfig.model_validate(document.config),
        output,
        progress,
        cancelled,
        emit=emit,
        document=document,
    )


def compile_tex(
    text: str, output: Path, progress=lambda _: None, cancelled=lambda: False, *, font="Ezra SIL"
):
    text = validate_tex(text)
    output = prepare_output(output)
    progress("Compiling uploaded TeX")
    compiler = Compiler(output, font, cancelled, greek=True)
    log = compiler.compile("reader", text, passes=2)
    checks = check_pdf(output, log)
    write_json(output / "layout-diagnostics.json", checks)
    artifacts = [
        "reader.tex",
        "reader.pdf",
        "reader.log",
        "layout-diagnostics.json",
        "reader-greek.ttf",
        "GentiumPlus-LICENSE.txt",
    ]
    (output / "GentiumPlus-LICENSE.txt").write_bytes(
        files("bible_reader").joinpath("resources/GentiumPlus-LICENSE.txt").read_bytes()
    )
    if font == "Ezra SIL":
        (output / "Ezra-LICENSE.txt").write_bytes(
            files("bible_reader").joinpath("resources/Ezra-LICENSE.txt").read_bytes()
        )
        artifacts += ["reader-hebrew.ttf", "Ezra-LICENSE.txt"]
    manifest = {
        "schema_version": 1,
        "stage": "tex-to-pdf",
        "checks": checks,
        "engine": compiler.environment,
        "engine_sha256": hashlib.sha256(Path(compiler.engine).read_bytes()).hexdigest(),
        "font_sha256": compiler.font_hash,
        "greek_font_sha256": compiler.greek_font_hash,
        "artifacts": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in artifacts},
    }
    write_json(output / "manifest.json", manifest)
    artifacts.append("manifest.json")
    bundle_artifacts(output, artifacts)
    progress("Completed with errors" if checks["errors"] else "Ready")
    return {**checks, "stage": "tex-to-pdf", "artifacts": artifacts, "output": str(output)}


def doctor(state: Path):
    result = {"engine": None, "fonts": {}, "packages": {}, "sources": [], "ready": False}
    try:
        result["engine"] = engine_path()
        kpse = str(Path(result["engine"]).parent / "kpsewhich")
        if not Path(kpse).exists():
            kpse = shutil.which("kpsewhich")
        if kpse:
            for name in (
                "fontspec.sty",
                "xcolor.sty",
                "polyglossia.sty",
                "bidi.sty",
                "hyperref.sty",
                "geometry.sty",
                "multicol.sty",
            ):
                probe = subprocess.run([kpse, name], capture_output=True, text=True, timeout=10)
                result["packages"][name] = probe.returncode == 0
    except ReaderError as error:
        result["engine_error"] = str(error)
    for font in ("Ezra SIL", "SBL Hebrew", "Gentium Plus"):
        try:
            result["fonts"][font] = str(font_path(font))
        except ReaderError:
            result["fonts"][font] = None
    info = catalog()
    verified_artifacts = {}

    def verified_asset(path, expected):
        key = (path, expected)
        if key not in verified_artifacts:
            verified_artifacts[key] = (
                path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected
            )
        return verified_artifacts[key]

    for code, book in info["books"].items():
        path, asset = book_artifact(state, code)
        installed = path.is_file()
        verified = verified_asset(path, asset["sha256"])
        result["sources"].append(
            {
                "book": code,
                "title": book["title"],
                "language": book.get("language", "hbo"),
                "source": book.get("source", "oshb"),
                "installed": installed,
                "verified": verified,
            }
        )
    lex = state / "raw/TBESH.txt"
    result["lexicon"] = verified_asset(lex, info["lexicon"]["sha256"])
    greek_lexicon = state / "raw/greek/TBESG.txt"
    result["greek_lexicon"] = verified_asset(greek_lexicon, info["greek"]["lexicon"]["sha256"])
    result["greek_crosswalk"] = all(
        verified_asset(state / "raw/greek" / asset["filename"], asset["sha256"])
        for asset in info["greek"]["crosswalk"]["assets"]
    )
    result["ready"] = bool(
        result["engine"]
        and result["packages"]
        and all(result["packages"].values())
        and any(result["fonts"].values())
        and any(
            s["verified"]
            and (
                result["greek_lexicon"]
                and result["fonts"]["Gentium Plus"]
                and (s["source"] != "sblgnt" or result["greek_crosswalk"])
                if s["language"] == "grc"
                else result["lexicon"]
            )
            for s in result["sources"]
        )
    )
    return result


def inspect_project(state: Path, config: ProjectConfig):
    document = build_document(state, config)
    counts = Counter(r["status"] if r["selected"] else "excluded" for r in document.review)
    return {
        "rows": document.review,
        "verses": document.verses,
        "coverage": dict(counts),
        "verse_count": len(document.verses),
        "help_count": len(document.helps),
        "appendix_entries": len(document.lexicon_appendix),
        "warnings": document.warnings,
        "config_hash": digest(config.model_dump()),
    }


def build(
    state: Path,
    config: ProjectConfig,
    output: Path,
    progress=lambda _: None,
    cancelled=lambda: False,
    *,
    emit="pdf",
    document=None,
):
    if emit not in {"data", "tex", "pdf"}:
        raise ReaderError("Choose data, tex, or pdf output")
    output = prepare_output(output)
    if document is None:
        progress("Aligning source text and lexical helps")
        document = build_document(state, config)
    else:
        progress("Loading saved reader data")
    # Embed exact source notices so subsequent transforms need no raw downloads.
    for asset in document.sources.get("notices", {}).values():
        name = asset["filename"]
        if Path(name).name != name or name in {"reader.tex", "reader.pdf", "manifest.json"}:
            raise ReaderError("Invalid source notice filename")
        content = document.source_notices.get(name)
        if content is None:
            content = read_verified(state / "raw/greek" / name, asset["sha256"]).decode("utf-8")
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != asset["sha256"]:
            raise ReaderError(f"Source notice checksum mismatch: {name}")
        document.source_notices[name] = content
    write_json(output / "config.resolved.json", config.model_dump())
    write_json(output / "reader.v2.json", document.json())
    write_json(output / "alignment-report.json", document.review)
    write_json(output / "sources.lock.json", document.sources)
    write_json(output / "note-registry.json", document.registry)
    if emit == "data":
        checks = {
            "stage": "source-to-data",
            "verse_count": len(document.verses),
            "help_count": len(document.helps),
            "unresolved_helps": sum(
                r["selected"] and r["status"] not in READY_HELP_STATUSES for r in document.review
            ),
        }
        artifacts = [
            "config.resolved.json",
            "reader.v2.json",
            "alignment-report.json",
            "sources.lock.json",
            "note-registry.json",
        ]
        write_json(
            output / "manifest.json",
            {
                "schema_version": 1,
                "stage": "source-to-data",
                "config_hash": digest(config.model_dump()),
                "checks": checks,
                "artifacts": {
                    name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in artifacts
                },
            },
        )
        artifacts.append("manifest.json")
        bundle_artifacts(output, artifacts)
        progress("Ready")
        return {
            **checks,
            "artifacts": artifacts,
            "output": str(output),
            "config_hash": digest(config.model_dump()),
        }
    require_resolved(document)
    if any(help["status"] not in READY_HELP_STATUSES for help in document.helps.values()):
        raise ReaderError("Review unresolved selected helps before building")
    greek = document.sources.get("language") == "grc"
    greek_font = greek or citation_needs_greek(document)
    compiler = Compiler(
        output, "Ezra SIL" if greek else config.layout.hebrew_font, cancelled, greek=greek_font
    )
    plans = [] if config.lexicon_only else paginate(document, compiler, progress)
    write_json(output / "page-plan.json", plans)
    text = final_tex(document, plans)
    (output / "reader.tex").write_text(text, encoding="utf-8")
    checks = {
        "reader_pages": len(plans),
        "verse_count": len(document.verses),
        "help_count": len(document.helps),
        "appendix_entries": len(document.lexicon_appendix),
        "lexicon_only": config.lexicon_only,
    }
    if emit == "pdf":
        progress("Compiling and checking the PDF")
        log = compiler.compile("reader", text, passes=2)
        checks.update(check_pdf(output, log, document=document, plans=plans))
    elif config.lexicon_only:
        # A lexicon-only TeX export has no scripture measurements. Load its TeX
        # dependencies once so the source bundle still records their hashes.
        compiler.compile(
            "measure",
            preamble(
                config.layout.model_dump(),
                lexicon_appendix=True,
                language="grc" if greek else "hbo",
                greek_notes=citation_needs_greek(document),
            )
            + r"\end{document}",
        )
    notices = "\n\n".join(
        document.sources["attributions"]
        + document.sources["transformations"]
        + document.warnings
        + citation_notes(document)
    )
    (output / "credits.txt").write_text(notices + "\n", encoding="utf-8")
    write_json(output / "layout-diagnostics.json", checks)
    artifacts = [
        "config.resolved.json",
        "reader.v2.json",
        "alignment-report.json",
        "sources.lock.json",
        "note-registry.json",
        "page-plan.json",
        "reader.tex",
        "credits.txt",
        "layout-diagnostics.json",
    ]
    if greek_font:
        (output / "GentiumPlus-LICENSE.txt").write_bytes(
            files("bible_reader").joinpath("resources/GentiumPlus-LICENSE.txt").read_bytes()
        )
        artifacts += ["reader-greek.ttf", "GentiumPlus-LICENSE.txt"]
    if greek:
        # Include the exact source notices in addition to the printed credits.
        for asset in document.sources["notices"].values():
            name = asset["filename"]
            (output / name).write_text(document.source_notices[name], encoding="utf-8")
            artifacts.append(name)
    if config.lexicon_appendix or config.lexicon_only:
        write_json(output / "lexicon-appendix.json", document.lexicon_appendix)
        artifacts.append("lexicon-appendix.json")
    if greek or config.layout.hebrew_font == "Ezra SIL":
        (output / "Ezra-LICENSE.txt").write_bytes(
            files("bible_reader").joinpath("resources/Ezra-LICENSE.txt").read_bytes()
        )
        artifacts += ["reader-hebrew.ttf", "Ezra-LICENSE.txt"]
        font_instructions = "The unmodified Ezra SIL font is included under its accompanying license."
    else:
        font_instructions = "SBL Hebrew is not redistributed. Obtain it under its own terms and copy the matching font to reader-hebrew.ttf before recompiling."
    (output / "BUILD.txt").write_text(
        "Rebuild this edition offline with XeLaTeX, fontspec, xcolor, polyglossia, bidi, hyperref, geometry, multicol, and Latin Modern.\n"
        "Run twice from this directory: xelatex -no-shell-escape -halt-on-error reader.tex\n"
        + font_instructions
        + ("\nGentium Plus is included under its accompanying SIL Open Font License." if greek_font else "")
        + "\nSee manifest.json for engine, font, source and application fingerprints.\n",
        encoding="utf-8",
    )
    artifacts.append("BUILD.txt")
    if emit == "pdf":
        artifacts += ["reader.pdf", "reader.log"]
    package = Path(str(files("bible_reader")))
    implementation = {
        str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(package.rglob("*"))
        if p.is_file() and p.suffix in {".py", ".tex", ".json"}
    }
    tex_inputs = {}
    recording = output / ("reader.fls" if emit == "pdf" else "measure.fls")
    for line in recording.read_text().splitlines():
        if line.startswith("INPUT "):
            dependency = Path(line[6:])
            if dependency.is_absolute() and dependency.is_file() and not dependency.is_relative_to(output):
                tex_inputs[dependency.name] = hashlib.sha256(dependency.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "app_version": "0.2.0",
        "config_hash": digest(config.model_dump()),
        "implementation": implementation,
        "implementation_hash": digest(implementation),
        "engine": compiler.environment,
        "engine_sha256": hashlib.sha256(Path(compiler.engine).read_bytes()).hexdigest(),
        "tex_inputs": tex_inputs,
        "font": config.layout.greek_font if greek else config.layout.hebrew_font,
        "font_sha256": compiler.greek_font_hash if greek else compiler.font_hash,
        "greek_font": config.layout.greek_font if greek_font else None,
        "greek_font_sha256": compiler.greek_font_hash,
        "checks": checks,
        "artifacts": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in artifacts},
    }
    write_json(output / "manifest.json", manifest)
    artifacts.append("manifest.json")
    bundle_artifacts(output, artifacts)
    progress("Completed with errors" if checks.get("errors") else "Ready")
    return {**checks, "artifacts": artifacts, "output": str(output), "config_hash": manifest["config_hash"]}
