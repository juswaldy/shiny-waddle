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

The initial update introduced justified RTL paragraphs with inline verse numbers,
following `bereshit002.jpg`. The release results above describe the earlier layout.

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

## Layout choice and code-review skill — 2026-10-09

`layout.verse_layout` now selects continuous text (default) or separate verse
starts. The browser exposes both choices and saves the selection per project.
CLI JSON/TOML configuration and immutable worker snapshots retain the same setting.

`make check` passes **80 tests and 8 unittest subtests**, including both layouts
on all four paper profiles, actual verse-number positions, single-verse openings,
offline bundle recompilation, reproducibility, and large-type A5 wrapping.
`make demo` and `make pdf` pass. Both layouts' reference/A5 proofs and short chapter
openings were rasterized and inspected. Complete-source CLI proofs are retained
at `build/reader-20261009-150439-581867/` (continuous) and
`build/reader-20261009-150318-621564/` (verse-per-line).

Browser acceptance passed at `test-results/browser-20261009-150255/`, checking
layout selection, persistence after reload, successful worker builds in both
modes, exports, failure/cancellation, and mobile width.

The new `.agents/skills/code-review-agent/SKILL.md` passes the skill validator and
was exercised with an independent read-only reviewer. That review found continuous
A5 overflow at 26 pt text / 38 pt leading. Adjusting paragraph tolerance fixed the
overflow; both modes now have a regression test for that configuration. The
reviewer verified the correction on compiled pages with no remaining actionable
findings. Full-book continuous flow and SBL Hebrew were not requalified in this
update.

## Paper size update — 2026-10-09

The default reader paper is now 140 × 216 mm with 10 mm margins. The four earlier
presets retain their sizes; the reference example explicitly selects its larger
proof profile. Custom paper saves validated decimal width/height in millimetres
and uses the same dimensions for measurements, page budgets, and final geometry.

`make check` passes **97 tests and 8 unittest subtests**. PDF checks cover both
verse layouts on all five presets and 160.5 × 230.25 mm custom paper, checking
every page's physical dimensions, page-local links, verse coverage, and fonts.
`make demo` and `make pdf` pass. The complete-source default proof at
`build/reader-20261009-153412-612918/` has two reader pages plus source credits;
all three pages were rasterized and inspected for Hebrew/English flow, markers,
chapter transition, notes, and margins.

Browser acceptance passes at `test-results/browser-20261009-153425/`, including
default/custom selection, invalid-input rejection, saved dimensions after reload,
immutable worker settings, actual downloaded PDF sizes, exports, cancellation,
and mobile width. Its custom verse-per-line test edition was also rasterized and
visually inspected across both reader pages.

## Fuller pages — 2026-10-09

Pagination now measures the complete page assembly, including the selected font's
running head and the actual separator spacing, against TeX's text height. The
previous fixed 55 pt allowance is removed. Measurement and final emission copy
the same scripture/note boxes through a shared page macro. Page plans now record
complete and usable page heights as well as the derived content budget.

The reader-size SBL Hebrew Genesis 1:1–6:1 proof at `build/page-fill-genesis/`
retains all 139 verses and 231 helps with verified page-local PDF destinations.
Its first page now ends at 1:13 rather than 1:12. Across non-final pages, mean
flexible space above the apparatus falls from approximately 47.3 pt to 30.1 pt
compared with the earlier build at `.reader/builds/d064fb281eb64a7597d6898ed716914b/`.
The passage still needs 13 reader pages; whole verses and chapter openings can
leave space when the next group cannot fit, and the final page can be sparse.

The complete-source continuous Proverbs proof at `build/page-fill-custom/`
(160.5 × 230.25 mm, Ezra SIL) now fits all 17 verses and 37 helps on one reader
page instead of two. This boundary case is covered by the PDF regression matrix.
The default proof at `build/reader-20261009-154640-941227/` still needs two reader
pages. Genesis before/after, chapter openings and transitions, and the dense
single-page custom proof were rasterized and visually inspected; their final
logs contain no overfull boxes or missing characters.

`make check` passes **97 tests and 8 unittest subtests**, including both verse
layouts, all paper profiles, large type, and portable bundle recompilation.
`make demo`, `make pdf`, and browser acceptance pass. Browser artifacts are at
`test-results/browser-20261009-154723/`.
