# Delivery status

The local browser app plus CLI is implemented. The original milestone design
remains in [python-app-plan.md](python-app-plan.md); actual validation and limits
are recorded in [release-validation.md](release-validation.md).

| Gate | Delivered evidence |
| --- | --- |
| M0 — Typography | Real XeLaTeX reference and A5 proofs; inspected mixed Hebrew/English and chapter transition |
| M1 — Contracts | Strict config, source records, reader v2, source lock, registry, page plans; v1 compatibility retained |
| M2 — Sources | Pinned 39-book OSHB catalog, STEP short-gloss adapter, attributed offline fixtures; all books parsed |
| M3 — Review | Exact/candidate/missing joins, explicit decisions and exclusions, frequency/known words, shared chapter labels |
| M4 — Pagination | TeX measurements, explicit pages, page-local notes, PDF link/font/overflow checks; four profiles tested |
| M5 — CLI | Setup, import, inspect/align, build, doctor, bundles, packaged font and offline rebuild instructions |
| M6 — Browser | Saved editions, revision conflicts, lexical review, job worker, native PDF preview, downloads; browser acceptance passed |
| M7 — Stabilization | Full Proverbs engineering proof, cancellation/recovery, package and clean-setup checks, regression suite and CI definition |
| Greek support | Pinned 27-book SBLGNT and 60-record Rahlfs catalog, TBESG/crosswalks, LTR browser/PDF, Gentium Plus, full source audit; see [Greek sources](greek-sources.md) for partial-witness and alignment limits |

Measured simplifications: canonical artifacts are parsed directly rather than
indexed in a second SQLite database; TeX candidate measurements are batched without
a persistent cache. These keep the pipeline inspectable. Full-book performance
and the source-review workload are documented, not hidden behind successful export.

Future work, outside the local Hebrew release: independently reviewed contextual
sense sets, additional lexicons with appropriate rights, detailed
Aramaic morphology display, persistent measurement caching, global page balancing,
within-verse splitting, and separately designed remote multi-user hosting.
