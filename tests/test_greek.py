import hashlib
import json
from pathlib import Path

import pytest

from bible_reader.greek import morphgnt_crosswalk, parse_morphgnt, parse_rahlfs, parse_tbesg
from bible_reader.models import ReaderError

FIXTURES = Path(__file__).parent / "fixtures/greek"


def test_greek_fixtures_are_attributable_and_unchanged():
    provenance = json.loads((FIXTURES / "provenance.json").read_text())
    for name, expected in provenance["files"].items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == expected


def test_morphgnt_retains_all_columns_punctuation_and_stable_positions():
    verses = parse_morphgnt((FIXTURES / "John.txt").read_bytes(), "John", 4)
    assert len(verses) == 18
    first = verses[0].tokens[0]
    assert (first.surface, first.lemma, first.morph, first.language) == ("Ἐν", "ἐν", "P- --------", "grc")
    assert first.id == "sblgnt:040101:1" and first.lexical_keys == ("morphgnt:ἐν",)
    assert verses[0].tokens[4].surface == "λόγος,"
    assert first.source_record.split() == ["040101", "P-", "--------", "Ἐν", "Ἐν", "ἐν", "ἐν"]
    assert len({t.id for v in verses for t in v.tokens}) == sum(len(v.tokens) for v in verses)
    mark = parse_morphgnt((FIXTURES / "Mark16.txt").read_bytes(), "Mark", 2)
    assert any("⟦" in t.surface or "⟧" in t.surface for v in mark for t in v.tokens)


@pytest.mark.parametrize(
    "data", [b"bad", "040101 P- -------- Ἐν Ἐν ἐν ἐν\n030101 P- -------- Ἐν Ἐν ἐν ἐν".encode()]
)
def test_morphgnt_rejects_bad_rows_and_wrong_source_book(data):
    with pytest.raises(ReaderError):
        parse_morphgnt(data, "John", 4)


def test_rahlfs_keeps_missing_links_morph_spaces_markers_zero_and_witness_order():
    data = (FIXTURES / "LXX-main.csv").read_bytes()
    gen = parse_rahlfs(data, "LXXGen", 10)
    assert gen[0].tokens[0].surface == "ἐν"
    assert gen[0].tokens[0].lexical_keys == ("G1722",)
    missing = next(t for t in gen[1].tokens if t.surface == "ἀκατασκεύαστος")
    assert missing.lexical_keys == (missing.lemma,)
    assert any(t.morph == "lxx.N.N M" for t in gen[-1].tokens)
    dan = parse_rahlfs(data, "LXXDanOG", 340)
    assert [v.verse for v in dan] == [12, 11]  # Actual artifact order, not silently sorted.
    odes = parse_rahlfs(data, "LXXOd", 800)
    assert odes[0].verse == 0
    assert odes[0].tokens[0].source_record
    prov = parse_rahlfs(data, "LXXProv", 240)
    assert any(t.kind == "source-marker" for v in prov for t in v.tokens)
    alternate = parse_rahlfs((FIXTURES / "LXX-alternate.csv").read_bytes(), "LXXDanTh", 340, "alternate")
    assert [v.verse for v in alternate] == [55, 54]
    assert not {t.id for v in dan for t in v.tokens} & {t.id for v in alternate for t in v.tokens}


def test_rahlfs_rejects_unknown_markup_and_duplicate_references():
    # Explicit synthetic format hazards, not source readings.
    row = "10\t1\t1\tα<S>700001</S><m>lxx.N</m>"
    for data in [row + "<unknown/>", row + "\n" + row]:
        with pytest.raises(ReaderError):
            parse_rahlfs(data.encode(), "LXXGen", 10)


def test_greek_lexicon_and_published_crosswalk_keep_candidates_and_gaps():
    entries, mapping = parse_tbesg((FIXTURES / "TBESG.txt").read_bytes())
    crosswalk = morphgnt_crosswalk(
        (FIXTURES / "gntLookups.js").read_bytes(), (FIXTURES / "GreekWordList.js").read_bytes(), mapping
    )
    assert entries[crosswalk["morphgnt:λόγος"][0]].gloss == "word"
    assert all(e.id.startswith("step-greek:") and e.definition == "" for e in entries.values())
    # A missing spelling never receives a guessed entry, even with a similar word present.
    assert "morphgnt:λογος" not in crosswalk
    assert morphgnt_crosswalk(b'gntLookups={"a":"x"}', b'greekWordList={"x":{"strong":"32a"}}', mapping) == {}
    with pytest.raises(ReaderError):
        morphgnt_crosswalk(b"gntLookups=evil()", b"greekWordList={}", mapping)
