import hashlib
import json
import shutil
from pathlib import Path

import pytest

from bible_reader import editorial, sources, tex

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
