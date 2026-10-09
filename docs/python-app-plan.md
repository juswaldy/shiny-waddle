# Python application implementation plan

Status: original design plan, retained as design history; local release 0.2.0
implemented on 2026-10-02. The print target is [the Proverbs reference-page specification](reference-page-spec.md).
The 2026-10-09 layout update adds a per-project choice between continuous RTL
paragraphs with inline verse numbers, following `bereshit002.jpg`, and the original
separate verse starts. Continuous is the default; verse boundaries remain pagination
units in both modes. Earlier fixed verse-layout descriptions below are design history.
For actual commands and modules use [README](../README.md) and
[architecture](architecture.md); for completed checks and limitations use
[release validation](release-validation.md) and [operations](operations.md).

Implementation adjustments: Pydantic validates project settings; immutable
dataclasses represent sources. SQLite stores projects/jobs, while verified raw
sources are parsed directly (the proposed separate lookup index is unnecessary
at current corpus sizes). Measurements are batched per candidate page, without
a persistent cache. PDF hyperlink destinations provide the page-membership proof
instead of zref. FastAPI serves Jinja2 plus plain JavaScript. Export bundles include
Ezra SIL under its license. The following proposed module names and routes are
design examples, not an API compatibility promise.

## 1. Deliverable and boundaries

Build a local application that imports identifiable biblical text and lexical
sources, lets a reader review passage-specific helps, and exports a PDF with the
reference page's verse layout and compact chapter-grouped apparatus. Python owns
data processing, editorial decisions, pagination orchestration, persistence, the
CLI, and the web service. XeLaTeX owns Unicode shaping, line breaking, and PDF
typesetting. The browser previews the actual resulting PDF.

First acceptance artifact: **Proverbs 1:29–2:12 on one calibrated reference-profile
page**, including chapter transition, shared notes, and source-backed readings.
Then prove a longer passage that crosses multiple pages. A one-page special case
alone is not a usable application.

The scan is a layout and note-topology reference. It does not automatically select
an upstream edition or license its lexical content. We can match the visual
structure while using reviewed, attributed lexical entries; exact gloss text is
not assumed. Do not hardcode the 17 verses into the production renderer.

## 2. Technical decisions

| Concern | Decision | Reason / limit |
| --- | --- | --- |
| Python | Keep Python 3.11+ compatibility; pin the development/CI interpreter | Reuse the existing project and standard-library tooling |
| Core models | Frozen dataclasses, enums, explicit validators; versioned JSON interchange | Keep source/reading/help identities visible and testable |
| Source parsing | Adapter-specific XML/TSV parsers over pinned local artifacts | Upstream markup and identifier schemes remain distinct |
| Storage | Canonical JSONL artifacts plus a rebuildable SQLite index; SQLite also stores app projects/jobs | Passage/lexeme lookup and local persistence, without a service database |
| CLI | Extend `argparse` into subcommands | The core pipeline does not need a CLI framework |
| Web layer | FastAPI, Uvicorn, server-rendered Jinja2 pages, small browser-side interactions | A Python app with no required SPA build toolchain |
| HTML/TeX templates | Separate template environments; retain controlled TeX emission in the core | HTML escaping and TeX escaping are different operations |
| PDF engine | XeLaTeX + fontspec + polyglossia; versioned project macros | Continue the bootstrap's engine and verify the reference typography |
| Pagination | Python page planner using actual TeX box measurements | Couple text and unique page-local notes without guessing Hebrew glyph widths |
| Background builds | A separate local worker process, persisted job state, one compile at a time initially | Keep the browser responsive and support cancel/recovery |
| Verification | Existing unittest suite, source/contract fixtures, compiled PDF checks and visual proofs | Domain correctness and visual correctness require different evidence |
| Dependency locking | Commit a lockfile when real dependencies are added | Record versions actually tested; avoid speculative version pins now |

FastAPI documents server-rendered templates through `Jinja2Templates`; this is
the basis for the proposed thin web layer, not a claim that FastAPI supplies the
reader workflow itself. [Official template documentation](https://fastapi.tiangolo.com/advanced/templates/).

SQLite is an index/persistence choice, not the only copy of imported source data.
Keep raw artifacts and canonical records outside the database so adapters and
indices can be rebuilt. Avoid an ORM in the first slice; use parameterized SQL
and explicit migrations for the small application schema.

## 3. Application structure

Add modules as their milestones arrive rather than creating empty scaffolding.

```text
src/bible_reader/
  __main__.py                 CLI dispatch; preserve/document legacy demo invocation
  models.py                   refs, tokens/readings, lexemes, alignments, notes
  config.py                   project/profile validation and resolved configuration
  sources/
    manifests.py              revisions, hashes, notices, layer provenance
    acquire.py                explicit import/download; never called by renderer
    oshb.py                   Hebrew text/morphology adapter
    step_lexicon.py            selected TBESH artifact adapter
  storage/
    canonical.py              canonical JSONL read/write
    sqlite.py                 passage and lexicon indices, migrations
    projects.py               saved projects, editorial decisions, jobs
  alignment/
    crosswalks.py              versioned source-ID mappings
    resolve.py                 candidate resolution and coverage reports
  editorial/
    selection.py               frequency/known-word/explicit policies
    overrides.py               reviewed changes without modifying imported data
    numbering.py               chapter-local semantic help registry
  layout/
    blocks.py                  verses, chapter openings, note paragraphs
    measure.py                 TeX metrics, cache keys, integer dimensions
    paginate.py                candidate pages and legal breaks
    verify.py                  fit, completeness, marker-to-note page membership
  tex/
    escape.py                  plain-text boundary and structured inline spans
    emit.py                    measured blocks and final planned pages
    compile.py                 engine discovery, timeout, logs, cancellation
    templates/                 reader class/macros and measurement document
  service.py                   build/preview/import use cases shared by CLI and API
  jobs.py                      persisted transitions and worker entrypoint
  web/
    app.py                     local routes and dependency wiring
    templates/                 passage, review, layout, preview screens
    static/                    CSS and minimal interaction code
```

The current `render.py` and `templates/reader.tex` remain the v1 synthetic demo
until the v2 pipeline is ready. Move their escaping logic only when its tests
move with it. Do not silently interpret old demo inputs as scholarly source data.

## 4. Version-2 data contracts

| Record | Minimum fields and invariants |
| --- | --- |
| SourceArtifact | ID/kind, immutable revision, artifact hash, edition, language(s), versification, attribution/license layers, transformation history |
| PassageRef | Source + edition + versification + book/chapter/verse/subverse; sortable by explicit canonical order, not lexical string sort |
| Token | Stable upstream identity, reference, ordinal, exact raw surface, source location, morphemes, raw lemma/morphology, language |
| DisplayUnit | One selected written/read form or punctuation unit; ordered spans, join-before/after behavior, source-token links, display-policy ID |
| ReadingAlternative | Written/read relation, original forms, source evidence, chosen presentation, independent marker anchors |
| Lexeme/Sense | Lexicon source/revision, entry ID, homograph, headword, sense IDs, glosses, stem/usage qualifiers, external IDs |
| Alignment | Token/segment/reading anchor, candidates, status, mapping method/version, source evidence; no arbitrary first-candidate choice |
| EditorialDecision | Target and source revision, action, previous/new value, author/reason, revision; stale decisions detectable after source updates |
| Help | Semantic help ID, lexeme/sense references, display headword, structured gloss spans, qualifiers, provenance, editorial revision |
| HelpReference | Display anchor → help ID; multiple anchors can reference one help |
| ChapterNoteRegistry | Chapter-qualified help IDs with printed integer labels; selection-policy fingerprint and allocation order |
| ReaderDocument | Selected passage, display units, chosen helps, registry projection, profiles, source notices; version 2 |
| PagePlan | Ordered block IDs, first/last references, chapter note groups, measured heights/widths, page/folio, profile and measurement fingerprint |
| BuildManifest | Input/config/code/template/font/engine digests, reader/registry/page-plan hashes, stage status, artifacts, diagnostics |

Keep imported bytes in raw artifacts. The parser may decode XML entities and
represent structures, but must not apply unrequested Unicode normalization to
surfaces. Retain enough source location information to compare the canonical
record back to its origin. Never reconstruct a verse by blindly joining all
token surfaces with a space: maqaf, punctuation, segments, and variants need
explicit display relationships.

Model language on records (`hbo`, `arc`, later `grc`), not only at document level.
Separate source surface, transformed display, and normalized lookup key. A
display policy can suppress a well-defined set of accents while retaining the
original surface and recording the change.

Do not encode a whole lexical note as raw TeX. Represent text, Hebrew headwords,
qualifiers, emphasis, and labels as typed spans emitted by trusted macros.

## 5. Import and alignment

Initial candidates remain OSHB for text/annotations and STEPBible TBESH for brief
lexical helps. OSHB documents OSIS words with lemma/morphology attributes and
source IDs; STEPBible describes TBESH as a Hebrew lexicon using extended Strong's
identifiers. These descriptions support trying that pairing, not assuming a
lossless ID join. [OSHB](https://github.com/openscriptures/morphhb),
[STEPBible data](https://github.com/STEPBible/STEPBible-Data).

1. Pin actual upstream revisions and selected files, preserve their notices,
   compute hashes, and write manifests following [sources.md](sources.md).
2. Import all of Proverbs chapters 1 and 2 for the first source-backed proof.
   Full chapter context is needed for chapter-scoped numbering; import the
   wider named corpus before offering corpus-frequency selection.
3. Preserve verse boundaries, IDs, surface marks, maqaf, section markers,
   segmentation, morphology codes, and alternatives in adapter fixtures.
4. Map documented identifier components; record how prefixes, homographs,
   extended IDs, and Aramaic language distinctions are handled.
5. Generate a coverage table for resolved, ambiguous, unmatched, excluded, and
   unsupported records. Show exact anchors and candidate source entries.
6. Review the target passage. Persist sense choices and shortened glosses as
   editorial decisions, never mutations of the imported lexicon.

Selected unresolved helps block a final-quality build. A review/draft mode can
show an explicit unresolved placeholder and a draft indicator; it must not invent
a definition. Intentional help omission is a different state with its own reason.

The target scan's small K/Q and other signs require careful source comparison.
If an upstream format does not contain the same editorial layer, record that
difference instead of synthesizing it from the image.

## 6. Selection and numbering algorithm

For each chapter in the requested passage:

1. Load the chapter's resolved display anchors, alignment results, and overrides.
2. Apply the explicit help policy. Initially this is a reviewed selection file.
   Later it can use a named-corpus frequency cutoff and a known-word list.
3. Resolve each selected anchor to a semantic Help key. Include a sense/stem or
   gloss revision only when it changes what the reader would see.
4. Walk the selected anchors in source reading order. Allocate the next label
   on first use of a Help; reuse that label on subsequent references.
5. Persist the complete chapter registry and its policy fingerprint. Project the
   requested passage without renumbering the remaining labels.

Changing page size must not change numbering. Changing help selection or an
editorial meaning can change it; regenerate the registry and invalidate affected
previews. A reference-proof mode may accept a validated explicit label map to
exercise 90–104 and 1–22 without pretending those labels came from a different
lexicon's selection rules. Reject duplicate labels for distinct helps within a
chapter and inconsistent labels for the same help.

Page apparatus = unique referenced Helps for that page, grouped by chapter and
sorted by their chapter labels. Repeated appearances on another page repeat the
entry there using the same label. Record HelpReferences separately from the
unique entries so word markers are never lost during deduplication.

## 7. TeX layout proof and page planner

### Why measure complete candidate pages

The difficult part is not substituting values into a TeX template. A verse can
introduce several new notes or reuse earlier notes, so its incremental page cost
depends on what is already on that page. Gloss length changes line breaks in the
run-in apparatus. A chapter boundary introduces both a text-opening object and
a new apparatus paragraph.

Use TeX as the source of shaping and line metrics. Python must not estimate
Hebrew width from character counts or draw/reverse strings itself.

### Measurement interface

Emit trusted macros for a verse block, chapter-opening group, note entry, and
chapter apparatus paragraph. A measurement document places candidate blocks in
boxes at the final fonts and widths, then writes their heights, depths, widths,
and overflow diagnostics to a machine-readable sidecar. Use generated ASCII
IDs in that sidecar, not unescaped upstream strings.

Measure scripture and apparatus with the **same macros** used in final emission.
Use integer TeX scaled-point dimensions internally. Cache by display content,
note set/order, profile, font file digests, macro digest, and engine/package
environment; a font or gloss change invalidates the relevant measurements.

The first proof should compare a small controlled set of implementations for
chapter-box insets and paragraph notes. `footmisc` provides paragraph footnotes,
and `reledmac` supports scholarly editions, but neither is assumed to solve our
chapter-shared note/page-membership requirements without evidence.
[footmisc](https://ctan.org/pkg/footmisc), [reledmac](https://ctan.org/pkg/reledmac).

The proposed production approach is explicit page construction from measured
blocks. It avoids depending on automatic footnote counters for semantic note
identity. Revisit only if the proof demonstrates a simpler package solution that
passes the same reference and multi-page tests.

### Pagination algorithm

```text
allocate chapter registries independently of pagination
remaining = ordered verse / chapter-opening blocks
while remaining:
    evaluate legal candidate prefixes from the next block
    for each prefix:
        notes = unique referenced helps, grouped by chapter
        metrics = measure(scripture(prefix), apparatus(notes), profile)
        retain candidates whose total fits the usable page rectangle
    choose the fullest fitting candidate that respects keep/break rules
    if no candidate fits:
        report the offending verse/group, notes, and overflow dimensions
        stop without publishing a successful build
    freeze a PagePlan; remove its consumed blocks
render every frozen page with those exact blocks and notes
verify final emitted pages against PagePlans
```

Evaluate prefixes within a bounded window based on the measured scripture height
and available page height, then extend that window only if needed. Cache and batch
measurements; do not start a separate TeX process for every word or note. Start
with an understandable linear candidate scan before adding performance shortcuts.
Do not assume estimated note height is monotonic enough for an unverified binary
search. For the first release, a small amount of unused space is preferable to
breaking the explicit keep rules.

The first two verse blocks of a chapter can form one opening group with a right
inset and chapter box. Ordinary verses are unbreakable page units in the MVP.
If such a unit exceeds one page with its notes, return a layout-overflow error.
Supporting within-verse page breaks is a later change requiring line-level
anchors, continued references, and notes for the actual fragments on each page.

Final pages contain a running head, scripture boxes, a controlled flexible gap,
the separator, and chapter note paragraphs in a fixed usable rectangle. Emit
explicit page breaks between plans. Prevent the TeX output routine from silently
repaginating planned boxes. Detect oversized boxes rather than clipping them.

Add diagnostic anchor positions/page labels when implementing PDF verification.
`zref` supplies page and position mechanisms, but the proof must establish exactly
which engine-compatible macros and coordinate convention the verifier will use.
[zref documentation](https://ctan.org/pkg/zref).

### Final compiler service

Locate XeLaTeX and required fonts/packages before starting. Compile in a unique
build directory with an argument list, `shell=False`, shell escape disabled,
a timeout, and captured logs. Use `Popen` when cancellation/process-group control
is needed; use `run` for simple bounded subprocesses. [Python subprocess docs](https://docs.python.org/3/library/subprocess.html).

Run enough passes to stabilize required references/sidecars, with a small explicit
cap (initially four). Fail if stability is not reached. Never retry indefinitely.
No live downloads or package installation during rendering. Keep the failed TeX,
logs, and diagnostic report available for inspection. A missing font is an error,
not permission to substitute an arbitrary face.

The local application accepts structured source/settings data and project
templates, not arbitrary uploaded TeX. Compilation should use a restricted build
environment. Disabling shell escape alone is not a complete TeX sandbox; remote
multi-user hosting would require a separate deployment design.

## 8. Shared service, CLI, and web interface

Service functions operate on validated records/configurations and return typed
results or diagnostics. The API and CLI must call those functions rather than
implementing their own source joins, note numbering, or page planning.

Proposed CLI surface:

```sh
bible-reader doctor
bible-reader sources list
bible-reader sources import --manifest data/manifests/selected-source.json
bible-reader inspect --project reader.toml --passage 'Prov 1:29-2:12'
bible-reader align --project reader.toml --report build/alignment.json
bible-reader build --project reader.toml --output build/proverbs
bible-reader build --project reader.toml --emit tex
bible-reader serve --host 127.0.0.1 --port 8765
```

These commands are planned, not current capabilities. Preserve the documented
synthetic-demo invocation during migration, or provide a deliberate documented
`demo` replacement. `doctor` reports engine, fonts, source/index availability,
and relevant versions. `build --emit tex` still performs source, alignment, and
layout validation; it is not a shortcut around unresolved data.

Project configuration contains source/lexicon selections, requested passage,
reading/diacritic policy, selection and numbering policy, profile, editorial
decision revision, page-number start, and output preferences. Resolve defaults
once; record the resolved result with each build. Use TOML for human-authored
projects and JSON for machine artifacts. Numeric settings need explicit units
and reasonable bounds, with unknown configuration keys rejected.

Suggested routes, subject to implementation details:

| Route | Responsibility |
| --- | --- |
| `GET /` | Open/create a project; list recent builds |
| `GET /sources` | Installed source revisions and attribution |
| `POST /sources/import` | Queue a supported source import with explicit input selection |
| `GET/POST /projects/{id}` | Load/save validated project settings |
| `GET /projects/{id}/passage` | Source-faithful token/reading view |
| `GET /projects/{id}/helps` | Candidate joins, help selection, coverage |
| `POST /projects/{id}/decisions` | Save lexical/editorial decisions with stale-revision detection |
| `POST /projects/{id}/builds` | Queue a build using a configuration snapshot |
| `GET /builds/{id}` | Status, diagnostics, current artifact metadata |
| `POST /builds/{id}/cancel` | Request cancellation and terminate the worker's active compile |
| `GET /builds/{id}/preview` | PDF preview with passage/page navigation |
| `GET /builds/{id}/artifacts/{name}` | Serve only registered artifacts for that build |

The review table shows source form, lemma/headword, morphology, chosen gloss,
chapter label, inclusion reason, and resolution status. Clicking a marker/help
selects the associated review row. Use stable anchor IDs, not printed numbers,
for cross-panel navigation. A changed project makes its older preview visibly
out of date; exporting an old artifact remains explicit and names its build.

Initially embed the browser's PDF viewer. If marker-to-review navigation needs
coordinates not exposed by that viewer, add a PDF-viewer integration or an
adjacent anchor list as a separate UI step. Do not promise clickable overlay
behavior before the diagnostic position map has been proven.

Bind to loopback by default; validate local mutation requests and restrict artifact
paths to registered build files. No account system or public deployment is needed
for the confirmed local workflow.

## 9. Jobs, artifacts, and reproducibility

Persist jobs with `queued → running → succeeded | failed | cancelled` transitions.
On restart, mark abandoned running jobs `interrupted` and offer an explicit rerun.
Maintain stage progress (import, align, select, measure, paginate, compile, verify).
Use a single local worker initially; do not add Redis or a distributed queue for
one user's local compiler.

Each job snapshots its configuration and source/decision revisions. Concurrent
UI edits cannot change a running build's inputs. Write output to a unique build
directory and only expose a final artifact as successful after verification.

```text
build/<build-id>/
  config.resolved.json
  sources.lock.json
  reader.v2.json
  alignment-report.json
  note-registry.json
  page-plan.json
  reader.tex
  reader.pdf
  compile.log
  layout-diagnostics.json
  credits.txt
  manifest.json
```

Not every stage produces every artifact on failure. Record which stage completed.
Offer PDF alone and a reproducibility bundle; never bundle the reference scan or
large raw downloads implicitly. Byte-identical PDF output is a separate target
requiring controlled timestamps and TeX/font environment. Initially guarantee
deterministic reader JSON, registry, page plan, and TeX for pinned inputs.

## 10. Verification strategy

| Layer | Meaningful checks |
| --- | --- |
| Adapter | Exact passage reconstruction against upstream fixtures; IDs/order; maqaf/marks/variants; source counts and skipped-record report |
| Alignment | Documented crosswalk; homographs; composite IDs; multiple candidates; missing entries; stale overrides |
| Numbering | Same help repeats; changed sense separates; chapter reset; partial-chapter export; page size does not renumber |
| Layout | Unique notes per page; both chapters on a page; repeated help on next page; long gloss; too-tall verse; no orphan chapter box |
| TeX emission | Escape all source text once, preserve Unicode, validate structured spans, never emit raw source commands |
| Compilation | Missing engine/font, timeout/cancellation, nonzero exit, unstable references, no success artifact on failure |
| PDF | Correct page count, no missing glyphs/overflow, embedded fonts, marker/entry page membership, visual inspection |
| App | Save/reopen project, stale preview indication, failed build recovery, equivalent CLI and API artifacts |

Use the checked-in reference topology to test 17 verses, 37 unique helps, chapter
groups, and repeated labels. Build actual text/gloss fixtures only from chosen
attributable sources. Test source fidelity separately from display transformations.

After a proof is reviewed, store a small generated golden PDF or raster under
the fixture policy, with environment metadata. Compare later builds to that
generated proof. Do not use a byte/pixel-perfect comparison to the skewed scan as
the sole quality gate. Registration against the scan can guide relative region
positions, text density, and hierarchy; human inspection decides glyph quality.

No renderer behavior changes are required just to write this plan. Existing
bootstrap tests remain meaningful for the v1 demo, but do not validate any proposed
page planner, real lexical joins, or browser workflow.

## 11. Milestones and completion gates

Effort estimates are planning ranges for one developer and exclude waiting for
editorial decisions or dependency installation. They are not delivery promises.

| Milestone | Work and deliverable | Gate before proceeding | Estimate |
| --- | --- | --- | --- |
| M0: typography proof | Install/document a pinned TeX/font environment; hand-authored structural specimen; test RTL markers, K/Q spans, box inset, two run-in apparatus groups; measure boxes | A compiled, visually inspected proof shows the hard layout features; font choice and measurement method documented | 2–4 days |
| M1: v2 core | Contracts, config, provenance, reader/help/page schemas, v1 compatibility boundary | Round-trip records and validation catch missing/dangling IDs without changing source surfaces | 2–3 days |
| M2: real sources | Pinned OSHB/TBESH artifacts, chapter 1–2 adapters, canonical files, SQLite lookup index, source notices | Every selected verse reconstructs; variants and unsupported structures are accounted for | 3–5 days |
| M3: lexical review core | Crosswalks, coverage reports, editorial decisions, help selection, chapter registries | Shared 4/9-style cases, homographs, chapter resets, and partial exports pass | 3–5 days |
| M4: measured pagination | Measurement cache, candidate planner, explicit pages, compiler service, PDF verification | Source-backed Proverbs 1:29–2:12 reference proof plus a longer multi-page proof; all page-local notes verified | 5–8 days |
| M5: production CLI | Import/inspect/align/build/doctor commands, bundles, clear diagnostics | A clean documented local setup reproduces the reviewed PDF from pinned inputs | 2–3 days |
| M6: local browser app | Project/source selection, lexical review, settings, jobs, PDF preview and export | A user completes the entire flow without editing TeX or JSON; CLI and web builds agree | 4–6 days |
| M7: stabilization | Full-book trial, cache profiling, overflow reports, cancellation/restart, packaging and regression docs | No silent truncation; repeatable setup; named limits and open editorial decisions | 3–5 days |

Total initial planning range: **24–39 developer-days**, with M0 and M4 carrying the
largest typography uncertainty. Re-estimate after M0. M1/M2 can begin after the
measurement interface is chosen; the browser should consume stable services from
M3–M5 rather than inventing a second pipeline. This sequencing does not require
parallel agents or separate teams.

Definition of the first app release: source-backed Hebrew reader exports with the
reference's visual hierarchy, chapter-scoped shared helps, correct same-page
apparatus, a functioning local review/preview workflow, and reproducible artifacts.
Greek, remotely hosted accounts, automatic scholarly gloss generation, elaborate
critical-edition features, and within-verse page splitting are later extensions.

## 12. Immediate implementation order

1. Complete M0 before broad UI work: one real compiled layout proof will settle
   more risk than adding endpoints around the synthetic renderer.
2. Implement the v2 core and import Proverbs 1–2 with actual provenance.
3. Review selected helps and produce the chapter registry; explicitly map the
   scan's reference topology only where the chosen scholarly data supports it.
4. Build and verify the first source-backed target page and multi-page neighbor.
5. Wrap the proven service in CLI commands and the confirmed local browser flow.
