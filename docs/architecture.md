# Pipeline and contracts

The local app and CLI share the same Python services. The original design is in
[python-app-plan.md](python-app-plan.md); the print contract is in
[reference-page-spec.md](reference-page-spec.md).

```mermaid
flowchart LR
    S[Pinned OSHB XML] --> I[Verified source adapters]
    L[Pinned STEP Gloss metadata] --> I
    I --> C[Source-preserving records]
    C --> A[ID alignment and lexical review]
    A --> N[Selection and chapter registry]
    N --> R[Reader document v2]
    R --> M[TeX box measurements and page plans]
    M --> T[Escaped LaTeX]
    T --> P[Compiled and verified PDF]
```

## Implemented modules

| Module | Responsibility |
| --- | --- |
| `models.py` | Strict Pydantic settings, frozen source records, reader document |
| `sources.py` | Pinned acquisition, hash checks, OSIS/TSV adapters, canonical exports |
| `editorial.py` | Crosswalk candidates, decisions, frequency, stable chapter help labels |
| `word_classes.py` | Source-morphology display categories and preset word-color palette |
| `tex.py` | Explicit language runs, TeX measurement, pagination, bounded compiler, PDF checks |
| `service.py` | Shared inspect/build/doctor use cases and reproducibility bundles |
| `store.py` | SQLite project revisions, durable job snapshots, atomic claims |
| `jobs.py` | One separate POSIX worker per workspace; cancellation and recovery |
| `cli.py` | Argparse commands; JSON/TOML project input |
| `web/` | FastAPI routes, escaped Jinja2 page, static JS/CSS, native PDF preview |
| `render.py` | Backward-compatible synthetic v1 JSON-to-TeX specimen |

Rendering reads only local verified sources. Source acquisition never occurs as
an implicit side effect of a build. There is no ORM, hosted database, JavaScript
build pipeline, or model-generated lexical content.

## Records and identity

`ProjectConfig` has schema version 2, name, book/passage, selection policy, reading
and accent policy, known entries, per-anchor decisions, and validated typography.
`examples/reference.project.json` is a minimal example. `bible-reader init` writes
all defaults. Unknown settings are rejected. Project saves use an integer revision;
a stale tab cannot overwrite newer work.

Source `Verse` records preserve ordered `Token`s and serialized source annotations.
A token keeps its OSHB ID, raw surface, lemma/morphology codes, word/separator kind,
normal/ketiv/qere reading, language, and source XML. Display strings remove slash
segmentation. The default `hide` accent policy removes only U+0591–U+05AF;
`preserve` retains source accents. `consonants-only` hides Hebrew combining marks
and punctuation. The existing `consonants` setting hides Hebrew combining marks
and punctuation except maqqef and is labeled **Consonants + maqqef**;
`consonants-maqqef-sof-pasuq` retains maqqef and sof pasuq while hiding the other
Hebrew marks and punctuation. Other-script characters and section letters remain
intact. Hidden separator tokens remain in the document with an empty display
surface; TeX skips them so hidden maqqef becomes ordinary word spacing. These policies apply
to scripture and review surfaces; lexical headwords retain their source pointing.
The chosen transformation is recorded in the source lock and credits. Raw surfaces
remain unchanged. Source IDs are interpreted within the pinned book/revision in the lock.
No source Unicode normalization or visual string reversal occurs.

Reader tokens also retain raw `morph`, a derived `word_class` (or null), and
`word_class_source` evidence. Classes follow the [OSHB morphology codes](https://hb.openscriptures.org/parsing/HebrewMorphologyCodes.html):
one language prefix applies to the full slash-separated analysis. Attached
conjunction/preposition/article prefixes and suffixes share the main component's
class; multiple main components or unknown codes remain unclassified. Cardinal
and ordinal adjective codes use the `number` display category. Confirmed OSHB
proper names or existing STEP name evidence use `name`, including omitted helps;
mixed candidates do not establish a name until a name entry is chosen.
`layout.word_colors` defaults to `auto` (no color) or enables `word-class`.
`layout.word_color_overrides` maps supported classes to `auto` or validated hex
colors. These settings affect presentation independently of help selection.

Each numeric lemma component maps to an anchor `<source-token-id>:<component-index>`.
Exact extended IDs can resolve only when a single lexicon candidate exists. Base-ID
fallbacks and multiple candidates require explicit review. `Entry` IDs are qualified
by `step:` and interpreted with the pinned lexicon revision. Only metadata and
STEP's short Gloss column are imported; `definition` remains empty.

A review row records candidates, chosen entry, status, reason, source/display
surface, morphology, reading, book frequency, selection, and help ID/label. Decisions
include action, optional supported entry ID, optional editorial gloss, and reason.
An exclusion is explicit and remains in the report. Missing source anchors or
incompatible entry choices fail rather than silently discarding stale decisions.

Names are excluded after alignment and editorial choices, before chapter help
registration, in every selection mode. OSHB noun type `Np` identifies proper
names; STEP's `N:` classification identifies names independently of language.
Parallel OSHB slash-separated lemma/morphology segments identify individual
lexical components where possible, so a neighboring common component retains
its help. Mixed name/common candidates remain ambiguous until an entry is chosen;
all-name candidate sets can be omitted without choosing between named identities.
Review rows retain raw morphology, component morphology, candidates, alignment
status, and explicit name-omission evidence. Existing inclusion decisions remain
inspectable history but cannot restore name helps. New inclusion attempts fail,
and book-wide inclusions report and skip name occurrences.

Lexical review can expand a decision to every matching word in the selected book.
A separate consonant key removes Hebrew marks/punctuation and slash segmentation
from the raw surface; prefixes/suffixes, logical order, and source Unicode remain
intact. Matching stays within a language and includes both K/Q records and words
outside the current passage. Each compatible lexical component receives an
ordinary per-anchor decision, replacing earlier edits. Components without the
chosen entry in their pinned crosswalk candidates are reported and left unchanged.
Review rows include the key and whole-book word count independently of lemma
frequency. The API saves the expanded configuration in one revision-checked update;
existing build snapshots remain immutable.

The lexical review grid and cards share per-anchor draft editors. Page submission
uses `POST /api/projects/{id}/decisions/batch`, with a project revision and up to
200 explicit anchor/decision/scope edits (the UI offers up to 160 rows per page).
The editorial service loads the pinned sources once for expansion, validates the
combined document, and saves one project revision. Duplicate anchors and
conflicting overlapping book/occurrence choices fail before persistence. Applied
and unsupported anchors are reported once each. Unresolved choices remain
explicit, and existing immutable build snapshots retain their saved decisions.
Browser drafts remain in memory across paging, filters, view switches, review
refreshes, and other row saves; they are never committed implicitly by a build.

The chapter registry is computed before filtering the requested passage, from the
same selected chapters and settings. General help identity includes lexical entry,
stem, and gloss. The reference fixture supplies separate observed slots where the
same lexeme has more than one note. Altered reference helps receive new labels.
Each page projects the registry and repeats just its referenced helps, once per
chapter-qualified help identity. Printed numbers are not lexical identities.

`ReaderDocument` version 2 contains resolved config, ordered verses/tokens, referenced
helps, review rows, chapter registry, source lock, and warnings. The source lock
contains actual artifact hashes and upstream revisions. `page-plan.json` contains
verse blocks, first/last references, folios, measured heights in TeX scaled points,
and unique help IDs per page. Each candidate's complete page height includes its
actual running head and separator spacing, measured using the same box assembly
as final output. Fit is checked against TeX's usable text height; there is no fixed
header allowance. Final TeX uses exactly those boxes, blocks, and page breaks.
Verse blocks are pagination units. `layout.verse_layout` selects continuous
justified RTL paragraphs with inline verse numbers, or separately started,
right-aligned verse paragraphs with a number gutter. Chapter boxes reserve the
first two lines in continuous mode and the first two verses in verse-per-line mode.
Measurements and the final PDF use the same selected construction. Saved projects
and immutable build snapshots retain the choice; omitted settings default to
continuous through project validation.

`layout.paper` defaults to `reader` (140 × 216 mm). Existing named profiles retain
their dimensions. Selecting `custom` requires validated `paper_width_mm` and
`paper_height_mm`; project revisions, immutable build snapshots, and reader JSON
retain them. A shared dimension resolver supplies measurement, page budgets, and
final PDF geometry, with 10 mm margins for reader/custom paper.

## Persistence and reproducibility

SQLite stores projects/jobs only; raw sources remain the authority. Imports also
write rebuildable canonical JSONL and lexical JSON. At current corpus sizes,
verified parsing is fast enough without a second persistent lookup index.
The worker batches candidate measurements per page; it does not have a persistent
measurement cache. Build results are immutable directories with complete manifests.

Reader JSON, page plans, registries, and TeX are deterministic under the same inputs
and environment. PDF bytes and logs are not promised identical across installations;
font/engine/loaded-TeX-input hashes are recorded for comparison. The output PDF is
checked for page count, complete ordered verse coverage, actual marker counts,
actual page-local hyperlink destinations, font embedding, missing glyphs, and
horizontal/vertical overflow. Visual inspection complements these checks.

## v1 compatibility

`examples/demo.reader.json` remains explicitly synthetic. Calling the CLI with
that filename and `--output` uses its strict schema-1 renderer: document title,
language, source notice, entries, and verses of tokens with already-selected entry
IDs. It retains occurrence numbering and passage-end notes. Production source
import, editorial review, and PDF builds all use schema 2.
