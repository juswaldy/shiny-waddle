import hashlib
import json
import shutil
from pathlib import Path

import pytest

from bible_reader import editorial, sources, tex
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
    for module in (sources, editorial, tex):
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
    monkeypatch.setattr(editorial, "load_lexicon", lambda _: (entries, crosswalk))
    return book
