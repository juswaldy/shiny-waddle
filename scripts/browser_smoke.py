"""Exercise the actual local server, worker, browser, and downloadable artifacts."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "test-results" / time.strftime("browser-%Y%m%d-%H%M%S")
OUTPUT.mkdir(parents=True)
STATE = OUTPUT / "state"
(STATE / "raw").mkdir(parents=True)
for name in ("Prov.xml", "TBESH.txt", "OSHB-LICENSE.md", "STEP-README.md"):
    source = ROOT / ".reader" / "raw" / name
    if not source.is_file():
        raise SystemExit("First run: bible-reader sources import --book Prov")
    shutil.copyfile(source, STATE / "raw" / name)
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
url = f"http://127.0.0.1:{port}"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".tools/browsers"))
errors = []


def check_verse_context(page, source_row, verse, *, screenshot=None):
    """Inspect real source Unicode and the popup's hover, pin, and keyboard behavior."""
    article = page.locator(f"[data-anchor='{source_row['anchor']}'].help-row")
    reference = article.get_by_role("button", name=f"Verse context for {source_row['anchor']}", exact=True)
    popup = page.locator("#verse-context")
    reference.hover()
    expect(popup).to_be_visible()
    expect(popup).to_have_attribute("data-pinned", "false")
    expect(reference).to_have_attribute("aria-expanded", "true")
    tokens = popup.locator(".verse-context-token")
    assert tokens.evaluate_all("nodes => nodes.map(n => n.dataset.tokenId)") == [
        t["id"] for t in verse["tokens"] if t["source_surface"].replace("/", "")
    ]
    assert tokens.all_text_contents() == [
        t["source_surface"].replace("/", "") for t in verse["tokens"] if t["source_surface"].replace("/", "")
    ]
    highlight = popup.locator(".verse-context-highlight")
    expect(highlight).to_have_count(1)
    expect(highlight).to_have_attribute("data-token-id", source_row["token_id"])
    expect(highlight).to_have_text(source_row["source_surface"].replace("/", ""))
    assert highlight.evaluate(
        "node => {const s = getComputedStyle(node); const rgb = s.color.match(/\\d+/g).map(Number); "
        "return Number(s.fontWeight) >= 700 && parseFloat(s.fontSize) > parseFloat(getComputedStyle(node.parentElement).fontSize) "
        "&& rgb[0] > rgb[1] && rgb[0] > rgb[2];}"
    )
    assert popup.locator("#verse-context-text").evaluate("node => getComputedStyle(node).direction") == "rtl"
    assert popup.locator(".verse-context-reading").all_text_contents() == [
        t["reading"] for t in verse["tokens"] if t["reading"] in {"ketiv", "qere"}
    ]
    page.mouse.move(0, 0)
    expect(popup).to_be_hidden()
    reference.focus()
    expect(popup).to_be_visible()
    reference.press("Enter")
    expect(popup).to_have_attribute("data-pinned", "true")
    page.mouse.move(0, 0)
    article.locator("textarea").focus()
    expect(popup).to_be_visible()  # Editing must leave the pinned context in view.
    if screenshot:
        page.screenshot(path=str(OUTPUT / screenshot), full_page=False)
    page.keyboard.press("Escape")
    expect(popup).to_be_hidden()
    expect(reference).to_have_attribute("aria-expanded", "false")
    reference.click()
    expect(popup).to_have_attribute("data-pinned", "true")
    other = next(
        r
        for r in page.locator(".verse-reference").all()
        if r.get_attribute("aria-label") != f"Verse context for {source_row['anchor']}"
    )
    other.hover()
    expect(popup).to_have_attribute("data-review-anchor", source_row["anchor"])
    other.click()
    expect(popup).to_have_attribute(
        "data-review-anchor", other.evaluate("node => node.closest('.help-row').dataset.anchor")
    )
    expect(popup).to_have_attribute("data-pinned", "true")
    popup.get_by_role("button", name="Close verse context", exact=True).click()
    expect(popup).to_be_hidden()
    reference.click()
    expect(popup).to_be_visible()
    reference.click()
    expect(popup).to_be_hidden()


with (OUTPUT / "server.log").open("w") as log:
    server = subprocess.Popen(
        [sys.executable, "-m", "bible_reader", "--state", str(STATE), "serve", "--port", str(port)],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(80):
            try:
                with urllib.request.urlopen(url + "/api/health", timeout=1):
                    break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError("Local server exited; inspect server.log") from None
                time.sleep(0.25)
        else:
            raise RuntimeError("Local server did not become ready")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chromium")
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url)
            expect(page.locator(".help-row")).to_have_count(40)
            expect(page.locator("#coverage")).to_contain_text("37")
            page.screenshot(path=str(OUTPUT / "review-desktop.png"), full_page=False)
            page.get_by_text("Page & reading settings", exact=True).click()
            expect(page.locator("#paper")).to_have_value("reader")
            expect(page.locator("#custom-paper")).to_be_hidden()
            expect(page.locator("#paper-width")).to_be_disabled()
            page.locator("#paper").select_option("custom")
            expect(page.locator("#custom-paper")).to_be_visible()
            page.locator("#paper-width").fill("")
            page.locator("#build").click()
            expect(page.locator("#notice")).to_contain_text("Enter a valid custom paper")
            assert page.request.get(url + "/api/jobs").json() == []
            page.locator("#paper-width").fill("160.5")
            page.locator("#paper-height").fill("230.25")
            expect(page.locator("#verse-layout")).to_have_value("continuous")
            page.locator("#verse-layout").select_option("verse-per-line")
            expect(page.locator("#cantillation")).to_have_value("hide")
            expect(page.locator('#cantillation option[value="consonants"]')).to_have_text(
                "Consonants + maqqef"
            )
            page.locator("#cantillation").select_option(label="Consonants only")
            page.get_by_role("button", name="Save settings", exact=True).click()
            expect(page.locator("#notice")).to_have_text("Edition settings saved")
            page.get_by_role("checkbox", name="Rework resolved helps", exact=True).check()
            row = page.locator('[data-anchor="20qg1:0"]')
            expect(row.locator(".row-status")).to_have_text("resolved")
            assert page.locator(".row-status.unresolved").count() == 0
            row.get_by_role("combobox", name="Apply to for 20qg1:0", exact=True).select_option("occurrence")
            row.locator("textarea").fill("Editorial browser test gloss")
            row.get_by_role("button", name="Save help").click()
            expect(row.locator(".note-label")).to_have_text("23")
            page.reload()
            expect(page.locator("#paper")).to_have_value("custom")
            expect(page.locator("#paper-width")).to_have_value("160.5")
            expect(page.locator("#paper-height")).to_have_value("230.25")
            expect(page.locator("#verse-layout")).to_have_value("verse-per-line")
            expect(page.locator("#cantillation")).to_have_value("consonants-only")
            expect(page.locator('[data-anchor="20qg1:0"] textarea')).to_have_value(
                "Editorial browser test gloss"
            )
            page.locator("#build").click()
            expect(page.locator("#download-pdf")).to_be_visible(timeout=90_000)
            expect(page.locator("#build-status")).to_contain_text("Current saved edition")
            with page.expect_download() as downloading:
                page.locator("#download-pdf").click()
            downloading.value.save_as(OUTPUT / "downloaded-reader.pdf")
            assert (OUTPUT / "downloaded-reader.pdf").read_bytes().startswith(b"%PDF-")
            for pdf_page in PdfReader(OUTPUT / "downloaded-reader.pdf").pages:
                assert abs(float(pdf_page.mediabox.width) * 25.4 / 72 - 160.5) < 0.01
                assert abs(float(pdf_page.mediabox.height) * 25.4 / 72 - 230.25) < 0.01
            bundle = page.request.get(url + page.locator("#download-bundle").get_attribute("href"))
            assert bundle.ok and bundle.body().startswith(b"PK")
            (OUTPUT / "downloaded-bundle.zip").write_bytes(bundle.body())
            # Layout and consonant choices must reach the immutable worker build config.
            page.get_by_text("Page & reading settings", exact=True).click()
            page.locator("#paper").select_option("reader")
            expect(page.locator("#custom-paper")).to_be_hidden()
            expect(page.locator("#paper-height")).to_be_disabled()
            page.locator("#verse-layout").select_option("continuous")
            for policy, filename in [
                ("consonants", "maqqef-reader.pdf"),
                ("consonants-maqqef-sof-pasuq", "default-reader.pdf"),
            ]:
                page.locator("#cantillation").select_option(policy)
                previous_pdf = page.locator("#download-pdf").get_attribute("href")
                page.locator("#build").click()
                expect(page.locator("#download-pdf")).not_to_have_attribute(
                    "href", previous_pdf, timeout=90_000
                )
                expect(page.locator("#download-pdf")).to_be_visible(timeout=90_000)
                pdf = page.request.get(url + page.locator("#download-pdf").get_attribute("href"))
                (OUTPUT / filename).write_bytes(pdf.body())
                for pdf_page in PdfReader(OUTPUT / filename).pages:
                    assert abs(float(pdf_page.mediabox.width) * 25.4 / 72 - 140) < 0.01
                    assert abs(float(pdf_page.mediabox.height) * 25.4 / 72 - 216) < 0.01
            jobs = page.request.get(url + "/api/jobs").json()
            successful_builds = [j for j in jobs if j["kind"] == "build" and j["status"] == "succeeded"]
            assert {j["config"]["layout"]["verse_layout"] for j in successful_builds} == {
                "continuous",
                "verse-per-line",
            }
            assert {j["config"]["layout"]["paper"] for j in successful_builds} == {"reader", "custom"}
            assert {j["config"]["cantillation"] for j in successful_builds} == {
                "consonants-only",
                "consonants",
                "consonants-maqqef-sof-pasuq",
            }
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(
                2000
            )  # Allow Chromium's native PDF viewer to paint before the visual proof.
            page.screenshot(path=str(OUTPUT / "preview-desktop.png"), full_page=False)
            # Importing already pinned local sources must work through the queue offline.
            page.locator('[data-tab="sources"]').click()
            page.locator("#import-source").click()
            page.wait_for_function(
                "async () => (await (await fetch('/api/jobs')).json()).some(j => j.kind === 'import' && j.status === 'succeeded')",
                timeout=30_000,
            )
            # Failed builds must never keep an unrelated successful PDF/export visible.
            page.locator("#passage").fill("1:99")
            page.locator("#selection").select_option("all")
            page.locator("#build").click()
            expect(page.locator("#build-status")).to_contain_text("endpoints", timeout=20_000)
            expect(page.locator("#pdf-preview")).to_be_hidden()
            expect(page.locator("#download-pdf")).to_be_hidden()
            page.locator("#passage").fill("1:29-2:12")
            page.locator("#selection").select_option("reference")
            page.locator("#build").click()
            page.locator("#cancel-build").click()
            expect(page.locator("#build-status")).to_contain_text("cancelled", timeout=20_000)
            page.locator('[data-tab="review"]').click()
            # Resolve repeated, differently pointed spellings throughout the actual pinned book.
            page.locator("#selection").select_option("all")
            page.get_by_role("button", name="Save settings", exact=True).click()
            expect(page.locator("#notice")).to_have_text("Edition settings saved")
            page.get_by_role("checkbox", name="Rework resolved helps", exact=True).check()
            page.locator("#unresolved-only").check()
            expect(page.locator("#resolved-only")).not_to_be_checked()
            repeated = page.locator('[data-anchor="207mS:0"]')
            identity = page.locator("#project-picker").input_value()
            review = page.request.get(url + f"/api/projects/{identity}/review").json()
            source_row = next(r for r in review["rows"] if r["anchor"] == "207mS:0")
            verse = next(v for v in review["verses"] if v["reference"] == source_row["reference"])
            assert source_row["surface"] == "תחת" and source_row["source_surface"] == "תַּ֭חַת"
            check_verse_context(page, source_row, verse, screenshot="verse-context-desktop.png")
            scope = repeated.get_by_role("combobox", name="Apply to for 207mS:0", exact=True)
            expect(scope).to_have_value("book")
            expect(repeated.locator(".hint")).to_contain_text("תחת")
            repeated.get_by_role("button", name="Save all", exact=True).click()
            expect(page.locator("#notice")).to_contain_text("Choose a source entry")
            repeated.get_by_role("combobox", name="Source entry for 207mS:0", exact=True).select_option(
                "step:H8478H"
            )
            with page.expect_response(
                lambda response: response.url.endswith("/decisions") and response.request.method == "POST"
            ) as saving:
                repeated.get_by_role("button", name="Save all", exact=True).click()
            bulk = saving.value.json()
            assert saving.value.ok
            assert len(bulk["applied"]) == 5
            assert [r["anchor"] for r in bulk["skipped"]] == ["20aQh:0"]
            expect(page.locator("#review-edit-result")).to_contain_text("Saved 5 lexical decisions")
            expect(page.locator("#review-edit-result")).to_contain_text("Prov 17 10")
            expect(repeated).to_have_count(0)  # Resolved rows leave the Needs review filter.
            identity = page.locator("#project-picker").input_value()
            saved = page.request.get(url + f"/api/projects/{identity}").json()
            assert all(saved["config"]["decisions"][a]["entry_id"] == "step:H8478H" for a in bulk["applied"])
            assert "20aQh:0" not in saved["config"]["decisions"]
            # A later passage loads the decisions saved outside the original review.
            page.locator("#unresolved-only").uncheck()
            page.locator("#passage").fill("17:13")
            page.get_by_role("button", name="Save settings", exact=True).click()
            expect(page.locator("#notice")).to_have_text("Edition settings saved")
            page.reload()
            elsewhere = page.locator('[data-anchor="20NTZ:0"]')
            expect(
                elsewhere.get_by_role("combobox", name="Source entry for 20NTZ:0", exact=True)
            ).to_have_value("step:H8478H")
            expect(elsewhere.locator(".row-status")).to_have_text("resolved")
            expect(elsewhere.get_by_role("combobox", name="Apply to for 20NTZ:0", exact=True)).to_have_value(
                "book"
            )
            # Two spellings of the same consonants in one verse must retain distinct highlights.
            review = page.request.get(url + f"/api/projects/{identity}/review").json()
            repeated_in_verse = next(r for r in review["rows"] if r["anchor"] == "20kxp:0")
            check_verse_context(page, repeated_in_verse, review["verses"][0])
            # Rework a resolved help without hiding its editor or changing other saved occurrences.
            page.locator("#unresolved-only").check()
            expect(elsewhere).to_have_count(0)
            page.get_by_role("checkbox", name="Rework resolved helps", exact=True).check()
            expect(page.locator("#unresolved-only")).not_to_be_checked()
            expect(elsewhere).to_have_count(1)
            assert page.locator(".row-status.unresolved").count() == 0
            elsewhere.get_by_role("combobox", name="Apply to for 20NTZ:0", exact=True).select_option(
                "occurrence"
            )
            elsewhere.get_by_role("combobox", name="Source entry for 20NTZ:0", exact=True).select_option(
                "step:H8478G"
            )
            elsewhere.locator("textarea").fill("Synthetic resolved-help rework gloss")
            elsewhere.get_by_role("button", name="Verse context for 20NTZ:0", exact=True).click()
            expect(page.locator("#verse-context")).to_have_attribute("data-pinned", "true")
            elsewhere.get_by_role("button", name="Save help", exact=True).click()
            expect(page.locator("#notice")).to_have_text("Lexical decision saved")
            expect(
                page.locator("#verse-context")
            ).to_be_visible()  # Saving reattaches the pin to the new row.
            page.keyboard.press("Escape")
            reworked = page.request.get(url + f"/api/projects/{identity}").json()
            assert reworked["config"]["decisions"]["20NTZ:0"]["entry_id"] == "step:H8478G"
            assert (
                reworked["config"]["decisions"]["20NTZ:0"]["gloss"] == "Synthetic resolved-help rework gloss"
            )
            assert all(
                reworked["config"]["decisions"][a]["entry_id"] == "step:H8478H"
                for a in bulk["applied"]
                if a != "20NTZ:0"
            )
            # The same resolved help can then be reworked throughout the book.
            elsewhere.get_by_role("combobox", name="Apply to for 20NTZ:0", exact=True).select_option("book")
            elsewhere.get_by_role("button", name="Save all", exact=True).click()
            expect(page.locator("#review-edit-result")).to_contain_text("Saved 5 lexical decisions")
            reworked = page.request.get(url + f"/api/projects/{identity}").json()
            assert all(
                reworked["config"]["decisions"][a]["entry_id"] == "step:H8478G"
                and reworked["config"]["decisions"][a]["gloss"] == "Synthetic resolved-help rework gloss"
                for a in bulk["applied"]
            )
            page.reload()
            expect(elsewhere.locator("textarea")).to_have_value("Synthetic resolved-help rework gloss")
            expect(elsewhere.locator(".row-status")).to_have_text("resolved")
            page.get_by_role("checkbox", name="Rework resolved helps", exact=True).check()
            # Explicit omissions can also be found again and re-included in the resolved view.
            elsewhere.get_by_role("combobox", name="Apply to for 20NTZ:0", exact=True).select_option(
                "occurrence"
            )
            elsewhere.get_by_role("checkbox").uncheck()
            elsewhere.get_by_role("button", name="Save help", exact=True).click()
            expect(page.locator("#notice")).to_have_text("Lexical decision saved")
            expect(elsewhere).to_have_count(0)
            page.locator("#show-all").check()
            expect(elsewhere.locator(".row-status")).to_have_text("omitted")
            elsewhere.get_by_role("combobox", name="Apply to for 20NTZ:0", exact=True).select_option(
                "occurrence"
            )
            elsewhere.get_by_role("checkbox").check()
            elsewhere.get_by_role("button", name="Save help", exact=True).click()
            expect(page.locator("#notice")).to_have_text("Lexical decision saved")
            expect(elsewhere.locator(".row-status")).to_have_text("resolved")
            page.locator("#show-all").uncheck()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            elsewhere.get_by_role("combobox", name="Apply to for 20NTZ:0", exact=True).select_option("book")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(OUTPUT / "review-mobile.png"), full_page=True)
            elsewhere.get_by_role("button", name="Verse context for 20NTZ:0", exact=True).click()
            expect(page.locator("#verse-context")).to_be_visible()
            bounds = page.locator("#verse-context").bounding_box()
            assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
            assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 844
            page.screenshot(path=str(OUTPUT / "verse-context-mobile.png"), full_page=False)
            page.locator("#verse-context").get_by_role(
                "button", name="Close verse context", exact=True
            ).click()
            expect(page.locator("#verse-context")).to_be_hidden()
            assert errors == [], errors
            browser.close()
        (OUTPUT / "checks.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "checks": [
                        "review",
                        "edit",
                        "persist",
                        "bulk consonant ambiguity resolution, unsupported matches, filters, and later-passage persistence",
                        "resolved-help filtering, individual and bulk reworking, persistence, and re-including omissions",
                        "pointed/accented verse hover, exact occurrence highlight, K/Q forms, keyboard and click pinning, editing/save persistence, mobile popup bounds",
                        "verse layout selection, reload, and both PDF builds",
                        "consonant policy selection, reload, and all three PDF builds",
                        "default/custom paper selection, validation, persistence, and actual PDF dimensions",
                        "real PDF build",
                        "PDF and bundle download",
                        "offline import job",
                        "failed build hides old PDF",
                        "cancel",
                        "mobile width",
                        "no browser errors",
                    ],
                },
                indent=2,
            )
            + "\n"
        )
        print(f"Browser checks passed. Artifacts: {OUTPUT}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
