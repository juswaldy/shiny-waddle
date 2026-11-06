"""Source-scoped lexical frequencies over complete, verified local corpora."""

from collections import Counter, OrderedDict
from pathlib import Path
from threading import Lock

from . import sources
from .greek import iter_rahlfs
from .models import ReaderError, Verse

CORPUS_LABELS = {"oshb": "Hebrew OT", "sblgnt": "Greek NT", "rahlfs": "Greek OT"}
_COUNTS_CACHE: OrderedDict[tuple, dict[str, Counter]] = OrderedDict()
_COUNTS_CACHE_LOCK = Lock()


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


def _artifact_counts(
    path: Path, checksum: str, source: str, witness: str | None, books: tuple[tuple[str, int | None], ...]
) -> dict[str, Counter]:
    # Verify even on cache hits; keep only compact counters, never source bytes
    # or the parsed corpus. Parser/book/witness identities also scope the cache.
    data = sources.read_verified(path, checksum)
    key = (path.resolve(), checksum, source, witness, books)
    with _COUNTS_CACHE_LOCK:
        if key in _COUNTS_CACHE:
            _COUNTS_CACHE.move_to_end(key)
            return _COUNTS_CACHE[key]
    counts: dict[str, Counter] = {}
    if source == "rahlfs":
        for verse in iter_rahlfs(data, {number: code for code, number in books}, witness):
            counts.setdefault(verse.book, Counter()).update(lemma_frequencies([verse]))
    else:
        for code, number in books:
            verses = (
                sources.parse_morphgnt(data, code, number)
                if source == "sblgnt"
                else sources.parse_oshb(data, code)
            )
            counts[code] = lemma_frequencies(verses)
    with _COUNTS_CACHE_LOCK:
        _COUNTS_CACHE[key] = counts
        _COUNTS_CACHE.move_to_end(key)
        if len(_COUNTS_CACHE) > 256:
            _COUNTS_CACHE.popitem(last=False)
    return counts


def corpus_frequencies(state: Path, book: str, book_counts: Counter) -> tuple[Counter, dict]:
    corpus = corpus_for_book(book)
    info = sources.catalog()
    artifacts = {}
    groups = {}
    missing = []
    for code in corpus["books"]:
        path, asset = sources.book_artifact(state, code)
        artifacts[code] = (path, asset)
        selected = info["books"][code]
        artifact = (path, asset["sha256"], selected.get("source", "oshb"), selected.get("witness"))
        groups.setdefault(artifact, []).append(code)
        if not path.is_file():
            missing.append(code)
    if missing:
        raise ReaderError(
            f"Whole-corpus frequency requires all {corpus['label']} books; missing: {', '.join(missing)}. "
            f"Run bible-reader sources import --corpus {corpus['id']}, or choose In this book."
        )
    counts = Counter()
    for (path, checksum, source, witness), codes in groups.items():
        if codes == [book]:
            sources.read_verified(path, checksum)
            counts.update(book_counts)
            continue
        if source == "rahlfs":
            # Cache all books in this artifact, so selecting another book or an
            # alternate witness can reuse the same main-artifact counters.
            books = tuple(
                (code, item["source_book"])
                for code, item in info["books"].items()
                if item.get("source") == source
                and item["witness"] == witness
                and item["artifact"]["filename"] == path.name
                and item["artifact"]["sha256"] == checksum
            )
        else:
            books = tuple((code, info["books"][code].get("source_book")) for code in codes)
        per_book = _artifact_counts(path, checksum, source, witness, books)
        for code in codes:
            if code != book and code not in per_book:
                raise ReaderError(f"No Rahlfs records found for {code}")
            counts.update(book_counts if code == book else per_book[code])
    return counts, {
        **corpus,
        "artifacts": {code: asset["sha256"] for code, (_, asset) in artifacts.items()},
        "counting": "source lexical components by language and extended lexical key; ketiv excluded",
    }
