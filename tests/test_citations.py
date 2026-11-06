import copy

import pytest
from pydantic import ValidationError

from bible_reader.citations import MODIFIED_HELPS_NOTICE, citation_notes, lexical_helps_modified
from bible_reader.data_files import load_reader_data
from bible_reader.editorial import build_document
from bible_reader.models import Decision, ProjectConfig, ReaderError
from bible_reader.tex import citation_text_tex


@pytest.mark.parametrize("modified", [False, True])
@pytest.mark.parametrize("notes", ["", "Reader's edition notes.\nA second line."])
@pytest.mark.parametrize("mode", ["append", "replace"])
def test_citation_notes_can_add_or_replace_with_or_without_help_edits(source_state, modified, notes, mode):
    config = ProjectConfig(citation_notes=notes, citation_notes_mode=mode)
    if modified:
        config.decisions = {"20qg1:0": Decision(gloss="Synthetic edited gloss")}
    document = build_document(source_state, config)
    assert lexical_helps_modified(document) is modified
    expected = [MODIFIED_HELPS_NOTICE] if modified and mode == "append" else []
    if notes:
        expected.append(notes)
    assert citation_notes(document) == expected
    restored = load_reader_data(copy.deepcopy(document.json()))
    assert restored.json() == document.json()
    assert citation_notes(restored) == expected


def test_modification_detection_ignores_unchanged_choices_and_other_passages(source_state):
    original = build_document(source_state, ProjectConfig())
    row = next(r for r in original.review if r["anchor"] == "20qg1:0")
    config = ProjectConfig(decisions={row["anchor"]: Decision(entry_id=row["entry_id"], gloss=row["gloss"])})
    assert not lexical_helps_modified(build_document(source_state, config))
    config.decisions = {row["anchor"]: Decision(gloss="Synthetic edited gloss")}
    assert lexical_helps_modified(build_document(source_state, config))
    config.passage = "1:29"
    assert not lexical_helps_modified(build_document(source_state, config))


def test_inclusion_and_omission_changes_are_disclosed(source_state):
    original = build_document(source_state, ProjectConfig())
    included = next(r for r in original.review if r["selected"])
    omitted = next(r for r in original.review if not r["selected"] and not r["name_excluded"])
    for row, decision in [
        (included, Decision(action="exclude")),
        (omitted, Decision(action="include")),
    ]:
        config = ProjectConfig(decisions={row["anchor"]: decision})
        changed = build_document(source_state, config)
        assert {r["anchor"] for r in changed.review if r["help_modified"]} == {row["anchor"]}
        assert citation_notes(changed) == [MODIFIED_HELPS_NOTICE]


def test_source_entry_choices_and_manual_glosses_are_disclosed(source_state, consonant_review):
    config = ProjectConfig(selection="all", passage="1:1-3:1", gloss_selection="first-entry")
    config.decisions = {
        "test-origin:0": Decision(entry_id="step:test-alternate"),
        "test-unmatched:0": Decision(gloss="Synthetic manual gloss"),
    }
    document = build_document(source_state, config)
    assert {r["anchor"] for r in document.review if r["help_modified"]} == set(config.decisions)


def test_historical_name_choices_do_not_claim_the_omitted_help_changed(source_state, name_review):
    config = ProjectConfig(
        passage="1:1",
        selection="all",
        decisions={"name-by-source:0": Decision(entry_id="step:test-name", gloss="Synthetic name gloss")},
    )
    assert not lexical_helps_modified(build_document(source_state, config))


def test_legacy_reader_with_saved_decisions_still_discloses_modifications(source_state):
    document = build_document(source_state, ProjectConfig(decisions={"20qg1:0": Decision(gloss="Test edit")}))
    for row in document.review:
        row.pop("help_modified")
    restored = load_reader_data(document.json())
    assert citation_notes(restored) == [MODIFIED_HELPS_NOTICE]


def test_multiline_notes_and_default_settings():
    assert ProjectConfig().citation_notes == ""
    assert ProjectConfig().citation_notes_mode == "append"
    assert (
        ProjectConfig(citation_notes="First\r\n\r\nSecond\rThird").citation_notes == "First\n\nSecond\nThird"
    )


@pytest.mark.parametrize(
    "values",
    [
        {"citation_notes": "bad\x00note"},
        {"citation_notes": "bad\tnote"},
        {"citation_notes": "bad\ud800note"},
        {"citation_notes": "x" * 4001},
        {"citation_notes": None},
        {"citation_notes_mode": "hide"},
    ],
)
def test_citation_notes_validation(values):
    with pytest.raises(ValidationError):
        ProjectConfig(**values)


def test_portable_modification_evidence_is_a_strict_boolean(source_state):
    data = build_document(source_state, ProjectConfig()).json()
    data["review"][0]["help_modified"] = "false"
    with pytest.raises(ReaderError, match="Invalid reader data"):
        load_reader_data(data)


def test_notes_are_escaped_once_and_keep_explicit_script_runs():
    text = citation_text_tex("50% & {review} \\input{private}\nHebrew שָׁלוֹם עוֹלָם; Greek λόγος α\u0301.")
    assert r"50\% \& \{review\} \textbackslash{}input\{private\}\par" in text
    assert r"\texthebrew{שָׁלוֹם עוֹלָם}" in text
    assert "\\ReaderGreek{λόγος α\u0301}" in text
    assert r"\input{private}" not in text
