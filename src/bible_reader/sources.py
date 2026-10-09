"""Pinned OSHB and STEP imports. No acquisition takes place during rendering."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from urllib.request import Request, urlopen

from defusedxml.ElementTree import fromstring

from .models import Entry, ReaderError, Token, Verse, canonical_json


def catalog() -> dict:
    return json.loads(files("bible_reader").joinpath("resources/sources.json").read_text())


def read_verified(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ReaderError(
            f"Source checksum mismatch: {path.name}. Move the corrupt artifact aside, then re-import."
        )
    return data


def acquire(asset: dict, destination: Path, cancelled=lambda: False) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        read_verified(destination, asset["sha256"])
        return destination
    request = Request(asset["url"], headers={"User-Agent": "OriginalLanguageReader/0.2"})
    temporary = None
    try:
        with (
            urlopen(request, timeout=45) as response,
            tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream,
        ):
            temporary = Path(stream.name)
            count = 0
            while chunk := response.read(65536):
                if cancelled():
                    raise ReaderError("Source import cancelled")
                count += len(chunk)
                if count > 30_000_000:
                    raise ReaderError("Source artifact exceeds the 30 MB import limit")
                stream.write(chunk)
        read_verified(temporary, asset["sha256"])
        temporary.replace(destination)
    except (OSError, ValueError) as error:
        raise ReaderError(f"Could not download {destination.name}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def local_tag(node) -> str:
    return node.tag.rsplit("}", 1)[-1]


def parse_oshb(data: bytes, book: str) -> list[Verse]:
    """Retain the source word surface, separators, IDs, and qere/ketiv order."""
    try:
        root = fromstring(data)
    except Exception as error:
        raise ReaderError(f"Invalid OSHB XML: {error}") from error
    verses = []
    seen_ids: set[str] = set()
    seen_refs: set[str] = set()
    for node in root.iter():
        if local_tag(node) != "verse" or "osisID" not in node.attrib:
            continue
        reference = node.attrib["osisID"]
        parts = reference.split(".")
        if len(parts) != 3 or parts[0] != book or reference in seen_refs:
            raise ReaderError(f"Unexpected or duplicate verse identity: {reference}")
        seen_refs.add(reference)
        tokens: list[Token] = []
        annotations: list[str] = []

        def append(element, reading="normal", reference=reference, tokens=tokens):
            tag = local_tag(element)
            raw = "".join(element.itertext())
            identity = element.get("id") or f"{reference}:unit:{len(tokens)}"
            if identity in seen_ids:
                raise ReaderError(f"Duplicate source identity: {identity}")
            seen_ids.add(identity)
            morph = element.get("morph", "")
            tokens.append(
                Token(
                    identity,
                    raw,
                    element.get("lemma", ""),
                    morph,
                    "word" if tag == "w" else element.get("type", "segment"),
                    "ketiv" if element.get("type") == "x-ketiv" else reading,
                    "arc" if morph.startswith("A") else "hbo",
                    ET.tostring(element, encoding="unicode").strip(),
                )
            )

        for element in node:
            tag = local_tag(element)
            if tag in {"w", "seg"}:
                append(element)
            elif tag == "note":
                annotations.append(ET.tostring(element, encoding="unicode").strip())
                if element.get("type") == "variant":
                    for reading in element:
                        if local_tag(reading) == "rdg":
                            if reading.get("type") != "x-qere":
                                raise ReaderError(f"Unsupported reading type in {reference}")
                            for word in reading:
                                if local_tag(word) not in {"w", "seg"}:
                                    raise ReaderError(f"Unsupported qere content in {reference}")
                                append(word, "qere")
            else:
                raise ReaderError(f"Unsupported OSHB element {tag} in {reference}")
        if not tokens:
            raise ReaderError(f"Empty verse: {reference}")
        verses.append(Verse(book, int(parts[1]), int(parts[2]), tuple(tokens), tuple(annotations)))
    if not verses or [(v.chapter, v.verse) for v in verses] != sorted((v.chapter, v.verse) for v in verses):
        raise ReaderError("Source verses are empty or out of order")
    return verses


def parse_tbesh(data: bytes) -> tuple[dict[str, Entry], dict[str, list[str]]]:
    """Only STEP-authored Gloss and metadata; never import the restricted Meaning column."""
    entries: dict[str, Entry] = {}
    mapping: dict[str, list[str]] = defaultdict(list)
    for number, line in enumerate(data.decode("utf-8-sig").splitlines(), 1):
        if not re.match(r"^H\d{4}", line):
            continue
        columns = line.split("\t")
        if len(columns) < 8:
            raise ReaderError(f"Malformed TBESH row {number}")
        extended, disambiguated, _unified, headword, transliteration, morph, gloss = columns[:7]
        match = re.match(r"H\d{4}[A-Za-z]*", disambiguated)
        if not match:
            raise ReaderError(f"Missing TBESH disambiguated ID on row {number}")
        key = "step:" + match.group()
        entry = Entry(key, headword.strip(), transliteration.strip(), morph.strip(), gloss.strip(), "")
        if key in entries and entries[key] != entry:
            raise ReaderError(f"Conflicting TBESH records: {key}")
        entries[key] = entry
        if key not in mapping[extended]:
            mapping[extended].append(key)
    if not entries:
        raise ReaderError("No TBESH entries found")
    return entries, dict(mapping)


def lemma_keys(lemma: str) -> list[str]:
    return [f"H{int(number):04d}{suffix}" for number, suffix in re.findall(r"(\d+)(?:\s+([a-z]))?", lemma)]


def load_book(state: Path, book: str) -> list[Verse]:
    info = catalog()
    if book not in info["books"]:
        raise ReaderError(f"Unsupported book: {book}")
    path = state / "raw" / f"{book}.xml"
    if not path.exists():
        raise ReaderError(f"Import {book} from Sources before building a reader.")
    return parse_oshb(read_verified(path, info["books"][book]["sha256"]), book)


def load_lexicon(state: Path):
    path = state / "raw" / "TBESH.txt"
    if not path.exists():
        raise ReaderError("Import the STEP gloss lexicon from Sources first.")
    return parse_tbesh(read_verified(path, catalog()["lexicon"]["sha256"]))


def import_sources(state: Path, book: str, progress=lambda _: None, cancelled=lambda: False):
    info = catalog()
    if book not in info["books"]:
        raise ReaderError(f"Unsupported book: {book}")
    for name, asset in [
        (f"{book}.xml", info["books"][book]),
        ("TBESH.txt", info["lexicon"]),
        ("OSHB-LICENSE.md", info["notices"]["oshb"]),
        ("STEP-README.md", info["notices"]["step"]),
    ]:
        progress(f"Importing {name}")
        acquire(asset, state / "raw" / name, cancelled)
    progress("Validating source records")
    verses = load_book(state, book)
    entries, mapping = load_lexicon(state)
    canonical = state / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    (canonical / f"{book}.jsonl").write_text("\n".join(canonical_json(v.json()) for v in verses) + "\n")
    (canonical / "lexicon.json").write_text(
        canonical_json(
            {
                "entries": {key: asdict(value) for key, value in entries.items()},
                "mapping": mapping,
                "imported_columns": ["eStrong", "dStrong", "Hebrew", "Transliteration", "Morph", "Gloss"],
                "excluded_columns": ["Meaning"],
            }
        )
    )
    return {
        "book": book,
        "verses": len(verses),
        "lexicon_entries": len(entries),
        "revision": info["oshb_revision"],
    }
