import hashlib
import json
import shutil
from pathlib import Path

import pytest

from bible_reader import editorial, service, sources, tex
from bible_reader.models import Entry, Token, Verse

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def source_state(tmp_path, monkeypatch):
    """Use explicitly identified excerpts; never claim their hashes are the full source's."""
    state = tmp_path / "state"
    raw = state / "raw"
    raw.mkdir(parents=True)
    provenance = json.loads((FIXTURES / "provenance.json").read_text())
    for name, expected in provenance["files"].items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == expected
        shutil.copyfile(FIXTURES / name, raw / name)
    info = sources.catalog()
    info["books"]["Prov"]["sha256"] = provenance["files"]["Prov.xml"]
    info["lexicon"]["sha256"] = provenance["files"]["TBESH.txt"]
    for module in (sources, editorial, service, tex):
        monkeypatch.setattr(module, "catalog", lambda: info)
    return state


@pytest.fixture
def tex_available():
    try:
        return tex.engine_path()
    except sources.ReaderError:
        pytest.skip("Install XeLaTeX with scripts/bootstrap.sh to run PDF integration checks")


@pytest.fixture
def consonant_review(source_state, monkeypatch):
    """Synthetic spellings/candidates for bulk editing, not evidence for biblical readings."""
    entries = {
        identity: Entry(identity, "", "", "", f"Synthetic {identity}", "")
        for identity in ("step:test-choice", "step:test-alternate", "step:test-other")
    }
    candidates = ["step:test-choice", "step:test-alternate"]
    crosswalk = {
        "H1001": candidates,
        "H1002": candidates,
        "H1003": ["step:test-other", "step:test-alternate"],
        "H2000": ["step:test-other"],
    }
    book = [
        Verse(
            "Prov",
            1,
            1,
            (
                Token("test-origin", "שָׁ/מַ֖ר", "1001"),
                Token("test-prefix", "וְ/שָׁמַר", "1001"),
                Token("test-different", "שָׁמְרוּ", "1001"),
                Token("test-aramaic", "שָׁמַר", "1001", language="arc"),
            ),
        ),
        Verse("Prov", 2, 1, (Token("test-repeat", "שֹׁמֵֽר", "1002"),)),
        Verse(
            "Prov",
            3,
            1,
            (
                Token("test-ketiv", "שַׁמֵּר", "1001", reading="ketiv"),
                Token("test-qere", "שֻׂמַר", "1001", reading="qere"),
                Token("test-segmented", "שָׁ/מַר", "1001 2000"),
                Token("test-homograph", "שָׂמַר", "1003"),
                Token("test-unmatched", "שְמֹר", "9999"),
            ),
        ),
    ]
    monkeypatch.setattr(editorial, "load_book", lambda *_: book)
    monkeypatch.setattr(editorial, "load_lexicon", lambda _, book="Prov": (entries, crosswalk))
    return book


@pytest.fixture
def unmatched_review(consonant_review):
    """Synthetic missing-source repeats, homographs, names, and language boundaries."""
    consonant_review.append(
        Verse(
            "Prov",
            4,
            1,
            (
                Token("test-unmatched-repeat", "שְמֹר", "9999"),
                Token("test-unmatched-homograph", "שְמֹר", "9998"),
                Token("test-unmatched-name", "שְמֹר", "9999", morph="HNp"),
                Token("test-unmatched-aramaic", "שְמֹר", "9999", language="arc"),
            ),
        )
    )
    return consonant_review


@pytest.fixture
def name_review(source_state, monkeypatch):
    """Synthetic source classifications; no proposed biblical readings or lexical senses."""
    entries = {
        identity: Entry(identity, "", "", morphology, "Synthetic classification gloss", "")
        for identity, morphology in [
            ("step:test-common", "H:N-M"),
            ("step:test-name", "N:N-M-P"),
            ("step:test-other-name", "N:N--L"),
        ]
    }
    crosswalk = {
        "H1001": ["step:test-common", "step:test-name"],
        "H1002": ["step:test-name", "step:test-other-name"],
        "H1003": ["step:test-name"],
        "H1004": ["step:test-common"],
    }
    book = [
        Verse(
            "Prov",
            1,
            1,
            (
                Token("name-by-source", "שָׁם", "1001", "HNp"),
                Token("common-by-source", "שָׁם", "1001", "HNcmsa"),
                Token("unmatched-name", "שֵׁם", "9999", "HNp"),
                Token("unmatched-common", "שֵׁם", "9998", "HNcmsa"),
                Token("lexicon-name", "שֵׁם", "1002", "HNcmsa"),
                Token("chosen-name", "שָׁם", "1001", "HNcmsa"),
                Token("segmented-name", "דָּבָר/שֵׁם", "1004/1003", "HNcmsc/Np"),
                Token("normal-spelling", "שָׁם", "1004", "HNcmsa"),
                Token("arc-prefixed-name", "בְּ/שָׁם", "b/1004", "AR/Np", language="arc"),
            ),
        )
    ]
    monkeypatch.setattr(editorial, "load_book", lambda *_: book)
    monkeypatch.setattr(editorial, "load_lexicon", lambda _, book="Prov": (entries, crosswalk))
    return book


@pytest.fixture
def greek_state(tmp_path, monkeypatch):
    greek_fixtures = FIXTURES / "greek"
    state = tmp_path / "state"
    raw = state / "raw/greek"
    raw.mkdir(parents=True)
    info = sources.catalog()
    for name in [
        "TBESG.txt",
        "gntLookups.js",
        "GreekWordList.js",
        "LXX-main.csv",
        "LXX-alternate.csv",
        "SBLGNT-README.md",
        "RAHLFS-README.md",
        "README.md",
        "SBLGNT-license.html",
    ]:
        shutil.copyfile(greek_fixtures / name, raw / name)
    for code, name in [("John", "John.txt"), ("Mark", "Mark16.txt")]:
        shutil.copyfile(greek_fixtures / name, raw / info["books"][code]["artifact"]["filename"])
    for selected in info["books"].values():
        if selected.get("language") != "grc":
            continue
        asset = selected["artifact"]
        path = raw / asset["filename"]
        if path.exists():
            asset["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for asset in [info["greek"]["lexicon"], *info["greek"]["crosswalk"]["assets"]]:
        asset["sha256"] = hashlib.sha256((raw / asset["filename"]).read_bytes()).hexdigest()
    for module in [sources, editorial, service, tex]:
        monkeypatch.setattr(module, "catalog", lambda: info)
    return state


@pytest.fixture
def frequency_state(source_state, monkeypatch):
    info = sources.catalog()
    for code, words in {
        "Prov": '<w id="a" lemma="1001">א</w><w id="b" lemma="1001 a">ב</w>',
        "Gen": (
            '<w id="c" lemma="1001">ג</w>'
            '<w id="k" lemma="1001" type="x-ketiv">ד</w>'
            '<note type="variant"><rdg type="x-qere"><w id="q" lemma="1001">ה</w></rdg></note>'
            '<w id="arc" lemma="1001" morph="ANcmsa">ו</w>'
        ),
    }.items():
        data = f'<verse osisID="{code}.1.1">{words}</verse>'.encode()
        (source_state / "raw" / f"{code}.xml").write_bytes(data)
        info["books"][code]["sha256"] = hashlib.sha256(data).hexdigest()
    # A complete, explicitly synthetic two-book OSHB corpus. Other corpora remain
    # cataloged but uninstalled to catch accidental cross-corpus requirements.
    info["books"] = {
        k: v for k, v in info["books"].items() if k in {"Prov", "Gen"} or v.get("language") == "grc"
    }
    monkeypatch.setattr("bible_reader.web.app.catalog", lambda: info)
    entries = {
        key: Entry(key, "א", "", "H:N", "Synthetic gloss", "") for key in ("step:test", "step:homograph")
    }
    monkeypatch.setattr(
        editorial,
        "load_lexicon",
        lambda *_: (entries, {"H1001": ["step:test"], "H1001a": ["step:homograph"]}),
    )
    return source_state
