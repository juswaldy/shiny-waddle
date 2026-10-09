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
            row = page.locator('[data-anchor="20qg1:0"]')
            row.locator("textarea").fill("Editorial browser test gloss")
            row.get_by_role("button", name="Save help").click()
            expect(row.locator(".note-label")).to_have_text("23")
            page.reload()
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
            bundle = page.request.get(url + page.locator("#download-bundle").get_attribute("href"))
            assert bundle.ok and bundle.body().startswith(b"PK")
            (OUTPUT / "downloaded-bundle.zip").write_bytes(bundle.body())
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
            page.set_viewport_size({"width": 390, "height": 844})
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
