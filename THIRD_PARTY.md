# Third-party materials

The repository MIT license applies to application code, not all input materials.

| Material | Included / fetched | Terms and provenance |
| --- | --- | --- |
| WLC Hebrew text | Pinned downloads; Proverbs 1–2 test excerpt | Public domain, via Open Scriptures Hebrew Bible |
| OSHB lemma/morphology annotations | Pinned downloads and test excerpt | CC BY 4.0; exact notice in `tests/fixtures/OSHB-LICENSE.md` |
| STEP TBESH metadata and short Gloss fields | Pinned download and selected test entries | CC BY 4.0; Tyndale House Cambridge / STEP Bible; `tests/fixtures/STEP-README.md` |
| TBESH long Meaning field | Raw upstream download only, ignored by Git | Excluded from parsing, canonical exports, reader documents, and bundles; its separate header terms are not treated as blanket CC BY permission |
| SBLGNT text / MorphGNT analysis | Pinned 27-book downloads; John/Mark excerpts | SBL text CC BY 4.0 (https://sblgnt.com/license/); MorphGNT morphology/lemmatization CC BY-SA 3.0; Tauber, ed., v6.12, DOI:10.5281/zenodo.376200 |
| Rahlfs 1935 / Wong MyBible main and alternate artifacts | Pinned downloads; selected fixture rows | Copyright 2017 Eliran Wong, CC BY-NC-SA 4.0; derived from CATSS/CCAT/TLG with Open Scriptures and James Tauber contributions. Upstream CCAT user-declaration requirements also apply; see `tests/fixtures/greek/RAHLFS-README.md` |
| STEP TBESG metadata and short Gloss | Pinned Greek lexicon; selected fixture rows | CC BY 4.0; STEP Bible / Tyndale House Cambridge; Meaning excluded |
| Open Scriptures GreekResources crosswalk | Pinned lookup and word-list artifacts; selected metadata fixture | CC BY 4.0, Open Scriptures Septuagint Project; definitions excluded from canonical imports |
| Ezra SIL 2.51 | Unmodified `src/bible_reader/resources/SILEOT.ttf` | SIL Open Font License 1.1; shaping-code MIT notice also retained in `Ezra-LICENSE.txt` |
| Gentium Plus | Unmodified `src/bible_reader/resources/GentiumPlus-Regular.ttf` | SIL Open Font License 1.1; accompanying `GentiumPlus-LICENSE.txt`; exact upstream revision and hash in the Greek catalog |
| SBL Hebrew | Optional user-installed font | Not redistributed by the application |
| Latin Modern / TeX packages | User or project-local TeX installation | Respective upstream font and TeX package licenses; the TeX distribution is not part of the Python wheel |
| `mishle002.jpg` | Local visual reference only | Provenance/redistribution terms not established; excluded from Git, packages, and exports |

Source revisions, URLs, and SHA-256 hashes are in
`src/bible_reader/resources/sources.json`. Fixture excerpts and transformations are
identified in `tests/fixtures/provenance.json`. Generated readers print source
credits; export bundles also include notices and the license for the bundled font.
Greek revisions, per-book counts, witnesses, artifact hashes, and layer-specific
terms are in `src/bible_reader/resources/greek-sources.json`; fixture provenance
and unmodified source notices are in `tests/fixtures/greek/`. Those fixtures and
derived Greek data retain their respective source licenses, including share-alike
and noncommercial conditions; the code's MIT license does not replace them.

Original work of the Open Scriptures Hebrew Bible available at
https://github.com/openscriptures/morphhb.

STEP Bible: https://www.STEPBible.org; based on work at Tyndale House Cambridge.
