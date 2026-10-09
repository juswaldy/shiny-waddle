import pytest
from fastapi.testclient import TestClient

from bible_reader.models import ProjectConfig
from bible_reader.web.app import create_app


@pytest.fixture
def client(source_state):
    app = create_app(source_state, start_worker=False)
    with TestClient(app) as client:
        client.headers["X-Reader-Token"] = app.state.csrf_token
        yield client


def test_home_and_local_request_protection(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "frame-ancestors 'self'" in page.headers["Content-Security-Policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/font/ezra.ttf").status_code == 200
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400
    assert client.post("/api/projects", json={}, headers={"X-Reader-Token": "wrong"}).status_code == 403


def test_project_review_edit_build_snapshot_and_conflict(client):
    created = client.post("/api/projects", json=ProjectConfig().model_dump())
    assert created.status_code == 201
    project = created.json()
    url = f"/api/projects/{project['id']}"
    review = client.get(url + "/review").json()
    assert review["verse_count"] == 17
    assert review["help_count"] == 37
    queued = client.post(url + "/builds").json()
    assert queued["project_revision"] == 1
    project["config"]["name"] = "Saved edition"
    project["config"]["layout"]["verse_layout"] = "verse-per-line"
    payload = {"revision": 1, "config": project["config"]}
    assert client.put(url, json=payload).json()["revision"] == 2
    assert client.get(url).json()["config"]["layout"]["verse_layout"] == "verse-per-line"
    assert client.put(url, json=payload).status_code == 409
    assert client.get(f"/api/jobs/{queued['id']}").json()["config"]["name"] == "Proverbs reader"
    assert client.get(f"/api/jobs/{queued['id']}").json()["config"]["layout"]["verse_layout"] == "continuous"
    assert client.post(f"/api/jobs/{queued['id']}/cancel").json()["status"] == "cancelled"


def test_validation_and_artifact_allowlist(client, source_state):
    assert client.post("/api/projects", json={"passage": "bad"}).status_code == 422
    assert client.post("/api/sources/import", json={"book": "../etc"}).status_code == 400
    store = client.app.state.store
    job = store.queue("build", {})
    path = source_state / "builds" / job["id"]
    path.mkdir(parents=True)
    (path / "reader.pdf").write_bytes(b"pdf")
    (path / "private.txt").write_bytes(b"secret")
    base = f"/api/jobs/{job['id']}/artifacts/"
    assert client.get(base + "reader.pdf").status_code == 404
    store.update_job(job["id"], status="succeeded", result={"artifacts": ["reader.pdf"]})
    assert client.get(base + "reader.pdf").content == b"pdf"
    assert client.get(base + "private.txt").status_code == 404
    assert client.get(base + "../reader.sqlite3").status_code == 404
    (path / "reader.pdf").unlink()
    (path / "reader.pdf").symlink_to(source_state / "reader.sqlite3")
    assert client.get(base + "reader.pdf").status_code == 404
