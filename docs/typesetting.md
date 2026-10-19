# Typesetting and PDF verification

The print contract is the [reference-page specification](reference-page-spec.md).
The implementation uses XeLaTeX, fontspec, xcolor, polyglossia/bidi, hyperref, and geometry.
Optional lexicon appendices also use the standard `multicol` package, included in
the pinned TeX setup and checked by `doctor`.
Trusted macros live in `src/bible_reader/tex.py`; all external plain text is escaped
once at the TeX boundary. Hebrew words are kept with their superscript markers.
English note flow contains explicitly delimited Hebrew headwords.
Greek editions use LTR scripture and explicitly delimited Gentium Plus headwords,
with the same measured page-local apparatus. Font files and notices are bundled
for offline rebuilding. See [Greek sources](greek-sources.md) for supported
editions, glyph coverage, and source limitations.

```sh
bash scripts/bootstrap.sh
.venv/bin/bible-reader sources import --book Prov
.venv/bin/bible-reader build --project examples/reference.project.json --output build/reference
make check
```

## Profiles and measurements

| Profile | Page size | Margins |
| --- | --- | --- |
| reader (default) | 140 × 216 mm | 10 mm |
| reference | 180 × 281 mm | 10 mm |
| a4 | 210 × 297 mm | 16 mm |
| a5 | 148 × 210 mm | 10 mm |
| letter | 215.9 × 279.4 mm | 16 mm |
| custom | Project width × height in mm | 10 mm |

The app's **Paper size** selector offers these profiles. Custom requires both
`layout.paper_width_mm` and `layout.paper_height_mm`, each a finite number from
21 to 1000 mm. Dimensions may include decimals and may specify landscape paper.
The same dimensions govern TeX measurement, page budgets, and final PDF geometry;
an indivisible word/help or chapter opening that cannot fit still reports a layout overflow.
Omitted paper settings use `reader`; an explicitly selected profile keeps its size.
`examples/reference.project.json` explicitly selects the larger reference proof.

Reference dimensions are calibrated approximations; the photograph does not
establish physical paper size. Defaults are Ezra SIL 18 pt / 23.5 pt leading and
9 pt notes. Latin Modern is loaded by its TeX font filenames. Type sizes, leading,
folio, accent policy, reading policy, and font choice are validated project settings.
Verb-stem labels in lexical notes use uppercase Latin letters at 50% of the note
size (4.5 pt with the default 9 pt notes). Running book titles alternate by printed
folio: Hebrew on odd folios, English on even folios, including exports whose
`layout.first_folio` starts on an even number. Hebrew book titles use 18 pt type.
English titles use Latin Modern Roman Caps, with taller title initials and smaller
capitals for lowercase letters. Their full height and baseline placement match
the same book's Hebrew title, measured in the selected Hebrew font.

Word coloring defaults to `layout.word_colors = "auto"` (no color).
`"word-class"` enables the preset palette with per-class hex/Auto overrides in
`layout.word_color_overrides`. The app exposes both under **Word colors**.
Color groups enclose only the escaped scripture surface; K/Q labels, lexical
markers, punctuation, headers, and notes remain black. Measurement and final
output use the same groups. Raw text, morphology, source-backed name evidence,
and unclassified words remain inspectable in the reader JSON.

The planner measures each complete candidate page in TeX scaled points, in batches
per page: its actual header, scripture box, separator spacing, and unique notes.
Measurement and final output share the same page assembly, so unused fixed
allowances cannot push fitting verses to the next page. It selects the fullest
legal fitting prefix against TeX's actual text height and emits explicit breaks.
Page plans retain scripture/note heights, complete page height, usable height,
and the content budget derived from the measured header and separator.
The `layout.verse_layout` setting chooses `continuous` (default) or
`verse-per-line`. The app exposes it as **Verse layout** in page settings.
Continuous scripture flows in justified RTL paragraphs with inline LTR verse
numbers, as in `bereshit002.jpg`. Numbers stay with the first word of their verse.
Chapter openings start a new paragraph; its first two lines share an inset beside
a double chapter box, then the text returns to full width. The first two verses
remain one page-planning unit. Other continuous verses may split at word boundaries
to fill the current page, including available space on its last line. Each fragment
retains its source reference and token offsets in the page plan; continuation text
does not repeat the inline verse number. Maqaf chains and adjacent ketiv/qere pairs
stay together, and each page includes only its own words' helps.
A passage containing only verse 1 keeps its chapter
marker and reserves at least two lines for the box. Candidate measurement windows
extend when more short verses fit, since several verses may share a line.
In `verse-per-line` mode each verse starts its own right-aligned RTL paragraph
with an LTR digit in a right-side gutter; longer verses wrap without repeating
the number. The first two verses share the chapter-box inset, as in `mishle002.jpg`.
Both measurement and final rendering use the selected mode. The final page may be
sparse: there is no global paragraph/page balancing pass. The apparatus follows
scripture directly, with 3 pt on either side of its separator; unused space stays
below the helps. Run-in notes use 1.15-times-size leading (with at least 0.5 pt
between tall line boxes), 0.45 em entry gaps, and a 3 pt chapter-group gap.

General labels come from the full relevant chapter registry. The reference map
supplies the sample's chapter-1 labels 90–104 and chapter-2 labels 1–22, including
repeated 4, 9, and 16 and distinct same-lexeme slots. Every page repeats only the
helps used on that page, grouped by chapter. K/Q superscripts identify source
readings independently of lexical-help numbers.

## Lexicon appendix

Enable **Add lexicon appendix**, top-level `lexicon_appendix = true` in a project,
or the CLI build option `--lexicon-appendix`. It defaults to off. The appendix
follows the final reader page and starts before **Sources and edition**, with
folios continuing from `layout.first_folio`. It uses four balanced columns,
ordered top-to-bottom and left-to-right, with the book's English and Hebrew names
in the heading. Each entry starts with an explicitly RTL Hebrew headword on the
left and LTR English stem/gloss to its right, on the same baseline. Hebrew uses
the saved note size; English matches the existing stem-label size at half that
size (4.5 pt by default). A 3 mm column gap, zero paragraph spacing, and tight line
spacing pack entries densely while line boxes retain pointed Hebrew glyphs' full
height. Headwords occupy 40% of each column, with unusually wide headwords scaled
to fit that space. Continuation lines indent beneath the gloss. Headwords stay
with the beginning of their gloss; long glosses may continue into later columns/pages. Hebrew
sorting uses a separate mark/punctuation-free key, with final letters folded to
ordinary forms. Headwords retain their vowels and source Unicode.

Entries are the deduplicated union of the built passage's footnote helps, using
the same whole-book frequency cutoff, editorial inclusion/omission, known-word,
name-exclusion, and gloss policies. Different source entries, verb stems, or
glosses remain distinct. An empty selection prints a clear empty-appendix notice.
`lexicon-appendix.json` retains links to the source-qualified entries and their
originating helps. This list also appears in `reader.v2.json` and the source bundle.

Appendix columns use TeX's automatic splitting and balancing. The reader's
measured verse/note boxes and page plans retain their existing construction.
PDF checks inspect actual destinations for every appendix entry and both section
boundaries; no fixed appendix page count is assumed.

Choose **Build content → Lexicon only**, set top-level `lexicon_only = true`, or
use CLI `--lexicon-only` to omit scripture pages and print the same selected
lexicon plus source credits. This mode implicitly includes the lexicon even if
`lexicon_appendix` is false. It does not measure scripture; `page-plan.json` is
empty, and PDF checks require the lexicon to begin on the first physical page.
Folios start at the saved first folio. `--emit tex` supports both lexicon modes.

## Compiler and artifact checks

The compiler uses an argument list, no shell escape, restricted TeX file access,
unique output directories, captured logs, cancellation, and a 90-second timeout
per invocation. It compiles final TeX twice. Measurement still requires TeX even
with `--emit tex`. Oversized indivisible word/help or chapter-opening groups fail explicitly.

A successful PDF build checks:

- Expected reader pages, any enabled lexicon pages, and a final source-credit page,
  without lost or duplicate verses.
- Actual PDF link count against every lexical marker in the reader document.
- Each marker's actual PDF destination resolves to a note on the same page.
- All PDF fonts are embedded; logs contain no missing glyphs or overfull boxes.
- Every page's help set exactly matches its word anchors.
- Every appendix entry has a PDF destination after the reader and before credits.

The bundle contains TeX, reader/selection records, page metrics, source credits,
manifest, PDF/logs, and, for Ezra, the unmodified font and license. `BUILD.txt`
explains offline compilation. Manifest hashes cover loaded TeX inputs as well as
source/configuration/application/font/engine files. PDF-byte reproducibility
across different installations is not guaranteed.

## Visual review

Inspect actual rasterized pages at print scale: Hebrew order, points/accents,
maqaf, K/Q forms, superscript attachment, chapter-box inset, mixed-script notes,
verse wraps, headers, rule, margins, and chapter/page boundaries. RTL text extraction
alone does not establish visual correctness. Compare source records and the scan's
structure as separate checks; the STEP short-gloss wording is deliberately different.

The dev environment includes pypdfium2/Pillow for rendering PDF pages to PNG. Browser
acceptance uses full Chromium to exercise its real PDF viewer. See
[release-validation.md](release-validation.md) for inspected proofs and test evidence.

`make demo` retains the old synthetic v1 TeX specimen. It is not the production
page planner, and its template requires separately installed SBL Hebrew.
