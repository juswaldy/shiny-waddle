---
name: align-reader-lexicon
description: Join this reader's source tokens or morphemes to lexicon entries and senses, resolve mapping gaps, or change lexical-help selection rules.
---

# Align lexical helps

Read the alignment model in `docs/architecture.md` and the relevant source
manifests. The starter renderer accepts already selected entry IDs; it is not an
alignment engine.

- Join through documented, source-qualified IDs and versioned crosswalks first.
  Treat Strong's variants, suffixes, homographs, and source-specific extensions
  explicitly. A Hebrew root is not automatically a lemma or sense.
- Distinguish orthographic words from morpheme segments; prefixes and suffixes can
  have separate analyses. Preserve original codes alongside parsed meanings.
- Keep all candidates when the source permits multiple analyses. Use `resolved`,
  `ambiguous`, or `unmatched` status with method/evidence; do not choose the first
  candidate merely to make rendering succeed. Spelling matches are suggestions.
- A short reader gloss needs a lexical source and, when selected, a sense
  reference. Keep editorial abbreviations and overrides traceable. If proposing
  new wording, label it as a proposal rather than sourced dictionary content.
- Apply known-word/frequency rules only after alignment. Name the frequency
  corpus and revision, decide how homographs and repeated occurrences count, and
  preserve the reason each help was included or omitted.

Check a representative matched item, a homograph or multi-candidate item, a
missing entry, and a segmented form if the source supports segments. Report
coverage over all relevant tokens/segments, including excluded and unresolved
items, so a successful join count cannot conceal lost data.

Produce an inspectable alignment/coverage report and selected reader notes.
Keep stable token/entry identities independent of printed note numbers. When
feeding the version-1 specimen renderer, `entry_id: null` means intentional note
omission; it must not be used to conceal a failed lexical join.
