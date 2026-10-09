import hashlib
from dataclasses import asdict

import pytest
from conftest import FIXTURES

from bible_reader.models import ReaderError
from bible_reader.sources import acquire, lemma_keys, parse_oshb, parse_tbesh, read_verified


def test_real_source_preserves_unicode_segments_and_readings():
    verses = parse_oshb((FIXTURES / "Prov.xml").read_bytes(), "Prov")
    assert len(verses) == 55
    words = {t.id: t for v in verses for t in v.tokens}
    assert words["20jyT"].reading == "ketiv"
    assert words["20Unh"].reading == "qere"
    assert words["20jyT"].surface != words["20Unh"].surface
    assert any("/" in t.surface for t in words.values())
    assert any(t.kind == "x-maqqef" and t.surface == "־" for t in words.values())
    assert any("\u0591" <= c <= "\u05af" for t in words.values() for c in t.surface)
    assert any(v.annotations for v in verses)
    assert len(words) == sum(len(v.tokens) for v in verses)


@pytest.mark.parametrize(
    "content",
    [
        '<verse osisID="Prov.1.1"><w id="a">א</w><w id="a">ב</w></verse>',
        '<verse osisID="Prov.1.1"><unknown>א</unknown></verse>',
        '<verse osisID="Gen.1.1"><w>א</w></verse>',
        '<verse osisID="Prov.1.1"/>',
        '<!DOCTYPE x [<!ENTITY a "hidden">]><verse osisID="Prov.1.1"><w>&a;</w></verse>',
    ],
)
def test_rejects_unknown_or_unsafe_xml(content):
    with pytest.raises(ReaderError):
        parse_oshb(content.encode(), "Prov")


def test_aramaic_and_qere_segments_are_preserved():
    # Explicit synthetic format fixture, not a textual reading.
    xml = '<verse osisID="Dan.1.1"><w id="a" lemma="1" morph="ANcmsa">א</w><note type="variant"><rdg type="x-qere"><w id="b" morph="ANcmsa">ב</w><seg type="x-maqqef">־</seg></rdg></note></verse>'
    verse = parse_oshb(xml.encode(), "Dan")[0]
    assert verse.tokens[0].language == "arc"
    assert verse.tokens[1].reading == verse.tokens[2].reading == "qere"
    assert verse.tokens[1].language == "arc"


def test_lexicon_retains_candidates_but_never_imports_meaning():
    data = "H0001\tH0001a\tH0001\tאָב\tav\tN\tfather\tRESTRICTED MEANING\nH0001\tH0001b\tH0001\tאָב\tav\tN\tancestor\tRESTRICTED MEANING\n"
    entries, mapping = parse_tbesh(data.encode())
    assert mapping["H0001"] == ["step:H0001a", "step:H0001b"]
    assert entries["step:H0001a"].gloss == "father"
    assert "RESTRICTED" not in str([asdict(e) for e in entries.values()])
    assert all(e.definition == "" for e in entries.values())
    with pytest.raises(ReaderError, match="Malformed"):
        parse_tbesh(b"H0001\tbad\n")


def test_extended_lemma_keys_keep_homograph_suffixes():
    assert lemma_keys("c/b/123 a/456") == ["H0123a", "H0456"]


def test_acquisition_is_atomic_pinned_and_cached(tmp_path):
    upstream = tmp_path / "upstream"
    upstream.write_bytes(b"verified")
    destination = tmp_path / "raw" / "source"
    asset = {"url": upstream.as_uri(), "sha256": hashlib.sha256(b"verified").hexdigest()}
    acquire(asset, destination)
    upstream.unlink()
    assert acquire(asset, destination).read_bytes() == b"verified"
    destination.write_bytes(b"changed")
    with pytest.raises(ReaderError, match="checksum"):
        read_verified(destination, asset["sha256"])


def test_bad_download_does_not_install_partial_source(tmp_path):
    upstream = tmp_path / "upstream"
    upstream.write_bytes(b"unexpected")
    destination = tmp_path / "raw" / "source"
    with pytest.raises(ReaderError, match="checksum"):
        acquire({"url": upstream.as_uri(), "sha256": "0" * 64}, destination)
    assert list(destination.parent.iterdir()) == []
