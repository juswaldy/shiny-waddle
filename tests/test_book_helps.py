import json

import pytest
from pydantic import ValidationError

from bible_reader.book_helps import BookHelps, load_book_helps, save_book_helps
from bible_reader.editorial import build_document
from bible_reader.models import Decision, ProjectConfig, ReaderError


def book_config():
    return ProjectConfig(
        passage="1:1",
        selection="all",
        readings="qere",
        gloss_selection="first-entry",
        decisions={
            "test-origin:0": Decision(entry_id="step:test-choice", gloss="Editorial שָׁמַר & help"),
            "test-repeat:0": Decision(action="exclude", reason="Already known"),
            "test-ketiv:0": Decision(entry_id="step:test-alternate", gloss="Editorial written form"),
            "test-qere:0": Decision(entry_id="step:test-choice", gloss="Editorial read form"),
            "test-segmented:1": Decision(action="exclude"),
            "test-unmatched:0": Decision(action="exclude", reason="Unmatched; reviewed omission"),
        },
    )


def test_attributed_source_excerpt_retains_editorial_provenance(source_state):
    config = ProjectConfig()
    before = build_document(source_state, config)
    row = next(row for row in before.review if row["selected"] and row["status"] == "resolved")
    config.decisions[row["anchor"]] = Decision(
        entry_id=row["entry_id"], gloss="Editorial test wording", reason="File round-trip test"
    )
    saved = save_book_helps(source_state, config)
    restored = load_book_helps(source_state, ProjectConfig(), saved)
    document = build_document(source_state, restored)
    edited = next(row for row in document.review if row["anchor"] in saved.decisions)
    assert edited["entry_id"] == row["entry_id"] and edited["choice_method"] == "decision"
    assert document.helps[edited["help_id"]]["editorial"]
    assert saved.decisions[row["anchor"]].reason == "File round-trip test"
    assert [t["source_surface"] for v in document.verses for t in v["tokens"]] == [
        t["source_surface"] for v in before.verses for t in v["tokens"]
    ]


def test_book_help_file_round_trip_includes_other_chapters_readings_and_segments(
    source_state, consonant_review
):
    original = book_config()
    raw = [verse.json() for verse in consonant_review]
    saved = save_book_helps(source_state, original)
    assert saved.sources.text_source == "oshb"
    assert saved.sources.lexicon_source == "step"
    assert saved.sources.text_revision and saved.sources.lexicon_revision
    assert "passage" not in saved.model_dump()
    assert saved.decisions == original.decisions
    destination = ProjectConfig(
        name="Another edition",
        passage="3:1",
        selection="book-frequency",
        frequency_max=3,
        cantillation="preserve",
        known_entries=["step:test-other"],
        decisions={"test-prefix:0": Decision(action="exclude")},
        layout={"paper": "a5"},
    )
    restored = load_book_helps(
        source_state, destination, BookHelps.model_validate_json(saved.model_dump_json())
    )
    assert restored.decisions == original.decisions
    assert restored.gloss_selection == "first-entry"
    assert restored.model_dump(exclude={"decisions", "gloss_selection"}) == destination.model_dump(
        exclude={"decisions", "gloss_selection"}
    )
    rows = {row["anchor"]: row for row in build_document(source_state, restored).review}
    assert rows["test-ketiv:0"]["gloss"] == "Editorial written form"
    assert rows["test-qere:0"]["gloss"] == "Editorial read form"
    assert rows["test-unmatched:0"]["status"] == "unmatched"
    assert not rows["test-unmatched:0"]["selected"]
    assert all(
        help["editorial"]
        for help in build_document(source_state, restored).helps.values()
        if help["gloss"].startswith("Editorial")
    )
    assert [verse.json() for verse in consonant_review] == raw
    assert "test-prefix:0" in destination.decisions


@pytest.mark.parametrize(
    "anchor,decision,message",
    [
        ("missing:0", Decision(action="exclude"), "missing source anchor"),
        ("test-ketiv:0", Decision(entry_id="step:test-other"), "incompatible lexical decision"),
        ("test-segmented:1", Decision(entry_id="step:test-choice"), "incompatible lexical decision"),
        ("test-unmatched:0", Decision(gloss="Editorial without a source"), "Choose a source entry"),
    ],
)
def test_save_checks_entire_book_even_when_chapters_and_readings_are_hidden(
    source_state, consonant_review, anchor, decision, message
):
    config = book_config()
    config.decisions[anchor] = decision
    with pytest.raises(ReaderError, match=message):
        save_book_helps(source_state, config)


@pytest.mark.parametrize("field", ["text_revision", "text_sha256", "lexicon_revision", "lexicon_sha256"])
def test_load_rejects_changed_source_identity(source_state, consonant_review, field):
    config = book_config()
    saved = save_book_helps(source_state, config)
    setattr(saved.sources, field, "different")
    with pytest.raises(ReaderError, match="different text or lexicon"):
        load_book_helps(source_state, config, saved)


def test_empty_file_clears_decisions_and_preserves_unresolved_choices(source_state, consonant_review):
    config = ProjectConfig(passage="1:1", selection="all")
    saved = save_book_helps(source_state, config)
    restored = load_book_helps(source_state, book_config(), saved)
    assert restored.decisions == {}
    assert restored.gloss_selection == "reviewed"
    assert all(row["status"] == "ambiguous" for row in build_document(source_state, restored).review)
    saved.decisions["test-origin:0"] = Decision(gloss="Editorial implicit first candidate")
    with pytest.raises(ReaderError, match="Choose a source entry"):
        load_book_helps(source_state, config, saved)
    saved.gloss_selection = "first-entry"
    assert load_book_helps(source_state, config, saved).decisions == saved.decisions


def test_legacy_name_decisions_remain_history_and_do_not_enable_name_helps(source_state, name_review):
    config = ProjectConfig(
        passage="1:1",
        selection="all",
        decisions={"name-by-source:0": Decision(entry_id="step:test-name", gloss="Historical edit")},
    )
    restored = load_book_helps(source_state, config, save_book_helps(source_state, config))
    row = next(
        row for row in build_document(source_state, restored).review if row["anchor"] == "name-by-source:0"
    )
    assert restored.decisions == config.decisions
    assert row["name_excluded"] and not row["selected"]


@pytest.mark.parametrize("change", [{"schema_version": 2}, {"format": "other"}, {"extra": True}])
def test_file_schema_is_strict(source_state, consonant_review, change):
    data = save_book_helps(source_state, book_config()).model_dump()
    with pytest.raises(ValidationError):
        BookHelps.model_validate_json(json.dumps({**data, **change}))


@pytest.mark.parametrize(
    "field", ["format", "schema_version", "book", "sources", "gloss_selection", "decisions"]
)
def test_file_identity_and_contents_are_required(source_state, consonant_review, field):
    data = save_book_helps(source_state, book_config()).model_dump()
    del data[field]
    with pytest.raises(ValidationError):
        BookHelps.model_validate(data)
