# Third-party materials

The repository MIT license applies to application code, not all input materials.

| Material | Included / fetched | Terms and provenance |
| --- | --- | --- |
| WLC Hebrew text | Pinned downloads; Proverbs 1–2 test excerpt | Public domain, via Open Scriptures Hebrew Bible |
| OSHB lemma/morphology annotations | Pinned downloads and test excerpt | CC BY 4.0; exact notice in `tests/fixtures/OSHB-LICENSE.md` |
| STEP TBESH metadata and short Gloss fields | Pinned download and selected test entries | CC BY 4.0; Tyndale House Cambridge / STEP Bible; `tests/fixtures/STEP-README.md` |
| TBESH long Meaning field | Raw upstream download only, ignored by Git | Excluded from parsing, canonical exports, reader documents, and bundles; its separate header terms are not treated as blanket CC BY permission |
| Ezra SIL 2.51 | Unmodified `src/bible_reader/resources/SILEOT.ttf` | SIL Open Font License 1.1; shaping-code MIT notice also retained in `Ezra-LICENSE.txt` |
| SBL Hebrew | Optional user-installed font | Not redistributed by the application |
| Latin Modern / TeX packages | User or project-local TeX installation | Respective upstream font and TeX package licenses; the TeX distribution is not part of the Python wheel |
| `mishle002.jpg` | Local visual reference only | Provenance/redistribution terms not established; excluded from Git, packages, and exports |

Source revisions, URLs, and SHA-256 hashes are in
`src/bible_reader/resources/sources.json`. Fixture excerpts and transformations are
identified in `tests/fixtures/provenance.json`. Generated readers print source
credits; export bundles also include notices and the license for the bundled font.

Original work of the Open Scriptures Hebrew Bible available at
https://github.com/openscriptures/morphhb.

STEP Bible: https://www.STEPBible.org; based on work at Tyndale House Cambridge.
