import copy
import hashlib
import json
import zipfile

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader

from bible_reader.editorial import build_document
from bible_reader.models import Cancelled, Decision, ProjectConfig, ReaderError
from bible_reader.service import build
from bible_reader.tex import (
    Compiler,
    final_tex,
    measure_candidates,
    page_plan,
    paginate,
    paper_dimensions,
    rebalance_pages,
    split_group,
    split_verse,
    verify_pdf,
)
from bible_reader.word_classes import word_color

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("language", ["hebrew", "greek"])
@pytest.mark.parametrize("verse_layout", ["continuous", "verse-per-line"])
def test_three_digit_chapter_badges_fit_in_both_languages_and_layouts(
    source_state, request, tmp_path, tex_available, language, verse_layout
):
    greek = language == "greek"
    state = request.getfixturevalue("greek_state") if greek else source_state
    config = ProjectConfig(
        book="John" if greek else "Prov",
        passage="1:1-3" if greek else "2:1-3",
        selection="all" if greek else "reference",
        gloss_selection="first-entry",
        layout={"verse_layout": verse_layout},
    )
    document = build_document(state, config)
    # Synthetic chapter numbering exercises the badge without importing new text.
    for verse in document.verses:
        verse["chapter"] = 122
        verse["reference"] = f"{config.book}.122.{verse['verse']}"
    for help in document.helps.values():
        help["chapter"] = 122
    compiler = Compiler(tmp_path / "three-digits", "Ezra SIL", greek=greek)
    plans = paginate(document, compiler)
    log = compiler.compile("reader", final_tex(document, plans), passes=2)
    assert verify_pdf(compiler.directory / "reader.pdf", plans, document, log)["verse_count"] == 3
    pdf = PdfReader(compiler.directory / "reader.pdf")
    assert "122" in pdf.pages[0].extract_text()


@pytest.mark.parametrize("language", ["hbo", "grc"])
@pytest.mark.parametrize("opening", ["short", "two-lines", "long"])
def test_separate_verses_reclaim_chapter_inset_after_two_lines(
    request, tmp_path, tex_available, language, opening
):
    greek = language == "grc"
    state = request.getfixturevalue("greek_state" if greek else "source_state")
    config = ProjectConfig(
        book="John" if greek else "Prov",
        passage="1:1-3" if greek else "2:1-3",
        selection="all",
        gloss_selection="first-entry",
        layout={"verse_layout": "verse-per-line"},
    )
    document = build_document(state, config)
    # Repeating one attributed word isolates line positions and wrapping; these
    # synthetic verses are typography fixtures, not proposed source readings.
    word = max(
        (t for v in document.verses for t in v["tokens"] if t["kind"] == "word"),
        key=lambda t: sum(c.isalpha() for c in t["surface"]),
    )
    word = {**word, "helps": []}
    opening_words = {"short": 1, "two-lines": 6 if greek else 9, "long": 24}[opening]
    for verse, count in zip(document.verses, [opening_words, 24, 1], strict=True):
        verse["tokens"] = [word] * count
    compiler = Compiler(tmp_path / "opening-inset", "Ezra SIL", greek=greek)
    plans = paginate(document, compiler)
    assert len(plans) == 1
    log = compiler.compile("reader", final_tex(document, plans), passes=2)
    assert verify_pdf(compiler.directory / "reader.pdf", plans, document, log)["verse_count"] == 3
    page = PdfReader(compiler.directory / "reader.pdf").pages[0]
    runs, digits = [], {}
    pt = 72 / 72.27

    def collect(text, cm, tm, font, size):
        if not text.strip():
            return
        x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
        y = round(cm[1] * tm[4] + cm[3] * tm[5] + cm[5], 1)
        if size == pytest.approx(11 * pt, abs=0.01) and text.strip() in {"2", "3"}:
            digits[text.strip()] = (x, y)
        family = "GentiumPlus" if greek else "Ezra"
        if (
            family in font["/BaseFont"]
            and size == pytest.approx(config.layout.body_pt * pt, abs=0.01)
            and y < float(page.mediabox.top) - 60
        ):
            runs.append((x, y))

    page.extract_text(visitor_text=collect)
    baselines = sorted({y for _, y in runs}, reverse=True)
    first_verse_lines = sum(y > digits["2"][1] for y in baselines)
    if opening_words == 1:
        assert first_verse_lines == 1
    elif opening == "two-lines":
        assert first_verse_lines == 2
    else:
        assert first_verse_lines > 2
    rendered = pdfium.PdfDocument(compiler.directory / "reader.pdf")
    text_page = rendered[0].get_textpage()
    lines = [[] for _ in baselines]
    for index in range(text_page.count_chars()):
        if text_page.get_text_range(index, 1).isalpha() and pdfium.raw.FPDFText_GetFontSize(
            text_page, index
        ) == pytest.approx(config.layout.body_pt * pt, abs=0.01):
            left, bottom, right, top = text_page.get_charbox(index)
            center = (bottom + top) / 2
            line = min(range(len(baselines)), key=lambda i: abs(baselines[i] - center))
            if abs(baselines[line] - center) < config.layout.leading_pt / 2:
                lines[line].append(left if greek else right)
    edge = min if greek else max
    positions = [edge(line) for line in lines]
    normal = positions[-1]
    inward = 1 if greek else -1
    # Verse 1 sits directly beside the badge, without an empty number gutter.
    assert inward * (positions[0] - normal) == pytest.approx(8 * 72 / 25.4, abs=0.2)
    second_inset_mm = 14 if first_verse_lines == 1 else 8
    assert inward * (positions[1] - normal) == pytest.approx(second_inset_mm * 72 / 25.4, abs=0.2)
    # Every subsequent line, including wrapped verse 2, uses the normal margin.
    assert all(x == pytest.approx(normal, abs=0.2) for x in positions[2:])
    number_inset_mm = 14 if first_verse_lines == 1 else 0
    assert inward * (digits["2"][0] - digits["3"][0]) == pytest.approx(number_inset_mm * 72 / 25.4, abs=0.2)
    assert all(
        a - b < config.layout.leading_pt * pt + 2 for a, b in zip(baselines, baselines[1:], strict=False)
    )
    rendered[0].render(scale=2).to_pil().save(compiler.directory / "proof.png")


@pytest.mark.parametrize("paper,verse_layout", [("reader", "continuous"), ("reference", "verse-per-line")])
def test_lexicon_appendix_is_four_columns_in_hebrew_order_before_credits(
    source_state, tmp_path, tex_available, paper, verse_layout
):
    config = ProjectConfig(
        lexicon_appendix=True, layout={"paper": paper, "verse_layout": verse_layout, "first_folio": 1329}
    )
    output = tmp_path / "appendix"
    result = build(source_state, config, output)
    document = build_document(source_state, config)
    pdf = PdfReader(output / "reader.pdf")
    entries = json.loads((output / "lexicon-appendix.json").read_text())
    assert entries == document.lexicon_appendix
    assert result["appendix_entries"] == len(entries) == 33
    assert result["appendix_pages"] == 1
    assert result["total_pages"] == result["reader_pages"] + 2
    appendix_page = pdf.pages[result["reader_pages"]]
    assert "Proverbs — Lexicon" in appendix_page.extract_text()
    assert "Sources and edition" in pdf.pages[-1].extract_text()
    assert result["pdf_marker_destinations"] == "verified" and result["fonts_embedded"]
    # Inspect actual PDF destinations, not TeX strings: the sorted sequence flows
    # down four separate columns, starting with the leftmost column.
    width, _, margin = paper_dimensions(config.layout.model_dump())
    step = ((width - 2 * margin - 9) / 4 + 3) * 72 / 25.4
    margin_pt = margin * 72 / 25.4
    positions = []
    for entry in entries:
        destination = pdf.named_destinations[f"lexicon-entry-{entry['id']}"]
        assert pdf.get_destination_page_number(destination) == result["reader_pages"]
        column = round((float(destination.left) - margin_pt) / step)
        positions.append((column, float(destination.top)))
    assert {column for column, _ in positions} == {0, 1, 2, 3}
    assert positions == sorted(positions, key=lambda item: (item[0], -item[1]))
    assert max(y for _, y in positions) - min(y for _, y in positions) < 140
    # Check actual typography: each Hebrew headword starts to the left of an
    # English gloss on the same baseline, at the stem labels' half-note size.
    hebrew, english = [], []
    pt = 72 / 72.27

    def collect_entry_runs(text, cm, tm, font, size):
        if not text.strip():
            return
        baseline = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
        x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
        if "Ezra" in font["/BaseFont"] and size == pytest.approx(config.layout.notes_pt * pt, abs=0.01):
            hebrew.append((x, baseline))
        if "LMRoman" in font["/BaseFont"] and size == pytest.approx(
            config.layout.notes_pt * 0.5 * pt, abs=0.01
        ):
            english.append((x, baseline))

    appendix_page.extract_text(visitor_text=collect_entry_runs)
    assert len(hebrew) >= len(entries) and len(english) >= len(entries)
    for x, baseline in hebrew:
        assert any(right > x and abs(other_baseline - baseline) < 0.1 for right, other_baseline in english)
    with zipfile.ZipFile(output / "reader-bundle.zip") as bundle:
        assert json.loads(bundle.read("lexicon-appendix.json")) == entries
    manifest = json.loads((output / "manifest.json").read_text())
    assert "multicol.sty" in manifest["tex_inputs"]
    # Preserve proof images for visual inspection, including the chapter boundary.
    rendered = pdfium.PdfDocument(output / "reader.pdf")
    for page_index in [0, result["reader_pages"]]:
        rendered[page_index].render(scale=2).to_pil().save(output / f"proof-{page_index + 1}.png")


def test_lexicon_appendix_continues_across_pages_and_escapes_edited_text(
    source_state, tmp_path, tex_available
):
    document = build_document(source_state, ProjectConfig(lexicon_appendix=True))
    # Synthetic repetition is a layout stress case, not new source lexicon data.
    base = document.lexicon_appendix[0]
    document.lexicon_appendix = [
        {
            **base,
            "id": f"test-layout-{i}",
            "gloss": f"Synthetic entry {i}: 50% & {{review}}. " + "Longer editorial wording. " * 12,
        }
        for i in range(60)
    ]
    compiler = Compiler(tmp_path / "long-appendix", "Ezra SIL")
    plans = paginate(document, compiler)
    text = final_tex(document, plans)
    log = compiler.compile("reader", text, passes=2)
    result = verify_pdf(compiler.directory / "reader.pdf", plans, document, log)
    assert result["appendix_pages"] > 1
    assert result["appendix_entries"] == 60
    pdf = PdfReader(compiler.directory / "reader.pdf")
    assert "Sources and edition" in pdf.pages[-1].extract_text()
    assert "50% & {review}" in " ".join(
        " ".join(page.extract_text() for page in pdf.pages[len(plans) : -1]).split()
    )
    assert r"50\% \& \{review\}" in text


def test_empty_lexicon_appendix_is_explicit_and_still_precedes_sources(source_state, tmp_path, tex_available):
    config = ProjectConfig(
        lexicon_appendix=True, known_entries=["step:H1847", "step:H3374", "step:H8130"], passage="1:29"
    )
    document = build_document(source_state, config)
    config.decisions = {row["anchor"]: Decision(action="exclude") for row in document.review}
    result = build(source_state, config, tmp_path / "empty-appendix")
    pdf = PdfReader(tmp_path / "empty-appendix/reader.pdf")
    assert result["appendix_pages"] == 1 and result["appendix_entries"] == 0
    assert "No lexical helps selected" in pdf.pages[result["reader_pages"]].extract_text()
    assert "Sources and edition" in pdf.pages[-1].extract_text()


@pytest.mark.parametrize("emit", ["pdf", "tex"])
def test_lexicon_only_skips_scripture_and_keeps_sources_and_exports(
    source_state, tmp_path, tex_available, monkeypatch, emit
):
    config = ProjectConfig(lexicon_only=True)
    assert not config.lexicon_appendix

    def no_scripture_measurements(*_):
        pytest.fail("Lexicon-only builds must not paginate scripture")

    monkeypatch.setattr("bible_reader.service.paginate", no_scripture_measurements)
    output = tmp_path / "lexicon-only"
    result = build(source_state, config, output, emit=emit)
    assert result["reader_pages"] == 0 and result["lexicon_only"]
    assert result["appendix_entries"] == 33
    assert json.loads((output / "page-plan.json").read_text()) == []
    entries = json.loads((output / "lexicon-appendix.json").read_text())
    assert entries == build_document(source_state, config).lexicon_appendix
    manifest = json.loads((output / "manifest.json").read_text())
    assert "multicol.sty" in manifest["tex_inputs"]
    with zipfile.ZipFile(output / "reader-bundle.zip") as bundle:
        assert json.loads(bundle.read("lexicon-appendix.json")) == entries
    if emit == "pdf":
        assert result["total_pages"] == 2 and result["appendix_pages"] == 1
        pdf = PdfReader(output / "reader.pdf")
        assert "Proverbs — Lexicon" in pdf.pages[0].extract_text()
        assert "Sources and edition" in pdf.pages[1].extract_text()
        assert not any(name.startswith("p1-") for name in pdf.named_destinations)
    else:
        assert not (output / "reader.pdf").exists()


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
    assert len({ref for p in plans for ref in p["references"]}) == 17
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


@pytest.mark.parametrize("language", ["hbo", "grc"])
def test_run_in_verse_uses_available_space_and_continues_with_local_helps(
    request, tmp_path, tex_available, language
):
    state = request.getfixturevalue("greek_state" if language == "grc" else "source_state")
    config = (
        ProjectConfig(book="John", passage="1:1-18", selection="all")
        if language == "grc"
        else ProjectConfig()
    )
    document = build_document(state, config)
    # Synthetic repetition tests pagination only; it is not a source passage.
    token = max(
        (t for v in document.verses for t in v["tokens"] if t["helps"]),
        key=lambda t: len(t["surface"]),
    )
    book = config.book
    document.verses = [
        {"reference": f"{book}.1.2", "chapter": 1, "verse": 2, "tokens": [{**token, "helps": []}]},
        {"reference": f"{book}.1.3", "chapter": 1, "verse": 3, "tokens": [token] * 80},
    ]
    compiler = Compiler(tmp_path / "split-verse", "Ezra SIL", greek=language == "grc")
    plans = paginate(document, compiler)
    assert len(plans) >= 2
    assert plans[0]["references"] == [f"{book}.1.2", f"{book}.1.3"]
    assert plans[1]["first"] == f"{book}.1.3"
    assert plans[1]["groups"][0][0]["continued"]
    fragments = [v for p in plans for g in p["groups"] for v in g if v["verse"] == 3]
    assert [t for v in fragments for t in v["tokens"]] == document.verses[1]["tokens"]
    assert all(p["page_height_sp"] <= p["usable_height_sp"] for p in plans)
    log = compiler.compile("reader", final_tex(document, plans), passes=2)
    assert verify_pdf(compiler.directory / "reader.pdf", plans, document, log)["verse_count"] == 2
    pdf = PdfReader(compiler.directory / "reader.pdf")
    digits = {}

    def collect_digits(text, cm, tm, font, size):
        if 10.5 < size < 11.5 and text.strip() in {"2", "3"}:
            digits[text.strip()] = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]

    pdf.pages[0].extract_text(visitor_text=collect_digits)
    assert set(digits) == {"2", "3"}
    assert digits["2"] == pytest.approx(digits["3"], abs=0.1)
    assert all(p["help_ids"] == token["helps"] for p in plans)
    rendered = pdfium.PdfDocument(compiler.directory / "reader.pdf")
    # Notes end at the bottom margin on every page, including sparse endings.
    for page_index, page in enumerate(pdf.pages[: len(plans)], 1):
        baseline = []

        def collect_scripture(text, cm, tm, font, size, baseline=baseline):
            if text.strip() and size == pytest.approx(config.layout.body_pt * 72 / 72.27, abs=0.01):
                baseline.append(cm[1] * tm[4] + cm[3] * tm[5] + cm[5])

        page.extract_text(visitor_text=collect_scripture)
        assert baseline
        # Destinations measure the actual first help baseline beneath the text.
        destination = next(
            dest for name, dest in pdf.named_destinations.items() if name.startswith(f"p{page_index}-")
        )
        extra = (
            (plans[page_index - 1]["usable_height_sp"] - plans[page_index - 1]["page_height_sp"])
            / 65536
            * 72
            / 72.27
        )
        assert 0 < min(baseline) - float(destination.top) - extra < 32
        rendered_page = rendered[page_index - 1]
        rules = []
        for obj in rendered_page.get_objects():
            if obj.type != pdfium.raw.FPDF_PAGEOBJ_PATH:
                continue
            left, bottom, right, top = obj.get_bounds()
            if right - left > rendered_page.get_width() * 0.8 and top - bottom < 1:
                rules.append((bottom + top) / 2)
        lower, upper = sorted(rules)
        text_page = rendered_page.get_textpage()
        body = [
            text_page.get_charbox(index)
            for index in range(text_page.count_chars())
            if text_page.get_text_range(index, 1).strip()
            and lower < text_page.get_charbox(index)[1] < text_page.get_charbox(index)[3] < upper
        ]
        assert 8 < min(box[1] for box in body) - lower - extra < 14
        margin = 10 * 72 / 25.4
        notes = [
            text_page.get_charbox(index)
            for index in range(text_page.count_chars())
            if text_page.get_text_range(index, 1).strip() and text_page.get_charbox(index)[3] < lower
        ]
        assert min(box[1] for box in notes) == pytest.approx(margin, abs=3)
        if page_index < len(plans):
            # A continued paragraph fills both physical edges of its last line.
            last_line = [
                box
                for box in body
                if min(baseline) - config.layout.body_pt * 0.5 < box[1]
                and box[3] < min(baseline) + config.layout.body_pt
            ]
            assert min(box[0] for box in last_line) - margin < 3
            assert rendered_page.get_width() - margin - max(box[2] for box in last_line) < 3
        text_page.close()
        rendered_page.close()
    corrupted = json.loads(json.dumps(plans))
    corrupted[1]["groups"][0][0]["tokens"].pop()
    with pytest.raises(ReaderError, match="source tokens"):
        verify_pdf(compiler.directory / "reader.pdf", corrupted, document, log)


@pytest.mark.parametrize("language", ["hbo", "grc"])
def test_long_chapter_opening_continues_after_two_real_lines(request, tmp_path, tex_available, language):
    state = request.getfixturevalue("greek_state" if language == "grc" else "source_state")
    layout = {"body_pt": 26, "leading_pt": 38}
    config = (
        ProjectConfig(book="John", passage="1:1-18", selection="all", layout=layout)
        if language == "grc"
        else ProjectConfig(layout=layout)
    )
    document = build_document(state, config)
    # Synthetic long opening tests the badge/page boundary, not source content.
    token = max(
        (t for v in document.verses if v["chapter"] == 1 for t in v["tokens"] if t["helps"]),
        key=lambda t: len(t["surface"]),
    )
    document.verses = [
        {"reference": f"{config.book}.1.1", "chapter": 1, "verse": 1, "tokens": [token] * 60},
        {"reference": f"{config.book}.1.2", "chapter": 1, "verse": 2, "tokens": [token] * 4},
    ]
    compiler = Compiler(tmp_path / "opening", "Ezra SIL", greek=language == "grc")
    plans = paginate(document, compiler)
    assert len(plans) >= 2
    assert plans[0]["chapter_lines"] >= 2
    assert plans[0]["last"] == f"{config.book}.1.1"
    assert plans[1]["groups"][0][0]["continued"]
    assert plans[1]["chapter_lines"] == 0
    log = compiler.compile("reader", final_tex(document, plans), passes=2)
    assert verify_pdf(compiler.directory / "reader.pdf", plans, document, log)["verse_count"] == 2
    badges = []

    def collect_badges(text, cm, tm, font, size):
        if size == pytest.approx(25 * 72 / 72.27, abs=0.01) and text.strip():
            badges.append(text.strip())

    for page in PdfReader(compiler.directory / "reader.pdf").pages[: len(plans)]:
        page.extract_text(visitor_text=collect_badges)
    assert badges == ["1"]


def short_opening_document(request, language):
    state = request.getfixturevalue("greek_state" if language == "grc" else "source_state")
    config = (
        ProjectConfig(book="John", passage="1:1-18", selection="all")
        if language == "grc"
        else ProjectConfig()
    )
    document = build_document(state, config)
    words = [t for v in document.verses for t in v["tokens"] if t["kind"] == "word" and t["helps"]]
    word = min(words, key=lambda t: abs(sum(c.isalpha() for c in t["surface"]) - 6))
    plain = {**word, "helps": []}
    # Synthetic repetition and gloss isolate layout constraints; neither is
    # scholarly content or a proposed source reading.
    document.config["name"] = "Layout test"
    document.sources = {
        "language": language,
        "text_revision": "synthetic",
        "lexicon": {"revision": "synthetic"},
        "attributions": ["Synthetic layout fixture derived from the attributed test tokens."],
        "transformations": [],
    }
    document.warnings = []
    for identity in word["helps"]:
        document.helps[identity]["gloss"] = "Synthetic layout note. " * 12
    document.verses = [
        {"reference": f"{config.book}.1.3", "chapter": 1, "verse": 3, "tokens": [plain] * 30},
        {"reference": f"{config.book}.2.1", "chapter": 2, "verse": 1, "tokens": [plain]},
        {"reference": f"{config.book}.2.2", "chapter": 2, "verse": 2, "tokens": [plain]},
        {"reference": f"{config.book}.2.3", "chapter": 2, "verse": 3, "tokens": [word] * 24},
    ]
    return document


def fit_short_opening_page(document, compiler, groups):
    partials = [groups + [head] for head, _ in split_group([document.verses[-1]])]
    metrics = measure_candidates(compiler, [groups] + partials, document, 1)
    assert metrics[0].chapter_lines == 1
    capacity = metrics[0].page_height_sp + 65536
    assert all(metric.page_height_sp > capacity for metric in metrics[1:])
    width, _, margin = paper_dimensions(document.config["layout"])
    document.config["layout"].update(
        paper="custom",
        paper_width_mm=width,
        paper_height_mm=2 * margin + capacity / 65536 * 25.4 / 72.27,
    )


@pytest.mark.parametrize("language", ["hbo", "grc"])
def test_one_line_whole_opening_looks_ahead_before_backtracking(request, tmp_path, tex_available, language):
    document = short_opening_document(request, language)
    compiler = Compiler(tmp_path / "backtrack-opening", "Ezra SIL", greek=language == "grc")
    fit_short_opening_page(document, compiler, [[document.verses[0]], document.verses[1:3]])
    source = copy.deepcopy(document.json())
    plans = paginate(document, compiler)
    assert plans[0]["references"] == [document.verses[0]["reference"]]
    assert plans[1]["first"] == document.verses[1]["reference"]
    assert plans[1]["chapter_lines"] >= 2
    assert document.json() == source
    log = compiler.compile("reader", final_tex(document, plans), passes=2)
    assert verify_pdf(compiler.directory / "reader.pdf", plans, document, log)["verse_count"] == 4

    # Without the large note, a prefix supplies a real second opening line.
    # Look ahead before rejecting the one-line complete verses 1–2 group.
    lookahead = copy.deepcopy(document)
    lookahead.verses[-1]["tokens"] = [{**t, "helps": []} for t in lookahead.verses[-1]["tokens"]]
    plans = paginate(lookahead, compiler)
    assert plans[0]["last"] == lookahead.verses[-1]["reference"]
    assert plans[0]["chapter_lines"] >= 2
    assert plans[0]["groups"][-1][-1]["token_end"] < len(lookahead.verses[-1]["tokens"])
    log = compiler.compile("lookahead", final_tex(lookahead, plans), passes=2)
    assert verify_pdf(compiler.directory / "lookahead.pdf", plans, lookahead, log)["verse_count"] == 4


@pytest.mark.parametrize("language", ["hbo", "grc"])
def test_one_line_opening_overflows_only_when_its_chapter_continues(
    request, tmp_path, tex_available, language
):
    document = short_opening_document(request, language)
    document.verses = document.verses[1:]
    compiler = Compiler(tmp_path / "short-opening", "Ezra SIL", greek=language == "grc")
    fit_short_opening_page(document, compiler, [document.verses[:2]])
    with pytest.raises(ReaderError, match="Layout overflow") as error:
        paginate(document, compiler)
    assert f"Layout overflow at {document.verses[0]['reference']}:" in str(error.value)

    ending = copy.deepcopy(document)
    ending.verses = ending.verses[:2]
    plans = paginate(ending, compiler)
    assert len(plans) == 1 and plans[0]["chapter_lines"] == 1
    log = compiler.compile("passage-end", final_tex(ending, plans), passes=2)
    assert verify_pdf(compiler.directory / "passage-end.pdf", plans, ending, log)["verse_count"] == 2

    plain = ending.verses[0]["tokens"][0]
    ending.verses.append(
        {"reference": f"{ending.config['book']}.3.1", "chapter": 3, "verse": 1, "tokens": [plain] * 12}
    )
    plans = paginate(ending, compiler)
    assert plans[0]["chapter_lines"] == 1
    assert plans[0]["last"] == ending.verses[1]["reference"]
    assert plans[1]["first"] == ending.verses[2]["reference"]
    log = compiler.compile("chapter-end", final_tex(ending, plans), passes=2)
    assert verify_pdf(compiler.directory / "chapter-end.pdf", plans, ending, log)["verse_count"] == 3


@pytest.mark.parametrize("language", ["hbo", "grc"])
def test_chapter_end_balance_reflows_preceding_pages_and_reassigns_helps(
    request, tmp_path, tex_available, language
):
    state = request.getfixturevalue("greek_state" if language == "grc" else "source_state")
    config = (
        ProjectConfig(book="John", passage="1:1-18", selection="all")
        if language == "grc"
        else ProjectConfig()
    )
    document = build_document(state, config)
    tokens = [t for v in document.verses if v["chapter"] == 1 for t in v["tokens"] if t["helps"]]
    main = min(tokens, key=lambda t: abs(sum(c.isalpha() for c in t["surface"]) - 6))
    rare = next(t for t in tokens if set(t["helps"]).isdisjoint(main["helps"]))
    # Synthetic repetition creates an underfilled chapter end with a help on
    # the preceding page that must move when the two boundaries are adjusted.
    document.verses = [
        {
            "reference": f"{config.book}.1.3",
            "chapter": 1,
            "verse": 3,
            "tokens": [main] * 95 + [rare] + [main] * 36,
        },
        {"reference": f"{config.book}.2.1", "chapter": 2, "verse": 1, "tokens": [{**main, "helps": []}] * 18},
        {"reference": f"{config.book}.2.2", "chapter": 2, "verse": 2, "tokens": [{**main, "helps": []}] * 4},
    ]
    source = copy.deepcopy(document.json())
    first, rest = split_verse(document.verses[0], 48)
    middle, last = split_verse(rest, 48)
    pages = [[[first]], [[middle]], [[last]], [document.verses[1:]]]
    compiler = Compiler(tmp_path / "balanced", "Ezra SIL", greek=language == "grc")
    original = []
    for number, groups in enumerate(pages, 1):
        measurement = measure_candidates(compiler, [groups], document, number)[0]
        assert measurement.fits
        original.append(page_plan(groups, document, measurement, number, number))
    saved = copy.deepcopy(original)
    balanced = rebalance_pages(document, compiler, original)
    assert original == saved and document.json() == source
    assert len(balanced) == len(original)
    assert balanced[0]["groups"] != original[0]["groups"]
    assert balanced[-1] == original[-1]

    def largest_gap(plans):
        return max(p["usable_height_sp"] - p["page_height_sp"] for p in plans[:3])

    assert largest_gap(balanced) < largest_gap(original) - 65536
    assert set(rare["helps"]) <= set(original[1]["help_ids"])
    assert set(rare["helps"]).isdisjoint(balanced[1]["help_ids"])
    assert set(rare["helps"]) <= set(balanced[2]["help_ids"])
    assert sum(len(v["tokens"]) for g in balanced[2]["groups"] for v in g) > len(last["tokens"])
    assert all(p["page_height_sp"] <= p["usable_height_sp"] for p in balanced)
    log = compiler.compile("reader", final_tex(document, balanced), passes=2)
    result = verify_pdf(compiler.directory / "reader.pdf", balanced, document, log)
    assert result["verse_count"] == 3 and result["pdf_marker_destinations"] == "verified"


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
