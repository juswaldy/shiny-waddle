# Greek sources and reader support

The Greek reader uses **SBLGNT** for the NT and **Rahlfs 1935** for the LXX.
They are separate editions, not replacements for Hebrew books. `Prov` remains
OSHB; `LXXProv` selects Greek Proverbs. The catalog includes 27 NT books and
60 LXX book/witness records, including the deuterocanonical books and Odes.

All revisions, download URLs, SHA-256 hashes, counts, default passages, source
versifications, and terms are pinned in
[`greek-sources.json`](../src/bible_reader/resources/greek-sources.json).

| Layer | Immutable revision | Terms |
| --- | --- | --- |
| [MorphGNT SBLGNT](https://github.com/morphgnt/sblgnt/tree/aaed91e57c8e4a8dc9a2383e129ca5e75fe6393d) | `aaed91e57c8e4a8dc9a2383e129ca5e75fe6393d` | SBL text CC BY 4.0 under the [official text license](https://sblgnt.com/license/); MorphGNT morphology and lemmas CC BY-SA 3.0 |
| [Wong Rahlfs 1935](https://github.com/eliranwong/LXX-Rahlfs-1935/tree/a1b5ff1c739f93cdd18dbab4c9e3fc6b1043141c) | `a1b5ff1c739f93cdd18dbab4c9e3fc6b1043141c` | CC BY-NC-SA 4.0, with upstream CCAT user-declaration requirements |
| [STEP TBESG](https://github.com/STEPBible/STEPBible-Data/tree/94802ced31e63882ab42a86d79eb0017df4545e3) | `94802ced31e63882ab42a86d79eb0017df4545e3` | CC BY 4.0; metadata and short Gloss only |
| [Open Scriptures GreekResources](https://github.com/openscriptures/GreekResources/tree/dd5a2fd530ab3c6b748c174cec38966c356d8111) | `dd5a2fd530ab3c6b748c174cec38966c356d8111` | CC BY 4.0; published lexical crosswalk only |

Before downloading Rahlfs, satisfy the access requirements in its pinned
upstream README. The code's MIT license does not relicense imported material.
The Sources panel displays those terms. Source credits, revisions, notices,
transformations, and font licenses travel with Greek export bundles.

## Commands and book identities

```sh
.venv/bin/bible-reader sources import --book John
.venv/bin/bible-reader sources import --corpus sblgnt
# After satisfying the Rahlfs access requirements:
.venv/bin/bible-reader sources import --book LXXGen
.venv/bin/bible-reader sources import --corpus rahlfs
.venv/bin/bible-reader init --book John --project build/john.json
.venv/bin/bible-reader inspect --project examples/john.project.json --report build/john-review.json
.venv/bin/bible-reader build --project examples/john.project.json --output build/john
.venv/bin/bible-reader inspect --project examples/lxx.project.json --report build/lxx-review.json
```

`sources list` reports all supported book codes and Greek edition metadata.
NT codes include `Matt`, `John`, `1Cor`, `Phil`, `Phlm`, `1Pet`, and `Rev`.
LXX codes use `LXX` followed by the artifact's abbreviation, such as `LXXGen`,
`LXXPs`, `LXXQoh`, `LXX1Esdr`, `LXXSir`, and `LXXOd`.

Witnesses stay separate: `LXXJoshB` / `LXXJoshA`, `LXXJudgB` / `LXXJudgA`,
`LXXTobBA` / `LXXTobS`, and `LXXDanOG` / `LXXDanTh` (likewise Susanna and Bel).
**Joshua A is partial:** the upstream alternate artifact supplies only 95 verse
rows, beginning at 15:21. Missing rows are not filled from Joshua B. Its browser
label, source metadata, default passage, and build warnings expose this limit.

## Source preservation and lexical joins

The MorphGNT adapter retains all seven original columns in `source_record`,
including punctuation-bearing text, unpunctuated word, normalized word, lemma,
part of speech, and parsing code. Display uses the original punctuation-bearing
column. Derived token IDs use source BCV plus the one-based verse word position;
the upstream format does not supply independent word IDs.

Rahlfs uses Wong's `LXX_final_main.csv` and `LXX_final_alternate.csv` MyBible
artifacts. These are tab-separated despite their suffix. Each original verse row
and each word's markup are retained. IDs include artifact witness, original book
number, chapter, verse, and unit position. The first `S` field is a Wong LXX lexeme
ID; subsequent Strong's links and NT-index metadata retain their separate roles.
Morphology with embedded spaces is preserved. `i`/`br` markup remains inspectable;
italic subverse markers are displayed literally, with no inferred expansion.

The **artifact's numeric MyBible versification** is authoritative for these
imports. No Hebrew mapping, reconstruction of original CATSS subverse IDs, or
witness merging occurs. Chapter/verse zero is addressable for LXX source headings
(for example `LXXOd` 1:0). The Daniel artifacts contain nonmonotonic verse
references; file and word order are preserved and the reader reports a warning.
Unknown markup, malformed rows, conflicting IDs, and duplicate references fail.

NT joins follow the published MorphGNT lemma → GreekResources word-list key →
Strong's → TBESG entry crosswalk. There is no spelling-based fallback. The
GreekResources header calls its initial listing unfinished and mentions 87
mismatched lemmas; a published join is not a scholarly contextual sense review.
Unsupported word-list Strong extensions and absent links remain unmatched.
LXX joins use the explicit source Strong's links; a Wong lexeme ID alone does not
authorize an invented mapping. `step-greek:` IDs remain distinct from Hebrew
`step:` IDs and are interpreted within the pinned revision/source lock.

Every word has an inspectable lexical row, including words without a usable link.
Multiple entries stay ambiguous under the default reviewed policy. Missing or
ambiguous selected helps block a build until the reader makes an explicit
supported choice or exclusion. The LXX example intentionally exposes such review
work; it is not a pre-reviewed publication edition. TBESG Meaning and word-list
definitions are excluded from canonical entries and export bundles.

Frequency counts the selected source book/witness. Proper-name omission uses
source lexical classifications, not capital letters. Bulk spelling matches retain
Greek accents and case; Hebrew consonant policies do not strip Greek accents.
Saved help files bind text, lexicon, and NT crosswalk hashes as well as revisions.

## Rendering and verification

Greek scripture, headwords, and browser context run left to right using bundled
**Gentium Plus** under the SIL Open Font License. Both continuous and separate
verse starts use measured page construction with chapter-grouped, page-local
helps. Mixed English markers remain explicitly delimited. Greek accents and
source Unicode are preserved under every Hebrew accent/K/Q setting. Greek runs
use explicit font/script/direction macros; atomic scripture words do not require
Greek hyphenation patterns in a minimal TeX installation.

The optional four-column lexicon sorts Greek with a separate case/mark-insensitive
key; final sigma collates with sigma. Display headwords retain source Unicode.
Builds retain their TeX, source lock, review rows, page plan, embedded fonts, and
offline rebuild bundle. Gentium Plus and Ezra's auxiliary font are included with
their notices; a prior Hebrew typeface selection cannot require an uninstalled
SBL Hebrew font for a Greek edition.

Run `make check`, `make demo`, and `make pdf` for regressions. Audit the entire
locally imported Greek corpus without network access with:

```sh
.venv/bin/python scripts/audit_greek_sources.py
```

Only installed book artifacts are audited. NT-only, Rahlfs-only, and mixed
installations are supported; each corpus's lexical mapping is loaded only when
an installed book needs it. Missing book artifacts are skipped. Corrupt installed
books or required lexical inputs still fail checksum verification.

The 2026-10-16 complete pinned-source audit found:

| Corpus | Book/witness records | Verse rows | Words | Single-entry links | Ambiguous links | Unmatched links |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SBLGNT | 27 | 7,927 | 137,554 | 124,511 | 11,896 | 1,147 |
| Rahlfs artifacts | 60 | 30,336 | 623,693 | 541,286 | 40,482 | 41,925 |

These are source-entry link counts before help/name/frequency exclusions, not
contextual sense accuracy. The LXX totals include separate alternate witnesses
and the partial Joshua A record. All source hashes, counts, IDs, and language tags
passed. Gentium Plus covers all 273 distinct nonspace characters observed across
the pinned Greek text/analysis artifacts and TBESG headwords. Real John 1:1–2:12
and Genesis 1:1–2:12 proofs compiled in both layouts;
their proof configurations explicitly record exclusions for unresolved joins.
PDF tests inspect glyph positions around the chapter inset, embedded fonts,
marker destinations on the same page, appendix coverage, and packaged notices.
