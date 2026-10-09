# Original-language Bible reader

A Python local browser app and CLI: pinned biblical text + lexical helps →
reviewable reader document → measured LaTeX → printable PDF.

The app imports the Open Scriptures Hebrew Bible and STEP short glosses, keeps
source readings and editorial decisions separate, and puts each page's lexical
helps beside the verses that need them. The reference edition is Proverbs
1:29–2:12. Choose continuous scripture flow as in `bereshit002.jpg` or separate
verse starts as in `mishle002.jpg`, with chapter-grouped lexical notes in both modes.

## Start

Supported release environment: **Linux x86-64 / WSL, Python 3.11+**. The setup uses
[uv](https://docs.astral.sh/uv/getting-started/installation/) and curl to install pinned
Python dependencies and a project-local TeX distribution; no sudo is needed.
Network access is needed for setup and source import. Subsequent builds are offline.

```sh
bash scripts/bootstrap.sh
.venv/bin/bible-reader sources import --book Prov
.venv/bin/bible-reader serve
```

Open **http://127.0.0.1:8765**. Choose a passage, save settings, review the lexical
helps, and build. The preview displays the actual PDF. Download the PDF or an
inspectable source bundle. Other books can be installed in the Sources tab.

If XeLaTeX is already installed, `uv sync --locked` is enough for Python setup.
Set `READER_XELATEX` to its executable if needed; run `bible-reader doctor` to check
fonts, TeX packages, and source hashes. Ezra SIL is bundled under its font license.
SBL Hebrew is optional and must be installed separately.

## CLI

```sh
.venv/bin/bible-reader init --project reader.json
.venv/bin/bible-reader inspect --project reader.json --report build/review.json
.venv/bin/bible-reader build --project reader.json --output build/my-edition
.venv/bin/bible-reader build --project reader.json --emit tex --output build/my-tex
.venv/bin/bible-reader sources import --all
.venv/bin/bible-reader --state /path/to/workspace serve --port 8766
```

JSON and TOML project files use the same validated settings as the browser. The
default paper is **140 × 216 mm**, with 10 mm margins. Under **Page & reading
settings**, **Paper size** offers the existing Reference proof, A4, A5, and US
Letter presets plus **Custom**, which reveals width and height in millimetres.
Custom dimensions accept finite numbers from 21 to 1000 mm and use 10 mm margins;
very small pages may fail with a layout overflow. For JSON projects use:

```json
{"layout": {"paper": "custom", "paper_width_mm": 160.5, "paper_height_mm": 230.25}}
```

For TOML, put `paper = "custom"`, `paper_width_mm`, and `paper_height_mm` in the
`[layout]` table. Omitted paper settings use `"reader"` (140 × 216 mm); explicit
presets keep their dimensions.

The **Verse layout** selector under **Page & reading settings** offers **Continuous
text** (the default) and **One verse per line**. In a project file set
`layout.verse_layout` to `"continuous"` or `"verse-per-line"`; long verses can wrap
in either mode. Projects without this setting use continuous text.
The reference help selection applies to Proverbs 1:29–2:12. For other passages choose
`all` or `book-frequency`; the latter counts occurrences in the entire selected
source book. `known_entries` and per-anchor `decisions` support exclusions and
reviewed glosses. Ambiguous or unmatched selected helps must be resolved or
explicitly omitted before a build succeeds.

`--emit tex` still needs XeLaTeX to measure page contents. Output directories must
be empty, preserving earlier editions. Every successful build includes the reader
JSON, alignment report, source lock, note registry, page plan, TeX, credits, checks,
and a manifest of source/configuration/code/engine/font/TeX-input hashes. PDF
builds include the PDF and compiler log. Ezra exports include the font and license.

## What is implemented

- Pinned imports for all 39 OSHB books; source IDs, Unicode, segmentation,
  annotations, and written/read forms retained.
- Extended lexical-ID matching, explicit ambiguity review, gloss overrides,
  frequency and known-word policies, and chapter-local shared help labels.
- Continuous RTL text or separate verse starts, chapter boxes, mixed Hebrew/English notes, running
  references, five paper profiles plus custom sizes, and measured page-local apparatus placement.
- Saved projects with revision-conflict checks, durable build jobs, cancellation,
  interrupted-job recovery, PDF preview, and export bundles.
- Offline regression fixtures, real PDF checks, browser acceptance tests, and CI.

The sample produces **17 verses, 37 distinct helps, and 43 markers**, spanning two
reader pages at the default paper size, followed by source credits. The larger
Reference proof profile fits the sample on one reader page. The scan's long
definitions are not copied: this edition uses STEP's shorter `Gloss` fields, so
note density and wording differ.
Exact source-entry matching establishes provenance, not a context-specific sense;
review lexical wording before publishing an edition.

The release is a single-user local tool. Greek, remote hosting, user accounts,
arbitrary uploaded TeX, full-dictionary definitions, and automated scholarly sense
selection are outside its scope. Extreme verse/note blocks that cannot fit fail
with a layout error. See [operations and limits](docs/operations.md).

## Develop and verify

```sh
make check       # Ruff + unit/API tests + actual PDF tests when XeLaTeX is present
make demo        # Original synthetic v1 TeX specimen
make pdf         # Real default reference reader in a new build directory
make serve
PLAYWRIGHT_BROWSERS_PATH=.tools/browsers .venv/bin/playwright install --with-deps chromium
make browser     # Real server, worker, browser, edit, build, export, failure, cancellation
uv build         # Wheel and source distribution
```

`make browser` requires imported Proverbs sources. Test artifacts and screenshots
are written to `test-results/`. See [release validation](docs/release-validation.md).

Project guidance: [AGENTS.md](AGENTS.md), [reference page specification](docs/reference-page-spec.md),
[implementation plan](docs/python-app-plan.md), [architecture](docs/architecture.md),
and [source provenance](docs/sources.md). Repository skills live in `.agents/skills/`.

## Licenses

Our code is MIT licensed. WLC text, OSHB annotations, STEP glosses, and fonts retain
their respective terms. The raw TBESH `Meaning` column is **never imported into
canonical data or exported**. Test fixtures contain attributed excerpts. The
reference scan is not distributed. See [THIRD_PARTY.md](THIRD_PARTY.md).
