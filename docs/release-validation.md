# Local release 0.2.0 validation

Validated in this workspace on 2026-10-02: Ubuntu 24.04 / WSL x86-64, Python 3.12,
locked Python dependencies, TinyTeX v2026.10 with archived bidi revision 77682,
bundled Ezra SIL. This is the supported local-app release scope, not a remote
hosting or independently edited Bible-publication certification.

## Automated checks

`make check`: **64 passed, plus 8 unittest subtests**; Ruff lint and formatting pass.
One upstream Starlette warning concerns its test client's deprecated httpx adapter;
it does not affect the application or test outcomes.

Coverage includes source Unicode and IDs, separators, ketiv/qere, Aramaic tagging,
unsafe/unknown XML rejection, checksum and atomic acquisition behavior, exclusion
of the restricted Meaning column, ambiguity/missing/base-ID matches, selection,
chapter labels, edited repeated helps, stale decisions, configuration validation,
CLI JSON/TOML behavior, SQLite revision conflicts and concurrent job claims,
cancellation/recovery, local request protection, artifact allowlists/symlinks,
actual XeLaTeX output, portable bundles, and deterministic reader/TeX/page plans.

The PDF integration suite compiles the reference, A4, A5, and US Letter profiles;
a long editorial note; preserved accents; and a single-verse chapter opening.
It also verifies explicit cancellation/overflow failures and refuses overwriting
existing artifacts. PDF checks inspect actual hyperlink destinations, marker
counts, page membership, page counts, and embedded fonts, plus TeX overflow/glyph logs.

## Reference proof

Generated `build/prov-1-29-2-12/reader.pdf` from
`examples/reference.project.json` using a fresh second TeX installation made by
`scripts/setup_tex.py` from the pinned archives. Result:

- One reader page, folio 1329, plus one source-credit page.
- 17 verses, 37 distinct helps, 43 word markers.
- Every observed verse's marker sequence agrees with the reference observation fixture.
- Chapter transition, shared notes, K/Q readings, pointing, mixed-script apparatus,
  margins, and headers inspected on actual rendered PDFs.
- Short STEP Gloss wording is attributed and differs from the scan's long definitions.

A5 produces two reader pages plus credits and repeats needed helps on each page.
The generated ZIP contains the inputs to the renderer, TeX, font/license, reports,
manifest, and PDF. Integration tests extract and recompile the bundle offline.

## Full-book trial

All 39 pinned OSHB books parsed successfully. The Proverbs engineering trial covered
all **915 verses**, **54 reader pages plus credits**, and **2,451 distinct helps**.
The build completed in approximately **237 seconds** in this environment, with no
lost/duplicated verses, overfull boxes, missing glyphs, wrong-page marker links,
or unembedded reader fonts. Start, middle/chapter transition, and final pages were
visually inspected. The greedy planner leaves a sparse final page; global balancing
is deferred.

This trial used book frequency ≤10 and **407 explicitly recorded omissions** for
unresolved lexical references. Its project name and decision reasons identify it
as an engineering proof. Those omissions are not scholarly resolutions or a
publication-ready edited corpus. The default reference passage needs no such
omissions. For other editions the app blocks selected unresolved items until a
reader chooses an entry or explicitly omits the help.

## Browser and packaging

`scripts/browser_smoke.py` passed with full Playwright Chromium against a real
local Uvicorn server and separate worker. It checks review, gloss edit, persistence
after reload, actual PDF build/download, ZIP export, offline cached source import,
failed-build cleanup, cancellation, mobile-width layout, and absence of browser
JavaScript errors. Desktop review and the native embedded PDF viewer were visually
inspected. Screenshots/checks are under `test-results/browser-20261002-182946/`.
The test uses a separate workspace and shuts down its server/worker.

The source distribution and wheel include the application resources; the source
distribution includes fixture provenance, tests, setup scripts, examples, and docs.
The sample scan and raw source downloads are excluded. Package installation and
resource checks passed on 2026-10-04 in a fresh virtual environment with the locked
runtime dependencies. The installed wheel built the reference PDF successfully
from `/tmp`, outside the repository working directory, using the separately
installed pinned TeX environment (`build/wheel-proof/`). CI is defined in
`.github/workflows/check.yml`; no remote CI run or package publication is claimed.

## Re-run

```sh
bash scripts/bootstrap.sh
.venv/bin/bible-reader sources import --book Prov
make check
make demo
.venv/bin/bible-reader build --project examples/reference.project.json
PLAYWRIGHT_BROWSERS_PATH=.tools/browsers .venv/bin/playwright install --with-deps chromium
make browser
uv build
```

See [operations](operations.md) for state backups, source review, errors, and
supported-platform limits. No scholarly-content or cross-installation byte-identical
PDF guarantee follows merely from passing software tests.

## Continuous scripture update — 2026-10-09

The reader now uses justified RTL paragraphs with inline verse numbers, following
`bereshit002.jpg`. The release results above describe the earlier layout.

`make check` passes **71 tests and 8 unittest subtests**, including actual PDF
baseline checks for consecutive run-in verses and a synthetic 60-short-verse
pagination stress case. Reference/A4/Letter remain one reader page plus credits;
A5 remains two reader pages plus credits. `make demo` emits the compatibility
specimen, and `make pdf` compiles the production proof with shell escape disabled.

The reference proof at `build/reader-20261009-144420-217346/reader.pdf`, both A5
reader pages, and the single-verse chapter opening were rasterized and inspected.
Review covered inline numbers, Hebrew points, maqaf, K/Q markers, chapter-box
insets, chapter/page boundaries, and dense mixed-script notes. Automated checks
verify all 17 source verses, 37 helps, same-page marker destinations, embedded
fonts, and absence of missing glyphs or overfull boxes. A short chapter opening
reserves two lines so its box does not extend beyond the measured text area.
