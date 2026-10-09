import hashlib
import importlib.util
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "setup_tex", Path(__file__).resolve().parents[1] / "scripts" / "setup_tex.py"
)
setup_tex = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup_tex)


@pytest.fixture
def download(monkeypatch):
    payload = b"synthetic archive bytes for download verification"
    checksum = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(
        setup_tex, "ASSETS", {"test.tar.xz": ("https://example.invalid/test.tar.xz", checksum)}
    )
    monkeypatch.setattr(setup_tex.shutil, "which", lambda name: "/usr/bin/curl")
    calls = []

    def respond(body=payload, content_type="application/x-xz", returncode=0):
        def run(command, **kwargs):
            calls.append(command)
            assert command[0] == "curl"
            assert "--fail" in command and "--location" in command
            assert kwargs["check"] is True
            assert not kwargs.get("shell")
            Path(command[command.index("--output") + 1]).write_bytes(body)
            if returncode:
                raise subprocess.CalledProcessError(returncode, command)
            return subprocess.CompletedProcess(command, returncode, stdout=content_type)

        monkeypatch.setattr(setup_tex.subprocess, "run", run)

    respond()
    return payload, checksum, calls, respond


def test_download_is_verified_and_reused_without_network(tmp_path, download):
    payload, _, calls, _ = download
    archive = setup_tex.acquire(tmp_path, "test.tar.xz")
    assert archive.read_bytes() == payload
    assert list(tmp_path.iterdir()) == [archive]
    assert setup_tex.acquire(tmp_path, "test.tar.xz") == archive
    assert len(calls) == 1


def test_checksum_mismatch_reports_both_hashes_and_discards_download(tmp_path, download):
    _, checksum, _, respond = download
    respond(body=b"unexpected")
    with pytest.raises(RuntimeError, match="Checksum mismatch") as error:
        setup_tex.acquire(tmp_path, "test.tar.xz")
    assert checksum in str(error.value)
    assert hashlib.sha256(b"unexpected").hexdigest() in str(error.value)
    assert list(tmp_path.iterdir()) == []


def test_html_challenge_is_reported_and_discarded(tmp_path, download):
    _, _, _, respond = download
    respond(body=b"<!doctype html><title>Oh noes!</title>", content_type="text/html; charset=utf-8")
    with pytest.raises(RuntimeError, match="returned HTML instead of an archive"):
        setup_tex.acquire(tmp_path, "test.tar.xz")
    assert list(tmp_path.iterdir()) == []


def test_failed_transfer_discards_partial_archive(tmp_path, download):
    _, _, _, respond = download
    respond(body=b"incomplete", returncode=28)
    with pytest.raises(subprocess.CalledProcessError):
        setup_tex.acquire(tmp_path, "test.tar.xz")
    assert list(tmp_path.iterdir()) == []


def test_corrupt_cache_is_rejected_without_network(tmp_path, download):
    _, _, calls, _ = download
    archive = tmp_path / "test.tar.xz"
    archive.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="Cached test.tar.xz has the wrong checksum"):
        setup_tex.acquire(tmp_path, "test.tar.xz")
    assert not calls
    assert archive.read_bytes() == b"corrupt"


def test_missing_curl_has_actionable_error(tmp_path, download, monkeypatch):
    monkeypatch.setattr(setup_tex.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Install curl"):
        setup_tex.acquire(tmp_path, "test.tar.xz")
    assert list(tmp_path.iterdir()) == []
