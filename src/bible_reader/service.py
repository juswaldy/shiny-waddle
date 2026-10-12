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

from .editorial import build_document, require_resolved
from .models import ProjectConfig, ReaderError, digest
from .sources import catalog
from .tex import Compiler, engine_path, final_tex, font_path, paginate, verify_pdf


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


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
            ):
                probe = subprocess.run([kpse, name], capture_output=True, text=True, timeout=10)
                result["packages"][name] = probe.returncode == 0
    except ReaderError as error:
        result["engine_error"] = str(error)
    for font in ("Ezra SIL", "SBL Hebrew"):
        try:
            result["fonts"][font] = str(font_path(font))
        except ReaderError:
            result["fonts"][font] = None
    info = catalog()
    for code, book in info["books"].items():
        path = state / "raw" / f"{code}.xml"
        installed = path.is_file()
        verified = installed and hashlib.sha256(path.read_bytes()).hexdigest() == book["sha256"]
        result["sources"].append(
            {"book": code, "title": book["title"], "installed": installed, "verified": verified}
        )
    lex = state / "raw/TBESH.txt"
    result["lexicon"] = (
        lex.is_file() and hashlib.sha256(lex.read_bytes()).hexdigest() == info["lexicon"]["sha256"]
    )
    result["ready"] = bool(
        result["engine"]
        and result["packages"]
        and all(result["packages"].values())
        and any(result["fonts"].values())
        and result["lexicon"]
        and any(s["verified"] for s in result["sources"])
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
):
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ReaderError("Output directory is not empty. Choose a new build directory.")
    output.mkdir(parents=True, exist_ok=True)
    progress("Aligning source text and lexical helps")
    document = build_document(state, config)
    write_json(output / "config.resolved.json", config.model_dump())
    write_json(output / "reader.v2.json", document.json())
    write_json(output / "alignment-report.json", document.review)
    write_json(output / "sources.lock.json", document.sources)
    write_json(output / "note-registry.json", document.registry)
    require_resolved(document)
    compiler = Compiler(output, config.layout.hebrew_font, cancelled)
    plans = paginate(document, compiler, progress)
    write_json(output / "page-plan.json", plans)
    text = final_tex(document, plans)
    (output / "reader.tex").write_text(text, encoding="utf-8")
    checks = {
        "reader_pages": len(plans),
        "verse_count": len(document.verses),
        "help_count": len(document.helps),
    }
    if emit == "pdf":
        progress("Compiling and checking the PDF")
        log = compiler.compile("reader", text, passes=2)
        checks = verify_pdf(output / "reader.pdf", plans, document, log)
    notices = "\n\n".join(
        document.sources["attributions"] + document.sources["transformations"] + document.warnings
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
    if config.layout.hebrew_font == "Ezra SIL":
        (output / "Ezra-LICENSE.txt").write_bytes(
            files("bible_reader").joinpath("resources/Ezra-LICENSE.txt").read_bytes()
        )
        artifacts += ["reader-hebrew.ttf", "Ezra-LICENSE.txt"]
        font_instructions = "The unmodified Ezra SIL font is included under its accompanying license."
    else:
        font_instructions = "SBL Hebrew is not redistributed. Obtain it under its own terms and copy the matching font to reader-hebrew.ttf before recompiling."
    (output / "BUILD.txt").write_text(
        "Rebuild this edition offline with XeLaTeX, fontspec, xcolor, polyglossia, bidi, hyperref, geometry, and Latin Modern.\n"
        "Run twice from this directory: xelatex -no-shell-escape -halt-on-error reader.tex\n"
        + font_instructions
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
        "font": config.layout.hebrew_font,
        "font_sha256": compiler.font_hash,
        "checks": checks,
        "artifacts": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in artifacts},
    }
    write_json(output / "manifest.json", manifest)
    artifacts.append("manifest.json")
    with zipfile.ZipFile(output / "reader-bundle.zip", "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in artifacts:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            bundle.writestr(entry, (output / name).read_bytes())
    artifacts.append("reader-bundle.zip")
    progress("Ready")
    return {**checks, "artifacts": artifacts, "output": str(output), "config_hash": manifest["config_hash"]}
