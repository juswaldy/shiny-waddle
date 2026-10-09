import hashlib
import json
import zipfile

import pytest
from pypdf import PdfReader

from bible_reader.editorial import build_document
from bible_reader.models import Cancelled, Decision, ProjectConfig, ReaderError
from bible_reader.service import build
from bible_reader.tex import Compiler, paginate

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("paper,pages", [("reference", 1), ("a5", 2), ("a4", 1), ("letter", 1)])
def test_real_pdf_pagination_links_fonts_and_portable_bundle(
    source_state, tmp_path, tex_available, paper, pages
):
    config = ProjectConfig(layout={"paper": paper, "first_folio": 1329})
    output = tmp_path / "edition"
    result = build(source_state, config, output)
    assert result["reader_pages"] == pages
    assert result["fonts_embedded"]
    assert result["pdf_marker_destinations"] == "verified"
    plans = json.loads((output / "page-plan.json").read_text())
    assert [p["folio"] for p in plans] == list(range(1329, 1329 + pages))
    assert sum(len(p["references"]) for p in plans) == 17
    assert all(p["text_height_sp"] + p["notes_height_sp"] <= p["budget_sp"] for p in plans)
    assert "Sources and edition" in PdfReader(output / "reader.pdf").pages[-1].extract_text()
    manifest = json.loads((output / "manifest.json").read_text())
    for name, expected in manifest["artifacts"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected
    with zipfile.ZipFile(output / "reader-bundle.zip") as bundle:
        assert "reader-hebrew.ttf" in bundle.namelist()
        assert "Ezra-LICENSE.txt" in bundle.namelist()
        if paper == "reference":
            extracted = tmp_path / "extracted"
            bundle.extractall(extracted)
            compiler = Compiler(extracted, "Ezra SIL")
            compiler.compile("reader", (extracted / "reader.tex").read_text(), passes=2)
            assert len(PdfReader(extracted / "reader.pdf").pages) == 2


def test_reproducible_reader_document_and_layout(source_state, tmp_path, tex_available):
    config = ProjectConfig()
    first, second = tmp_path / "one", tmp_path / "two"
    build(source_state, config, first)
    build(source_state, config, second)
    for name in ["reader.v2.json", "page-plan.json", "note-registry.json", "reader.tex", "sources.lock.json"]:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_editorial_tex_is_escaped_and_long_gloss_paginated(source_state, tmp_path, tex_available):
    gloss = r"Test editorial wording: 50% & $ # _ {x} ~ ^ \input{private}. " + "Longer review wording. " * 20
    config = ProjectConfig(decisions={"20qg1:0": Decision(gloss=gloss)}, layout={"paper": "a5"})
    output = tmp_path / "edited"
    result = build(source_state, config, output)
    assert result["reader_pages"] >= 2
    latex = (output / "reader.tex").read_text()
    assert r"\input{private}" not in latex
    assert r"\textbackslash{}input\{private\}" in latex


def test_accents_and_single_verse_chapter_opening(source_state, tmp_path, tex_available):
    config = ProjectConfig(passage="2:1", cantillation="preserve")
    result = build(source_state, config, tmp_path / "single")
    assert result["verse_count"] == 1


def test_compiler_cancellation_and_overflow_fail_explicitly(source_state, tmp_path, tex_available):
    compiler = Compiler(tmp_path / "cancel", "Ezra SIL", cancelled=lambda: True)
    with pytest.raises(Cancelled):
        compiler.compile("reader", "")
    config = ProjectConfig(layout={"paper": "a5", "body_pt": 26.0, "leading_pt": 38.0, "notes_pt": 14.0})
    document = build_document(source_state, config)
    for help_record in document.helps.values():
        help_record["gloss"] = "Deliberately excessive fixture wording. " * 100
    with pytest.raises(ReaderError, match="overflow"):
        paginate(document, Compiler(tmp_path / "overflow", "Ezra SIL"))


def test_build_does_not_overwrite_existing_artifacts(source_state, tmp_path, tex_available):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "important").write_text("keep")
    with pytest.raises(ReaderError, match="not empty"):
        build(source_state, ProjectConfig(), output)
    assert (output / "important").read_text() == "keep"
