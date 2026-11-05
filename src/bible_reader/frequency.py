"""Source-scoped lexical frequencies over complete, verified local corpora."""

from collections import Counter
from functools import lru_cache
from pathlib import Path

from . import sources
from .models import ReaderError, Verse

CORPUS_LABELS = {"oshb": "Hebrew OT", "sblgnt": "Greek NT", "rahlfs": "Greek OT"}


def corpus_for_book(book: str) -> dict:
    info = sources.catalog()
    selected = info["books"][book]
    source = selected.get("source", "oshb")
    books = {
        code: item
        for code, item in info["books"].items()
        if item.get("source", "oshb") == source and (source != "rahlfs" or item["witness"] == "main")
    }
    # An alternate witness replaces its main book; never sum parallel witnesses.
    if source == "rahlfs" and selected["witness"] != "main":
        books = {k: v for k, v in books.items() if v["source_book"] != selected["source_book"]}
        books[book] = selected
    return {
        "id": source,
        "label": CORPUS_LABELS[source],
        "revision": info["oshb_revision"] if source == "oshb" else selected["revision"],
        "books": list(books),
        "witness_policy": "main books, with selected alternate replacing its main witness"
        if source == "rahlfs"
        else "all source books",
    }


def lemma_frequencies(verses: list[Verse]) -> Counter:
    # Extended source lexical keys and language remain distinct. Count every
    # lexical component, using qere rather than counting both written/read forms.
    return Counter(
        (token.language, key)
        for verse in verses
        for token in verse.tokens
        if token.kind == "word" and token.reading != "ketiv"
        for key in sources.token_keys(token)
    )


@lru_cache(maxsize=256)
def _book_counts(state: Path, book: str, checksum: str) -> Counter:
    # The caller verifies the artifact even on a cache hit. Cache only compact
    # counts, scoped by state, source book/witness, and pinned artifact checksum.
    return lemma_frequencies(sources.load_book(state, book))


def corpus_frequencies(state: Path, book: str, book_counts: Counter) -> tuple[Counter, dict]:
    corpus = corpus_for_book(book)
    artifacts = {}
    missing = []
    for code in corpus["books"]:
        path, asset = sources.book_artifact(state, code)
        artifacts[code] = (path, asset)
        if not path.is_file():
            missing.append(code)
    if missing:
        raise ReaderError(
            f"Whole-corpus frequency requires all {corpus['label']} books; missing: {', '.join(missing)}. "
            f"Run bible-reader sources import --corpus {corpus['id']}, or choose In this book."
        )
    counts = Counter()
    verified = set()
    for code, (path, asset) in artifacts.items():
        artifact = (path, asset["sha256"])
        if artifact not in verified:
            sources.read_verified(path, asset["sha256"])
            verified.add(artifact)
        counts.update(book_counts if code == book else _book_counts(state, code, asset["sha256"]))
    return counts, {
        **corpus,
        "artifacts": {code: asset["sha256"] for code, (_, asset) in artifacts.items()},
        "counting": "source lexical components by language and extended lexical key; ketiv excluded",
    }
