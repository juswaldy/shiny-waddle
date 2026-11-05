import json
import zipfile

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader

from bible_reader.citations import MODIFIED_HELPS_NOTICE
from bible_reader.editorial import build_document
from bible_reader.models import Decision, ProjectConfig
from bible_reader.service import build, build_from_data

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "modified,notes,mode",
    [
        (True, "", "append"),
        (True, "Synthetic edition notes: 50% & {review}.\nFor the reading group.", "append"),
        (True, "Synthetic replacement note.", "replace"),
        (False, "Synthetic edition note, without edited helps.", "append"),
        (False, "Synthetic replacement note, without edited helps.", "replace"),
    ],
)
def test_citation_footer_is_printed_at_the_bottom_and_preserves_sources(
    source_state, tmp_path, tex_available, modified, notes, mode
):
    config = ProjectConfig(
        passage="1:29",
        lexicon_only=True,
        citation_notes=notes,
        citation_notes_mode=mode,
    )
    if modified:
        row = next(r for r in build_document(source_state, config).review if r["selected"])
        config.decisions = {row["anchor"]: Decision(gloss="Synthetic edited gloss")}
    output = tmp_path / "proof"
    result = build(source_state, config, output)
    assert result["errors"] == [] and result["credits_pages"] == 1
    pdf = PdfReader(output / "reader.pdf")
    page = pdf.pages[-1]
    text = " ".join(page.extract_text().split())
    assert (MODIFIED_HELPS_NOTICE in text) is (modified and mode == "append")
    if notes:
        assert " ".join(notes.split()) in text
    assert "Sources and edition" in text and "Text revision:" in text and "Lexicon revision:" in text
    assert "Open Scriptures" in text and "STEP" in text
    credits = (output / "credits.txt").read_text()
    assert (MODIFIED_HELPS_NOTICE in credits) is (modified and mode == "append")
    if notes:
        assert credits.endswith(notes + "\n")
    # Verify the final note's actual baseline is near the bottom margin.
    baselines = []
    final_line = notes.split("\n")[-1] if notes else "Changes may include"

    def locate_footer(run, cm, tm, font, size):
        if final_line[:20] in run:
            baselines.append(cm[1] * tm[4] + cm[3] * tm[5] + cm[5])

    page.extract_text(visitor_text=locate_footer)
    assert baselines and min(baselines) < 60
    with zipfile.ZipFile(output / "reader-bundle.zip") as bundle:
        assert bundle.read("credits.txt").decode() == credits
    rendered = pdfium.PdfDocument(output / "reader.pdf")
    rendered[len(rendered) - 1].render(scale=2).to_pil().save(output / "citation-page.png")


def test_mixed_script_citation_notes_survive_offline_data_and_font_bundling(
    source_state, tmp_path, tex_available
):
    config = ProjectConfig(
        passage="1:29",
        citation_notes="Synthetic reader note: 50% & {review}.\nHebrew שָׁלוֹם עוֹלָם; Greek λόγος α\u0301.",
    )
    build(source_state, config, tmp_path / "data", emit="data")
    data = json.loads((tmp_path / "data/reader.v2.json").read_text())
    output = tmp_path / "offline-proof"
    result = build_from_data(tmp_path / "no-installed-sources", data, output, emit="pdf")
    assert result["errors"] == [] and result["credits_pages"] == 1
    pdf = PdfReader(output / "reader.pdf")
    text = " ".join(pdf.pages[-1].extract_text().split())
    assert "50% & {review}" in text and "λόγος" in text
    assert "Synthetic reader note" not in pdf.pages[0].extract_text()
    with zipfile.ZipFile(output / "reader-bundle.zip") as bundle:
        assert {"reader-greek.ttf", "GentiumPlus-LICENSE.txt", "reader-hebrew.ttf"} <= set(bundle.namelist())
    rendered = pdfium.PdfDocument(output / "reader.pdf")
    rendered[len(rendered) - 1].render(scale=2).to_pil().save(output / "citation-page.png")


def test_long_user_notes_continue_across_credit_pages_without_losing_lines(
    source_state, tmp_path, tex_available
):
    notes = "\n".join(f"Synthetic edition note {number:03d}." for number in range(100))
    config = ProjectConfig(passage="1:29", lexicon_only=True, citation_notes=notes)
    output = tmp_path / "long-notes"
    result = build(source_state, config, output)
    assert result["errors"] == [] and result["credits_pages"] > 1
    pdf = PdfReader(output / "reader.pdf")
    first = pdf.get_destination_page_number(pdf.named_destinations["reader-credits"])
    text = "\n".join(page.extract_text() for page in pdf.pages[first:])
    for line in notes.split("\n"):
        assert line in text
    assert result["total_pages"] == result["appendix_pages"] + result["credits_pages"]
