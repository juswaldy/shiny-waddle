# Original-language Bible reader

Build a reader that combines an explicitly chosen biblical text and lexicon,
produces inspectable LaTeX, and compiles a readable PDF. Hebrew Bible first;
keep source identities and language metadata suitable for later Aramaic and Greek.

## Project context

- [README.md](README.md): working commands and current implementation limits.
- [docs/reference-page-spec.md](docs/reference-page-spec.md): detailed Proverbs
  1:29–2:12 layout, note semantics, and acceptance criteria; authoritative print target.
- [docs/python-app-plan.md](docs/python-app-plan.md): Python local browser app + CLI
  architecture, measured pagination, and implementation milestones.
- [docs/product.md](docs/product.md): reader experience and the reference image.
- [docs/architecture.md](docs/architecture.md): pipeline boundaries and data model.
- [docs/sources.md](docs/sources.md): source candidates, provenance, attribution.
- [docs/roadmap.md](docs/roadmap.md): next deliverables and acceptance criteria.

Read the documents relevant to the task; small edits do not require the full set.
The repository implements the local Python app and CLI. See
`docs/release-validation.md` for measured evidence and `docs/operations.md` for
supported environments and limits. The original v1 renderer is compatibility code.

## Domain invariants

- Preserve source Unicode and word order. Store any normalized lookup key
  separately; do not normalize or strip pointing/cantillation in display text.
- Preserve edition, versification, source word IDs, segmentation, and ketiv/qere
  distinctions. Never silently replace a written form with a reading form.
- Scope lexical IDs by source and revision. A Strong's number is a cross-reference,
  not a universal word identity. Missing or ambiguous matches stay explicit.
- Glosses and morphology must be sourced or marked as editorial proposals.
  Do not invent scholarly content to fill gaps or infer a sense from spelling alone.
- Hebrew/Aramaic runs are RTL; Greek/English runs are LTR. Store logical Unicode
  order, never visually reverse strings. Test mixed-script markers and notes.
- The final reader offers continuous text or separate verse starts and reuses
  semantic help labels within a chapter. Notes are unique per page and grouped by
  chapter. The v1 demo's per-occurrence numbering and passage-end notes are not the
  final product contract.
- Keep imported text, annotations, lexica, fonts, and reference images under
  their own terms. The root MIT license applies to our code, not every input.

## Implementation conventions

- Start with the Python CLI and a XeLaTeX template. Keep fetching, parsing,
  alignment, note selection, rendering, and compilation separate.
- The checked-in demo is synthetic typesetting data, not a Bible transcription.
  Do not use it as evidence for a reading, morphology, or lexical sense.
- Keep raw downloads immutable under ignored `.reader/raw/` (or the chosen state
  directory); research downloads may use `data/raw/`. CLI outputs belong in
  ignored `build/`; app jobs use the state's `builds/`. Track attributable fixtures.
- Escape external text once at the LaTeX boundary. Only our templates emit TeX
  commands. Compile with shell escape disabled; do not interpolate shell commands.
- No live network lookup during rendering. Pin imported inputs and report
  unmatched/ambiguous records before producing a publication edition.
- Keep changes focused. Add tests for data integrity or behavior changes; use
  actual PDF inspection for typography rather than string tests alone.

## Repository skills

Use the matching skill when doing these workflows:

| Workflow | Skill |
| --- | --- |
| Import or update text, morphology, or lexicon data | [.agents/skills/import-bible-source/SKILL.md](.agents/skills/import-bible-source/SKILL.md) |
| Join tokens to lexical entries or choose glosses | [.agents/skills/align-reader-lexicon/SKILL.md](.agents/skills/align-reader-lexicon/SKILL.md) |
| Change LaTeX, RTL layout, fonts, pagination, or PDF builds | [.agents/skills/typeset-bible-reader/SKILL.md](.agents/skills/typeset-bible-reader/SKILL.md) |
| Review code changes or request an independent PR review | [.agents/skills/code-review-agent/SKILL.md](.agents/skills/code-review-agent/SKILL.md) |

## Verification

Run `make check` for Python and renderer changes. Run `make demo` to inspect the
generated TeX. For layout changes, run `make pdf` when XeLaTeX and the documented
fonts are installed, inspect the PDF and log, and report missing prerequisites.
Do not describe an uncompiled template as a verified PDF layout.
