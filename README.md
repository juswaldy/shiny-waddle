# Original-language Bible reader

A Python local browser app and CLI: pinned biblical text + lexical helps →
reviewable reader document → measured LaTeX → printable PDF.

The app imports the Open Scriptures Hebrew Bible, SBLGNT, Rahlfs LXX, and STEP short glosses, keeps
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
Greek uses bundled Gentium Plus. See [Greek sources and commands](docs/greek-sources.md)
for edition identities, Rahlfs access requirements, alternate witnesses, and lexical gaps.

```sh
.venv/bin/bible-reader sources import --book John
.venv/bin/bible-reader build --project examples/john.project.json --output build/john
# After satisfying the documented Rahlfs access requirements:
.venv/bin/bible-reader sources import --book LXXGen
.venv/bin/bible-reader inspect --project examples/lxx.project.json --report build/lxx-review.json
```

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

Check **Add lexicon appendix** above **Save settings** to add an alphabetically sorted,
four-column lexicon after the reader pages and before **Sources and edition**.
It uses the selected passage's footnote helps, including the same **Maximum
occurrences in this book** cutoff in **Uncommon in this book** mode, known-word
omissions, name exclusions, and saved inclusion/gloss edits. Counts still come
from the whole book. It does not add words from outside the built passage.
Identical entry/stem/gloss combinations appear once across chapters; different
source entries, verb stems, or edited glosses remain separate.

The lexicon includes the book name and reads down each column from left to right.
Each entry puts the Hebrew headword on the left and its English stem/gloss on the
right, starting on the same line. English uses half the saved note size, matching
the QAL/PIEL labels (4.5 pt with default settings), with compact spacing. Long
glosses wrap beneath the English text or continue into another column/page.
Hebrew sorting ignores points and punctuation and groups final letters with their
ordinary forms; displayed headwords retain their source spelling and vowels.
An empty selection produces an explicit empty lexicon. The appendix defaults to off.
In JSON or TOML projects, set the top-level `lexicon_appendix` to `true`.
The CLI can override the saved setting for one build:

```sh
.venv/bin/bible-reader build --project reader.json --lexicon-appendix --output build/with-lexicon
# Override a saved enabled appendix:
.venv/bin/bible-reader build --project reader.json --no-lexicon-appendix --output build/without-lexicon
```

Choose **Build content → Lexicon only** to build the same selected lexicon and
source credits without scripture pages. This does not require enabling the
appendix checkbox. The saved project setting is top-level `lexicon_only = true`
in TOML or `"lexicon_only": true` in JSON. CLI overrides are:

```sh
.venv/bin/bible-reader build --project reader.json --lexicon-only --output build/lexicon-only
.venv/bin/bible-reader build --project reader.json --no-lexicon-only --output build/reader-again
```

Both lexicon modes use the same passage, whole-book occurrence limit, and saved
help decisions. Lexicon-only builds skip scripture pagination and start at the
saved first folio. They also support `--emit tex`.

Lexicon builds include `lexicon-appendix.json` with source-entry IDs, editorial
status, and the originating chapter help IDs, both beside the PDF and in the
source bundle. Unresolved selected helps still require review before building.

**Word colors** defaults to **Auto (no color)**. Choose **Word class + names**
for a preset palette, then open **Palette & class colors** to pick a custom color
or **Auto (no color)** for each class. **Set all to no color** resets every class,
including names, to Auto; you can then color individual classes. Use **Save settings**
to keep the reset palette. Switching back to Auto keeps your overrides
for later use. Scripture words use their source morphology; names also use the
existing STEP name metadata. Attached prefixes and suffixes share the main word's
color. Unknown or compound classes stay uncolored. Notes, markers, punctuation,
and source text keep their existing appearance and content.
In JSON projects, for example:

```json
{"layout": {"word_colors": "word-class", "word_color_overrides": {"noun": "#245A81", "name": "auto"}}}
```

TOML uses `word_colors = "word-class"` under `[layout]` and per-class values under
`[layout.word_color_overrides]`. Supported keys are `noun`, `verb`, `adjective`,
`adverb`, `pronoun`, `preposition`, `conjunction`, `particle`, `suffix`, `number`,
and `name`. Omit an override to use its preset; custom colors are six-digit hex values.
Omitted `word_colors` uses `"auto"`, including older projects.

The **Cantillation** selector also offers **Consonants only**, **Consonants +
maqqef**, and **Consonants + maqqef + sof pasuq**. All three hide Hebrew combining
marks, including vowels, dagesh, and shin/sin dots. Consonants only hides all Hebrew
punctuation; the other options retain maqqef (־), or maqqef and sof pasuq (׃).
Set `cantillation` to `"consonants-only"`, `"consonants"`, or
`"consonants-maqqef-sof-pasuq"`, respectively, in JSON/TOML projects. The existing
`"consonants"` setting keeps its maqqef behavior. Source text, K/Q readings,
section letters, and lexical headwords stay intact. The default remains `"hide"`
(hide accents, retain vowel points); `"preserve"` retains source accents.

The reference help selection applies to Proverbs 1:29–2:12. For other passages choose
`all` or `book-frequency`; the latter counts occurrences in the entire selected
source book. `known_entries` and per-anchor `decisions` support exclusions and
reviewed glosses. Ambiguous or unmatched selected helps must be resolved or
explicitly omitted before a build succeeds.

**Gloss selection → Default gloss (first entry)** uses the first entry in
each word’s source-entry list, including ambiguous and base-ID matches. The order
comes from the pinned STEP lexicon. Saved source-entry choices, editorial glosses,
and inclusion edits take precedence. All source candidates and the original
alignment status remain inspectable; this option does not select a contextual
sense. Missing entries still require review or omission, and names stay omitted.
The default **Review ambiguous entries** keeps the existing explicit-review behavior.
In JSON/TOML projects, set `gloss_selection` to `"first-entry"` or `"reviewed"`.

**Reset helps to defaults** clears all saved source-entry, gloss, and inclusion
decisions throughout the project’s book, including occurrences outside the current
passage. It first switches **Gloss selection** to **Default gloss (first entry)**,
then saves that setting with the cleared decisions. A progress indicator shows
saving and refreshing until the updated helps are ready. The saved help-selection,
known-word, and frequency settings still apply. Save or discard pending row edits
before resetting. Existing build snapshots retain their original decisions.

**Save book helps** downloads a reusable `Prov-lexical-helps.json` file (or the
selected book's code). It includes every saved source-entry choice, editorial
gloss, inclusion/omission, and reason throughout the book, including chapters
outside the current passage and both written/read forms, plus the saved default
gloss policy. **Load book helps** restores that file into any edition of the same
book, replacing its saved decisions and default gloss policy. An empty set clears
the decisions. Save or discard row drafts and save edition settings first.
The edition's passage, layout, help-selection policy, frequency threshold, and
known-word list stay as saved; previous build snapshots retain their decisions.

Help files contain editorial decisions, not a copy of the biblical text or
dictionary. They pin the text and lexicon source revisions and checksums. Loading
checks every decision against the installed sources, including hidden chapters
and readings. A different book, incompatible sources or entries, malformed file,
or stale project revision rejects the entire load. Projects support up to 100,000
decisions; help files and API requests are limited to 64 MB.

The CLI uses the same save/load checks and writes a new JSON file:

```sh
.venv/bin/bible-reader helps save --project reader.json --output build/Prov-lexical-helps.json
.venv/bin/bible-reader helps load --project another-edition.toml --input build/Prov-lexical-helps.json --output build/restored-reader.json
```

Existing output files are never overwritten. The source project may be JSON or
TOML; load preserves its other settings in the new JSON project.

Names are automatically omitted from lexical helps in every selection mode,
including existing saved inclusion decisions. The rule uses OSHB proper-name
morphology and STEP name metadata, including personal, place, and divine names.
It does not infer names from spelling or capitalization. **Show omitted words**
retains their source candidates and omission reasons; their inclusion checkboxes
are disabled, and **Include page** skips them. Source scripture stays intact.

In lexical review, **Apply to** defaults to **All occurrences in this book
(consonants only)**. Choose **Save all** to apply the source entry, gloss, and
inclusion choice to matching words throughout the selected
book, including occurrences outside the current passage and both written/read
forms. Matching ignores Hebrew vowel points, accents, punctuation, and slash
segmentation, retains prefixes/suffixes, and stays within the word's language.
This replaces earlier decisions on matching anchors. Occurrences whose source
candidates do not support the chosen entry remain unchanged and are listed for
separate review. Source text remains intact; saved decisions and build snapshots
still identify every affected source anchor.
Select **This occurrence** and **Save help** to edit just the current occurrence.

Choose **View → Grid** in lexical review to edit a page in a table. **Save page**
submits all edited rows on that review page in one update; **Save & next** saves
and advances. Choose 20, 40, 80, or 160 rows per page. Each row retains its own
**Apply to** scope, source details, and verse popup. In the grid, **Source entry**
and **Apply to** use radio buttons; hover over **Apply to** for the matching hint.
Invalid choices or a stale project revision reject the whole submission and retain
your drafts; conflicting book-wide edits must be reconciled or saved separately.

Data-entry shortcuts and controls work alongside individual row saves:

- Enter / Shift+Enter in a gloss moves to the next / previous gloss; Tab moves
  between fields. Ctrl/Cmd+Enter saves the edited rows on the current page.
- Ctrl/Cmd+D copies the previous row's gloss when both rows use the same chosen
  source entry. In grid mode, paste one spreadsheet column to fill consecutive
  glosses on the current page; choose source entries first.
- **Source gloss** restores the chosen entry's STEP gloss; **Undo row** restores
  the saved row. Custom wording remains an editorial override.
- **Include page** / **Omit page** stages explicit inclusion choices for all
  visible rows. **Discard page edits** restores the page without saving.
- **Unsaved edits** finds pending rows, including omitted words. The edit count
  reports pending work on other pages.

Drafts survive paging, filtering, view changes, review refreshes, and saving
another row. Save or discard them before changing edition settings, switching
projects, or building. Drafts live in the open tab; closing or reloading it warns
about unsaved work. Only submitted decisions are persisted with the project.

Select **Rework resolved helps** to revisit source entries that already resolve.
Change the gloss, choose another available source candidate, or change inclusion,
then use **Save help** for one occurrence or **Save all** for matching words in the
book. This filter and **Needs review** switch each other off; **Show omitted words**
also exposes resolved entries currently excluded from the reader.

Hover over a word's verse reference (or focus it with the keyboard) to see the
whole verse with source vowel points and accents, regardless of the edition's
cantillation setting. The word at that source occurrence is red, bold, and larger.
Click the reference to pin the popup while editing; click it again, use the close
button, or press Escape to dismiss it. Click another reference to switch the pinned
verse. Written/read forms retain their ketiv/qere labels.

`--emit tex` still needs XeLaTeX to measure page contents. Output directories must
be empty, preserving earlier editions. Every successful build includes the reader
JSON, alignment report, source lock, note registry, page plan, TeX, credits, checks,
and a manifest of source/configuration/code/engine/font/TeX-input hashes. PDF
builds include the PDF and compiler log. Ezra exports include the font and license.

## What is implemented

- Pinned imports for all 39 OSHB books; source IDs, Unicode, segmentation,
  annotations, and written/read forms retained.
- Pinned SBLGNT NT and Rahlfs LXX sources, TBESG and published lexical crosswalks,
  separate witnesses, Greek source audit, and explicit mapping gaps.
- Extended lexical-ID matching, explicit ambiguity review, gloss overrides,
  frequency and known-word policies, and chapter-local shared help labels.
- Continuous RTL Hebrew or LTR Greek text, separate verse starts, chapter boxes, mixed-script notes, running
  references, five paper profiles plus custom sizes, and measured page-local apparatus placement.
- Compact helps directly below scripture; continuous verses can start in remaining
  line space and continue on the next page with their words' own helps.
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

The release is a single-user local tool. Remote hosting, user accounts,
arbitrary uploaded TeX, full-dictionary definitions, and automated scholarly sense
selection are outside its scope. Indivisible words/helps, chapter openings, or
separate-verse blocks that cannot fit fail
with a layout error. See [operations and limits](docs/operations.md).

## Develop and verify

```sh
make check       # Ruff + unit/API tests + actual PDF tests when XeLaTeX is present
make demo        # Original synthetic v1 TeX specimen
make pdf         # Real default reference reader in a new build directory
make serve
PLAYWRIGHT_BROWSERS_PATH=.tools/browsers .venv/bin/playwright install --with-deps chromium
make browser     # Real server, worker, browser, edit, build, export, failure, cancellation
READER_BROWSER_TESTS=1 .venv/bin/pytest -q tests/test_browser_review.py  # Grid editing, offline fixtures
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
