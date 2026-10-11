import copy

import pytest

from bible_reader.editorial import build_document
from bible_reader.models import ProjectConfig, ReaderDocument
from bible_reader.tex import blocks, contents, page_tex


@pytest.mark.parametrize(
    "book,folio,title",
    [
        ("Gen", 1, r"\texthebrew{בראשית}"),
        ("Gen", 2, r"\textenglish{GENESIS}"),
        ("Prov", 1329, r"\texthebrew{משלי}"),
        ("Prov", 1330, r"\textenglish{PROVERBS}"),
    ],
)
def test_running_title_uses_printed_folio_language(book, folio, title):
    config = ProjectConfig(book=book, selection="all", passage="2:3").model_dump()
    verse = {"reference": f"{book}.2.3", "chapter": 2, "verse": 3, "tokens": []}
    document = ReaderDocument(config, [verse], {}, [], {}, {})
    _, page = page_tex([[verse]], document, "p1", folio)
    assert page == rf"\ReaderPage{{2:3}}{{{title}}}{{{folio}}}"


def test_stem_capitalization_only_changes_tex_display(source_state):
    document = build_document(source_state, ProjectConfig())
    original = copy.deepcopy(document.json())
    _, notes, note_ids = contents(blocks(document), document, "p1")
    stems = {document.helps[identity]["stem"] for identity in note_ids} - {""}
    assert stems >= {"Qal", "Hif"}
    for stem in stems:
        assert rf"\NoteStem{{{stem.upper()}}}" in notes
        assert rf"\NoteStem{{{stem}}}" not in notes
    assert r"\NoteStem{}" not in notes
    assert document.json() == original
