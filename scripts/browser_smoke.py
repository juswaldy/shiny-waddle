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
            page.locator("#project-form summary").click()
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
            row = page.locator('[data-anchor="20qg1:0"]')
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
            page.locator("#project-form summary").click()
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
            page.locator("#unresolved-only").check()
            repeated = page.locator('[data-anchor="207mS:0"]')
            scope = repeated.get_by_role("combobox", name="Apply to for 207mS:0", exact=True)
            expect(scope).to_have_value("occurrence")
            scope.select_option("book")
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
                "occurrence"
            )
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            elsewhere.get_by_role("combobox", name="Apply to for 20NTZ:0", exact=True).select_option("book")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(OUTPUT / "review-mobile.png"), full_page=True)
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
