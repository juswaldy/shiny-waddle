"""Opt-in browser checks against the attributable offline source fixtures."""

import os
import socket
import threading
import time
from collections import Counter
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from bible_reader.models import ProjectConfig
from bible_reader.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(os.environ.get("READER_BROWSER_TESTS") != "1", reason="Set READER_BROWSER_TESTS=1"),
]


@pytest.fixture
def review_server(source_state):
    app = create_app(source_state, start_worker=False)
    project = app.state.store.create_project(ProjectConfig(selection="all"))
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
        for scope in page.locator(".help-row select[aria-label^='Apply to for ']").all():
            expect(scope).to_have_value("book")
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")
        origin = page.locator("[data-anchor='test-origin:0']")
        expect(origin.get_by_role("button", name="Save all", exact=True)).to_be_visible()
        expect(origin.locator(".hint")).to_be_visible()
        origin.get_by_role("combobox", name="Source entry for test-origin:0", exact=True).select_option(
            "step:test-choice"
        )
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
        scope = origin.get_by_role("combobox", name="Apply to for test-origin:0", exact=True)
        expect(scope).to_have_value("book")

        # An explicit narrower choice survives view switches and review refreshes.
        scope.select_option("occurrence")
        origin.locator("textarea").fill("Synthetic one occurrence gloss")
        page.locator("#review-view").select_option("grid" if view == "cards" else "cards")
        page.locator("#reload-review").click()
        expect(scope).to_have_value("occurrence")
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
        expect(scope).to_have_value("book")
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
        first.get_by_role("combobox", name=f"Apply to for {first_anchor}", exact=True).select_option(
            "occurrence"
        )
        second.get_by_role("combobox", name=f"Apply to for {second_anchor}", exact=True).select_option(
            "occurrence"
        )
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

        # Unmatched choices require explicit entry selection before any gloss paste or save.
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
        for scope in page.locator(".help-row select[aria-label^='Apply to for ']").all():
            scope.select_option("occurrence")
        page.locator("#omit-page").click()
        expect(page.locator("#draft-count")).to_have_text("20 unsaved edits on this page")
        page.locator("#save-next").click()
        expect(page.locator("#draft-count")).to_have_text("No unsaved edits")
        expect(page.locator(".help-row").first).to_have_attribute("data-anchor", following)
        page.locator("#show-all").check()
        for scope in page.locator(".help-row select[aria-label^='Apply to for ']").all():
            scope.select_option("occurrence")
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
