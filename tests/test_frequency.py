"""Synthetic lexical counts test policy, without proposing biblical content."""

import hashlib
from collections import Counter

import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from bible_reader import editorial, frequency, sources
from bible_reader.data_files import load_reader_data
from bible_reader.models import Decision, ProjectConfig, ReaderError, Token, Verse
from bible_reader.service import build


def test_old_projects_default_to_book_scope_and_invalid_scopes_fail():
    assert ProjectConfig(selection="book-frequency").frequency_scope == "book"
    with pytest.raises(ValidationError):
        ProjectConfig(frequency_scope="passage")


def test_named_corpora_separate_editions_and_replace_alternate_witnesses():
    hebrew = frequency.corpus_for_book("Prov")
    nt = frequency.corpus_for_book("John")
    ot = frequency.corpus_for_book("LXXProv")
    alternate = frequency.corpus_for_book("LXXJoshA")
    assert (hebrew["id"], len(hebrew["books"])) == ("oshb", 39)
    assert (nt["id"], len(nt["books"])) == ("sblgnt", 27)
    assert (ot["id"], len(ot["books"])) == ("rahlfs", 54)
    assert set(hebrew["books"]).isdisjoint(nt["books"] + ot["books"])
    assert set(alternate["books"]) == (set(ot["books"]) - {"LXXJoshB"}) | {"LXXJoshA"}
    assert "LXXDanTh" not in alternate["books"]


def test_corpus_threshold_language_homographs_overrides_and_portable_provenance(frequency_state):
    config = ProjectConfig(passage="1:1", selection="book-frequency", frequency_max=1, lexicon_appendix=True)
    book = editorial.build_document(frequency_state, config)
    assert [r["selected"] for r in book.review] == [True, True]
    config.frequency_scope = "corpus"
    corpus = editorial.build_document(frequency_state, config)
    assert [r["selected"] for r in corpus.review] == [False, True]
    assert [r["frequency"] for r in corpus.review] == [3, 1]  # No extra ketiv or Aramaic count.
    assert [r["book_frequency"] for r in corpus.review] == [1, 1]
    assert all(r["frequency_corpus"] == "Hebrew OT" for r in corpus.review)
    assert corpus.review[0]["reason"] == "Hebrew OT corpus frequency 3"
    assert [e["entry_id"] for e in corpus.lexicon_appendix] == ["step:homograph"]
    locked = corpus.sources["frequency_corpus"]
    assert locked["revision"] == sources.catalog()["oshb_revision"]
    assert set(locked["artifacts"]) == {"Prov", "Gen"}
    assert load_reader_data(corpus.json()).json() == corpus.json()
    config.frequency_max = 3
    assert all(r["selected"] for r in editorial.build_document(frequency_state, config).review)
    config.frequency_max = 1
    config.decisions = {"a:0": Decision(), "b:0": Decision(action="exclude")}
    overridden = editorial.build_document(frequency_state, config)
    assert [r["selected"] for r in overridden.review] == [True, False]
    config.decisions = {}
    config.known_entries = ["step:homograph"]
    assert not editorial.build_document(frequency_state, config).helps


def test_corpus_requires_complete_verified_inputs_even_after_counts_are_cached(frequency_state):
    config = ProjectConfig(passage="1:1", selection="book-frequency", frequency_scope="corpus")
    editorial.build_document(frequency_state, config)
    path = frequency_state / "raw/Gen.xml"
    path.write_bytes(b"corrupt cached source")
    with pytest.raises(ReaderError, match="checksum mismatch"):
        editorial.build_document(frequency_state, config)
    path.unlink()
    with pytest.raises(ReaderError, match="missing: Gen.*--corpus oshb"):
        editorial.build_document(frequency_state, config)
    config.frequency_scope = "book"
    assert editorial.build_document(frequency_state, config).helps
    config.frequency_scope = "corpus"
    config.selection = "all"
    assert editorial.build_document(frequency_state, config).helps


@pytest.mark.integration
def test_corpus_pdf_uses_selected_helps_and_names_the_frequency_scope(
    frequency_state, tmp_path, tex_available
):
    config = ProjectConfig(
        passage="1:1",
        selection="book-frequency",
        frequency_scope="corpus",
        frequency_max=1,
        lexicon_appendix=True,
    )
    output = tmp_path / "corpus-proof"
    result = build(frequency_state, config, output)
    assert result["errors"] == []
    assert result["help_count"] == result["appendix_entries"] == 1
    pdf = PdfReader(output / "reader.pdf")
    text = " ".join(" ".join(page.extract_text() for page in pdf.pages).split())
    assert "Maximum occurrences in the whole corpus (Hebrew OT): 1" in text


@pytest.mark.parametrize(
    "code,lemma,keys",
    [("John", "λόγος", ("morphgnt:λόγος",)), ("LXXProv", "rahlfs:1", ("G3056",))],
)
def test_greek_corpus_counts_use_source_keys_not_spelling_or_other_corpora(
    tmp_path, monkeypatch, code, lemma, keys
):
    info = sources.catalog()
    source = info["books"][code]["source"]
    codes = [k for k, v in info["books"].items() if v.get("source") == source][:2]
    if code not in codes:
        codes[0] = code
    info["books"] = {k: v for k, v in info["books"].items() if k in codes or v.get("source") != source}
    monkeypatch.setattr(sources, "catalog", lambda: info)
    tokens = (Token("a", "α", lemma, language="grc", lexical_keys=keys),)
    for other in codes:
        path, asset = sources.book_artifact(tmp_path, other)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic verified artifact")
        asset["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(sources, "load_book", lambda _, other: [Verse(other, 1, 1, tokens)])
    counts, provenance = frequency.corpus_frequencies(tmp_path, code, Counter({("grc", keys[0]): 1}))
    assert counts == {("grc", keys[0]): 2}
    assert set(provenance["books"]) == set(codes)


def test_frequency_counts_every_segment_but_preserves_language_and_extended_keys():
    tokens = (
        Token("segmented", "א/ב", "1001/1001 a"),
        Token("unmatched", "ג", "9999"),
        Token("arc", "ד", "1001", language="arc"),
        Token("separator", "־", "1001", kind="segment"),
    )
    assert frequency.lemma_frequencies([Verse("Prov", 1, 1, tokens)]) == {
        ("hbo", "H1001"): 1,
        ("hbo", "H1001a"): 1,
        ("hbo", "H9999"): 1,
        ("arc", "H1001"): 1,
    }
