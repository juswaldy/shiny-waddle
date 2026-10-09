---
name: import-bible-source
description: Import or update biblical text, morphology, or lexicon artifacts in this reader repository with pinned provenance and source-preserving adapters.
---

# Import a Bible source

Read `docs/sources.md` and the canonical model in `docs/architecture.md` at the
repository root. Use the user's chosen edition; source candidates are not a mandate.

1. Inspect the actual upstream format, immutable revision, file notices, and
   terms. Record artifact hashes, edition, language, versification, layer-specific
   licenses, and required attribution in a source manifest. Do not use a moving
   branch name as the reproducibility pin.
2. Preserve the downloaded artifact under `data/raw/`. Build an adapter that keeps
   raw display text, original word IDs, punctuation, segmentation, lemma codes,
   morphology codes, and textual alternatives. Any lookup normalization is a
   separate derived field; do not normalize the display surface automatically.
3. Keep a small attributable fixture that exercises the format's real hazards.
   For Hebrew this may include attached prefixes, maqaf, cantillation, and
   ketiv/qere. Include Aramaic language tags when present. Avoid invented records
   presented as upstream excerpts.
4. Verify counts, reference order, stable IDs, Unicode fidelity, and unparsed
   records. Report unsupported structures instead of flattening or silently
   dropping them. Document any deliberate verse mapping or transformation.

Return the manifest, adapter, fixture provenance, verification results, and any
unresolved interpretation. Keep scholarly corrections separate from raw imports.
Fetching may need network permission; rendering should use local pinned inputs.
No source import requires contacting its authors or changing upstream repositories.
