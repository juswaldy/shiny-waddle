"""Opt-in browser checks against the attributable offline source fixtures."""

import json
import os
import socket
import threading
import time
from collections import Counter
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from bible_reader.jobs import run_worker
from bible_reader.models import ProjectConfig
from bible_reader.store import Store
from bible_reader.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(os.environ.get("READER_BROWSER_TESTS") != "1", reason="Set READER_BROWSER_TESTS=1"),
]


@pytest.fixture
def review_server(source_state, request):
    greek = getattr(request, "param", None) == "greek"
    state = request.getfixturevalue("greek_state") if greek else source_state
    app = create_app(state, start_worker=False)
    config = (
        ProjectConfig(book="John", passage="1:1-18", selection="all")
        if greek
        else ProjectConfig(selection="all")
    )
    project = app.state.store.create_project(config)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                if not thread.is_alive():
                    pytest.fail("Review server exited before becoming ready")
                time.sleep(0.05)
            else:
                pytest.fail("Review server did not start")
            yield f"http://127.0.0.1:{port}", project["id"], app.state.csrf_token
        finally:
            server.should_exit = True
            thread.join(timeout=10)


def set_review_choice(row, field, value):
    name = f"{field} for {row.get_attribute('data-anchor')}"
    group = row.get_by_role("radiogroup", name=name, exact=True)
    if group.count():
        group.locator(f"input[value='{value}']").check()
    else:
        row.get_by_role("combobox", name=name, exact=True).select_option(value)


def expect_review_choice(row, field, value):
    name = f"{field} for {row.get_attribute('data-anchor')}"
    group = row.get_by_role("radiogroup", name=name, exact=True)
    if group.count():
        expect(group.locator(f"input[value='{value}']")).to_be_checked()
    else:
        expect(row.get_by_role("combobox", name=name, exact=True)).to_have_value(value)


@pytest.mark.parametrize("view", ["grid", "cards"])
@pytest.mark.parametrize("batch", [False, True])
def test_manual_gloss_without_source_entry_saves_and_reloads(
    unmatched_review, review_server, monkeypatch, view, batch
):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, identity, csrf = review_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        project_url = url + f"/api/projects/{identity}"
        project = page.request.get(project_url).json()
        project["config"]["passage"] = "3:1-4:1"
        assert page.request.put(
            project_url,
            headers={"X-Reader-Token": csrf},
            data={"revision": project["revision"], "config": project["config"]},
        ).ok
        page.goto(url)
        page.locator("#review-view").select_option(view)
        page.locator("#unresolved-only").check()
        row = page.locator("[data-anchor='test-unmatched:0']")
        expect(row.locator(".gloss-provenance")).to_have_text(
            "No source entry available · write your own gloss"
        )
        if view == "grid":
            row.locator("textarea").evaluate(
                "node => {const data = new DataTransfer(); data.setData('text/plain', "
                "'Synthetic manual browser gloss\\n'); "
                "node.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));}"
            )
        else:
            row.locator("textarea").fill("Synthetic manual browser gloss")
        expect(row.locator("textarea")).to_have_value("Synthetic manual browser gloss")
        expect(row.locator(".gloss-provenance")).to_have_text("Editorial proposal · no source entry")
        endpoint = "/decisions/batch" if batch else "/decisions"
        with page.expect_response(lambda response: response.url.endswith(endpoint)) as response:
            if batch:
                page.locator("#save-page").click()
            else:
                row.get_by_role("button", name="Save all", exact=True).click()
        assert response.value.ok
        saved = response.value.json()
        assert set(saved["applied"]) == {"test-unmatched:0", "test-unmatched-repeat:0"}
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")
        expect(row).to_have_count(0)  # An explicit proposal leaves Needs review.
        page.locator("#unresolved-only").uncheck()
        page.locator("#resolved-only").check()
        expect(row.locator("textarea")).to_have_value("Synthetic manual browser gloss")
        expect(row.locator(".row-status")).to_have_text("editorial")
        expect(row.locator(".row-status")).not_to_have_class("unresolved")
        expect(row.get_by_role("button", name="Use source gloss for test-unmatched:0")).to_be_disabled()
        page.reload()
        expect(row.locator("textarea")).to_have_value("Synthetic manual browser gloss")
        expect_review_choice(row, "Source entry", "")
        assert (
            page.request.get(project_url).json()["config"]["decisions"]["test-unmatched:0"]["entry_id"]
            is None
        )
        browser.close()


def test_overflow_summary_links_logs_and_keeps_completed_pdf_files(
    review_server, source_state, tmp_path, tex_available, monkeypatch
):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, _, _ = review_server
    source = tmp_path / "overflow.tex"
    source.write_text(
        r"\documentclass{article}\begin{document}"
        r"\noindent\hbox to 0pt{Synthetic overflow}\par\end{document}"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        page.locator("#show-pipeline").click()
        page.locator("#pipeline-tex").set_input_files(source)
        with page.expect_response(lambda response: response.url.endswith("/transforms/tex-to-pdf")) as queued:
            page.locator("#make-pdf").click()
        job = queued.value.json()
        run_worker(source_state, once=True)
        expect(page.locator("#build-status")).to_contain_text("Build completed with errors", timeout=15000)
        expect(page.locator("#build-status")).to_contain_text("Overfull")
        link = page.locator("#build-status").get_by_role("link", name="reader.log", exact=True)
        expect(link).to_have_attribute("href", f"/api/jobs/{job['id']}/artifacts/reader.log")
        response = page.request.get(url + link.get_attribute("href"))
        assert response.ok and "Overfull" in response.text()
        assert page.request.get(url + f"/api/jobs/{job['id']}").json()["status"] == "failed"
        expect(page.locator("#download-pdf")).to_be_visible()
        expect(page.locator("#download-bundle")).to_be_visible()
        expect(page.locator("#pdf-preview")).to_be_visible()
        page.reload()
        page.get_by_role("button", name="PDF preview", exact=True).click()
        expect(page.locator("#build-history").get_by_role("button", name="View files")).to_be_visible()
        expect(page.locator("#build-status")).to_contain_text("Build completed with errors")
        page.screenshot(path=str(tmp_path / "build-errors-browser.png"), full_page=True)
        # Older failed jobs have no result manifest, but their log is still useful.
        store = Store(source_state)
        previous = store.queue("build", ProjectConfig().model_dump(), job["project_id"])
        output = source_state / "builds" / previous["id"]
        output.mkdir()
        (output / "reader.log").write_text("Overfull \\hbox (11.89pt too wide)")
        store.update_job(
            previous["id"],
            status="failed",
            error="The PDF has overflowing content; inspect reader.log and adjust the layout.",
        )
        page.reload()
        page.get_by_role("button", name="PDF preview", exact=True).click()
        link = page.locator("#build-status").get_by_role("link", name="reader.log", exact=True)
        expect(link).to_have_attribute("href", f"/api/jobs/{previous['id']}/artifacts/reader.log")
        expect(page.locator("#download-pdf")).to_be_hidden()
        page.locator("#build-history").get_by_role("button", name="View files").click()
        expect(page.locator("#build-status")).to_contain_text("Build completed with errors")
        expect(page.locator("#download-pdf")).to_be_visible()
        assert not errors
        browser.close()


def test_pipeline_download_upload_and_standalone_pdf_in_browser(
    review_server, source_state, tmp_path, tex_available, monkeypatch
):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, _, _ = review_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator(".help-row").first).to_be_visible()
        page.locator("#selection").select_option("reference")
        page.get_by_text("Page & reading settings", exact=True).click()
        page.locator("#word-colors").select_option("word-class")
        page.get_by_text("Palette & class colors", exact=True).click()
        page.locator("#word-color-custom-noun").fill("#123abc")
        page.locator("#word-color-name").select_option("auto")
        page.locator("#show-pipeline").click()
        expect(page.locator("#pipeline-data")).to_be_visible()

        def run_stage(button, suffix):
            with page.expect_response(
                lambda response: response.url.endswith(suffix) and response.request.method == "POST"
            ) as response:
                page.locator(button).click()
            assert response.value.status == 202
            run_worker(source_state, once=True)

        run_stage("#make-data", "/data")
        expect(page.locator("#download-data")).to_be_visible(timeout=15000)
        expect(page.locator("#download-tex")).to_be_hidden()
        expect(page.locator("#pdf-preview")).to_be_hidden()
        with page.expect_download() as download:
            page.locator("#download-data").click()
        saved = tmp_path / "reader.v2.json"
        download.value.save_as(saved)
        data = json.loads(saved.read_text())
        assert data["config"]["selection"] == "reference"
        layout = data["config"]["layout"]
        assert layout["word_colors"] == "word-class"
        assert layout["word_color_overrides"]["noun"] == "#123ABC"
        assert layout["word_color_overrides"]["name"] == "auto"
        assert layout["word_color_overrides"]["verb"] == "#A33432"
        assert len(layout["word_color_overrides"]) == page.locator("[data-word-class]").count()
        page.locator("#pipeline-data").set_input_files(saved)
        run_stage("#make-tex", "/transforms/data-to-tex")
        expect(page.locator("#download-tex")).to_be_visible(timeout=15000)
        expect(page.locator("#download-pdf")).to_be_hidden()
        with page.expect_download() as download:
            page.locator("#download-tex").click()
        tex = tmp_path / "reader.tex"
        download.value.save_as(tex)
        page.locator("#pipeline-tex").set_input_files(tex)
        run_stage("#make-pdf", "/transforms/tex-to-pdf")
        expect(page.locator("#download-pdf")).to_be_visible(timeout=15000)
        expect(page.locator("#pdf-preview")).to_be_visible()
        expect(page.locator("#build-status")).to_contain_text("PDF ready from uploaded TeX")
        expect(page.locator("#build-history .history-row")).to_have_count(3)
        response = page.request.get(url + page.locator("#download-pdf").get_attribute("href"))
        assert response.body().startswith(b"%PDF")
        page.wait_for_timeout(2000)  # Let Chromium's native PDF viewer paint the proof.
        page.screenshot(path=str(tmp_path / "pipeline-browser.png"), full_page=True)
        assert errors == []
        browser.close()


@pytest.mark.parametrize("review_server", ["greek"], indirect=True)
def test_greek_review_context_and_source_controls_are_left_to_right(review_server, monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, _, _ = review_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        row = page.locator(".help-row").first
        expect(row).to_be_visible()
        expect(row.locator(".help-word")).to_have_attribute("dir", "ltr")
        expect(row.locator(".help-word")).to_have_attribute("lang", "el")
        row.locator(".verse-reference").focus()
        expect(page.locator("#verse-context")).to_be_visible()
        assert page.locator("#verse-context-text").evaluate("n => getComputedStyle(n).direction") == "ltr"
        assert page.locator(".verse-context-token").first.text_content() == "Ἐν"
        page.keyboard.press("Escape")
        page.get_by_text("Page & reading settings", exact=True).click()
        expect(page.locator("#greek-typeface")).to_be_visible()
        expect(page.locator("#cantillation")).to_be_hidden()
        page.get_by_role("button", name="Sources", exact=True).click()
        page.locator("#import-book").select_option("LXXGen")
        expect(page.locator("#source-terms")).to_contain_text("CCAT")
        expect(page.locator("#source-terms")).to_contain_text("CC-BY-NC-SA-4.0")
        proof = ROOT / "test-results/greek-review.png"
        proof.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(proof), full_page=True)
        assert not errors
        browser.close()


@pytest.mark.parametrize("lexicon_only", [False, True])
def test_lexicon_appendix_build_option_persists_and_is_in_the_build_snapshot(
    review_server, monkeypatch, lexicon_only
):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, identity, _ = review_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator(".help-row").first).to_be_visible()
        option = page.get_by_role("checkbox", name="Add lexicon appendix", exact=True)
        expect(option).not_to_be_checked()
        option.check()
        if lexicon_only:
            page.get_by_label("Build content", exact=True).select_option("lexicon")
            expect(option).to_be_disabled()
        page.get_by_role("button", name="Save settings", exact=True).click()
        expect(page.locator("#notice")).to_have_text("Edition settings saved")
        page.reload()
        expect(option).to_be_checked()
        expect(page.get_by_label("Build content", exact=True)).to_have_value(
            "lexicon" if lexicon_only else "reader"
        )
        page.get_by_role(
            "button", name="Build lexicon PDF" if lexicon_only else "Build reader PDF", exact=False
        ).click()
        expect(page.locator("#preview-panel")).to_be_visible()
        job = page.request.get(url + "/api/jobs").json()[0]
        assert job["project_id"] == identity and job["config"]["lexicon_appendix"] is True
        assert job["config"]["frequency_max"] == 10
        assert job["config"]["lexicon_only"] is lexicon_only
        assert errors == []
        browser.close()


@pytest.mark.parametrize("view", ["cards", "grid"])
def test_save_and_load_book_help_file(consonant_review, review_server, monkeypatch, tmp_path, view):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, identity, csrf = review_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        project_url = url + f"/api/projects/{identity}"
        project = page.request.get(project_url).json()
        project["config"].update(
            passage="1:1",
            gloss_selection="reviewed",
            readings="qere",
            decisions={
                "test-origin:0": {"entry_id": "step:test-alternate", "gloss": "Editorial שָׁמַר & help"},
                "test-prefix:0": {"action": "exclude"},
                "test-repeat:0": {"entry_id": "step:test-choice", "gloss": "Editorial other chapter"},
                "test-ketiv:0": {"entry_id": "step:test-alternate", "gloss": "Editorial written form"},
            },
        )
        assert page.request.put(
            project_url,
            headers={"X-Reader-Token": csrf},
            data={"revision": project["revision"], "config": project["config"]},
        ).ok
        page.goto(url)
        page.locator("#review-view").select_option(view)
        page.locator("#show-all").check()
        expect(page.locator(".help-row")).to_have_count(4)
        origin = page.locator("[data-anchor='test-origin:0']")
        origin.locator("textarea").fill("Unsaved draft")
        page.get_by_role("button", name="Save book helps", exact=True).click()
        expect(page.locator("#notice")).to_contain_text("Save or discard")
        page.get_by_role("button", name="Load book helps", exact=True).click()
        expect(page.locator("#notice")).to_contain_text("Save or discard")
        expect(origin.locator("textarea")).to_have_value("Unsaved draft")
        page.locator("#discard-page").click()
        page.get_by_label("Gloss selection", exact=True).select_option("first-entry")
        page.get_by_role("button", name="Save book helps", exact=True).click()
        expect(page.locator("#notice")).to_contain_text("Save edition settings")
        page.get_by_label("Gloss selection", exact=True).select_option("reviewed")
        with page.expect_download() as download:
            page.get_by_role("button", name="Save book helps", exact=True).click()
        assert download.value.suggested_filename == "Prov-lexical-helps.json"
        saved_file = tmp_path / download.value.suggested_filename
        download.value.save_as(saved_file)
        saved = json.loads(saved_file.read_text())
        assert len(saved["decisions"]) == 4 and "test-ketiv:0" in saved["decisions"]
        expect(page.locator("#book-helps-status")).to_have_text("Saved 4 lexical decisions for Proverbs.")
        page.locator("#reset-helps").click()
        expect(page.locator("#reset-helps-message")).to_contain_text("Reset complete")
        expect(origin.locator("textarea")).to_have_value("Synthetic step:test-choice")
        before = page.request.get(project_url).json()
        page.locator("#book-helps-file").set_input_files(
            {"name": "invalid.json", "mimeType": "application/json", "buffer": b"invalid JSON"}
        )
        expect(page.locator("#notice")).to_contain_text("valid book helps JSON")
        assert page.request.get(project_url).json() == before
        wrong_book = {**saved, "book": "Gen"}
        page.locator("#book-helps-file").set_input_files(
            {"name": "wrong.json", "mimeType": "application/json", "buffer": json.dumps(wrong_book).encode()}
        )
        expect(page.locator("#notice")).to_contain_text("current edition uses Prov")
        assert page.request.get(project_url).json() == before
        with page.expect_file_chooser() as chooser:
            page.get_by_role("button", name="Load book helps", exact=True).click()
        chooser.value.set_files(saved_file)
        expect(page.locator("#book-helps-status")).to_have_text("Loaded 4 lexical decisions for Proverbs.")
        expect(origin.locator("textarea")).to_have_value("Editorial שָׁמַר & help")
        expect_review_choice(origin, "Source entry", "step:test-alternate")
        expect(page.get_by_label("Gloss selection", exact=True)).to_have_value("reviewed")
        restored = page.request.get(project_url).json()
        assert restored["config"]["decisions"] == saved["decisions"]
        assert restored["config"]["passage"] == "1:1" and restored["config"]["readings"] == "qere"
        page.reload()
        expect(origin.locator("textarea")).to_have_value("Editorial שָׁמַר & help")
        assert errors == [], errors
        browser.close()


@pytest.mark.parametrize("view", ["cards", "grid"])
@pytest.mark.parametrize("reset_policy", ["reviewed", "first-entry"])
def test_default_gloss_policy_and_project_reset(
    consonant_review, review_server, monkeypatch, view, reset_policy
):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, identity, csrf = review_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        project_url = url + f"/api/projects/{identity}"
        project = page.request.get(project_url).json()
        project["config"].update(
            passage="1:1",
            decisions={
                "test-origin:0": {"entry_id": "step:test-alternate", "gloss": "Synthetic edited gloss"},
                "test-prefix:0": {"action": "exclude"},
                "test-repeat:0": {"entry_id": "step:test-alternate", "gloss": "Synthetic outside passage"},
            },
        )
        assert page.request.put(
            project_url,
            headers={"X-Reader-Token": csrf},
            data={"revision": project["revision"], "config": project["config"]},
        ).ok
        page.goto(url)
        page.locator("#review-view").select_option(view)
        page.locator("#show-all").check()
        expect(page.locator(".help-row")).to_have_count(4)
        origin = page.locator("[data-anchor='test-origin:0']")
        expect(page.get_by_label("Gloss selection", exact=True)).to_have_value("reviewed")
        expect_review_choice(origin, "Source entry", "step:test-alternate")
        expect(origin.locator("textarea")).to_have_value("Synthetic edited gloss")
        page.get_by_label("Gloss selection", exact=True).select_option("first-entry")
        with page.expect_response(lambda response: response.request.method == "PUT"):
            page.get_by_role("button", name="Save settings", exact=True).click()
        expect(page.locator("#notice")).to_have_text("Edition settings saved")
        expect(origin.locator("textarea")).to_have_value("Synthetic edited gloss")
        prefix = page.locator("[data-anchor='test-prefix:0']")
        expect(prefix.locator("textarea")).to_have_value("Synthetic step:test-choice")
        expect(prefix.locator("input[type=checkbox]")).not_to_be_checked()
        if reset_policy == "reviewed":
            page.get_by_label("Gloss selection", exact=True).select_option("reviewed")
            with page.expect_response(lambda response: response.request.method == "PUT"):
                page.get_by_role("button", name="Save settings", exact=True).click()
            expect(page.locator("#notice")).to_have_text("Edition settings saved")
        origin.locator("textarea").fill("Synthetic pending draft")
        page.get_by_role("button", name="Reset helps to defaults", exact=True).click()
        expect(page.locator("#notice")).to_contain_text("Save or discard")
        expect(origin.locator("textarea")).to_have_value("Synthetic pending draft")
        expect(page.get_by_label("Gloss selection", exact=True)).to_have_value(reset_policy)
        expect(page.locator("#reset-helps-status")).to_be_hidden()
        page.get_by_role("button", name="Discard page edits", exact=True).click()
        before = page.request.post(project_url + "/builds", headers={"X-Reader-Token": csrf}).json()
        pending_saves, pending_reviews = [], []
        page.route(
            project_url,
            lambda route: pending_saves.append(route) if route.request.method == "PUT" else route.continue_(),
        )
        page.route(project_url + "/review", lambda route: pending_reviews.append(route))
        page.get_by_role("button", name="Reset helps to defaults", exact=True).click()
        expect(page.get_by_label("Gloss selection", exact=True)).to_have_value("first-entry")
        expect(page.get_by_label("Gloss selection", exact=True)).to_be_disabled()
        expect(page.locator("#reset-helps-progress")).to_be_visible()
        assert page.locator("#reset-helps-progress").get_attribute("value") is None
        expect(page.locator("#reset-helps-message")).to_have_text("Saving default gloss and resetting helps…")
        expect(page.locator("#notice")).to_be_hidden()
        expect(page.get_by_role("button", name="Resetting helps…", exact=True)).to_be_disabled()
        expect(page.locator("#draft-count")).to_have_text("Resetting helps…")
        expect(page.locator("#review-list")).to_have_attribute("aria-busy", "true")
        expect(page.locator("#reload-review")).to_be_disabled()
        expect(origin.locator("textarea")).to_be_disabled()
        assert len(pending_saves) == 1
        submitted = pending_saves[0].request.post_data_json
        assert submitted["config"]["gloss_selection"] == "first-entry"
        assert submitted["config"]["decisions"] == {}
        pending_saves.pop().continue_()
        expect(page.locator("#reset-helps-message")).to_have_text("Refreshing lexical helps…")
        expect(page.locator("#reset-helps-progress")).to_be_visible()
        expect(page.locator("#review-list")).to_have_attribute("aria-busy", "true")
        assert len(pending_reviews) == 1
        artifacts = ROOT / "test-results"
        artifacts.mkdir(exist_ok=True)
        page.screenshot(path=str(artifacts / f"reset-helps-progress-{view}-{reset_policy}.png"))
        pending_reviews.pop().continue_()
        page.unroute(project_url)
        page.unroute(project_url + "/review")
        expect(page.locator("#notice")).to_have_text(
            "Lexical helps reset to defaults throughout this project’s book"
        )
        expect(page.locator("#reset-helps-message")).to_have_text(
            "Reset complete. Lexical helps now use Default gloss (first entry)."
        )
        expect(page.locator("#reset-helps-progress")).to_have_attribute("value", "1")
        expect(page.locator("#review-list")).to_have_attribute("aria-busy", "false")
        expect(page.get_by_label("Gloss selection", exact=True)).to_be_enabled()
        expect_review_choice(origin, "Source entry", "step:test-choice")
        expect(origin.locator("textarea")).to_have_value("Synthetic step:test-choice")
        expect(origin.locator(".row-status")).to_have_text("default")
        expect(origin.locator(".gloss-provenance")).to_have_text("Default gloss · first STEP source entry")
        expect(prefix.locator("input[type=checkbox]")).to_be_checked()
        expect(page.locator("#reset-helps")).to_be_disabled()
        saved = page.request.get(project_url).json()
        assert saved["config"]["decisions"] == {}
        assert saved["config"]["gloss_selection"] == "first-entry"
        assert (
            "test-repeat:0"
            in page.request.get(url + f"/api/jobs/{before['id']}").json()["config"]["decisions"]
        )
        page.screenshot(path=str(artifacts / f"default-gloss-{view}.png"))
        page.reload()
        expect(page.get_by_label("Gloss selection", exact=True)).to_have_value("first-entry")
        expect(page.locator("#reset-helps")).to_be_disabled()
        expect(origin.locator("textarea")).to_have_value("Synthetic step:test-choice")
        assert not errors
        browser.close()


@pytest.mark.parametrize("failure_stage", ["save", "review"])
def test_reset_progress_reports_failures_and_restores_controls(review_server, monkeypatch, failure_stage):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, identity, _ = review_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page()
        project_url = url + f"/api/projects/{identity}"
        page.goto(url)
        expect(page.locator(".help-row").first).to_be_visible()
        expect(page.locator("#reset-helps")).to_be_enabled()
        before = page.request.get(project_url).json()
        assert before["config"]["decisions"] == {}
        route_url = project_url if failure_stage == "save" else project_url + "/review"
        page.route(
            route_url,
            lambda route: route.fulfill(status=409, json={"detail": "Synthetic reset failure"}),
        )
        page.get_by_role("button", name="Reset helps to defaults", exact=True).click()
        expected = (
            "Reset failed" if failure_stage == "save" else "Helps reset, but the review could not refresh"
        )
        expect(page.locator("#reset-helps-status")).to_have_class("info-card reset-helps-status error")
        expect(page.locator("#reset-helps-message")).to_have_text(f"{expected}: Synthetic reset failure")
        expect(page.locator("#reset-helps-progress")).to_be_hidden()
        expect(page.locator("#review-list")).to_have_attribute("aria-busy", "false")
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")
        expect(page.locator("#reload-review")).to_be_enabled()
        expect(page.get_by_label("Gloss selection", exact=True)).to_be_enabled()
        page.unroute(route_url)
        saved = page.request.get(project_url).json()
        if failure_stage == "save":
            expect(page.get_by_label("Gloss selection", exact=True)).to_have_value("reviewed")
            expect(page.locator("#reset-helps")).to_be_enabled()
            assert saved == before
            expect(page.locator(".help-row").first.locator("textarea")).to_be_enabled()
        else:
            expect(page.get_by_label("Gloss selection", exact=True)).to_have_value("first-entry")
            expect(page.locator("#reset-helps")).to_be_disabled()
            assert saved["config"]["gloss_selection"] == "first-entry"
            assert saved["revision"] == before["revision"] + 1
            page.locator("#reload-review").click()
            expect(page.locator(".help-row").first).to_be_visible()
        browser.close()


def test_word_colors_default_palette_customization_and_project_persistence(review_server, monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, identity, _ = review_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator(".help-row").first).to_be_visible()
        expect(page.locator("#edition-title")).to_have_text("Proverbs reader")
        expect(page.locator("#word-colors")).to_have_value("auto")
        expect(page.locator("#word-color-settings")).to_be_hidden()
        page.get_by_text("Page & reading settings", exact=True).click()
        page.locator("#word-colors").select_option("word-class")
        page.get_by_text("Palette & class colors", exact=True).click()
        expect(page.locator("#word-color-noun")).to_have_value("preset")
        expect(page.locator("#word-color-custom-noun")).to_have_value("#245a81")
        page.locator("#word-color-custom-noun").fill("#123abc")
        expect(page.locator("#word-color-noun")).to_have_value("custom")
        page.locator("#word-color-name").select_option("auto")
        expect(page.locator("#word-color-custom-name")).to_be_disabled()
        with page.expect_response(lambda response: response.request.method == "PUT"):
            page.get_by_role("button", name="Save settings", exact=True).click()
        expect(page.locator("#notice")).to_have_text("Edition settings saved")
        saved = page.request.get(url + f"/api/projects/{identity}").json()
        assert saved["config"]["layout"]["word_color_overrides"] == {"noun": "#123ABC", "name": "auto"}
        page.reload()
        expect(page.locator(".help-row").first).to_be_visible()
        expect(page.locator("#word-colors")).to_have_value("word-class")
        page.get_by_text("Page & reading settings", exact=True).click()
        page.get_by_text("Palette & class colors", exact=True).click()
        expect(page.locator("#word-color-noun")).to_have_value("custom")
        expect(page.locator("#word-color-custom-noun")).to_have_value("#123abc")
        expect(page.locator("#word-color-name")).to_have_value("auto")
        expect(page.locator("#word-color-verb")).to_have_value("preset")
        page.set_viewport_size({"width": 390, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        artifacts = ROOT / "test-results"
        artifacts.mkdir(exist_ok=True)
        page.locator("#word-color-settings").screenshot(path=str(artifacts / "word-color-settings.png"))
        page.locator("#word-colors").select_option("auto")
        expect(page.locator("#word-color-settings")).to_be_hidden()
        with page.expect_response(lambda response: response.request.method == "PUT"):
            page.get_by_role("button", name="Save settings", exact=True).click()
        expect(page.locator("#notice")).to_have_text("Edition settings saved")
        page.reload()
        expect(page.locator(".help-row").first).to_be_visible()
        expect(page.locator("#word-colors")).to_have_value("auto")
        page.get_by_text("Page & reading settings", exact=True).click()
        page.locator("#word-colors").select_option("word-class")
        page.get_by_text("Palette & class colors", exact=True).click()
        expect(page.locator("#word-color-noun")).to_have_value("custom")
        page.locator("#word-color-noun").select_option("preset")
        with page.expect_response(lambda response: response.request.method == "PUT"):
            page.get_by_role("button", name="Save settings", exact=True).click()
        expect(page.locator("#notice")).to_have_text("Edition settings saved")
        saved = page.request.get(url + f"/api/projects/{identity}").json()
        assert saved["config"]["layout"]["word_color_overrides"] == {"name": "auto"}
        page.locator("#word-color-custom-noun").fill("#ab1234")
        page.get_by_role("button", name="Set all to no color", exact=True).click()
        expect(page.locator("#word-colors")).to_have_value("word-class")
        categories = page.locator("[data-word-class]").evaluate_all(
            "rows => rows.map(row => row.dataset.wordClass)"
        )
        assert "name" in categories
        for category in categories:
            expect(page.locator(f"#word-color-{category}")).to_have_value("auto")
            expect(page.locator(f"#word-color-custom-{category}")).to_be_disabled()
        assert page.request.get(url + f"/api/projects/{identity}").json() == saved
        with page.expect_response(lambda response: response.request.method == "PUT"):
            page.get_by_role("button", name="Save settings", exact=True).click()
        expect(page.locator("#notice")).to_have_text("Edition settings saved")
        saved = page.request.get(url + f"/api/projects/{identity}").json()
        assert saved["config"]["layout"]["word_color_overrides"] == dict.fromkeys(categories, "auto")
        page.reload()
        expect(page.locator(".help-row").first).to_be_visible()
        page.get_by_text("Page & reading settings", exact=True).click()
        page.get_by_text("Palette & class colors", exact=True).click()
        for category in categories:
            expect(page.locator(f"#word-color-{category}")).to_have_value("auto")
        page.locator("#word-color-verb").select_option("preset")
        expect(page.locator("#word-color-custom-verb")).to_be_enabled()
        with page.expect_response(lambda response: response.request.method == "PUT"):
            page.get_by_role("button", name="Save settings", exact=True).click()
        expect(page.locator("#notice")).to_have_text("Edition settings saved")
        saved = page.request.get(url + f"/api/projects/{identity}").json()
        assert saved["config"]["layout"]["word_color_overrides"] == {
            category: "auto" for category in categories if category != "verb"
        }
        page.locator("#word-color-custom-verb").fill("#ab1234")
        page.get_by_role("button", name="Set all to presets", exact=True).click()
        expect(page.locator("#word-colors")).to_have_value("word-class")
        for category in categories:
            row = page.locator(f"[data-word-class='{category}']")
            expect(page.locator(f"#word-color-{category}")).to_have_value("preset")
            expect(page.locator(f"#word-color-custom-{category}")).to_have_value(
                row.get_attribute("data-preset-color").lower()
            )
            expect(page.locator(f"#word-color-custom-{category}")).to_be_enabled()
        assert page.request.get(url + f"/api/projects/{identity}").json() == saved
        with page.expect_response(lambda response: response.request.method == "PUT"):
            page.get_by_role("button", name="Save settings", exact=True).click()
        expect(page.locator("#notice")).to_have_text("Edition settings saved")
        saved = page.request.get(url + f"/api/projects/{identity}").json()
        assert saved["config"]["layout"]["word_color_overrides"] == {}
        page.reload()
        expect(page.locator(".help-row").first).to_be_visible()
        page.get_by_text("Page & reading settings", exact=True).click()
        page.get_by_text("Palette & class colors", exact=True).click()
        for category in categories:
            expect(page.locator(f"#word-color-{category}")).to_have_value("preset")
        page.get_by_role("button", name="Build reader PDF", exact=False).click()
        expect(page.locator("#preview-panel")).to_be_visible()
        job = page.request.get(url + "/api/jobs").json()[0]
        assert job["config"]["layout"] == saved["config"]["layout"]
        assert job["project_revision"] == saved["revision"]
        assert not errors
        browser.close()


@pytest.mark.parametrize("view", ["cards", "grid"])
@pytest.mark.parametrize("batch", [False, True], ids=["row-save", "page-save"])
def test_review_defaults_to_book_scope_and_allows_occurrence_override(
    consonant_review, review_server, monkeypatch, view, batch
):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, identity, csrf = review_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page()
        project_url = url + f"/api/projects/{identity}"
        project = page.request.get(project_url).json()
        project["config"]["passage"] = "1:1"
        assert page.request.put(
            project_url,
            headers={"X-Reader-Token": csrf},
            data={"revision": project["revision"], "config": project["config"]},
        ).ok
        page.goto(url)
        page.locator("#review-view").select_option(view)
        expect(page.locator(".help-row")).to_have_count(4)
        for row in page.locator(".help-row").all():
            expect_review_choice(row, "Apply to", "book")
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")
        origin = page.locator("[data-anchor='test-origin:0']")
        expect(origin.get_by_role("button", name="Save all", exact=True)).to_be_visible()
        if view == "grid":
            expect(origin.locator("select")).to_have_count(0)
            expect(origin.locator(".hint")).to_have_count(0)
            source = origin.get_by_role("radiogroup", name="Source entry for test-origin:0", exact=True)
            expect(source.get_by_role("radio")).to_have_count(3)
            expect_review_choice(origin, "Source entry", "")
            scope = origin.get_by_role("radiogroup", name="Apply to for test-origin:0", exact=True)
            scope.hover()
            assert "שמר" in scope.get_attribute("title")
            assert "Replaces earlier edits" in scope.get_attribute("title")
        else:
            expect(origin.locator(".hint")).to_be_visible()
        set_review_choice(origin, "Source entry", "step:test-choice")
        expect(origin.locator("textarea")).to_have_value("Synthetic step:test-choice")
        if view == "grid":
            # Native arrow-key selection changes only this row's source choice.
            selected = source.locator("input[value='step:test-choice']")
            selected.focus()
            selected.press("ArrowDown")
            expect_review_choice(origin, "Source entry", "step:test-alternate")
            expect(origin.locator("textarea")).to_have_value("Synthetic step:test-alternate")
            neighbor = page.locator("[data-anchor='test-prefix:0']")
            expect_review_choice(neighbor, "Source entry", "")
            expect_review_choice(neighbor, "Apply to", "book")
            source.locator("input[value='step:test-alternate']").press("ArrowUp")
            expect_review_choice(origin, "Source entry", "step:test-choice")
        origin.locator("textarea").fill("Synthetic default book gloss")
        endpoint = "/decisions/batch" if batch else "/decisions"
        with page.expect_response(lambda response: response.url.endswith(endpoint)) as response:
            if batch:
                page.locator("#save-page").click()
            else:
                origin.get_by_role("button", name="Save all", exact=True).click()
        assert response.value.ok
        payload = response.value.request.post_data_json
        assert (payload["edits"][0] if batch else payload)["scope"] == "book"
        result = response.value.json()
        applied = {"test-origin:0", "test-repeat:0", "test-ketiv:0", "test-qere:0", "test-segmented:0"}
        assert set(result["applied"]) == applied
        assert {item["anchor"] for item in result["skipped"]} == {
            "test-segmented:1",
            "test-homograph:0",
            "test-unmatched:0",
        }
        decisions = result["project"]["config"]["decisions"]
        assert set(decisions) == applied
        assert all(decision["gloss"] == "Synthetic default book gloss" for decision in decisions.values())
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")
        expect_review_choice(origin, "Apply to", "book")

        # An explicit narrower choice survives view switches and review refreshes.
        set_review_choice(origin, "Apply to", "occurrence")
        origin.locator("textarea").fill("Synthetic one occurrence gloss")
        page.locator("#review-view").select_option("grid" if view == "cards" else "cards")
        page.locator("#reload-review").click()
        expect_review_choice(origin, "Apply to", "occurrence")
        expect_review_choice(origin, "Source entry", "step:test-choice")
        expect(origin.locator(".hint")).to_be_hidden()
        expect(origin.get_by_role("button", name="Save help", exact=True)).to_be_visible()
        with page.expect_response(lambda response: response.url.endswith(endpoint)) as response:
            if batch:
                page.locator("#save-page").click()
            else:
                origin.get_by_role("button", name="Save help", exact=True).click()
        assert response.value.ok
        result = response.value.json()
        assert result["applied"] == ["test-origin:0"]
        saved = page.request.get(project_url).json()["config"]["decisions"]
        assert saved["test-origin:0"]["gloss"] == "Synthetic one occurrence gloss"
        assert all(saved[anchor] == decisions[anchor] for anchor in applied - {"test-origin:0"})
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")
        expect_review_choice(origin, "Apply to", "book")
        browser.close()


def test_grid_page_entry_drafts_shortcuts_atomic_saves_and_mobile(review_server, monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
    url, identity, csrf = review_server
    output = ROOT / "test-results" / "grid-review"
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator(".help-row")).to_have_count(40)
        page.locator("#resolved-only").check()
        page.locator("#review-view").select_option("grid")
        expect(page.get_by_role("table")).to_be_visible()
        rows = page.locator(".help-row")
        first_anchor, second_anchor = [rows.nth(i).get_attribute("data-anchor") for i in range(2)]
        first = page.locator(f"[data-anchor='{first_anchor}']")
        second = page.locator(f"[data-anchor='{second_anchor}']")
        # These independent wording edits explicitly use the narrower scope.
        set_review_choice(first, "Apply to", "occurrence")
        set_review_choice(second, "Apply to", "occurrence")
        first.locator("textarea").fill("Synthetic grid first gloss")
        first.locator("textarea").press("Enter")
        expect(second.locator("textarea")).to_be_focused()
        second.locator("textarea").press("Shift+Enter")
        expect(first.locator("textarea")).to_be_focused()
        second.locator("textarea").press("Control+d")
        expect(page.locator("#notice")).to_contain_text("same chosen source entry")
        second.locator("textarea").fill("Synthetic grid second gloss")
        expect(page.locator("#draft-count")).to_have_text("2 unsaved edits on this page")
        expect(first.locator(".gloss-provenance")).to_contain_text("Editorial wording")
        page.screenshot(path=str(output / "desktop.png"))

        page.locator("#next").click()
        expect(page.locator("#draft-count")).to_contain_text("2 elsewhere")
        page.locator("#previous").click()
        expect(first.locator("textarea")).to_have_value("Synthetic grid first gloss")
        page.locator("#review-view").select_option("cards")
        expect(first.locator("textarea")).to_have_value("Synthetic grid first gloss")
        page.locator("#search").fill("no such lexical row")
        expect(page.locator(".help-row")).to_have_count(0)
        page.locator("#search").fill("")
        expect(second.locator("textarea")).to_have_value("Synthetic grid second gloss")
        page.locator("#edited-only").check()
        expect(page.locator(".help-row")).to_have_count(2)
        page.locator("#edited-only").uncheck()
        page.locator("#reload-review").click()
        expect(second.locator("textarea")).to_have_value("Synthetic grid second gloss")
        page.locator("#review-view").select_option("grid")

        # Saving one row must retain the other row's draft through the refresh.
        first.get_by_role("button", name="Save help", exact=True).click()
        expect(page.locator("#notice")).to_have_text("Lexical decision saved")
        expect(second.locator("textarea")).to_have_value("Synthetic grid second gloss")
        expect(page.locator("#draft-count")).to_have_text("1 unsaved edit on this page")
        page.locator("#build").click()
        expect(page.locator("#notice")).to_contain_text("Save or discard")
        assert page.request.get(url + "/api/jobs").json() == []
        before = page.request.get(url + f"/api/projects/{identity}").json()
        with page.expect_response(lambda r: r.url.endswith("/decisions/batch")) as response:
            second.locator("textarea").press("Control+Enter")
        assert response.value.ok
        saved = response.value.json()["project"]
        assert saved["revision"] == before["revision"] + 1
        assert saved["config"]["decisions"][first_anchor]["gloss"] == "Synthetic grid first gloss"
        assert saved["config"]["decisions"][second_anchor]["gloss"] == "Synthetic grid second gloss"
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")
        page.reload()
        expect(page.locator("#review-view")).to_have_value("grid")
        page.locator("#resolved-only").check()
        expect(second.locator("textarea")).to_have_value("Synthetic grid second gloss")

        # A spreadsheet column fills consecutive glosses as editorial drafts.
        first.locator("textarea").evaluate(
            "node => {const data = new DataTransfer(); data.setData('text/plain', "
            "'Synthetic pasted first\\nSynthetic pasted second\\n'); "
            "node.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));}"
        )
        expect(first.locator("textarea")).to_have_value("Synthetic pasted first")
        expect(second.locator("textarea")).to_have_value("Synthetic pasted second")
        expect(page.locator("#draft-count")).to_have_text("2 unsaved edits on this page")
        first.get_by_role("button", name=f"Use source gloss for {first_anchor}", exact=True).click()
        review = page.request.get(url + f"/api/projects/{identity}/review").json()
        source_row = next(row for row in review["rows"] if row["anchor"] == first_anchor)
        source_gloss = next(c["gloss"] for c in source_row["candidates"] if c["id"] == source_row["entry_id"])
        expect(first.locator("textarea")).to_have_value(source_gloss)
        expect(first.locator(".gloss-provenance")).to_have_text("STEP source gloss")
        first.get_by_role("button", name=f"Undo edits for {first_anchor}", exact=True).click()
        expect(first.locator("textarea")).to_have_value("Synthetic grid first gloss")
        page.locator("#discard-page").click()
        expect(second.locator("textarea")).to_have_value("Synthetic grid second gloss")

        # Copy down requires the same source identity; it never guesses from spelling.
        repeated_id = next(
            entry
            for entry, count in Counter(
                row["entry_id"] for row in review["rows"] if row["status"] == "resolved"
            ).items()
            if count > 1
        )
        page.locator("#search").fill(repeated_id)
        repeated = page.locator(".help-row textarea")
        repeated.nth(0).fill("Synthetic repeated entry gloss")
        repeated.nth(1).press("Control+d")
        expect(repeated.nth(1)).to_have_value("Synthetic repeated entry gloss")
        page.locator("#discard-page").click()
        page.locator("#search").fill("")

        # Ambiguous choices still require entry selection before gloss paste or save.
        page.locator("#unresolved-only").check()
        unresolved = page.locator(".help-row").first
        unresolved.locator("textarea").evaluate(
            "node => {const data = new DataTransfer(); data.setData('text/plain', "
            "'Synthetic unsupported paste\\nSynthetic unsupported paste'); "
            "node.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));}"
        )
        expect(page.locator("#notice")).to_contain_text("Choose a source entry")
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")
        unresolved.locator("textarea").fill("Synthetic unresolved draft")
        page.locator("#save-page").click()
        expect(page.locator("#notice")).to_contain_text("Choose a source entry")
        expect(unresolved.locator("textarea")).to_have_value("Synthetic unresolved draft")
        # Pending rows remain discoverable even if another status filter would hide them.
        page.locator("#resolved-only").check()
        page.locator("#edited-only").check()
        expect(page.locator(".help-row")).to_have_count(1)
        page.locator("#discard-page").click()
        page.locator("#edited-only").uncheck()

        # Server validation errors retain every draft and save none of the page.
        before = page.request.get(url + f"/api/projects/{identity}").json()
        first.locator("textarea").fill("Synthetic valid page gloss")
        second.locator("textarea").fill("Synthetic invalid\ngloss")
        with page.expect_response(lambda r: r.url.endswith("/decisions/batch")) as response:
            page.locator("#save-page").click()
        assert response.value.status == 422
        assert page.request.get(url + f"/api/projects/{identity}").json() == before
        expect(first.locator("textarea")).to_have_value("Synthetic valid page gloss")
        expect(second.locator("textarea")).to_have_value("Synthetic invalid\ngloss")
        expect(page.locator("#save-page")).to_be_enabled()
        page.locator("#discard-page").click()

        # Save-and-next follows the next source page even when omissions remove rows.
        page.locator("#review-page-size").select_option("20")
        expect(page.locator(".help-row")).to_have_count(20)
        page.locator("#next").click()
        following = page.locator(".help-row").first.get_attribute("data-anchor")
        page.locator("#previous").click()
        for row in page.locator(".help-row").all():
            set_review_choice(row, "Apply to", "occurrence")
        page.locator("#omit-page").click()
        expect(page.locator("#draft-count")).to_have_text("20 unsaved edits on this page")
        page.locator("#save-next").click()
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")
        expect(page.locator(".help-row").first).to_have_attribute("data-anchor", following)
        page.locator("#show-all").check()
        for row in page.locator(".help-row").all():
            set_review_choice(row, "Apply to", "occurrence")
        page.locator("#include-page").click()
        page.locator("#save-page").click()
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")

        # Grid uses horizontal scrolling within the review, retaining a bounded RTL popup.
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        reference = page.locator(".verse-reference").first
        reference.click()
        expect(page.locator("#verse-context")).to_be_visible()
        expect(page.locator(".verse-context-highlight")).to_have_count(1)
        assert (
            page.locator("#verse-context-text").evaluate("node => getComputedStyle(node).direction") == "rtl"
        )
        bounds = page.locator("#verse-context").bounding_box()
        assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
        page.screenshot(path=str(output / "mobile.png"))
        page.locator("#close-verse-context").click()
        page.set_viewport_size({"width": 1440, "height": 1000})

        # A stale tab fails atomically, keeping its typed text for reconciliation.
        first = page.locator(".help-row").first
        first.locator("textarea").fill("Synthetic stale-tab draft")
        latest = page.request.get(url + f"/api/projects/{identity}").json()
        latest["config"]["name"] = "Changed in another tab"
        assert page.request.put(
            url + f"/api/projects/{identity}",
            headers={"X-Reader-Token": csrf},
            data={"revision": latest["revision"], "config": latest["config"]},
        ).ok
        with page.expect_response(lambda r: r.url.endswith("/decisions/batch")) as response:
            page.locator("#save-page").click()
        assert response.value.status == 409
        expect(first.locator("textarea")).to_have_value("Synthetic stale-tab draft")
        expect(page.locator("#notice")).to_contain_text("another tab")
        page.locator("#discard-page").click()

        # Genuine names stay visible as scripture and inspectable omissions, with inclusion disabled.
        latest = page.request.get(url + f"/api/projects/{identity}").json()
        latest["config"]["passage"] = "1:1"
        assert page.request.put(
            url + f"/api/projects/{identity}",
            headers={"X-Reader-Token": csrf},
            data={"revision": latest["revision"], "config": latest["config"]},
        ).ok
        page.reload()
        expect(page.locator(".help-row")).to_have_count(3)
        expect(page.locator("#coverage")).to_contain_text("NAMES OMITTED")
        page.locator("#show-all").check()
        expect(page.locator(".help-row")).to_have_count(6)
        for anchor in ["20Nvk:0", "20vuQ:0", "20k5P:0"]:
            name = page.locator(f"[data-anchor='{anchor}']")
            expect(name.get_by_role("checkbox")).not_to_be_checked()
            expect(name.get_by_role("checkbox")).to_be_disabled()
            expect(name.locator(".row-status")).to_have_text("name omitted")
            name.get_by_role("button", name=f"Verse context for {anchor}", exact=True).click()
            expect(page.locator(".verse-context-highlight")).to_have_count(1)
            page.locator("#close-verse-context").click()
        page.locator("#include-page").click()
        expect(page.locator("#draft-count")).to_have_text("3 unsaved edits on this page")
        page.locator("#discard-page").click()
        assert errors == [], errors
        browser.close()
