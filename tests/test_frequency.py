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
    for other in codes:
        path, asset = sources.book_artifact(tmp_path, other)
        path.parent.mkdir(parents=True, exist_ok=True)
        if source == "rahlfs":
            data = "\n".join(
                f"{info['books'][code]['source_book']}\t1\t1\tα<S>1</S><m>lxx.N</m><S>3056</S>"
                for code in codes
            )
        else:
            data = f"{info['books'][other]['source_book']:02d}0101 N- -------- α α α {lemma}"
        path.write_bytes(data.encode())
        asset["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    counts, provenance = frequency.corpus_frequencies(tmp_path, code, Counter({("grc", keys[0]): 1}))
    assert counts == {("grc", keys[0]): 2}
    assert set(provenance["books"]) == set(codes)


@pytest.fixture
def lxx_frequency_state(greek_state):
    info = sources.catalog()
    codes = {"LXXGen", "LXXProv", "LXXOd", "LXXDanOG", "LXXDanTh"}
    info["books"] = {
        code: item for code, item in info["books"].items() if item.get("source") != "rahlfs" or code in codes
    }
    return greek_state


def test_lxx_corpus_parses_shared_artifact_once_and_reuses_across_books_and_witnesses(
    lxx_frequency_state, monkeypatch
):
    state = lxx_frequency_state
    per_book = {
        code: frequency.lemma_frequencies(sources.load_book(state, code))
        for code in ("LXXGen", "LXXProv", "LXXOd", "LXXDanOG", "LXXDanTh")
    }
    main = sum((counts for code, counts in per_book.items() if code != "LXXDanTh"), Counter())
    alternate = main - per_book["LXXDanOG"] + per_book["LXXDanTh"]
    calls = Counter()
    read_verified, iter_rahlfs = sources.read_verified, frequency.iter_rahlfs

    def read(path, checksum):
        calls[path.name] += 1
        return read_verified(path, checksum)

    def parse(*args):
        calls["parse"] += 1
        return iter_rahlfs(*args)

    monkeypatch.setattr(sources, "read_verified", read)
    monkeypatch.setattr(frequency, "iter_rahlfs", parse)
    # Start with an alternate: the excluded main book must also be cached for
    # subsequent main-witness reviews without counting both parallel witnesses.
    for code, expected in [("LXXDanTh", alternate), ("LXXProv", main), ("LXXGen", main)]:
        counts, provenance = frequency.corpus_frequencies(state, code, per_book[code])
        assert counts == expected
        assert ("LXXDanTh" in provenance["books"]) == (code == "LXXDanTh")
        assert ("LXXDanOG" in provenance["books"]) == (code != "LXXDanTh")
        assert set(provenance["artifacts"]) == set(provenance["books"])
        counts.clear()  # Returning a total must not expose mutable cached counters.
    assert calls == {"LXX-main.csv": 3, "LXX-alternate.csv": 1, "parse": 1}


@pytest.mark.parametrize("filename", ["LXX-main.csv", "LXX-alternate.csv"])
def test_lxx_corpus_verifies_cached_and_selected_artifacts_and_requires_complete_inputs(
    lxx_frequency_state, filename
):
    state = lxx_frequency_state
    selected = frequency.lemma_frequencies(sources.load_book(state, "LXXDanTh"))
    frequency.corpus_frequencies(state, "LXXDanTh", selected)
    path = state / "raw/greek" / filename
    path.write_bytes(b"corrupt cached source")
    with pytest.raises(ReaderError, match="checksum mismatch"):
        frequency.corpus_frequencies(state, "LXXDanTh", selected)
    path.unlink()
    with pytest.raises(ReaderError, match="missing:.*--corpus rahlfs"):
        frequency.corpus_frequencies(state, "LXXDanTh", selected)


def test_lxx_corpus_cache_uses_artifact_checksum_and_state(lxx_frequency_state, tmp_path):
    state = lxx_frequency_state
    selected = frequency.lemma_frequencies(sources.load_book(state, "LXXProv"))
    counts, _ = frequency.corpus_frequencies(state, "LXXProv", selected)
    path = state / "raw/greek/LXX-main.csv"
    # An explicitly synthetic extra frequency record represents a new artifact revision.
    data = path.read_bytes().rstrip(b"\n") + "\n10\t999\t1\tα<S>1</S><m>lxx.N</m><S>9999</S>\n".encode()
    path.write_bytes(data)
    checksum = hashlib.sha256(data).hexdigest()
    for item in sources.catalog()["books"].values():
        if item.get("source") == "rahlfs" and item["witness"] == "main":
            item["artifact"]["sha256"] = checksum
    revised, provenance = frequency.corpus_frequencies(state, "LXXProv", selected)
    assert revised == counts + Counter({("grc", "G9999"): 1})
    assert set(provenance["artifacts"].values()) == {checksum}

    other_state = tmp_path / "other-state"
    other_path = other_state / "raw/greek/LXX-main.csv"
    other_path.parent.mkdir(parents=True)
    # A matching checksum must not bypass validation of a different workspace.
    other_path.write_bytes(b"corrupt source in another workspace")
    with pytest.raises(ReaderError, match="checksum mismatch"):
        frequency.corpus_frequencies(other_state, "LXXProv", selected)


def test_lxx_corpus_rejects_books_missing_from_a_shared_artifact(lxx_frequency_state):
    state = lxx_frequency_state
    selected = frequency.lemma_frequencies(sources.load_book(state, "LXXProv"))
    frequency.corpus_frequencies(state, "LXXProv", selected)
    sources.catalog()["books"]["LXXGen"]["source_book"] = 999
    with pytest.raises(ReaderError, match="No Rahlfs records found for LXXGen"):
        frequency.corpus_frequencies(state, "LXXProv", selected)


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
