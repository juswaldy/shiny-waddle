import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from bible_reader import editorial
from bible_reader.editorial import build_document, display_surface, require_resolved
from bible_reader.models import Decision, Layout, ProjectConfig, ReaderError, parse_passage


def test_reference_matches_every_observed_verse_label(source_state):
    expected = json.loads(Path("examples/prov-1-29-2-12.expected-layout.json").read_text())
    document = build_document(source_state, ProjectConfig())
    require_resolved(document)
    assert len(document.verses) == expected["verse_count"]
    assert len(document.helps) == expected["visible_unique_note_count"]
    for observed, verse in zip(expected["verses"], document.verses, strict=True):
        assert (verse["chapter"], verse["verse"]) == (observed["chapter"], observed["verse"])
        assert [document.helps[h]["label"] for t in verse["tokens"] for h in t["helps"]] == observed[
            "help_labels_in_reading_order"
        ]
    assert sum(len(t["helps"]) for v in document.verses for t in v["tokens"]) == 43


def test_selection_is_stable_across_passage_and_layout(source_state):
    whole = build_document(source_state, ProjectConfig())
    part = build_document(source_state, ProjectConfig(passage="2:6-12", layout={"paper": "a5"}))
    assert {r["anchor"]: r["label"] for r in part.review} == {
        r["anchor"]: r["label"]
        for r in whole.review
        if r["reference"] in {v["reference"] for v in part.verses}
    }
    assert part.registry["2"] == whole.registry["2"]


def test_edit_repeated_reference_help_allocates_independent_label(source_state):
    original = build_document(source_state, ProjectConfig())
    config = ProjectConfig(decisions={"20qg1:0": Decision(gloss="An editorial test gloss")})
    changed = build_document(source_state, config)
    edited = next(r for r in changed.review if r["anchor"] == "20qg1:0")
    others = [r for r in changed.review if r["anchor"] in {"20T2S:0", "20e6B:0", "2074R:0"}]
    assert edited["label"] == 23
    assert {r["label"] for r in others} == {4}
    assert changed.helps[edited["help_id"]]["editorial"]
    assert len(changed.helps) == len(original.helps) + 1


def test_source_unicode_is_separate_from_display(source_state):
    document = build_document(source_state, ProjectConfig(cantillation="preserve"))
    assert all(
        t["surface"] == t["source_surface"].replace("/", "") for v in document.verses for t in v["tokens"]
    )
    raw = "בְּ/רֵאשִׁ֖יתֽ"
    assert display_surface(raw, "hide") == "בְּרֵאשִׁיתֽ"
    assert display_surface(raw, "preserve") == raw.replace("/", "")


@pytest.mark.parametrize("reading,excluded", [("qere", "ketiv"), ("ketiv", "qere")])
def test_reading_policy_is_explicit(source_state, reading, excluded):
    document = build_document(source_state, ProjectConfig(readings=reading))
    assert excluded not in {t["reading"] for v in document.verses for t in v["tokens"]}
    assert reading in {t["reading"] for v in document.verses for t in v["tokens"]}


def test_ambiguity_requires_choice_or_explicit_exclusion(source_state, monkeypatch):
    entries, crosswalk = editorial.load_lexicon(source_state)
    selected = next(r for r in build_document(source_state, ProjectConfig()).review if r["selected"])
    original = entries[selected["entry_id"]]
    other = replace(original, id="step:test-alternative", gloss="Synthetic alternate")
    entries[other.id] = other
    crosswalk[selected["lemma"]] = [original.id, other.id]
    monkeypatch.setattr(editorial, "load_lexicon", lambda _: (entries, crosswalk))
    config = ProjectConfig()
    doc = build_document(source_state, config)
    with pytest.raises(ReaderError, match="unresolved"):
        require_resolved(doc)
    ambiguous = [r for r in doc.review if r["selected"] and r["status"] != "resolved"]
    config.decisions = {r["anchor"]: Decision(entry_id=other.id) for r in ambiguous}
    require_resolved(build_document(source_state, config))
    config.decisions = {r["anchor"]: Decision(action="exclude") for r in ambiguous}
    require_resolved(build_document(source_state, config))


def test_missing_mapping_stays_unmatched(source_state, monkeypatch):
    entries, crosswalk = editorial.load_lexicon(source_state)
    row = next(r for r in build_document(source_state, ProjectConfig()).review if r["selected"])
    crosswalk.pop(row["lemma"])
    crosswalk.pop(row["lemma"][:5], None)
    monkeypatch.setattr(editorial, "load_lexicon", lambda _: (entries, crosswalk))
    document = build_document(source_state, ProjectConfig())
    assert any(r["status"] == "unmatched" and r["selected"] for r in document.review)
    with pytest.raises(ReaderError, match="unresolved"):
        require_resolved(document)


def test_single_base_id_candidate_still_requires_review(source_state, monkeypatch):
    book = editorial.load_book(source_state, "Prov")
    entries, crosswalk = editorial.load_lexicon(source_state)
    row = next(
        r
        for r in build_document(source_state, ProjectConfig()).review
        if r["selected"] and len(r["lemma"]) == 5
    )
    modified = [
        replace(
            v,
            tokens=tuple(
                replace(t, lemma=t.lemma + " z") if t.id == row["token_id"] else t for t in v.tokens
            ),
        )
        for v in book
    ]
    monkeypatch.setattr(editorial, "load_book", lambda *_: modified)
    monkeypatch.setattr(editorial, "load_lexicon", lambda _: (entries, crosswalk))
    document = build_document(source_state, ProjectConfig())
    candidate = next(r for r in document.review if r["anchor"] == row["anchor"])
    assert candidate["candidates"]
    assert candidate["entry_id"] is None
    assert candidate["status"] == "ambiguous"
    with pytest.raises(ReaderError, match="unresolved"):
        require_resolved(document)


def test_frequency_known_words_and_decisions(source_state):
    config = ProjectConfig(selection="book-frequency", frequency_max=1)
    document = build_document(source_state, config)
    assert all(r["book_frequency"] <= 1 for r in document.review if r["selected"])
    row = next(r for r in document.review if r["selected"] and r["entry_id"])
    config.known_entries = [row["entry_id"]]
    omitted = build_document(source_state, config)
    assert all(not r["selected"] for r in omitted.review if r["entry_id"] == row["entry_id"])
    config.decisions[row["anchor"]] = Decision(action="include")
    assert next(r for r in build_document(source_state, config).review if r["anchor"] == row["anchor"])[
        "selected"
    ]


def test_stale_decisions_and_missing_verses_fail(source_state):
    for config in [
        ProjectConfig(decisions={"absent:0": Decision()}),
        ProjectConfig(passage="1:99", selection="all"),
    ]:
        with pytest.raises(ReaderError):
            build_document(source_state, config)


@pytest.mark.parametrize("passage", ["0:1", "1:0", "2:2-1:1", "1", "1:1;rm", "1:1-", "1000:1"])
def test_invalid_passages_are_rejected(passage):
    with pytest.raises(ValueError):
        parse_passage(passage)


@pytest.mark.parametrize(
    "values",
    [
        {"frequency_max": True},
        {"book": "../Prov"},
        {"name": "bad\nname"},
        {"layout": {"body_pt": 26, "leading_pt": 16}},
        {"schema_version": 99},
        {"unknown": True},
    ],
)
def test_config_validation(values):
    with pytest.raises(ValidationError):
        ProjectConfig(**values)


def test_valid_passage_and_layout():
    assert parse_passage("2:1–12") == ((2, 1), (2, 12))
    assert parse_passage("1:29-2:12") == ((1, 29), (2, 12))
    assert Layout().body_pt == 18
