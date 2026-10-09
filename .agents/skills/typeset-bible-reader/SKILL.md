---
name: typeset-bible-reader
description: Build or revise this reader's LaTeX and PDF output, including Hebrew directionality, lexical notes, fonts, and pagination.
---

# Typeset a Bible reader

Read `docs/typesetting.md`; use `docs/product.md` for layout goals and the reader
contract in `docs/architecture.md` when changing the renderer boundary.

1. Confirm the selected reader document, edition/language, template, and fonts.
   Preserve logical Unicode order. Use explicit language runs for mixed Hebrew,
   Greek, English, digits, and note markers; never reverse strings for RTL.
2. Escape imported text only at the TeX boundary. Keep template commands separate
   from text content. Preserve the input reader document alongside generated TeX
   so a misplaced marker can be traced back to its token and selected note.
3. Run `make check` for renderer changes and `make demo` for the specimen. Compile
   using `make pdf` when XeLaTeX and fonts are available, or the equivalent command
   with shell escape disabled for a real document. Retain logs and intermediate TeX.
4. Inspect the actual pages: pointed/accented glyphs, reading order, references,
   marker attachment, notes, line spacing, margins, and embedded fonts. Typography
   changes need a page/chapter boundary and a dense note section, not just a
   single short line. Follow the checklist in `docs/typesetting.md`.

Use `mishle002.jpg`, if present, for layout inspiration only. Do not transcribe
its notes or package the scan as source data. The bootstrap template has
passage-end helps; do not describe them as verified same-page footnotes.

Report generated paths and distinguish automated checks, TeX compilation, and
visual review. If an engine/font is missing, preserve the reviewable TeX and name
the prerequisite; do not claim a PDF exists or silently substitute fonts.
