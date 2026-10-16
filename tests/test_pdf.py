import hashlib
import json
import zipfile

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader

from bible_reader.editorial import build_document
from bible_reader.models import Cancelled, Decision, ProjectConfig, ReaderError
from bible_reader.service import build
from bible_reader.tex import Compiler, final_tex, paginate, verify_pdf
from bible_reader.word_classes import word_color

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("verse_layout", ["continuous", "verse-per-line"])
def test_pdf_word_palette_and_overrides_only_paint_scripture(
    source_state, tmp_path, tex_available, verse_layout
):
    config = ProjectConfig(
        layout={
            "word_colors": "word-class",
            "word_color_overrides": {"noun": "#123ABC", "particle": "auto"},
            "verse_layout": verse_layout,
        }
    )
    output = tmp_path / "colors"
    result = build(source_state, config, output)
    assert result["reader_pages"] == 2
    assert result["fonts_embedded"]
    assert result["pdf_marker_destinations"] == "verified"
    document = build_document(source_state, config)
    expected = {
        tuple(round(int(color[index : index + 2], 16) / 255, 3) for index in (1, 3, 5))
        for verse in document.verses
        for token in verse["tokens"]
        if (color := word_color(token["word_class"], config.layout.model_dump()))
    }
    assert word_color("name", config.layout.model_dump()) is not None
    painted = set()
    pdf = PdfReader(output / "reader.pdf")
    for page in pdf.pages:
        fill, font, size = (0, 0, 0), None, None
        stack = []
        for operands, operator in page.get_contents().operations:
            if operator == b"q":
                stack.append((fill, font, size))
            elif operator == b"Q":
                fill, font, size = stack.pop()
            elif operator == b"rg":
                fill = tuple(float(value) for value in operands)
            elif operator == b"g":
                fill = (float(operands[0]),) * 3
            elif operator == b"Tf":
                font, size = operands
            elif operator in {b"Tj", b"TJ"} and fill != (0, 0, 0):
                painted.add(fill)
                assert float(size) == pytest.approx(config.layout.body_pt * 72 / 72.27, abs=0.01)
                assert "Ezra" in page["/Resources"]["/Font"][font]["/BaseFont"]
    assert painted == expected


@pytest.mark.parametrize(
    "paper,continuous_pages,verse_pages,width,height",
    [
        ("reader", 2, 2, 140, 216),
        ("reference", 1, 1, 180, 281),
        ("a5", 2, 2, 148, 210),
        ("a4", 1, 1, 210, 297),
        ("letter", 1, 1, 215.9, 279.4),
        # Measuring the full page reclaims enough space to avoid a second
        # continuous reader page at this size (previously two in both modes).
        ("custom", 1, 2, 160.5, 230.25),
    ],
)
@pytest.mark.parametrize("verse_layout", ["continuous", "verse-per-line"])
def test_real_pdf_pagination_links_fonts_and_portable_bundle(
    source_state, tmp_path, tex_available, paper, continuous_pages, verse_pages, width, height, verse_layout
):
    pages = continuous_pages if verse_layout == "continuous" else verse_pages
    layout = {"paper": paper, "first_folio": 1329, "verse_layout": verse_layout}
    if paper == "custom":
        layout.update(paper_width_mm=width, paper_height_mm=height)
    config = ProjectConfig(layout=layout)
    output = tmp_path / "edition"
    result = build(source_state, config, output)
    assert result["reader_pages"] == pages
    assert result["fonts_embedded"]
    assert result["pdf_marker_destinations"] == "verified"
    pdf = PdfReader(output / "reader.pdf")
    for page in pdf.pages:
        assert float(page.mediabox.width) * 25.4 / 72 == pytest.approx(width, abs=0.01)
        assert float(page.mediabox.height) * 25.4 / 72 == pytest.approx(height, abs=0.01)
    plans = json.loads((output / "page-plan.json").read_text())
    assert [p["folio"] for p in plans] == list(range(1329, 1329 + pages))
    assert sum(len(p["references"]) for p in plans) == 17
    assert all(p["text_height_sp"] + p["notes_height_sp"] <= p["budget_sp"] for p in plans)
    assert all(p["page_height_sp"] <= p["usable_height_sp"] for p in plans)
    if paper == "reference":
        # Inspect actual verse-digit baselines to distinguish the two layouts.
        digits = {}

        def collect_digits(text, cm, tm, font, size):
            if 10.5 < size < 11.5 and text.strip() in {"29", "30"}:
                digits[text.strip()] = (cm[4] + tm[4], cm[5] + tm[5])

        PdfReader(output / "reader.pdf").pages[0].extract_text(visitor_text=collect_digits)
        assert set(digits) == {"29", "30"}
        if verse_layout == "continuous":
            assert digits["29"][1] == pytest.approx(digits["30"][1], abs=0.1)
            assert digits["30"][0] < digits["29"][0]
        else:
            assert digits["30"][1] < digits["29"][1] - 10
            assert digits["29"][0] == pytest.approx(digits["30"][0], abs=0.1)
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


@pytest.mark.parametrize("verse_layout", ["continuous", "verse-per-line"])
def test_reproducible_reader_document_and_layout(source_state, tmp_path, tex_available, verse_layout):
    config = ProjectConfig(layout={"verse_layout": verse_layout})
    first, second = tmp_path / "one", tmp_path / "two"
    build(source_state, config, first)
    build(source_state, config, second)
    for name in ["reader.v2.json", "page-plan.json", "note-registry.json", "reader.tex", "sources.lock.json"]:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


@pytest.mark.parametrize("first_folio,notes_pt", [(2, 9.0), (1329, 12.0)])
def test_pdf_running_title_language_and_smaller_uppercase_stems(
    source_state, tmp_path, tex_available, first_folio, notes_pt
):
    config = ProjectConfig(layout={"first_folio": first_folio, "notes_pt": notes_pt})
    output = tmp_path / "formatting"
    result = build(source_state, config, output)
    assert result["reader_pages"] >= 2
    document = json.loads((output / "reader.v2.json").read_text())
    plans = json.loads((output / "page-plan.json").read_text())
    pdf = PdfReader(output / "reader.pdf")
    rendered_pdf = pdfium.PdfDocument(output / "reader.pdf")
    title_bounds = []
    # PDF sizes use 72 points/inch; TeX sizes use 72.27 points/inch.
    pdf_pt_per_tex_pt = 72 / 72.27
    for page, plan in zip(pdf.pages[: len(plans)], plans, strict=True):
        headings, stems = [], []
        expected_stems = [
            document["helps"][identity]["stem"].upper()
            for identity in plan["help_ids"]
            if document["helps"][identity]["stem"]
        ]

        def collect_formatting(
            text,
            cm,
            tm,
            font,
            size,
            headings=headings,
            stems=stems,
            expected_stems=expected_stems,
            header_min_y=float(page.mediabox.top) - 60,
            heading_size=18.0 * pdf_pt_per_tex_pt,
        ):
            if not text.strip():
                return
            baseline = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
            if size == pytest.approx(heading_size, abs=0.01) and baseline > header_min_y:
                headings.append((text.strip(), font["/BaseFont"]))
            if text.strip() in expected_stems:
                stems.append(text.strip())
                assert size == pytest.approx(notes_pt * 0.5 * pdf_pt_per_tex_pt, abs=0.01)

        page.extract_text(visitor_text=collect_formatting)
        assert len(headings) == 1
        title, font_name = headings[0]
        if plan["folio"] % 2:
            assert "Ezra" in font_name
            assert all("\u0590" <= char <= "\u05ff" for char in title)
        else:
            assert title == "Proverbs"
            assert "LMRomanCaps" in font_name
        assert sorted(stems) == sorted(expected_stems)
        rendered_page = rendered_pdf[plan["page"] - 1]
        text_page = rendered_page.get_textpage()
        width, height = rendered_page.get_size()
        title_chars = [
            text_page.get_charbox(index)
            for index in range(text_page.count_chars())
            if text_page.get_text_range(index, 1).strip()
            and text_page.get_charbox(index)[1] > height - 60
            and width * 0.3 < text_page.get_charbox(index)[0] < width * 0.7
        ]
        bottom = min(box[1] for box in title_chars)
        top = max(box[3] for box in title_chars)
        title_bounds.append((bottom, top))
        if not plan["folio"] % 2:
            initial_height = title_chars[0][3] - title_chars[0][1]
            assert all(initial_height > box[3] - box[1] + 1 for box in title_chars[1:])
        text_page.close()
        rendered_page.close()
    rendered_pdf.close()
    # Compare actual glyph bounds across odd/even pages, including the baseline.
    for bottom, top in title_bounds[1:]:
        assert bottom == pytest.approx(title_bounds[0][0], abs=0.2)
        assert top == pytest.approx(title_bounds[0][1], abs=0.2)


def test_editorial_tex_is_escaped_and_long_gloss_paginated(source_state, tmp_path, tex_available):
    gloss = r"Test editorial wording: 50% & $ # _ {x} ~ ^ \input{private}. " + "Longer review wording. " * 20
    config = ProjectConfig(decisions={"20qg1:0": Decision(gloss=gloss)}, layout={"paper": "a5"})
    output = tmp_path / "edited"
    result = build(source_state, config, output)
    assert result["reader_pages"] >= 2
    latex = (output / "reader.tex").read_text()
    assert r"\input{private}" not in latex
    assert r"\textbackslash{}input\{private\}" in latex


@pytest.mark.parametrize("verse_layout", ["continuous", "verse-per-line"])
def test_accents_and_single_verse_chapter_opening(source_state, tmp_path, tex_available, verse_layout):
    config = ProjectConfig(passage="2:1", cantillation="preserve", layout={"verse_layout": verse_layout})
    result = build(source_state, config, tmp_path / "single")
    assert result["verse_count"] == 1


@pytest.mark.parametrize("policy", ["consonants-only", "consonants", "consonants-maqqef-sof-pasuq"])
@pytest.mark.parametrize("verse_layout", ["continuous", "verse-per-line"])
def test_consonant_policies_build_verified_pdf(source_state, tmp_path, tex_available, policy, verse_layout):
    config = ProjectConfig(cantillation=policy, layout={"verse_layout": verse_layout})
    output = tmp_path / "consonants"
    result = build(source_state, config, output)
    assert result["verse_count"] == 17
    assert result["help_count"] == 37
    assert result["reader_pages"] >= 2
    assert result["fonts_embedded"]
    assert result["pdf_marker_destinations"] == "verified"
    document = json.loads((output / "reader.v2.json").read_text())
    assert document["config"]["cantillation"] == policy
    first = document["verses"][0]["tokens"]
    maqqef = "" if policy == "consonants-only" else "־"
    assert [t["surface"] for t in first[:4]] == ["תחת", "כי", maqqef, "שנאו"]
    assert first[-1]["surface"] == ("׃" if policy == "consonants-maqqef-sof-pasuq" else "")
    assert first[1]["source_surface"] == "כִּי"


def test_many_short_run_in_verses_fill_a_page(source_state, tmp_path, tex_available):
    # Synthetic layout stress case derived from one fixture token. This is not
    # source scripture: it checks that the planner has no verse-per-line cap.
    document = build_document(source_state, ProjectConfig(passage="1:29"))
    token = {**document.verses[0]["tokens"][0], "helps": []}
    document.verses = [
        {"reference": f"Prov.1.{number}", "chapter": 1, "verse": number, "tokens": [token]}
        for number in range(2, 62)
    ]
    compiler = Compiler(tmp_path / "short-verses", "Ezra SIL")
    plans = paginate(document, compiler)
    assert len(plans) == 1
    assert len(plans[0]["references"]) == 60
    log = compiler.compile("reader", final_tex(document, plans), passes=2)
    assert verify_pdf(compiler.directory / "reader.pdf", plans, document, log)["verse_count"] == 60


@pytest.mark.parametrize("verse_layout", ["continuous", "verse-per-line"])
def test_large_type_on_a5_wraps_without_overflow(source_state, tmp_path, tex_available, verse_layout):
    config = ProjectConfig(
        layout={"paper": "a5", "verse_layout": verse_layout, "body_pt": 26.0, "leading_pt": 38.0}
    )
    result = build(source_state, config, tmp_path / "large-type")
    assert result["verse_count"] == 17
    assert result["reader_pages"] >= 2
    assert result["pdf_marker_destinations"] == "verified"


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
