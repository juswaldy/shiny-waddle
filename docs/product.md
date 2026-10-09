# Product brief

## Purpose

Let a reader work through an original-language biblical passage with enough
lexical help to continue reading. The output is a printable PDF with selectable
text, built from identifiable sources through inspectable LaTeX.

Confirmed delivery: Python **local browser app plus CLI**, using one shared build
service. The first print target is **Proverbs 1:29–2:12**, matching the supplied
sample's structure. Hebrew Bible and English lexical helps are the initial scope.
Aramaic passages need language tagging when real Hebrew Bible data is imported;
Greek is a later adapter and typography milestone.

The [reference-page specification](reference-page-spec.md) defines layout and
acceptance criteria. The [Python app plan](python-app-plan.md) defines proposed
modules, interfaces, algorithms, and delivery gates. These supersede the original
bootstrap's tentative layout/stack choices.

## Reading experience

The local reference image `mishle002.jpg` shows a Proverbs reader page with:

- Seventeen separately started, right-aligned Hebrew verses with smaller verse
  numbers; longer verses may wrap in other passages.
- A double-boxed chapter 2 beside the first two verse lines.
- Small word-linked note markers; semantic helps reuse their labels within the
  chapter, and labels restart at the chapter boundary shown.
- Two full-width run-in lexical paragraphs under a horizontal rule, containing
  15 chapter-1 entries and 22 chapter-2 entries, with Hebrew headwords, English
  glosses, and short grammatical labels.
- A running passage reference, book name, and page number.

The reader chooses **Continuous text**, following `bereshit002.jpg`, or **One
verse per line**, following the Proverbs scan. Continuous is the default and uses
justified RTL paragraphs with smaller verse numbers inline. The alternative starts
each verse separately; long verses wrap in either mode. Both retain the double
chapter box and chapter-grouped lexical apparatus. The choice is saved per project
and used by both the app and CLI.
The scans' publishers, editions, and redistribution terms have not been identified.
They are not sources for transcription or lexical data and should not be packaged
into outputs.

## First usable reader

The reader selects an edition and passage, a compatible lexicon, and a help policy.
The app preserves the source reading and creates numbered notes with headwords,
brief sourced glosses, and optional morphology. Unknown joins are reported. The
user can inspect the intermediate document and TeX before compiling a PDF.

Implemented help policies include the explicit reference selection, all lexical
items, book-frequency cutoff, known-word lists, and per-anchor reader overrides.
Chapter-local shared labels are allocated before pagination. Repeat a help entry
on each page that needs it, once per page.
Frequency counts need a named corpus/revision and must not be confused with counts
within the selected passage.

For the first publishable passage, acceptance requires correct verse order,
pointing and accents, visible note-to-word correspondence, source credits, and no
clipped text or missing glyphs. A longer passage must keep notes with their text
across page and chapter boundaries. A successful TeX exit code alone is insufficient.

## Release choices and remaining decisions

The release pins OSHB and STEP source revisions, ships Ezra SIL, and includes
reference/A4/A5/Letter profiles with explicit K/Q display. Its browser app and CLI
share the print core. See [release validation](release-validation.md).
The scan does not establish an exact vocabulary cutoff, font, or meaning for all
small editorial signs. Remote accounts, live lookup services, translations, and
commentary generation remain outside the first release.
