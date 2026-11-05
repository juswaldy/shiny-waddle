import copy
import unicodedata

import pytest

from bible_reader.appendix import collect_lexicon, greek_sort_key, hebrew_sort_key
from bible_reader.editorial import build_document, require_resolved
from bible_reader.models import Decision, ProjectConfig, ReaderError


def test_hebrew_order_ignores_points_and_collates_final_letters():
    headwords = ["שָׁלוֹם", "מֶלֶךְ", "צֶדֶק", "בֵּן", "לֵב", "כֹּל", "אָב"]
    original = list(headwords)
    assert sorted(headwords, key=hebrew_sort_key) == ["אָב", "בֵּן", "כֹּל", "לֵב", "מֶלֶךְ", "צֶדֶק", "שָׁלוֹם"]
    assert hebrew_sort_key("מֶלֶךְ") == hebrew_sort_key("מלכ")
    assert hebrew_sort_key("כַּף־יָד") == "כפיד"
    assert headwords == original


def test_greek_order_ignores_subscript_iota_before_case_folding(greek_state):
    headword = "ᾠδή"
    assert greek_sort_key(headword) == "ωδη"
    assert greek_sort_key(unicodedata.normalize("NFD", headword)) == "ωδη"
    assert greek_sort_key("ᾨΔΉ") == "ωδη"
    assert greek_sort_key("ὁδός") == greek_sort_key("ΟΔΟΣ") == "οδοσ"
    assert greek_sort_key("ωι") == "ωι"  # A separate iota letter remains significant.
    document = build_document(
        greek_state,
        ProjectConfig(book="LXXOd", passage="1:0", selection="all", lexicon_appendix=True),
    )
    entry = next(e for e in document.lexicon_appendix if e["entry_id"] == "step-greek:G5603")
    assert entry["headword"] == headword


def test_appendix_deduplicates_chapters_but_keeps_entries_stems_and_editorial_wording():
    # Synthetic metadata tests identities, without proposing a biblical sense.
    help = {
        "entry_id": "step:test",
        "headword": "שָׁמַר",
        "stem": "Qal",
        "gloss": "Synthetic gloss",
        "source": "Synthetic test",
        "status": "resolved",
        "editorial": False,
    }
    helps = {
        "Prov.1:a": help,
        "Prov.2:a": {**help, "editorial": True},
        "Prov.2:b": {**help, "gloss": "Synthetic edited wording", "editorial": True},
        "Prov.2:c": {**help, "stem": "Hif"},
        "Prov.2:d": {**help, "entry_id": "step:other"},
    }
    original = copy.deepcopy(helps)
    entries = collect_lexicon(helps)
    assert len(entries) == 4
    repeated = next(entry for entry in entries if len(entry["help_ids"]) == 2)
    assert repeated["help_ids"] == ["Prov.1:a", "Prov.2:a"]
    assert repeated["editorial"]
    assert len({entry["id"] for entry in entries}) == 4
    assert collect_lexicon(dict(reversed(list(helps.items())))) == entries
    assert helps == original


@pytest.mark.parametrize("lexicon_only", [False, True])
def test_appendix_uses_the_same_frequency_and_override_selection_as_notes(
    source_state, consonant_review, lexicon_only
):
    config = ProjectConfig(
        passage="1:1-3:1",
        selection="book-frequency",
        frequency_max=1,
        gloss_selection="first-entry",
        lexicon_appendix=not lexicon_only,
        lexicon_only=lexicon_only,
        known_entries=["step:test-other"],
        decisions={
            "test-origin:0": Decision(entry_id="step:test-alternate", gloss="Synthetic edited help"),
            "test-repeat:0": Decision(action="exclude"),
            "test-unmatched:0": Decision(action="exclude"),
            "test-aramaic:0": Decision(action="exclude"),
        },
    )
    document = build_document(source_state, config)
    require_resolved(document)
    selected = [row for row in document.review if row["selected"]]
    assert [row["anchor"] for row in selected] == ["test-origin:0"]
    assert selected[0]["book_frequency"] > config.frequency_max  # Explicit inclusion, just as in notes.
    assert document.lexicon_appendix[0]["entry_id"] == "step:test-alternate"
    assert document.lexicon_appendix[0]["gloss"] == "Synthetic edited help"
    assert {help for entry in document.lexicon_appendix for help in entry["help_ids"]} == set(document.helps)
    # Switching the appendix off changes neither notes nor source scripture.
    config.lexicon_appendix = False
    config.lexicon_only = False
    ordinary = build_document(source_state, config)
    assert ordinary.lexicon_appendix == []
    assert ordinary.helps == document.helps and ordinary.verses == document.verses


def test_appendix_contains_only_built_passage_and_does_not_hide_unresolved_helps(
    source_state, consonant_review
):
    config = ProjectConfig(passage="1:1", selection="all", lexicon_appendix=True)
    document = build_document(source_state, config)
    assert {help for entry in document.lexicon_appendix for help in entry["help_ids"]} == set(document.helps)
    assert all(
        help.startswith("Prov.1:") for entry in document.lexicon_appendix for help in entry["help_ids"]
    )
    assert any(entry["status"] == "ambiguous" for entry in document.lexicon_appendix)
    with pytest.raises(ReaderError, match="unresolved"):
        require_resolved(document)
    config.passage = "1:1-3:1"
    document = build_document(source_state, config)
    unresolved = [entry for entry in document.lexicon_appendix if entry["entry_id"] is None]
    assert len(unresolved) == 4  # Three distinct candidate lists and one missing source lemma.
    assert {entry["status"] for entry in unresolved} == {"ambiguous", "unmatched"}
    assert collect_lexicon(dict(reversed(list(document.helps.items())))) == document.lexicon_appendix


def test_appendix_omits_names_and_keeps_reference_helps_traceable(source_state):
    config = ProjectConfig(lexicon_appendix=True)
    document = build_document(source_state, config)
    require_resolved(document)
    assert len(document.lexicon_appendix) <= len(document.helps)
    assert {help for entry in document.lexicon_appendix for help in entry["help_ids"]} == set(document.helps)
    assert [hebrew_sort_key(entry["headword"]) for entry in document.lexicon_appendix] == sorted(
        hebrew_sort_key(entry["headword"]) for entry in document.lexicon_appendix
    )
    for entry in document.lexicon_appendix:
        assert all(
            document.helps[identity]["entry_id"] == entry["entry_id"] for identity in entry["help_ids"]
        )


def test_appendix_cannot_restore_names(source_state, name_review):
    config = ProjectConfig(
        passage="1:1",
        selection="all",
        gloss_selection="first-entry",
        lexicon_appendix=True,
        decisions={
            "unmatched-common:0": Decision(action="exclude"),
            "name-by-source:0": Decision(entry_id="step:test-name"),
        },
    )
    document = build_document(source_state, config)
    assert all(entry["entry_id"] == "step:test-common" for entry in document.lexicon_appendix)
    assert not {row["help_id"] for row in document.review if row["name_excluded"]} & set(document.helps)
