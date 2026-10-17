import hashlib
import json
from pathlib import Path

import pytest

from bible_reader import editorial
from bible_reader.book_helps import load_book_helps, save_book_helps
from bible_reader.greek import morphgnt_crosswalk, parse_morphgnt, parse_rahlfs, parse_tbesg
from bible_reader.models import Decision, ProjectConfig, ReaderError

FIXTURES = Path(__file__).parent / "fixtures/greek"


def test_greek_projects_align_offline_preserve_surfaces_and_round_trip_helps(greek_state):
    config = ProjectConfig(book="John", passage="1:1-18", selection="all")
    document = editorial.build_document(greek_state, config)
    assert document.sources["language"] == "grc" and document.sources["direction"] == "ltr"
    assert len(document.review) == sum(t["kind"] == "word" for v in document.verses for t in v["tokens"])
    assert all(t["surface"] == t["source_surface"] for v in document.verses for t in v["tokens"])
    assert any(row["name_excluded"] for row in document.review)
    assert all(row["entry_id"].startswith("step-greek:") for row in document.review if row["entry_id"])
    row = next(r for r in document.review if r["selected"] and r["entry_id"])
    config, result = editorial.edit_decision(
        greek_state,
        config,
        row["anchor"],
        Decision(entry_id=row["entry_id"], gloss="Editorial Greek gloss"),
        "book",
    )
    assert row["anchor"] in result["applied"]
    saved = save_book_helps(greek_state, config)
    assert saved.sources.text_source == "sblgnt" and saved.sources.crosswalk_sha256
    assert load_book_helps(greek_state, config, saved) == config
    config.cantillation = "consonants-only"
    assert [
        t["surface"] for v in editorial.build_document(greek_state, config).verses for t in v["tokens"]
    ] == [t["surface"] for v in document.verses for t in v["tokens"]]


def test_lxx_missing_lexical_links_stay_explicit_and_verse_zero_is_addressable(greek_state):
    config = ProjectConfig(book="LXXGen", passage="1:1-2", selection="all")
    document = editorial.build_document(greek_state, config)
    missing = next(r for r in document.review if r["surface"] == "ἀκατασκεύαστος")
    assert missing["status"] == "unmatched" and missing["selected"] and not missing["candidates"]
    with pytest.raises(ReaderError, match="unresolved"):
        editorial.require_resolved(document)
    odes = editorial.build_document(greek_state, ProjectConfig(book="LXXOd", passage="1:0", selection="all"))
    assert odes.verses[0]["verse"] == 0
    assert "MyBible" in document.sources["text"]["versification"]
    with pytest.raises(ReaderError, match="checksum"):
        (greek_state / "raw/greek/TBESG.txt").write_text("changed")
        editorial.build_document(greek_state, config)


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


@pytest.mark.integration
@pytest.mark.parametrize("verse_layout", ["continuous", "verse-per-line"])
def test_greek_pdf_has_embedded_fonts_same_page_notes_and_clear_chapter_inset(
    greek_state, tmp_path, tex_available, verse_layout
):
    import zipfile

    from pypdf import PdfReader

    from bible_reader.service import build

    config = ProjectConfig(
        book="John",
        passage="1:1-18",
        selection="all",
        lexicon_appendix=True,
        layout={"verse_layout": verse_layout},
    )
    document = editorial.build_document(greek_state, config)
    config.decisions = {
        r["anchor"]: Decision(
            action="exclude", reason="Typography fixture: unresolved help explicitly excluded"
        )
        for r in document.review
        if r["selected"] and r["status"] != "resolved"
    }
    output = tmp_path / "greek-pdf"
    result = build(greek_state, config, output)
    assert result["fonts_embedded"] and result["pdf_marker_destinations"] == "verified"
    assert result["reader_pages"] >= 2 and result["appendix_pages"] == 1
    pdf = PdfReader(output / "reader.pdf")
    assert "Ἐν" in pdf.pages[0].extract_text() and "λόγος" in pdf.pages[0].extract_text()
    if verse_layout == "continuous":
        runs = []

        def collect(text, cm, tm, font, size):
            if (
                text.strip()
                and "GentiumPlus" in font["/BaseFont"]
                and size == pytest.approx(18 * 72 / 72.27, abs=0.01)
            ):
                runs.append(
                    (cm[0] * tm[4] + cm[2] * tm[5] + cm[4], round(cm[1] * tm[4] + cm[3] * tm[5] + cm[5], 1))
                )

        pdf.pages[0].extract_text(visitor_text=collect)
        baselines = sorted({y for _, y in runs}, reverse=True)
        # The chapter box occupies the first two lines. Check real PDF glyph
        # positions, including wrapped words, rather than just TeX strings.
        assert len(baselines) >= 2
        for baseline in baselines[:2]:
            assert min(x for x, y in runs if y == baseline) >= (10 + 14) * 72 / 25.4 - 0.2
    with zipfile.ZipFile(output / "reader-bundle.zip") as bundle:
        assert b"SIL OPEN FONT LICENSE" in bundle.read("GentiumPlus-LICENSE.txt")
        assert bundle.read("reader-greek.ttf")
        assert bundle.read("SBLGNT-README.md")
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["font"] == "Gentium Plus" and manifest["greek_font_sha256"]
