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


def test_custom_paper_settings_and_build_snapshot(client):
    project = client.post("/api/projects", json={}).json()
    assert project["config"]["layout"]["paper"] == "reader"
    url = f"/api/projects/{project['id']}"
    project["config"]["layout"].update(paper="custom", paper_width_mm=160.5, paper_height_mm=230.25)
    saved = client.put(url, json={"revision": 1, "config": project["config"]})
    assert saved.status_code == 200
    assert client.get(url).json()["config"]["layout"] == saved.json()["config"]["layout"]
    queued = client.post(url + "/builds").json()
    snapshot = client.get(f"/api/jobs/{queued['id']}").json()["config"]["layout"]
    assert snapshot["paper"] == "custom"
    assert snapshot["paper_width_mm"] == 160.5
    assert snapshot["paper_height_mm"] == 230.25
    project["config"]["layout"]["paper_width_mm"] = 180
    assert client.put(url, json={"revision": 2, "config": project["config"]}).status_code == 200
    assert client.get(f"/api/jobs/{queued['id']}").json()["config"]["layout"] == snapshot
    assert client.post("/api/projects", json={"layout": {"paper": "custom"}}).status_code == 422
    assert (
        client.post(
            "/api/projects",
            json={"layout": {"paper": "custom", "paper_width_mm": 10, "paper_height_mm": 216}},
        ).status_code
        == 422
    )


@pytest.mark.parametrize("policy", ["consonants-only", "consonants", "consonants-maqqef-sof-pasuq"])
def test_consonant_policy_is_saved_reviewed_and_snapshotted(client, policy):
    project = client.post("/api/projects", json={}).json()
    assert project["config"]["cantillation"] == "hide"
    url = f"/api/projects/{project['id']}"
    project["config"]["cantillation"] = policy
    saved = client.put(url, json={"revision": 1, "config": project["config"]})
    assert saved.status_code == 200
    assert client.get(url).json()["config"]["cantillation"] == policy
    review = client.get(url + "/review").json()
    assert review["verses"][0]["tokens"][0]["surface"] == "תחת"
    assert review["verses"][0]["tokens"][2]["surface"] == ("" if policy == "consonants-only" else "־")
    queued = client.post(url + "/builds").json()
    project["config"]["cantillation"] = "preserve"
    assert client.put(url, json={"revision": 2, "config": project["config"]}).status_code == 200
    assert client.get(f"/api/jobs/{queued['id']}").json()["config"]["cantillation"] == policy


@pytest.mark.parametrize("scope,count", [("occurrence", 1), ("book", 5)])
def test_decision_scope_is_saved_atomically_with_report_and_build_snapshot(
    client, consonant_review, scope, count
):
    project = client.post("/api/projects", json={"passage": "1:1", "selection": "all"}).json()
    url = f"/api/projects/{project['id']}"
    before = client.post(url + "/builds").json()
    payload = {
        "revision": project["revision"],
        "anchor": "test-origin:0",
        "scope": scope,
        "decision": {"entry_id": "step:test-choice", "gloss": "Synthetic API gloss", "reason": "API test"},
    }
    response = client.post(url + "/decisions", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["project"]["revision"] == 2
    assert len(result["applied"]) == count
    assert len(result["skipped"]) == (3 if scope == "book" else 0)
    saved = client.get(url).json()
    assert saved == result["project"]
    assert len(saved["config"]["decisions"]) == count
    assert saved["config"]["passage"] == "1:1"
    review = client.get(url + "/review").json()
    origin = next(r for r in review["rows"] if r["anchor"] == "test-origin:0")
    assert origin["status"] == "resolved" and origin["gloss"] == "Synthetic API gloss"
    after = client.post(url + "/builds").json()
    assert after["config"]["decisions"] == saved["config"]["decisions"]
    assert client.get(f"/api/jobs/{before['id']}").json()["config"]["decisions"] == {}
    assert client.post(url + "/decisions", json=payload).status_code == 409
    assert client.get(url).json() == saved


def test_single_decision_api_defaults_and_validation_do_not_save_partial_edits(client, consonant_review):
    project = client.post("/api/projects", json={"passage": "1:1", "selection": "all"}).json()
    url = f"/api/projects/{project['id']}"
    payload = {"revision": 1, "anchor": "test-origin:0", "decision": {"entry_id": "step:test-choice"}}
    for changes, status in [
        ({"anchor": "missing:0"}, 400),
        ({"decision": {"entry_id": "step:test-other"}}, 400),
        ({"scope": "book", "decision": {}}, 400),
        ({"decision": {"gloss": "Synthetic proposal"}}, 400),
        ({"scope": "invalid"}, 422),
    ]:
        assert client.post(url + "/decisions", json={**payload, **changes}).status_code == status
        assert client.get(url).json() == project
    saved = client.post(url + "/decisions", json=payload).json()
    assert saved["applied"] == ["test-origin:0"] and not saved["skipped"]
