# Reader page specification: Proverbs 1:29–2:12

Status: implementation target, based on direct inspection of `mishle002.jpg`,
with scripture flow updated on 2026-10-09 to follow `bereshit002.jpg`.
Companion: [Python application plan](python-app-plan.md). This specification
retains the Proverbs apparatus and chapter-opening design while using continuous
scripture paragraphs with inline verse numbers. The Proverbs scan coordinates
below document the original observation, rather than the new paragraph line count.
Implementation evidence and current limitations are recorded separately in
[release-validation.md](release-validation.md).

## 1. Reference and evidence

The reference is a 1256 × 2048 pixel JPEG, SHA-256
`d3b1a5a905b79cfcdd236192756587d2e1413b3797f3fe4c7a9172244d4c58dc`.
Its JFIF density is an aspect-ratio value, not a usable print resolution. Physical
page size, original font names, and point sizes cannot be recovered from that alone.
The scan includes slight skew and tight cropping; do not reproduce those defects.

The page contains 17 verses: five from chapter 1 and twelve from chapter 2. The
running head reads `1:29–2:12` at left, `משלי` at center, and `1329` at right.
These are three independent header fields. Page 1329 is the reference edition's
folio, not a required page number for a new export.

The [expected-layout fixture](../examples/prov-1-29-2-12.expected-layout.json)
records visible verse/note relationships. It is an observation fixture, not a
corpus transcription, lexical dataset, or input to the current demo renderer.

## 2. Page regions

Coordinates below are approximate visual measurements in the original raster;
origin is top left. Tolerances allow about 10–15 pixels of uncertainty. They are
calibration anchors, not exact ink bounding boxes or inferred paper margins.

| Region | Approximate extent / location | Requirement |
| --- | --- | --- |
| Running head | x 25–1225, y 20–70 | Passage at left, Hebrew book title centered, folio at right |
| Header rule | x 25–1225, y 73 | Thin continuous black line |
| Chapter 1 text | x 250–1220, y 85–390 | Five separately started, right-aligned verses |
| Chapter transition | y 395–445 | Extra whitespace; preserve the preceding paragraph/section sign |
| Chapter 2 box | x 1130–1220, y 443–535 | Double-outline square containing a large `2` |
| Chapter 2 text | x 280–1220, y 440–1180 | Twelve verse starts; first two lines leave room for the chapter box |
| Text–notes separator | x 30–1225, y 1230 | Full-width thin rule with breathing room |
| Chapter 1 lexical notes | x 30–1225, y 1245–1550 | Run-in paragraph containing notes 90–104 |
| Chapter 2 lexical notes | x 30–1225, y 1565–2015 | New run-in paragraph containing notes 1–22 |

The scripture occupies roughly the upper three fifths of the visible page; the
lexical apparatus occupies most of the lower two fifths. That is a reference-page
composition, not a fixed 60/40 split for every passage. A page with fewer notes
should admit more text or additional whitespace according to its layout profile.

```text
 passage range                Hebrew book title                  folio
 ────────────────────────────────────────────────────────────────────
  ... Hebrew verse ... 30    ... Hebrew verse ... 29
  ... Hebrew verse ... 32    ... Hebrew verse ... 31
                            ... Hebrew verse ... 33
                         section sign / chapter separation
                         ... Hebrew verse ...               ╔══════╗
                         ... Hebrew verse ... 2             ║  2   ║
                                                             ╚══════╝
  ... Hebrew verse ... 4     ... Hebrew verse ... 3
                            ... Hebrew verse ... 12

 ────────────────────────────────────────────────────────────────────
 90 headword gloss.  91 headword gloss.  ... 104 headword gloss.
 paragraph continues across the full width as needed.

     1 headword gloss.  2 headword gloss.  ... 22 headword gloss.
 paragraph continues across the full width as needed.
```

The schematic describes placement only; actual Hebrew remains in logical Unicode
order and is shaped by TeX.

## 3. Scripture typography

**R01 — Continuous scripture.** Flow consecutive verses through a justified RTL
paragraph, as in `bereshit002.jpg`. Verse numbers appear inline; adjacent verses
may share a line and longer verses wrap naturally without repeating the number.
The final line is right-aligned. Start a new paragraph at each chapter opening or
page boundary. Preserve source section signs. Verse boundaries remain explicit
in source records and page plans, even though they no longer force line breaks.

**R02 — Verse numbers.** Render Arabic digits in a smaller Latin serif face inline
before the verse's first word, keeping the number attached to that word. Keep
digits LTR inside the RTL context.
Verse 1 at a chapter opening has no separate printed `1` in the sample; the chapter
box introduces it. Verse 2 has its own number beside the inset text.

**R03 — Hebrew.** Use a clear book-style Hebrew face with reliable pointing and
combining-mark positioning. Retain consonants, vowel points, dagesh, shin/sin dots,
maqaf, sof pasuq, and source-provided section signs. Do not add word spacing around
maqaf or detach punctuation from the intended word. Avoid synthetic bold if a
font has no suitable weight; establish perceived weight through proofing.

**R04 — Diacritic policies.** Preserve the complete imported surface separately
from display transformations. Vowels are essential to the reference style. The
scan does not establish an exact cantillation or editorial-mark policy: small
additional signs are visible and need identification. Provide named display
policies with provenance; never delete all combining marks to suppress accents.

**R05 — Lexical markers.** Use small, raised Latin digits, visually at the left
edge of the annotated RTL word in the reference. Attach the marker to the word or
explicit morpheme/reading anchor so it cannot start a line by itself. It must not
move to an adjacent word because of bidirectional punctuation. Multi-digit labels
such as `104` must remain internally LTR and must not collide with Hebrew marks.

**R06 — Chapter opening.** Introduce chapter 2 mid-page with a large Latin `2`
inside two fine square outlines. Reserve space on the right beside the first two
lines of the continuous chapter paragraph. The text returns to full width after
those two lines. Treat the opening and its first two verses as a measured page
group; the box is not an independent floating object. Reserve two lines even for
a passage containing only a short verse 1, so the box remains inside the measured
scripture area.

**R07 — Alternative readings and editorial signs.** Small raised K/Q labels and
alternative forms are visible around 2:7–8. Represent written/read alternatives
as related readings with separate anchors; verify their exact mapping against the
chosen source. Other small diamond/sublinear signs remain unidentified here.
Allow structured editorial annotations, but do not assign their meaning from
shape alone or invent them to improve visual similarity.

## 4. Lexical apparatus

**R08 — Run-in layout.** Notes form full-width LTR paragraphs, not columns, a
table, one note per line, or a bottom list with hanging numbers. A note consists
of a raised label, a Hebrew headword, optional homograph/stem/usage labels, and
English gloss text. The headword is an isolated RTL run; surrounding prose and
numbers remain LTR. English glosses can wrap and hyphenate normally.

Keep the note number with its headword, and preferably the headword with the first
gloss word. Permit the rest of a long entry to wrap. Separate entries with modest
horizontal space and punctuation. Optional labels use a smaller or small-cap
Latin style; they come from a verified morphology/lexicon mapping.

**R09 — Grouping.** Use one note paragraph per chapter represented on the page.
This page has a chapter-1 paragraph followed by a chapter-2 paragraph, with a
visible paragraph gap/indent. The sample has no large “Chapter 1” or “Chapter 2”
headings in the apparatus. Keep that restrained style; expose group identities
in structured output and the review UI.

**R10 — Number reuse.** A lexical help can be referenced repeatedly in a chapter.
It is not assigned a fresh number at every occurrence. Directly visible examples:

| Chapter-2 label | Visible locations | Required behavior |
| --- | --- | --- |
| 4 | 2:2, 2:3, 2:6, 2:11 | One chapter-local help identity; one entry in this page's apparatus |
| 9 | 2:5, 2:6, 2:10 | Repeated markers point to the same chapter-local help |
| 16 | Two forms in 2:8 | Multiple reading anchors may share one help |

Chapter 1 uses labels 90–104 on this page; chapter 2 restarts at 1 and reaches 22.
Thus there are **37 distinct displayed help entries** across two chapter groups,
with more than 37 body references. Labels are local to a chapter: `(chapter, 4)`
is the identity of a printed label, not the integer `4` by itself.

**R11 — Semantic identity.** Proposed deduplication key:
`(edition, book, chapter, lexicon revision, lexeme, sense selection,
grammatical qualification, editorial gloss revision)`.
Include only qualifications that change the displayed help. Different inflections
may share a help; distinct homographs, stems, or senses may require different ones.
Do not deduplicate solely by headword spelling or the same English gloss.

**R12 — Numbering scope.** Assign numbers before pagination in first-use reading
order within a chapter's selected helps. Build a chapter registry independent of
page breaks, then project the requested passage. A passage beginning at 1:29 must
not automatically start at 90: that number requires the full chapter registry or
an explicit validated reference-profile map. A new lexicon/selection policy can
legitimately produce different numbers from the scan.

**R13 — Notes on later pages.** Proposed app behavior, not inferable from this
single scan: if a chapter-local help is referenced on another page, repeat its
entry there with the same number. Each page remains independently readable.
Within a page, print the entry once. List entries by chapter order then chapter
label order, even when reused labels make the sequence non-consecutive.

**R14 — Selection policy.** The scan annotates selected words, but gives no evidence
for the corpus-frequency threshold or known-vocabulary list. For the first proof,
use an explicit reviewed selection. Later offer all eligible helps, a named-corpus
frequency cutoff, known-word lists, and per-occurrence overrides. Record why each
item is included or omitted. Do not silently omit failed lexical joins.

## 5. Pagination and page construction

**R15 — Page-local notes.** Every displayed lexical marker must have its help in
that page's apparatus, in the correct chapter group. The page contains no unrelated
unused lexical entries. Chapter-reset labels cannot resolve to the wrong group.

**R16 — Coupled layout.** Determine fit from both scripture and unique note content:

```text
header + header gap + scripture blocks + chapter gaps
+ text/notes gap + rule + apparatus paragraphs <= usable page height
```

Do not allocate scripture to pages first and append all notes afterward. A
candidate page's note set changes when a verse crosses its boundary.

**R17 — Breaking rules.** Prefer page breaks between verses. Keep a chapter box
with its opening group. Keep ordinary short verses and all their notes on one
page. For an exceptionally tall verse-plus-apparatus unit, fail with an actionable
layout-overflow report in the first release; never shrink fonts or omit notes
silently. Later allow explicitly configured splitting with continued verse labels
and line/anchor-aware note assignment.

**R18 — Header and whitespace.** Derive the running reference from the first and
last visible verse on that page, not the full requested passage. Keep book title
centered geometrically. Use a page-local, full-width apparatus separator. Place
extra vertical space between text and apparatus when bottom-aligning the notes;
do not stretch Hebrew baselines to fill the page.

## 6. First proof profile

These are proposed starting values for calibration, not measurements of the
original print edition. Store them in a named profile rather than embedding them
in Python algorithms. Pin font files/versions once a proof is approved.

| Parameter | Proposed first value / calibration range |
| --- | --- |
| Reference design area | 160 × 261 mm, approximately the raster aspect ratio |
| Proof media | 180 × 281 mm with the design area centered; 10 mm margins |
| Header/body/apparatus width | About 153 mm within the design area |
| Hebrew body | Start 18 pt; calibrate within 17–20 pt |
| Hebrew baseline distance | Start 23.5 pt; calibrate within 22–25 pt |
| Verse digits | Start 11 pt |
| Body help markers | Start 7 pt; calibrate rise and horizontal separation |
| English apparatus | Start 10 pt on 12.5 pt baseline |
| Hebrew apparatus headwords | Start 11 pt; calibrate relative weight and baseline |
| Book title | Start 18 pt; passage/folio about 10 pt |
| Chapter box | Start 11.5 mm square; double fine rules; numeral about 25 pt |
| Horizontal rules | Start 0.35 pt |

The reference design area is a way to compare page composition without claiming
the scan reveals paper trim. A4, A5, and Letter exports should reflow through the
same planner; they are not required to keep this passage on exactly one page.
The calibrated reference profile must fit the target passage on one page with
its reviewed help set. If it does not, revise the explicit profile or gloss
selection during proofing instead of adding an invisible squeeze-to-fit rule.

SBL Hebrew is the existing development font, but the scan's face has not been
identified. Font choice remains an explicit proofing decision. The project uses
[fontspec](https://ctan.org/pkg/fontspec) for OpenType font selection and
[polyglossia](https://ctan.org/pkg/polyglossia) for language runs on XeLaTeX.
Neither package guarantees that a particular font resembles the reference.

## 7. App behavior

The user confirmed a **local browser app plus CLI**. Both use one Python build
service and produce the same artifacts from the same saved project configuration.

| Screen | User actions | Result |
| --- | --- | --- |
| Sources | Choose installed text/lexicon revisions, inspect attribution, import a supported source | A reproducible source selection |
| Passage | Select book, chapter/verse range, reading policy, and output profile | Validated passage in its source versification |
| Lexical review | Inspect surface/lemma/morphology, resolve candidates, select/shorten sourced glosses, include/exclude helps | Saved, traceable decisions; unresolved counts remain visible |
| Layout | Adjust font sizes, page size, note policy, and page-number start | Named settings with preview invalidation |
| Preview/export | Build, inspect pages, follow markers to the lexical review row, export | PDF plus optional TeX and reproducibility bundle |

The preview must render the generated PDF, not an HTML imitation of the print
layout. A passage table can be HTML, but it is not the proof. Source credits should
be available in the app and export bundle; include any attribution required in
the PDF in a credits page/front matter without crowding the reference reading page.

Default workflow: choose sources → choose passage → review lexical helps → build
preview → adjust if needed → export PDF. Advanced logs and source IDs belong in
details panels, not between routine reading/export actions.

## 8. Acceptance checklist

| Check | Passing result |
| --- | --- |
| Passage coverage | Exactly 1:29–33 and 2:1–12, in order, without missing or extra tokens |
| Source fidelity | Text/marks/readings match the selected source and documented display policy |
| Reference header | Correct passage, centered Hebrew book title, configurable folio |
| Verse layout | Continuous justified RTL flow, inline LTR digits attached to first words, stable wrapping and punctuation |
| Chapter opening | Double-boxed 2, no redundant verse-1 digit, room beside first two paragraph lines |
| Shared notes | Labels 4 and 9 are demonstrably reused in the reference fixture |
| Reference apparatus | Two paragraphs with 15 and 22 unique entries when using the reference topology |
| Page membership | Every marker resolves on that page to exactly one chapter-qualified help |
| Mixed scripts | Correct headword, gloss, digits, punctuation, and K/Q directions |
| PDF quality | Embedded permitted fonts, selectable text, no missing glyphs/clipping/overfull content |
| Generality | A longer sample crosses a page and chapter boundary without renumbering or lost notes |
| Rebuild | Same inputs give identical reader records, note registry, page plan, and TeX |

The 37-entry requirement is for the reference topology, not a claim that an
unconfigured external lexicon will produce identical helps. A real sourced proof
uses reviewed source entries; any differences in help selection or gloss length
from the scan must be recorded rather than concealed.

Unresolved editorial questions: exact text edition, font face, vocabulary cutoff,
meaning of the additional tiny signs, and preferred cantillation presentation.
They do not block implementing the model, source adapters, or layout proof; they
do block claiming an exact edition-level reproduction.
