import pytest
from fastapi.testclient import TestClient

from bible_reader.models import ProjectConfig, Token, Verse
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


def test_greek_catalog_review_and_source_job_use_selected_edition(greek_state):
    app = create_app(greek_state, start_worker=False)
    with TestClient(app) as client:
        client.headers["X-Reader-Token"] = app.state.csrf_token
        info = client.get("/api/sources").json()
        assert len(info["books"]) == 126
        assert info["books"]["John"]["edition"] == "SBLGNT"
        assert info["books"]["LXXJoshA"]["witness"] == "alternate"
        assert info["greek_lexicon"] and "John" in info["installed"]
        assert client.get("/font/greek.ttf").content[:4] == b"\x00\x01\x00\x00"
        project = client.post(
            "/api/projects", json={"book": "John", "passage": "1:1-18", "selection": "all"}
        ).json()
        review = client.get(f"/api/projects/{project['id']}/review").json()
        assert review["verse_count"] == 18
        assert all(row["language"] == "grc" for row in review["rows"])
        job = client.post("/api/sources/import", json={"book": "LXXGen"}).json()
        assert job["config"]["book"] == "LXXGen"


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


def test_book_help_download_load_restore_and_snapshot(client, consonant_review):
    project = client.post(
        "/api/projects",
        json={
            "selection": "all",
            "passage": "1:1",
            "gloss_selection": "first-entry",
            "decisions": {
                "test-origin:0": {"entry_id": "step:test-choice", "gloss": "Editorial שָׁמַר"},
                "test-repeat:0": {"action": "exclude", "reason": "Outside the passage"},
                "test-ketiv:0": {"entry_id": "step:test-alternate", "gloss": "Editorial K/Q help"},
            },
        },
    ).json()
    url = f"/api/projects/{project['id']}"
    download = client.get(url + "/helps?revision=1")
    assert download.status_code == 200
    assert download.headers["content-disposition"] == 'attachment; filename="Prov-lexical-helps.json"'
    saved = download.json()
    assert saved["decisions"] == project["config"]["decisions"]
    assert client.get(url).json() == project  # Downloading never changes the project.
    destination = client.post(
        "/api/projects",
        json={
            "name": "Different edition",
            "selection": "all",
            "passage": "3:1",
            "readings": "qere",
            "layout": {"paper": "a4"},
            "decisions": {"test-qere:0": {"action": "exclude"}},
        },
    ).json()
    target = f"/api/projects/{destination['id']}"
    before = client.post(target + "/builds").json()
    response = client.post(target + "/helps", json={"revision": 1, "helps": saved})
    assert response.status_code == 200
    result = response.json()
    assert result["loaded"] == 3
    assert result["project"]["revision"] == 2
    config = result["project"]["config"]
    assert config == {
        **destination["config"],
        "decisions": saved["decisions"],
        "gloss_selection": "first-entry",
    }
    assert client.get(f"/api/jobs/{before['id']}").json()["config"] == destination["config"]
    assert client.post(target + "/builds").json()["config"] == config
    # Both load and download reject stale tabs.
    assert client.post(target + "/helps", json={"revision": 1, "helps": saved}).status_code == 409
    assert client.get(target + "/helps?revision=1").status_code == 409
    assert client.get(target).json() == result["project"]


@pytest.mark.parametrize(
    "change,status",
    [
        ({"book": "Gen"}, 400),
        ({"schema_version": 2}, 422),
        ({"format": "other"}, 422),
        ({"sources": {}}, 422),
        ({"decisions": {"missing:0": {"action": "exclude"}}}, 400),
        ({"decisions": {"test-ketiv:0": {"entry_id": "step:test-other"}}}, 400),
        ({"decisions": {"test-repeat:0": {"gloss": "Unattributed edit"}}}, 400),
        ({"decisions": {"test-origin:0": {"gloss": "Invalid\ntext"}}}, 422),
    ],
)
def test_invalid_book_help_load_is_atomic(client, consonant_review, change, status):
    project = client.post("/api/projects", json={"selection": "all", "passage": "1:1"}).json()
    url = f"/api/projects/{project['id']}"
    saved = client.get(url + "/helps?revision=1").json()
    response = client.post(url + "/helps", json={"revision": 1, "helps": {**saved, **change}})
    assert response.status_code == status
    assert client.get(url).json() == project


def test_book_help_load_supports_large_books(client, consonant_review):
    # Synthetic identities exercise the former 10,000-decision / 2 MB limits.
    tokens = tuple(Token(f"large-{i}", "שמר", "1001") for i in range(10001))
    consonant_review[:] = [Verse("Prov", 1, 1, tokens)]
    decisions = {
        f"{token.id}:0": {"entry_id": "step:test-choice", "gloss": "Synthetic gloss " * 10}
        for token in tokens
    }
    created = client.post(
        "/api/projects", json={"selection": "all", "passage": "1:1", "decisions": decisions}
    )
    assert created.status_code == 201
    project = created.json()
    url = f"/api/projects/{project['id']}"
    download = client.get(url + "/helps?revision=1")
    assert download.status_code == 200
    assert len(download.content) > 2_000_000
    response = client.post(url + "/helps", json={"revision": 1, "helps": download.json()})
    assert response.status_code == 200
    assert response.json()["loaded"] == 10001
    assert response.json()["project"]["config"]["decisions"] == project["config"]["decisions"]


@pytest.mark.parametrize("policy", ["reviewed", "first-entry"])
def test_reset_helps_sets_first_entry_and_preserves_settings_and_builds(client, consonant_review, policy):
    project = client.post(
        "/api/projects",
        json={
            "passage": "1:1",
            "selection": "all",
            "gloss_selection": policy,
            "known_entries": ["step:test-other"],
            "layout": {"verse_layout": "verse-per-line"},
            "decisions": {
                "test-origin:0": {"entry_id": "step:test-alternate", "gloss": "Synthetic edited gloss"},
                "test-prefix:0": {"action": "exclude"},
                "test-repeat:0": {"action": "exclude"},
            },
        },
    ).json()
    url = f"/api/projects/{project['id']}"
    before = client.post(url + "/builds").json()
    source_verses = client.get(url + "/review").json()["verses"]
    config = {**project["config"], "gloss_selection": "first-entry", "decisions": {}}
    payload = {"revision": project["revision"], "config": config}
    response = client.put(url, json=payload)
    assert response.status_code == 200
    saved = response.json()
    assert saved["revision"] == project["revision"] + 1
    assert saved["config"] == config
    review = client.get(url + "/review").json()
    rows = {row["anchor"]: row for row in review["rows"]}
    assert rows["test-prefix:0"]["selected"]
    assert rows["test-origin:0"]["alignment_status"] == "ambiguous"
    assert rows["test-origin:0"]["entry_id"] == "step:test-choice"
    assert rows["test-origin:0"]["gloss"] == "Synthetic step:test-choice"
    assert rows["test-origin:0"]["choice_method"] == "first-entry"
    assert review["coverage"] == {"resolved": 4}
    assert [t["source_surface"] for t in review["verses"][0]["tokens"]] == [
        t["source_surface"] for t in source_verses[0]["tokens"]
    ]
    assert client.get(f"/api/jobs/{before['id']}").json()["config"] == project["config"]
    assert client.post(url + "/builds").json()["config"] == config
    assert client.put(url, json=payload).status_code == 409
    assert client.get(url).json() == saved


def test_gloss_policy_defaults_and_validation(client):
    assert client.post("/api/projects", json={}).json()["config"]["gloss_selection"] == "reviewed"
    assert client.post("/api/projects", json={"gloss_selection": "unknown"}).status_code == 422


def test_lexicon_appendix_setting_is_saved_and_snapshotted(client):
    project = client.post("/api/projects", json={}).json()
    assert project["config"]["lexicon_appendix"] is False
    url = f"/api/projects/{project['id']}"
    before = client.post(url + "/builds").json()
    project["config"]["lexicon_appendix"] = True
    saved = client.put(url, json={"revision": 1, "config": project["config"]}).json()
    assert saved["config"]["lexicon_appendix"] is True
    assert client.get(url + "/review").json()["appendix_entries"] == 33
    assert client.post(url + "/builds").json()["config"]["lexicon_appendix"] is True
    assert client.get(f"/api/jobs/{before['id']}").json()["config"]["lexicon_appendix"] is False
    assert client.post("/api/projects", json={"lexicon_appendix": "yes"}).status_code == 422


def test_lexicon_only_setting_is_saved_snapshotted_and_collects_helps(client):
    project = client.post("/api/projects", json={}).json()
    assert project["config"]["lexicon_only"] is False
    url = f"/api/projects/{project['id']}"
    before = client.post(url + "/builds").json()
    project["config"]["lexicon_only"] = True
    saved = client.put(url, json={"revision": 1, "config": project["config"]}).json()
    assert saved["config"]["lexicon_only"] is True
    assert saved["config"]["lexicon_appendix"] is False
    assert client.get(url + "/review").json()["appendix_entries"] == 33
    assert client.post(url + "/builds").json()["config"]["lexicon_only"] is True
    assert client.get(f"/api/jobs/{before['id']}").json()["config"]["lexicon_only"] is False
    assert client.post("/api/projects", json={"lexicon_only": "yes"}).status_code == 422


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


def test_word_colors_are_saved_validated_and_snapshotted(client):
    project = client.post("/api/projects", json={}).json()
    assert project["config"]["layout"]["word_colors"] == "auto"
    url = f"/api/projects/{project['id']}"
    project["config"]["layout"].update(
        word_colors="word-class", word_color_overrides={"noun": "#123abc", "name": "auto"}
    )
    saved = client.put(url, json={"revision": 1, "config": project["config"]})
    assert saved.status_code == 200
    layout = saved.json()["config"]["layout"]
    assert layout["word_color_overrides"] == {"noun": "#123ABC", "name": "auto"}
    assert client.get(url).json()["config"]["layout"] == layout
    review = client.get(url + "/review").json()
    assert any(t["word_class"] == "name" for v in review["verses"] for t in v["tokens"])
    queued = client.post(url + "/builds").json()
    project["config"]["layout"]["word_colors"] = "auto"
    assert client.put(url, json={"revision": 2, "config": project["config"]}).status_code == 200
    assert client.get(f"/api/jobs/{queued['id']}").json()["config"]["layout"] == layout
    project["config"]["layout"]["word_color_overrides"]["noun"] = r"\input{x}"
    assert client.put(url, json={"revision": 3, "config": project["config"]}).status_code == 422
    assert client.get(url).json()["revision"] == 3


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


def test_review_page_is_one_revision_with_editorial_glosses_and_immutable_builds(client, consonant_review):
    project = client.post("/api/projects", json={"passage": "1:1", "selection": "all"}).json()
    url = f"/api/projects/{project['id']}"
    before = client.post(url + "/builds").json()
    source_verses = client.get(url + "/review").json()["verses"]
    payload = {
        "revision": 1,
        "edits": [
            {
                "anchor": "test-origin:0",
                "decision": {"entry_id": "step:test-choice", "gloss": "Synthetic page gloss"},
            },
            {"anchor": "test-prefix:0", "decision": {"action": "exclude"}},
        ],
    }
    response = client.post(url + "/decisions/batch", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["project"]["revision"] == 2
    assert result["applied"] == ["test-origin:0", "test-prefix:0"]
    assert result["skipped"] == []
    assert client.get(url).json() == result["project"]
    review = client.get(url + "/review").json()
    rows = {r["anchor"]: r for r in review["rows"]}
    assert rows["test-origin:0"]["gloss"] == "Synthetic page gloss"
    assert rows["test-origin:0"]["status"] == "resolved"
    assert not rows["test-prefix:0"]["selected"]
    assert [t["source_surface"] for t in review["verses"][0]["tokens"]] == [
        t["source_surface"] for t in source_verses[0]["tokens"]
    ]
    assert client.get(f"/api/jobs/{before['id']}").json()["config"]["decisions"] == {}
    assert (
        client.post(url + "/builds").json()["config"]["decisions"] == result["project"]["config"]["decisions"]
    )
    assert client.post(url + "/decisions/batch", json=payload).status_code == 409
    assert client.get(url).json() == result["project"]


@pytest.mark.parametrize(
    "second",
    [
        {"anchor": "missing:0", "decision": {}},
        {"anchor": "test-prefix:0", "decision": {"entry_id": "step:test-other"}},
        {"anchor": "test-prefix:0", "decision": {"gloss": "Synthetic unsupported gloss"}},
        {"anchor": "test-origin:0", "decision": {"entry_id": "step:test-choice"}},
        {"anchor": "test-repeat:0", "decision": {"action": "exclude"}, "scope": "book"},
    ],
)
def test_invalid_or_conflicting_page_does_not_save_any_rows(client, consonant_review, second):
    project = client.post("/api/projects", json={"passage": "1:1", "selection": "all"}).json()
    url = f"/api/projects/{project['id']}"
    first = {"anchor": "test-origin:0", "decision": {"entry_id": "step:test-choice"}}
    response = client.post(url + "/decisions/batch", json={"revision": 1, "edits": [first, second]})
    assert response.status_code == 400
    assert client.get(url).json() == project


def test_page_book_scopes_report_unsupported_components_and_merge_compatible_edits(client, consonant_review):
    project = client.post("/api/projects", json={"passage": "1:1", "selection": "all"}).json()
    url = f"/api/projects/{project['id']}"
    response = client.post(
        url + "/decisions/batch",
        json={
            "revision": 1,
            "edits": [
                {
                    "anchor": anchor,
                    "scope": "book",
                    "decision": {"entry_id": "step:test-choice", "reason": f"Edited from {anchor}"},
                }
                for anchor in ["test-origin:0", "test-repeat:0"]
            ],
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["project"]["revision"] == 2
    assert len(result["applied"]) == 5
    assert {item["anchor"] for item in result["skipped"]} == {
        "test-segmented:1",
        "test-homograph:0",
        "test-unmatched:0",
    }
    assert len(result["project"]["config"]["decisions"]) == 5
    assert "test-aramaic:0" not in result["project"]["config"]["decisions"]


def test_page_api_rejects_empty_oversized_or_invalid_payloads(client, consonant_review):
    project = client.post("/api/projects", json={"passage": "1:1", "selection": "all"}).json()
    url = f"/api/projects/{project['id']}"
    edit = {"anchor": "test-origin:0", "decision": {"entry_id": "step:test-choice"}}
    for edits in [[], [edit] * 201, [{**edit, "scope": "invalid"}]]:
        assert client.post(url + "/decisions/batch", json={"revision": 1, "edits": edits}).status_code == 422
        assert client.get(url).json() == project


def test_name_inclusion_is_rejected_atomically_and_review_retains_omission_evidence(client, name_review):
    project = client.post("/api/projects", json={"passage": "1:1", "selection": "all"}).json()
    url = f"/api/projects/{project['id']}"
    common = {"anchor": "common-by-source:0", "decision": {"entry_id": "step:test-common"}}
    name = {"anchor": "name-by-source:0", "decision": {"entry_id": "step:test-common"}}
    response = client.post(url + "/decisions/batch", json={"revision": 1, "edits": [common, name]})
    assert response.status_code == 400 and "Names are excluded" in response.json()["detail"]
    assert client.get(url).json() == project
    assert client.post(url + "/decisions", json={"revision": 1, **name}).status_code == 400
    assert client.get(url).json() == project
    review = client.get(url + "/review").json()
    row = next(row for row in review["rows"] if row["anchor"] == "name-by-source:0")
    assert not row["selected"] and row["name_excluded"]
    assert row["reason"] == "Proper name omitted (OSHB Np morphology)"
    assert row["candidates"] and row["source_surface"] == "שָׁם"
    assert review["coverage"]["excluded"] == 5


def test_chosen_name_entry_is_rejected_for_inclusion_with_mixed_source_candidates(client, name_review):
    project = client.post("/api/projects", json={"passage": "1:1", "selection": "all"}).json()
    url = f"/api/projects/{project['id']}"
    response = client.post(
        url + "/decisions",
        json={"revision": 1, "anchor": "common-by-source:0", "decision": {"entry_id": "step:test-name"}},
    )
    assert response.status_code == 400 and "Names are excluded" in response.json()["detail"]
    assert client.get(url).json() == project
