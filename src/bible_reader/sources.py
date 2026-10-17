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

from .greek import morphgnt_crosswalk, parse_morphgnt, parse_rahlfs, parse_tbesg
from .models import Entry, ReaderError, Token, Verse, canonical_json


def catalog() -> dict:
    info = json.loads(files("bible_reader").joinpath("resources/sources.json").read_text())
    greek = json.loads(files("bible_reader").joinpath("resources/greek-sources.json").read_text())
    info["greek"] = greek
    info["books"].update(greek["books"])
    return info


def book_artifact(state: Path, book: str) -> tuple[Path, dict]:
    info = catalog()
    if book not in info["books"]:
        raise ReaderError(f"Unsupported book: {book}")
    selected = info["books"][book]
    if selected.get("language") == "grc":
        asset = selected["artifact"]
        return state / "raw/greek" / asset["filename"], asset
    return state / "raw" / f"{book}.xml", selected


def token_keys(token: Token) -> list[str]:
    if token.kind != "word":
        return []
    return list(token.lexical_keys) if token.language == "grc" else lemma_keys(token.lemma)


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
                limit = min(50_000_000, max(30_000_000, asset.get("bytes", 0)))
                if count > limit:
                    raise ReaderError(f"Source artifact exceeds the {limit} byte import limit")
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
    path, asset = book_artifact(state, book)
    if not path.exists():
        raise ReaderError(f"Import {book} from Sources before building a reader.")
    selected = info["books"][book]
    data = read_verified(path, asset["sha256"])
    if selected.get("source") == "sblgnt":
        return parse_morphgnt(data, book, selected["source_book"])
    if selected.get("source") == "rahlfs":
        return parse_rahlfs(data, book, selected["source_book"], selected["witness"])
    return parse_oshb(data, book)


def load_lexicon(state: Path, book="Prov"):
    info = catalog()
    if info["books"].get(book, {}).get("language") == "grc":
        greek = info["greek"]
        root = state / "raw/greek"
        assets = [greek["lexicon"]]
        if info["books"][book]["source"] == "sblgnt":
            assets += greek["crosswalk"]["assets"]
        if any(not (root / asset["filename"]).is_file() for asset in assets):
            raise ReaderError("Import the Greek lexicon and lexical crosswalk from Sources first.")
        records = [read_verified(root / asset["filename"], asset["sha256"]) for asset in assets]
        entries, mapping = parse_tbesg(records[0])
        if len(records) > 1:
            mapping.update(morphgnt_crosswalk(records[1], records[2], mapping))
        return entries, mapping
    path = state / "raw" / "TBESH.txt"
    if not path.exists():
        raise ReaderError("Import the STEP gloss lexicon from Sources first.")
    return parse_tbesh(read_verified(path, catalog()["lexicon"]["sha256"]))


def import_sources(state: Path, book: str, progress=lambda _: None, cancelled=lambda: False):
    info = catalog()
    if book not in info["books"]:
        raise ReaderError(f"Unsupported book: {book}")
    if info["books"][book].get("language") == "grc":
        return import_greek_sources(state, book, progress, cancelled)
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


def import_greek_sources(state: Path, book: str, progress, cancelled):
    info = catalog()
    greek, selected = info["greek"], info["books"][book]
    source = selected["source"]
    assets = [selected["artifact"], greek["lexicon"], greek["notices"][source]]
    if source == "sblgnt":
        assets += greek["crosswalk"]["assets"] + [
            greek["notices"]["crosswalk"],
            greek["notices"]["sblgnt-license"],
        ]
    for asset in assets:
        progress(f"Importing {asset['filename']}")
        acquire(asset, state / "raw/greek" / asset["filename"], cancelled)
    progress("Validating Greek source records")
    verses = load_book(state, book)
    words = sum(t.kind == "word" for v in verses for t in v.tokens)
    if (len(verses), words) != (selected["verse_count"], selected["word_count"]):
        raise ReaderError(f"Greek source count mismatch for {book}")
    entries, mapping = load_lexicon(state, book)
    canonical = state / "canonical/greek"
    canonical.mkdir(parents=True, exist_ok=True)
    (canonical / f"{book}.jsonl").write_text(
        "\n".join(canonical_json(v.json()) for v in verses) + "\n", encoding="utf-8"
    )
    (canonical / f"{source}-lexicon.json").write_text(
        canonical_json(
            {
                "entries": {key: asdict(value) for key, value in entries.items()},
                "mapping": mapping,
                "imported_columns": greek["lexicon"]["columns"],
                "excluded_columns": ["Meaning"],
            }
        ),
        encoding="utf-8",
    )
    keys = [key for v in verses for t in v.tokens for key in token_keys(t)]
    coverage = {"resolved": 0, "ambiguous": 0, "unmatched": 0}
    for key in keys:
        candidates = mapping.get(key, [])
        coverage["resolved" if len(candidates) == 1 else "ambiguous" if candidates else "unmatched"] += 1
    return {
        "book": book,
        "verses": len(verses),
        "words": words,
        "lexicon_entries": len(entries),
        "revision": selected["revision"],
        "coverage": coverage,
    }


def source_lock(book: str, cantillation: str, hebrew_transformation: str) -> dict:
    info = catalog()
    selected = info["books"][book]
    if selected.get("language") != "grc":
        return {
            "text": selected,
            "lexicon": info["lexicon"],
            "oshb_revision": info["oshb_revision"],
            "step_revision": info["step_revision"],
            "language": "hbo",
            "direction": "rtl",
            "attributions": info["attributions"],
            "transformations": info["transformations"] + [hebrew_transformation],
        }
    greek = info["greek"]
    return {
        "text": selected,
        "text_source": selected["source"],
        "text_revision": selected["revision"],
        "language": "grc",
        "direction": "ltr",
        "lexicon": greek["lexicon"],
        "crosswalk": greek["crosswalk"] if selected["source"] == "sblgnt" else None,
        "notices": {
            k: v
            for k, v in greek["notices"].items()
            if k == selected["source"]
            or (selected["source"] == "sblgnt" and k in {"crosswalk", "sblgnt-license"})
        },
        "attributions": greek["layers"][selected["source"]]["attributions"] + greek["attributions"],
        "terms": greek["layers"][selected["source"]],
        "transformations": greek["transformations"]
        + ["Hebrew accent and K/Q display policies do not transform Greek source text."],
    }
