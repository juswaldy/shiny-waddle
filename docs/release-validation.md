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

## Greek NT and LXX support — 2026-10-16

Pinned SBLGNT (27 books) and Rahlfs MyBible artifacts (60 book/witness records)
were parsed in full: **38,263 verse rows and 761,247 words**. Hashes, source counts,
unique derived token IDs, and Greek language tags passed the offline audit in
`scripts/audit_greek_sources.py`; its detailed output is
`build/greek-source-audit.json`. [Greek sources](greek-sources.md) records the
edition revisions, layer-specific terms, exact link coverage, numeric source
versification, partial Joshua A coverage, and nonmonotonic Daniel references.

Real John 1:1–2:12 and Genesis 1:1–2:12 proofs compiled in both verse layouts.
Dense all-word proofs are under `build/greek2-John-verse-per-line/` and
`build/greek2-LXXGen-verse-per-line/`. Final continuous proofs after correcting
the two-line chapter inset are under `build/greek-final-John-continuous/` and
`build/greek-final-LXXGen-continuous/`, each with eight reader pages, one lexicon
page, and one source-credit page. Proof configurations explicitly exclude
unresolved lexical joins for typography inspection; they are engineering proofs,
not claims of contextual lexical review.

First pages, the chapter 1/2 boundary, and Greek lexicon columns were rasterized
and visually inspected. Accents, logical reading order, word-linked markers,
note grouping, chapter insets, and appendix sorting were checked. PDF validation
passed page membership, same-page note destinations, embedded fonts, appendix
coverage, and overflow/missing-glyph checks. The Greek PDF regression also checks
actual first/second-line glyph positions around the chapter box. Gentium Plus
covers all 273 distinct nonspace characters found across the pinned Greek
text/analysis artifacts and TBESG headwords.

`make check` passes **280 tests and 8 subtests**, with the 17 opt-in browser tests
skipped by default. All **17 browser review regressions** pass separately, including Greek review text and verse
context direction, font delivery, edition selection, and Rahlfs terms. The local
Chromium run uses the existing libraries in `.tools/browser-libs/`; proof output
is `test-results/greek-review.png`. `make demo` and `make pdf` pass; the Hebrew
regression proof is at `build/reader-20261016-173403-915008/`.

Wheel and source-distribution builds pass offline. Packaged Greek resources and
all CSV/JS/HTML provenance fixtures were verified, and raw downloads remain
excluded. The extracted wheel built the John example successfully at
`build/greek-wheel-smoke-proof/`, including the font/license/source-notice bundle.
`doctor` verifies the NT crosswalk as well as text and lexicon checksums before
reporting Greek readiness, and hashes shared LXX artifacts only once per check.

## Compact spacing and verse continuations — 2026-10-19

Helps now follow scripture directly, with 3 pt on either side of the separator
and unused space below the apparatus. Note leading is 1.15 times the note size;
entry and chapter-group gaps are smaller, with tall glyph boxes kept apart.
Continuous pages can include a word-level prefix of the next verse, with source
token offsets retained and only those words' helps printed on that page.
Chapter openings, maqaf chains, and adjacent ketiv/qere pairs stay together.
PDF validation reconstructs exact source token order across continuations.

The default Proverbs proof at `build/reader-20261019-141021-935373/` advances the
first page's end from 2:8 to 2:9. Its first-page apparatus shrinks from 104.7 pt to
85.8 pt despite including another verse. Both reader pages were rasterized and
inspected, including the sparse final page's text-to-help spacing.

The existing Genesis engineering project's final proof at
`build/spacing-genesis-final/` retains 139 verses and 193 helps over 12 reader
pages, with nine verse continuations. First pages, a chapter transition, and the
final page were visually inspected. The saved Greek engineering proof at
`build/spacing-greek-final/` retains 63 verses and 87 helps over eight reader
pages, plus the lexicon and credits. Inspection covered dense notes, continued
verses, and the chapter 1/2 boundary. Both proofs pass same-page marker links,
source-token coverage, embedded fonts, and overflow/missing-glyph checks. Their
existing editorial decisions remain engineering-proof inputs.

`make check` passes **297 tests and 8 subtests**, with 17 opt-in browser checks
skipped. New regressions cover Hebrew and Greek verse continuations, same-line
verse starts, compact apparatus placement on every page, exact source-token
coverage, and intact maqaf/K/Q boundaries. `make demo` and `make pdf` pass.

## Full-Genesis spacing refinement — 2026-10-19

Continuous chapter openings can now break after two actual text lines beside
the chapter box. Their continuation does not repeat the box. Paragraphs that
continue onto another page justify their last line; chapter and passage endings
keep their natural alignment. The scripture-to-apparatus rule gap is now 9 pt,
matching the header's scripture gap, with 3 pt below the apparatus rule.

Rebuilt the saved full-Genesis edition at
`build/genesis-spacing-refined/`: SBL Hebrew 14.5 pt / 19 pt leading, 8.5 pt helps,
preserved accents, and the saved word colors and book-frequency policy. The
reader JSON is identical to the original 84-page build. All 1,533 verses and
2,187 helps remain across 84 reader pages plus credits, with verified source
tokens, page-local note links, embedded fonts, and no overflow or missing glyphs.

The full-book PDF audit reduces mean unused space on non-final pages from
13.83 pt to 8.96 pt. The largest gap falls from 72.90 pt to 47.93 pt, and gaps
over 30 pt fall from seven pages to three. On pages 6, 20, and 77, measuring all
legal prefixes confirms that the next chapter's two-line opening and its helps
still cannot fit. Their available/minimum-required extra heights are respectively
47.93/54.77 pt, 36.06/42.00 pt, and 40.31/42.00 pt. Final-page unused space falls
from 292.29 pt to 133.56 pt. No continued page ends in a short last line.

Rasterized and visually inspected the chapter 16/17 and 42/43 splits, their
continuations, dense helps, the remaining chapter-boundary gaps, and the final
page. The apparatus rule's measured ink gap is 9.15–10.69 PDF points, compared
with 3.17–4.71 before. Audit details remain in
`build/genesis-spacing-audit/comparison.json` and `remaining-gaps.json`.

`make check` passes **299 tests and 8 subtests**, with 17 opt-in browser tests
skipped. New PDF checks cover both languages' long chapter openings, a single
chapter box across continuations, full last-line width, and the lower rule's
actual glyph clearance. `make demo` and `make pdf` pass.
