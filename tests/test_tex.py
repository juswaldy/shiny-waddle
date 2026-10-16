import copy

import pytest

from bible_reader.editorial import build_document
from bible_reader.models import ProjectConfig, ReaderDocument
from bible_reader.tex import blocks, contents, page_tex, word_tex


@pytest.mark.parametrize(
    "book,folio,title",
    [
        ("Gen", 1, r"\HebrewBookTitle{בראשית}"),
        ("Gen", 2, r"\EnglishBookTitle{בראשית}{Genesis}"),
        ("Prov", 1329, r"\HebrewBookTitle{משלי}"),
        ("Prov", 1330, r"\EnglishBookTitle{משלי}{Proverbs}"),
        ("1Sam", 2, r"\EnglishBookTitle{שמואל א}{1 Samuel}"),
        ("Song", 2, r"\EnglishBookTitle{שיר השירים}{Song of Songs}"),
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


def test_color_scope_preserves_markers_readings_punctuation_and_escaping(source_state):
    document = build_document(source_state, ProjectConfig())
    token = next(t for v in document.verses for t in v["tokens"] if t["helps"])
    token = {**token, "surface": "א&ב", "word_class": "noun", "reading": "ketiv"}
    plain = word_tex(token, document, "p1")
    document.config["layout"].update(word_colors="word-class", word_color_overrides={"noun": "#123456"})
    colored = word_tex(token, document, "p1")
    assert colored.replace(r"\textcolor[HTML]{123456}{א\&ב}", r"א\&ב") == plain
    assert r"{א\&ב}\ReadingMark{K}\HelpMarker" in colored
    assert r"\textcolor" not in word_tex({**token, "kind": "x-maqqef"}, document, "p1")
    assert r"\textcolor" not in word_tex({**token, "word_class": None}, document, "p1")
    document.config["layout"]["word_color_overrides"]["noun"] = "auto"
    assert word_tex(token, document, "p1") == plain
