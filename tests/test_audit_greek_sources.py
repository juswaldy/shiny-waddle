import importlib.util
import json
from pathlib import Path

import pytest

from bible_reader import sources
from bible_reader.models import ReaderError

SPEC = importlib.util.spec_from_file_location(
    "audit_greek_sources", Path(__file__).resolve().parents[1] / "scripts/audit_greek_sources.py"
)
audit_greek_sources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_greek_sources)


@pytest.fixture
def audit_state(greek_state, monkeypatch):
    info = sources.catalog()
    codes = ["Matt", "John", "Mark", "LXXGen", "LXXDanOG", "LXXDanTh"]
    info["greek"]["books"] = {code: info["books"][code] for code in codes}
    # Counts describe the attributable excerpts, not the complete upstream books.
    for code, selected in info["greek"]["books"].items():
        path, _ = sources.book_artifact(greek_state, code)
        if not path.exists():
            continue
        lines = path.read_text().splitlines()
        if selected["source"] == "sblgnt":
            selected["verse_count"] = len({line.split()[0] for line in lines})
            selected["word_count"] = len(lines)
        else:
            rows = [line for line in lines if line.split("\t")[0] == str(selected["source_book"])]
            selected["verse_count"] = len(rows)
            selected["word_count"] = sum(row.count("<m>") for row in rows)
    monkeypatch.setattr(audit_greek_sources, "catalog", sources.catalog)
    return greek_state


@pytest.mark.parametrize("corpora", [(), ("sblgnt",), ("rahlfs",), ("sblgnt", "rahlfs")])
def test_audit_only_installed_books_and_load_each_needed_mapping_once(
    audit_state, tmp_path, monkeypatch, corpora
):
    for code, selected in sources.catalog()["greek"]["books"].items():
        if selected["source"] not in corpora:
            sources.book_artifact(audit_state, code)[0].unlink(missing_ok=True)
    if "sblgnt" not in corpora:
        for name in ["gntLookups.js", "GreekWordList.js"]:
            (audit_state / "raw/greek" / name).unlink()
    if not corpora:
        (audit_state / "raw/greek/TBESG.txt").unlink()
    mapping_calls = []
    load_lexicon = audit_greek_sources.load_lexicon

    def record_mapping(state, book):
        mapping_calls.append(sources.catalog()["books"][book]["source"])
        return load_lexicon(state, book)

    monkeypatch.setattr(audit_greek_sources, "load_lexicon", record_mapping)
    output = tmp_path / "audit.json"
    monkeypatch.setattr("sys.argv", ["audit", "--state", str(audit_state), "--output", str(output)])
    audit_greek_sources.main()
    report = json.loads(output.read_text())
    expected = ({"John", "Mark"} if "sblgnt" in corpora else set()) | (
        {"LXXGen", "LXXDanOG", "LXXDanTh"} if "rahlfs" in corpora else set()
    )
    assert set(report["books"]) == expected
    assert set(mapping_calls) == set(corpora) and len(mapping_calls) == len(corpora)
    assert report["totals"].get("books", 0) == len(expected)


@pytest.mark.parametrize("artifact", ["64-Jn-morphgnt.txt", "LXX-main.csv", "TBESG.txt", "gntLookups.js"])
def test_audit_rejects_corrupt_installed_text_lexicon_and_crosswalk(
    audit_state, tmp_path, monkeypatch, artifact
):
    (audit_state / "raw/greek" / artifact).write_bytes(b"corrupt installed source")
    output = tmp_path / "audit.json"
    monkeypatch.setattr("sys.argv", ["audit", "--state", str(audit_state), "--output", str(output)])
    with pytest.raises(ReaderError, match="checksum"):
        audit_greek_sources.main()
    assert not output.exists()
