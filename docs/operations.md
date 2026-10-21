# Running and maintaining the local reader

## Environment

The supported release target is Linux x86-64, including Ubuntu under WSL, with
Python 3.11+ (use a maintained patch release), uv, and curl. Python dependencies
are locked in `uv.lock`. `scripts/setup_tex.py` installs TinyTeX v2026.10 plus bidi revision 77682
from an archived TeX Live repository; both downloads have SHA-256 pins. The script
uses curl because the archive host can return HTML bot challenges to Python's
HTTP client. HTML responses and checksum mismatches are rejected before extraction.
The script is idempotent, does not change system TeX, and can use an alternate `--directory`.
The application discovers the default `.tools/.TinyTeX` relative to the working
directory. Set `READER_XELATEX` when running an installed wheel elsewhere.

The default font is the bundled unmodified Ezra SIL 2.51. Latin Modern comes from
TeX. Selecting SBL Hebrew requires that font locally. A missing selected font fails;
there is no silent substitution. SBL font files are not included in export bundles;
`BUILD.txt` explains how to supply the exact font for recompilation.

Native Windows and macOS have not been qualified. The worker uses POSIX process
groups and `fcntl` locks. WSL is the supported Windows route.

## State and backups

`--state` (before the subcommand) or `READER_STATE` selects the workspace, defaulting
to `.reader/`. It holds:

- `reader.sqlite3`: saved project revisions and durable job records, using WAL.
- `raw/`: checksum-verified source files and notices; rendering never downloads.
- `canonical/`: rebuildable JSONL/lexicon exports from the import adapter.
- `builds/<job-id>/`: immutable per-job outputs, logs, and review reports.
- `inputs/`: immutable uploaded reader JSON and TeX snapshots used by transform jobs.
- `worker.lock`: one worker per workspace, acquired with a kernel file lock.

Stop the server before copying the entire workspace for backup. Restore into an
empty directory and start with `--state` pointing there. Do not copy only the
SQLite main file while its WAL is live. Exported ZIP bundles preserve individual
editions but do not replace a workspace backup. Build history is retained; the UI
shows the most recent 50 jobs across projects and up to eight per selected project.
No automatic destructive cleanup runs.

The server starts its worker subprocess and stops it on shutdown. Queued jobs
survive restarts. Jobs left running by a crashed worker become `interrupted` with
an actionable error when a new worker obtains the lock. Start a new build to retry;
existing build directories are never reused. A project edit cannot change a queued
build's configuration snapshot.

## Build integrity and limits

Selected unresolved lexical mappings block compilation. Exact cross-reference
matches do not independently establish a word's sense in context. Changes to gloss
wording are marked editorial; the source record and reason remain in the report.
An edited reference help gets a new label, preserving unedited repeated markers.
Source lookup is at the numeric lexical component level; prefix morphology and
slash boundaries are preserved but not turned into a full morpheme-interlinear.

Frequency is over the selected entire OSHB book, counts qere rather than ketiv
when both are present, and preserves extended lexical IDs. Changing a policy or
an earlier chapter decision can renumber later helps. Changing page size or passage
endpoints within a chapter does not independently renumber unchanged helps.

Pagination measures candidate text and unique notes together with XeLaTeX. It
splits continuous verses at word boundaries to fill available space, with their
helps assigned to the actual words on each page. Maqaf chains, adjacent ketiv/qere
pairs stay intact. A continuous chapter opening can continue onto another page
after two actual text lines beside its box. Verse-per-line mode keeps whole verses
and two-verse openings intact. An oversized indivisible
block fails rather than dropping text, shrinking type silently, or separating
notes from their words. Shorten reviewed notes, lower type size within validation
limits, or increase page size. No general-purpose arbitrary-TeX upload is accepted.
The compiler disables shell escape, restricts TeX file access, checks glyphs and
overflow, and kills the compilation process group on cancellation or a 90-second
**per TeX invocation** deadline. Full books can take several minutes across many
measurement invocations. The browser remains responsive to status and cancellation.

The PDF includes one source-credit page. Reference layout parameters are visual
approximations because the scan's physical size, exact font, and lexical edition
are unknown. All K/Q markers explicitly identify OSHB readings; unexplained marks
in the scan have not been invented. Greek NT/LXX support and its edition,
partial-witness, lexical, and license limits are documented in
[Greek sources](greek-sources.md). Detailed Aramaic stem glossing remains outside
this release.

## Troubleshooting

- **Missing source:** import the book in Sources or use `sources import --book CODE`.
- **Checksum mismatch:** move the corrupt raw artifact aside, then re-import. Never
  edit the pinned artifact to make an editorial correction.
- **Missing engine/font/package:** run `doctor`, then setup or select an installed font.
- **Unresolved help:** filter Needs review, select a supported source candidate, or
  uncheck it and save the explicit omission. A gloss alone cannot invent a source.
- **Revision conflict:** another tab saved a change; reload before applying your edit.
- **Interrupted/failed job:** inspect its message and the workspace build directory;
  correct the input and start a fresh build. Failed jobs do not expose export links.
- **Blank embedded preview:** the browser must have a native PDF viewer enabled.
  The PDF download works independently. Browser acceptance uses full Chromium;
  Playwright's minimal headless shell cannot display embedded PDFs.
- **Browser test cannot launch:** install Chromium's OS libraries with Playwright's
  `install --with-deps chromium` on a development/CI machine. These are test-only
  requirements; a user opens the app with their installed browser.

The server listens only on loopback through the CLI. It has local Host checks and
a per-server CSRF token, but no remote-user authentication or multi-user isolation.
Do not expose it through a public reverse proxy as a hosted service.
