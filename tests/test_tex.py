import copy

import pytest

from bible_reader.editorial import build_document
from bible_reader.models import ProjectConfig, ReaderDocument, ReaderError
from bible_reader.tex import blocks, contents, merge_fragments, page_tex, split_points, split_verse, word_tex


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


def test_verse_fragments_preserve_source_order_and_unbreakable_runs(source_state):
    document = build_document(source_state, ProjectConfig(passage="1:29"))
    word = document.verses[0]["tokens"][0]
    tokens = [
        {**word, "surface": "א"},
        {**word, "surface": "־", "kind": "x-maqqef"},
        {**word, "surface": "ב"},
        {**word, "surface": "", "kind": "x-sof-pasuq"},
        {**word, "surface": "ג", "reading": "ketiv"},
        {**word, "surface": "ד", "reading": "qere"},
        {**word, "surface": "׃", "kind": "x-sof-pasuq"},
        {**word, "surface": "ה"},
    ]
    verse = {**document.verses[0], "tokens": tokens}
    assert split_points(verse) == [4, 7]
    head, tail = split_verse(verse, 4)
    middle, end = split_verse(tail, 3)
    assert head["tokens"] + middle["tokens"] + end["tokens"] == tokens
    assert (head["token_start"], head["token_end"]) == (0, 4)
    assert (middle["token_start"], middle["token_end"]) == (4, 7)
    assert (end["token_start"], end["token_end"]) == (7, 8)
    assert middle["continued"] and end["continued"]
    scripture, _, _ = contents([[tail]], document, "p2")
    assert r"\Verse" not in scripture
    assert verse["tokens"] == tokens and "continued" not in verse


def test_joined_fragments_keep_offsets_readings_and_source_tokens(source_state):
    document = build_document(source_state, ProjectConfig(passage="1:29"))
    verse = copy.deepcopy(document.verses[0])
    first, rest = split_verse(verse, 2)
    middle, last = split_verse(rest, 2)
    joined = merge_fragments([first, middle, last])
    assert len(joined) == 1
    assert joined[0][0]["tokens"] == verse["tokens"]
    assert joined[0][0]["token_start"] == 0
    assert joined[0][0]["token_end"] == len(verse["tokens"])
    assert not joined[0][0].get("continued")
    continuation = merge_fragments([middle, last])[0][0]
    assert continuation["continued"] and continuation["token_start"] == 2
    assert continuation["tokens"] == verse["tokens"][2:]
    with pytest.raises(ReaderError, match="noncontiguous"):
        merge_fragments([first, {**rest, "token_start": 3}])
    assert document.verses[0] == verse
