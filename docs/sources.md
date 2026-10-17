# Pinned sources and editorial provenance

The Hebrew release imports two explicit source layers. Greek NT and LXX support,
their separate editions, terms, lexical crosswalks, and complete source-audit counts
are documented in [greek-sources.md](greek-sources.md). The Hebrew artifact catalog
with 39 book hashes, download URLs, notices, and transformations is
[`sources.json`](../src/bible_reader/resources/sources.json).

| Layer | Revision | Terms / use |
| --- | --- | --- |
| [Open Scriptures Hebrew Bible](https://github.com/openscriptures/morphhb/tree/3d15126fb1ef74867fc1434be1942e837932691f) | `3d15126fb1ef74867fc1434be1942e837932691f` | WLC text public domain; lemma/morphology annotations CC BY 4.0 |
| [STEPBible TBESH](https://github.com/STEPBible/STEPBible-Data/tree/b99716b0cddb648ddb95cc786a197180f2f97d48) | `b99716b0cddb648ddb95cc786a197180f2f97d48` | STEP metadata and short Gloss fields, CC BY 4.0 |

Verified 2026-10-02. Raw artifacts are immutable under the chosen state's `raw/`
directory. Each is checked against its pinned SHA-256 before parsing. Download
installation is atomic and normally bounded to 30 MB per source artifact. The
pinned 36 MB Rahlfs main artifact uses its cataloged size, with an absolute 50 MB
ceiling. No live fetch
occurs during render/build. License notices are imported alongside source files.

## The TBESH column distinction

The source header distinguishes the Tyndale-authored **Gloss** column from the
long **Meaning** column based on Online Bible's abridged BDB material, with separate
permission wording. The adapter imports eStrong/dStrong cross-references, Hebrew,
transliteration, morphology, and **Gloss only**. It does not treat the entire file
as uniformly redistributable dictionary definitions. `Meaning` never enters
canonical entries, candidate records, reader JSON, PDF, or bundles.

This makes the shipped notes shorter than the reference scan. Users may supply
traceable editorial glosses in lexical review; the app records them separately
from imported wording. It does not generate a contextual sense or invent missing
source entries. Source-entry resolution and scholarly contextual review are
separate checks.

## Preservation and transformations

The OSHB adapter keeps source IDs, raw word text, slash segmentation, morphology,
lemma codes, punctuation, annotations, and both written/read forms. It preserves
logical Unicode without NFC normalization. Display transformations are explicit:
remove slash separators; optionally hide only the cantillation range; choose both,
qere, or ketiv. The resolved build settings and source records retain these choices.
OSHB versification is authoritative; no silent mapping to another edition occurs.

Extended ID crosswalks preserve candidate sets. A base-ID fallback is a suggestion
requiring review even if it returns only one candidate. Known-word/frequency rules
have explicit reasons. Frequency counts the selected whole source book, not the
requested passage, and avoids counting both ketiv and qere as two occurrences.

Name omission follows [OSHB noun type `Np`](https://hb.openscriptures.org/parsing/HebrewMorphologyCodes.html)
and the pinned TBESH header's `N:` name classification (people, locations,
gentilics, and titles including divine names). A STEP analysis is treated as a
name only when every supplied morphology alternative is a name. A selected name
entry, or an entirely name-classified candidate set, is omitted; mixed candidates
retain their explicit alignment status. Raw text and lexical records are retained.

Only numeric lexical components become help anchors. Prefix/suffix analysis remains
in the source morphology and segmentation; this is not a full interlinear parser.
Hebrew and Aramaic language tags are preserved. The stem abbreviation formatter
currently covers the common Hebrew stems; original morphology remains available
when no display abbreviation is provided.

## Fixtures, attribution, and upgrades

`tests/fixtures/` contains genuine Proverbs 1–2 OSHB excerpts and the corresponding
STEP metadata/Gloss rows. `provenance.json` identifies upstream revisions, artifact
hashes, excerpt hashes, and extraction transformations. The Meaning column is
empty in these tracked fixtures. Test-only artificial cases are explicitly marked
synthetic in the tests and are never presented as biblical readings.

The reference anchor map records observed marker topology, not copied definitions.
The local scan is excluded from Git, wheels, and export bundles. Ezra SIL's separate
font notice is in the packaged resources and copied into applicable bundles.
See [THIRD_PARTY.md](../THIRD_PARTY.md).

For a source upgrade, update the immutable revisions and actual hashes together,
retain new notices, refresh attributable fixtures, review changed source IDs and
crosswalks, and rerun source/PDF regressions. Never edit downloaded source records
to make an editorial correction. Old edition bundles preserve their original lock.
