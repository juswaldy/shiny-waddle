import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from bible_reader import editorial
from bible_reader.editorial import (
    build_document,
    consonant_key,
    display_surface,
    edit_decision,
    is_name_morphology,
    require_resolved,
)
from bible_reader.models import Decision, Layout, ProjectConfig, ReaderError, parse_passage
from bible_reader.tex import verse_content


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


@pytest.mark.parametrize(
    "policy,expected",
    [
        ("consonants-only", "בראשיתשר"),
        ("consonants", "בראשית־שר"),
        ("consonants-maqqef-sof-pasuq", "בראשית־שר׃"),
    ],
)
def test_consonant_display_removes_hebrew_points_and_only_retains_chosen_punctuation(policy, expected):
    raw = "בְּ/רֵאשִׁ֖יתֽ־שָׂר׃׀׆\u05bf\u05c4\u05c5\u05c7\u05f3\u05f4"
    assert display_surface(raw, policy) == expected
    assert display_surface("אָב פ ס α\u0301 e\u0301 123.", policy) == "אב פ ס α\u0301 e\u0301 123."


@pytest.mark.parametrize("policy", ["consonants-only", "consonants", "consonants-maqqef-sof-pasuq"])
def test_consonant_policies_preserve_source_records_readings_and_help_selection(source_state, policy):
    original = build_document(source_state, ProjectConfig(cantillation="preserve"))
    document = build_document(source_state, ProjectConfig(cantillation=policy))
    require_resolved(document)
    assert document.helps == original.helps
    assert document.registry == original.registry
    for before, after in zip(original.verses, document.verses, strict=True):
        assert before["source_annotations"] == after["source_annotations"]
        for source, displayed in zip(before["tokens"], after["tokens"], strict=True):
            assert {k: v for k, v in source.items() if k != "surface"} == {
                k: v for k, v in displayed.items() if k != "surface"
            }
            if displayed["kind"] == "x-maqqef":
                assert displayed["surface"] == ("" if policy == "consonants-only" else "־")
            elif displayed["kind"] == "x-sof-pasuq":
                assert displayed["surface"] == ("׃" if policy == "consonants-maqqef-sof-pasuq" else "")
    assert {r["reading"] for r in document.review} >= {"ketiv", "qere"}
    assert [{k: v for k, v in r.items() if k != "surface"} for r in document.review] == [
        {k: v for k, v in r.items() if k != "surface"} for r in original.review
    ]
    assert editorial.DISPLAY_TRANSFORMATIONS[policy] in document.sources["transformations"]


@pytest.mark.parametrize("policy", ["consonants-only", "consonants", "consonants-maqqef-sof-pasuq"])
def test_consonant_tex_respects_maqqef_choice_and_skips_hidden_punctuation(source_state, policy):
    document = build_document(source_state, ProjectConfig(passage="1:29", cantillation=policy))
    verse = document.verses[0]
    # Actual source words/separator; omit helps here to inspect word boundaries.
    first = [{**t, "helps": []} for t in verse["tokens"][1:4]]
    expected = r"\mbox{כי} \mbox{שנאו}" if policy == "consonants-only" else r"\mbox{כי}־\mbox{שנאו}"
    assert verse_content({"tokens": first}, document, "test") == expected
    hidden = {"surface": "", "kind": "x-paseq"}
    assert verse_content({"tokens": [first[0], hidden, first[2]]}, document, "test") == (
        r"\mbox{כי} \mbox{שנאו}"
    )


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
    monkeypatch.setattr(editorial, "load_lexicon", lambda _, book="Prov": (entries, crosswalk))
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
    monkeypatch.setattr(editorial, "load_lexicon", lambda _, book="Prov": (entries, crosswalk))
    document = build_document(source_state, ProjectConfig())
    assert any(r["status"] == "unmatched" and r["selected"] for r in document.review)
    with pytest.raises(ReaderError, match="unresolved"):
        require_resolved(document)


def test_first_entry_policy_preserves_candidates_source_records_and_missing_matches(
    source_state, consonant_review
):
    config = ProjectConfig(passage="1:1-3:1", selection="all")
    original_sources = [verse.json() for verse in consonant_review]
    reviewed = build_document(source_state, config)
    assert next(r for r in reviewed.review if r["anchor"] == "test-origin:0")["status"] == "ambiguous"
    config.gloss_selection = "first-entry"
    document = build_document(source_state, config)
    assert len(document.review) == len(reviewed.review) == 11
    for original, row in zip(reviewed.review, document.review, strict=True):
        assert row["candidates"] == original["candidates"]
        assert row["alignment_status"] == original["status"]
        assert row["source_surface"] == original["source_surface"]
        if row["candidates"]:
            assert row["entry_id"] == row["candidates"][0]["id"]
            assert row["gloss"] == row["candidates"][0]["gloss"]
            assert row["status"] == "resolved"
            assert row["choice_method"] == "first-entry"
            assert "project default" in row["method"]
            assert not document.helps[row["help_id"]]["editorial"]
        else:
            assert row["status"] == "unmatched"
            assert row["choice_method"] == "unresolved"
            assert row["entry_id"] is None and row["gloss"] == ""
    assert [verse.json() for verse in consonant_review] == original_sources
    with pytest.raises(ReaderError, match="1 unresolved"):
        require_resolved(document)
    config.decisions = {"test-unmatched:0": Decision(action="exclude")}
    require_resolved(build_document(source_state, config))


def test_first_entry_policy_keeps_saved_choices_glosses_and_inclusion_rules(source_state, consonant_review):
    config = ProjectConfig(
        passage="1:1-3:1",
        selection="all",
        gloss_selection="first-entry",
        known_entries=["step:test-choice"],
        decisions={
            "test-origin:0": Decision(entry_id="step:test-alternate", gloss="Synthetic edited gloss"),
            "test-prefix:0": Decision(action="exclude"),
        },
    )
    rows = {r["anchor"]: r for r in build_document(source_state, config).review}
    assert rows["test-origin:0"]["entry_id"] == "step:test-alternate"
    assert rows["test-origin:0"]["gloss"] == "Synthetic edited gloss"
    assert rows["test-origin:0"]["choice_method"] == "decision"
    assert rows["test-origin:0"]["selected"]
    assert not rows["test-prefix:0"]["selected"]
    assert rows["test-different:0"]["reason"] == "Known-word list"
    changed, _ = edit_decision(
        source_state, config, "test-aramaic:0", Decision(gloss="Synthetic default edit"), "occurrence"
    )
    edited = next(r for r in build_document(source_state, changed).review if r["anchor"] == "test-aramaic:0")
    assert edited["entry_id"] == "step:test-choice" and edited["gloss"] == "Synthetic default edit"


def test_first_entry_policy_preserves_name_and_segment_omissions(source_state, name_review):
    document = build_document(
        source_state, ProjectConfig(passage="1:1", selection="all", gloss_selection="first-entry")
    )
    rows = {r["anchor"]: r for r in document.review}
    assert all(not row["selected"] for row in rows.values() if row["name_excluded"])
    assert rows["segmented-name:0"]["selected"]
    assert not rows["segmented-name:1"]["selected"]
    assert rows["lexicon-name:0"]["alignment_status"] == "ambiguous"
    assert rows["unmatched-common:0"]["status"] == "unmatched"


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
    monkeypatch.setattr(editorial, "load_lexicon", lambda _, book="Prov": (entries, crosswalk))
    document = build_document(source_state, ProjectConfig())
    candidate = next(r for r in document.review if r["anchor"] == row["anchor"])
    assert candidate["candidates"]
    assert candidate["entry_id"] is None
    assert candidate["status"] == "ambiguous"
    with pytest.raises(ReaderError, match="unresolved"):
        require_resolved(document)
    default_document = build_document(source_state, ProjectConfig(gloss_selection="first-entry"))
    default_row = next(r for r in default_document.review if r["anchor"] == row["anchor"])
    assert default_row["entry_id"] == candidate["candidates"][0]["id"]
    assert default_row["alignment_status"] == "ambiguous"
    assert default_row["choice_method"] == "first-entry"
    assert default_row["method"] == "base ID candidates; first listed source entry (project default)"
    require_resolved(default_document)


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


@pytest.mark.parametrize("selection", ["all", "book-frequency"])
def test_genuine_names_are_omitted_and_retained_in_review(source_state, selection):
    config = ProjectConfig(passage="1:1", selection=selection, frequency_max=100000)
    document = build_document(source_state, config)
    rows = {row["anchor"]: row for row in document.review}
    for anchor in ["20Nvk:0", "20vuQ:0", "20k5P:0"]:
        row = rows[anchor]
        assert row["name_excluded"] and row["candidates"]
        assert not row["selected"]
        assert row["reason"] == "Proper name omitted (OSHB Np morphology)"
        assert row["label"] is None and row["help_id"] is None
        assert not next(token for token in document.verses[0]["tokens"] if token["id"] == row["token_id"])[
            "helps"
        ]
        assert all(help["entry_id"] != row["entry_id"] for help in document.helps.values())
    assert any(row["selected"] and not row["name_excluded"] for row in rows.values())
    assert [token["source_surface"] for token in document.verses[0]["tokens"]] == [
        token.surface for token in editorial.load_book(source_state, "Prov")[0].tokens
    ]


def test_existing_inclusion_does_not_reintroduce_names(source_state):
    config = ProjectConfig(
        passage="1:1",
        selection="all",
        decisions={"20Nvk:0": Decision(entry_id="step:H8010", gloss="Synthetic name override")},
    )
    before = config.model_dump()
    document = build_document(source_state, config)
    name = next(row for row in document.review if row["anchor"] == "20Nvk:0")
    assert not name["selected"] and name["name_excluded"]
    assert name["gloss"] == "Synthetic name override"
    assert not any(help["entry_id"] == "step:H8010" for help in document.helps.values())
    assert config.model_dump() == before


@pytest.mark.parametrize(
    "morphology,expected",
    [
        ("N:N-M-P", True),
        ("N:N--L", True),
        ("N:N--T", True),
        ("N:N--LG / N:N-M-P", True),
        ("H:N-M / N:N--T", False),
        ("H:N-M/F", False),
        ("A:N-F", False),
        ("", False),
    ],
)
def test_name_metadata_never_guesses_from_gloss_or_spelling(morphology, expected):
    assert is_name_morphology(morphology) is expected


def test_name_exclusion_preserves_ambiguities_missing_matches_and_component_identity(
    source_state, name_review
):
    raw = [verse.json() for verse in name_review]
    config = ProjectConfig(
        passage="1:1",
        selection="all",
        decisions={"chosen-name:0": Decision(entry_id="step:test-name")},
    )
    document = build_document(source_state, config)
    rows = {row["anchor"]: row for row in document.review}
    for anchor in [
        "name-by-source:0",
        "unmatched-name:0",
        "lexicon-name:0",
        "chosen-name:0",
        "segmented-name:1",
        "arc-prefixed-name:0",
    ]:
        assert rows[anchor]["name_excluded"] and not rows[anchor]["selected"]
        assert rows[anchor]["label"] is None and rows[anchor]["help_id"] is None
    assert rows["unmatched-name:0"]["status"] == "unmatched"
    assert rows["lexicon-name:0"]["status"] == "ambiguous"
    assert rows["common-by-source:0"]["selected"] and rows["common-by-source:0"]["status"] == "ambiguous"
    assert rows["unmatched-common:0"]["selected"] and rows["unmatched-common:0"]["status"] == "unmatched"
    assert rows["segmented-name:0"]["selected"] and not rows["segmented-name:0"]["name_excluded"]
    assert rows["segmented-name:0"]["lexical_morphology"] == "HNcmsc"
    assert rows["segmented-name:1"]["lexical_morphology"] == "HNp"
    assert rows["normal-spelling:0"]["selected"]
    with pytest.raises(ReaderError, match="unresolved"):
        require_resolved(document)
    config.decisions.update(
        {
            row["anchor"]: Decision(action="exclude")
            for row in document.review
            if row["selected"] and row["status"] != "resolved"
        }
    )
    require_resolved(build_document(source_state, config))
    assert [verse.json() for verse in name_review] == raw


def test_book_inclusion_skips_source_name_homographs(source_state, name_review):
    config = ProjectConfig(passage="1:1", selection="all")
    changed, report = edit_decision(
        source_state, config, "common-by-source:0", Decision(entry_id="step:test-common"), "book"
    )
    assert "name-by-source:0" not in changed.decisions
    assert {item["anchor"]: item["reason"] for item in report["skipped"]}["name-by-source:0"] == (
        "Names are excluded from lexical helps"
    )
    assert set(report["applied"]) == {"common-by-source:0", "chosen-name:0", "normal-spelling:0"}


@pytest.mark.parametrize(
    "raw,expected",
    [("שָׁ/מַ֖ר", "שמר"), ("שֻׂמֵּֽר־׃", "שמר"), ("וְ/שָׁמַר", "ושמר"), ("מֶלֶךְ", "מלך"), ("α\u0301", "α\u0301")],
)
def test_consonant_key_uses_whole_spelling_without_normalizing_other_scripts(raw, expected):
    assert consonant_key(raw) == expected


def test_edit_defaults_to_one_anchor_without_mutating_config(source_state, consonant_review):
    config = ProjectConfig(passage="1:1", selection="all")
    decision = Decision(entry_id="step:test-choice")
    changed, report = edit_decision(source_state, config, "test-origin:0", decision, "occurrence")
    assert changed.decisions == {"test-origin:0": decision}
    assert not config.decisions
    assert report == {"consonants": "שמר", "applied": ["test-origin:0"], "skipped": []}
    rows = {r["anchor"]: r for r in build_document(source_state, changed).review}
    assert rows["test-origin:0"]["status"] == "resolved"
    assert rows["test-origin:0"]["word_occurrences"] == 7
    assert rows["test-prefix:0"]["status"] == "ambiguous"


def test_bulk_edit_matches_whole_book_and_preserves_unsupported_source_choices(
    source_state, consonant_review
):
    original_sources = [verse.json() for verse in consonant_review]
    preserved = Decision(entry_id="step:test-other", gloss="Synthetic existing gloss")
    config = ProjectConfig(
        passage="1:1",
        selection="all",
        readings="qere",
        decisions={
            "test-repeat:0": Decision(action="exclude"),
            "test-homograph:0": preserved,
        },
    )
    decision = Decision(entry_id="step:test-choice", gloss="Synthetic editorial gloss", reason="Bulk test")
    changed, report = edit_decision(source_state, config, "test-origin:0", decision, "book")
    expected = {"test-origin:0", "test-repeat:0", "test-ketiv:0", "test-qere:0", "test-segmented:0"}
    assert set(report["applied"]) == expected
    assert {r["anchor"] for r in report["skipped"]} == {
        "test-segmented:1",
        "test-homograph:0",
        "test-unmatched:0",
    }
    assert all(changed.decisions[anchor] == decision for anchor in expected)
    assert changed.decisions["test-homograph:0"] == preserved
    assert set(changed.decisions) == expected | {"test-homograph:0"}
    assert config.decisions["test-repeat:0"].action == "exclude"
    assert [verse.json() for verse in consonant_review] == original_sources
    assert changed.passage == "1:1" and changed.readings == "qere"
    changed.passage = "1:1-3:1"
    document = build_document(source_state, changed)
    rows = {r["anchor"]: r for r in document.review}
    assert "test-ketiv:0" not in rows
    assert all(rows[a]["status"] == "resolved" and rows[a]["selected"] for a in expected - {"test-ketiv:0"})
    assert rows["test-unmatched:0"]["status"] == "unmatched"
    assert rows["test-homograph:0"]["gloss"] == preserved.gloss
    assert document.helps[rows["test-repeat:0"]["help_id"]]["editorial"]
    with pytest.raises(ReaderError, match="unresolved"):
        require_resolved(document)


def test_bulk_omission_can_explicitly_exclude_unmatched_and_ambiguous_words(source_state, consonant_review):
    config = ProjectConfig(passage="1:1", selection="all")
    changed, report = edit_decision(source_state, config, "test-origin:0", Decision(action="exclude"), "book")
    assert len(report["applied"]) == 8
    assert not report["skipped"]
    changed.passage = "1:1-3:1"
    rows = build_document(source_state, changed).review
    assert all(
        not r["selected"] for r in rows if r["consonants"] == "שמר" and r["anchor"] != "test-aramaic:0"
    )
    assert next(r for r in rows if r["anchor"] == "test-aramaic:0")["selected"]


@pytest.mark.parametrize("scope", ["occurrence", "book"])
def test_unmatched_gloss_is_an_explicit_editorial_help(source_state, unmatched_review, scope):
    raw = [verse.json() for verse in unmatched_review]
    config = ProjectConfig(passage="3:1-4:1", selection="all", lexicon_appendix=True)
    decision = Decision(gloss="Synthetic editorial proposal", reason="Manual missing-source help")
    changed, report = edit_decision(source_state, config, "test-unmatched:0", decision, scope)
    expected = {"test-unmatched:0"}
    if scope == "book":
        expected.add("test-unmatched-repeat:0")
        assert "test-unmatched-homograph:0" in {row["anchor"] for row in report["skipped"]}
        assert "test-unmatched-name:0" in {row["anchor"] for row in report["skipped"]}
    assert set(report["applied"]) == expected
    assert set(changed.decisions) == expected
    document = build_document(source_state, changed)
    rows = {row["anchor"]: row for row in document.review}
    for anchor in expected:
        row = rows[anchor]
        assert row["status"] == "editorial" and row["alignment_status"] == "unmatched"
        assert row["entry_id"] is None and row["candidates"] == []
        assert row["choice_method"] == "editorial" and row["gloss"] == decision.gloss
        help = document.helps[row["help_id"]]
        assert help["editorial"] and help["source"] == "Editorial proposal; source word form"
        assert help["headword"] == row["source_surface"].replace("/", "")
    assert any(entry["editorial"] and entry["entry_id"] is None for entry in document.lexicon_appendix)
    changed.cantillation = "consonants-only"
    assert build_document(source_state, changed).helps == document.helps
    # Other gaps still block publication; a proposal never chooses their sources.
    with pytest.raises(ReaderError, match="unresolved"):
        require_resolved(document)
    assert [verse.json() for verse in unmatched_review] == raw
    assert not config.decisions


@pytest.mark.parametrize(
    "anchor,decision,scope,message",
    [
        ("absent:0", Decision(entry_id="step:test-choice"), "book", "missing source anchor"),
        ("test-origin:0", Decision(entry_id="step:test-other"), "book", "incompatible"),
        ("test-origin:0", Decision(), "book", "Choose a source entry"),
        ("test-origin:0", Decision(gloss="Synthetic proposal"), "occurrence", "Choose a source entry"),
        ("test-origin:0", Decision(), "invalid", "Choose this occurrence"),
    ],
)
def test_invalid_bulk_choices_do_not_change_config(
    source_state, consonant_review, anchor, decision, scope, message
):
    config = ProjectConfig(passage="1:1", selection="all")
    with pytest.raises(ReaderError, match=message):
        edit_decision(source_state, config, anchor, decision, scope)
    assert not config.decisions


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
        {"cantillation": "unknown"},
    ],
)
def test_config_validation(values):
    with pytest.raises(ValidationError):
        ProjectConfig(**values)


def test_valid_passage_and_layout():
    assert parse_passage("2:1–12") == ((2, 1), (2, 12))
    assert parse_passage("1:29-2:12") == ((1, 29), (2, 12))
    assert Layout().body_pt == 18
