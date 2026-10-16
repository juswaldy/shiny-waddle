# Typesetting and PDF verification

The print contract is the [reference-page specification](reference-page-spec.md).
The implementation uses XeLaTeX, fontspec, xcolor, polyglossia/bidi, hyperref, and geometry.
Trusted macros live in `src/bible_reader/tex.py`; all external plain text is escaped
once at the TeX boundary. Hebrew words are kept with their superscript markers.
English note flow contains explicitly delimited Hebrew headwords.

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
an atomic verse/opening that cannot fit still reports a layout overflow.
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
remain one page-planning unit. A passage containing only verse 1 keeps its chapter
marker and reserves at least two lines for the box. Candidate measurement windows
extend when more short verses fit, since several verses may share a line.
In `verse-per-line` mode each verse starts its own right-aligned RTL paragraph
with an LTR digit in a right-side gutter; longer verses wrap without repeating
the number. The first two verses share the chapter-box inset, as in `mishle002.jpg`.
Both measurement and final rendering use the selected mode. The final page may be
sparse: there is no global paragraph/page balancing pass. Notes align at the page
bottom with flexible whitespace above them.

General labels come from the full relevant chapter registry. The reference map
supplies the sample's chapter-1 labels 90–104 and chapter-2 labels 1–22, including
repeated 4, 9, and 16 and distinct same-lexeme slots. Every page repeats only the
helps used on that page, grouped by chapter. K/Q superscripts identify source
readings independently of lexical-help numbers.

## Compiler and artifact checks

The compiler uses an argument list, no shell escape, restricted TeX file access,
unique output directories, captured logs, cancellation, and a 90-second timeout
per invocation. It compiles final TeX twice. Measurement still requires TeX even
with `--emit tex`. Oversized atomic verse/opening groups fail explicitly.

A successful PDF build checks:

- Expected reader pages plus a source-credit page, without lost or duplicate verses.
- Actual PDF link count against every lexical marker in the reader document.
- Each marker's actual PDF destination resolves to a note on the same page.
- All reader-page fonts are embedded; logs contain no missing glyphs or overfull boxes.
- Every page's help set exactly matches its word anchors.

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
