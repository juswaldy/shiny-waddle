import pytest

from bible_reader.editorial import build_document
from bible_reader.models import Decision, Layout, ProjectConfig
from bible_reader.word_classes import WORD_CLASS_COLORS, word_class, word_color


@pytest.mark.parametrize(
    "morphology,category",
    [
        ("HNcmsa", "noun"),
        ("HR/Ncfsa", "noun"),
        ("HC/R/Td/Ncmsa/Sp3ms", "noun"),
        ("HVqp3ms", "verb"),
        ("HC/Vqi3mp/Sn", "verb"),
        ("HAamsa", "adjective"),
        ("HC/Aafsa", "adjective"),
        ("HAcmsa", "number"),
        ("HAomsa", "number"),
        ("HD", "adverb"),
        ("HPp3ms", "pronoun"),
        ("HR", "preposition"),
        ("HC/R/Sp3fs", "preposition"),
        ("HC", "conjunction"),
        ("HTn", "particle"),
        ("HC/To", "particle"),
        ("HSp3ms", "suffix"),
        ("HNp", "name"),
        ("HR/Np", "name"),
        ("AR/Np", "name"),
        ("ANcmsa", "noun"),
        ("AVqp3ms", "verb"),
        ("AAamsa", "adjective"),
        ("", None),
        ("Ncmsa", None),
        ("G123", None),
        ("HX", None),
        ("HR/", None),
        ("HNcmsa/X", None),
        ("HNcmsa/Vqp3ms", None),
    ],
)
def test_source_morphology_categories(morphology, category):
    assert word_class(morphology) == category


def test_rahlfs_indeclinable_number_uses_number_palette_and_override(greek_state):
    config = ProjectConfig(
        book="LXXDanOG",
        passage="4:12",
        selection="all",
        layout={"word_colors": "word-class", "word_color_overrides": {"number": "#123ABC"}},
    )
    document = build_document(greek_state, config)
    token = next(t for v in document.verses for t in v["tokens"] if t["surface"] == "τριάκοντα")
    assert token["morph"] == "lxx.M"
    assert token["word_class"] == "number"
    assert (
        word_color(token["word_class"], {"word_colors": "word-class"}) == "#" + WORD_CLASS_COLORS["number"][1]
    )
    assert word_color(token["word_class"], document.config["layout"]) == "#123ABC"


def test_names_use_existing_source_evidence_and_leave_common_candidates_explicit(source_state, name_review):
    config = ProjectConfig(
        passage="1:1",
        selection="all",
        decisions={"chosen-name:0": Decision(action="exclude", entry_id="step:test-name")},
    )
    document = build_document(source_state, config)
    tokens = {token["id"]: token for token in document.verses[0]["tokens"]}
    for identity in [
        "name-by-source",
        "unmatched-name",
        "lexicon-name",
        "chosen-name",
        "segmented-name",
        "arc-prefixed-name",
    ]:
        assert tokens[identity]["word_class"] == "name"
    assert tokens["common-by-source"]["word_class"] == "noun"
    assert tokens["unmatched-common"]["word_class"] == "noun"
    for source in name_review[0].tokens:
        token = tokens[source.id]
        assert token["source_surface"] == source.surface
        assert token["morph"] == source.morph
    assert "OSHB" in tokens["name-by-source"]["word_class_source"]
    assert "STEP" in tokens["lexicon-name"]["word_class_source"]


def test_coloring_is_independent_of_help_selection_and_preserves_sources(source_state):
    plain = build_document(source_state, ProjectConfig())
    colored = build_document(source_state, ProjectConfig(layout={"word_colors": "word-class"}))
    assert plain.verses == colored.verses
    assert plain.helps == colored.helps
    assert plain.review == colored.review
    assert plain.registry == colored.registry
    assert plain.sources == colored.sources
    assert any(
        not token["helps"] and token["word_class"] is not None
        for verse in colored.verses
        for token in verse["tokens"]
    )
    assert all(
        token["word_class"] is None
        for verse in colored.verses
        for token in verse["tokens"]
        if token["kind"] != "word"
    )


def test_palette_overrides_and_auto_disable_all_colors():
    layout = Layout(word_colors="word-class", word_color_overrides={"noun": "#aAbBcC", "name": "auto"})
    assert layout.word_color_overrides["noun"] == "#AABBCC"
    assert word_color("noun", layout.model_dump()) == "#AABBCC"
    assert word_color("verb", layout.model_dump()) == "#" + WORD_CLASS_COLORS["verb"][1]
    assert word_color("name", layout.model_dump()) is None
    assert word_color(None, layout.model_dump()) is None
    assert word_color("unknown", layout.model_dump()) is None
    layout.word_colors = "auto"
    assert all(word_color(category, layout.model_dump()) is None for category in WORD_CLASS_COLORS)
    assert word_color("noun", {}) is None


@pytest.mark.parametrize(
    "overrides",
    [{"unknown": "#245A81"}, {"noun": "red"}, {"noun": "#123"}, {"verb": r"\input{x}"}, {"name": 123}],
)
def test_invalid_class_or_color_is_rejected(overrides):
    with pytest.raises(ValueError):
        Layout(word_color_overrides=overrides)
