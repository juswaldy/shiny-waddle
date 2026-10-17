"""Source-preserving Greek adapters; no normalization, inference, or network IO."""

from __future__ import annotations

import json
import re
from collections import defaultdict

from .models import Entry, ReaderError, Token, Verse


def parse_morphgnt(data: bytes, book: str, source_book: int) -> list[Verse]:
    """Read all seven MorphGNT columns, keeping punctuation and analysis apart.

    MorphGNT supplies verse references but no word IDs. IDs use the source
    reference plus the one-based word position within that verse.
    """
    grouped: dict[tuple[int, int], list[Token]] = {}
    previous = (0, 0)
    for number, line in enumerate(data.decode("utf-8-sig").splitlines(), 1):
        columns = line.split()
        if len(columns) != 7 or not re.fullmatch(r"\d{6}", columns[0]):
            raise ReaderError(f"Malformed MorphGNT row {number}")
        ref, pos, parsing, text, word, normalized, lemma = columns
        reference = (int(ref[2:4]), int(ref[4:6]))
        if int(ref[:2]) != source_book or min(reference) < 1 or reference < previous:
            raise ReaderError(f"Unexpected or out-of-order MorphGNT reference on row {number}")
        previous = reference
        tokens = grouped.setdefault(reference, [])
        tokens.append(
            Token(
                id=f"sblgnt:{ref}:{len(tokens) + 1}",
                surface=text,
                lemma=lemma,
                morph=f"{pos} {parsing}",
                language="grc",
                source_record=line,
                lexical_keys=(f"morphgnt:{lemma}",),
                spelling_key=word,
            )
        )
    if not grouped:
        raise ReaderError("No MorphGNT records found")
    return [Verse(book, c, v, tuple(tokens)) for (c, v), tokens in grouped.items()]


def parse_rahlfs(data: bytes, book: str, source_book: int, witness="main") -> list[Verse]:
    """Read Wong's MyBible TSV without flattening its explicit witness identity.

    This artifact uses its own numeric MyBible versification (including verse
    zero). It is not a crosswalk to Hebrew or a claim of native CATSS numbering.
    The first S field is a Wong LXX lexeme ID; subsequent traditional Strong's
    references are lexical links, while 70000+ NT index values remain raw data.
    """
    verses = []
    seen = set()
    units = re.compile(
        r"(?P<word>(?P<surface>[^<>\s]+)<S>(?P<lexeme>\d+)</S><m>(?P<morph>lxx\.[^<>]+)</m>(?P<links>(?:<S>\d+</S>)*))"
        r"|(?P<marker><i>[^<>]*</i>)|(?P<break><br/>)"
    )
    for number, line in enumerate(data.decode("utf-8-sig").splitlines(), 1):
        columns = line.split("\t")
        if len(columns) != 4 or not all(part.isdigit() for part in columns[:3]):
            raise ReaderError(f"Malformed Rahlfs TSV row {number}")
        if int(columns[0]) != source_book:
            continue
        chapter, verse = map(int, columns[1:3])
        if (chapter, verse) in seen:
            raise ReaderError(f"Duplicate Rahlfs reference on row {number}")
        seen.add((chapter, verse))
        tokens = []
        cursor = 0
        for position, match in enumerate(units.finditer(columns[3]), 1):
            if columns[3][cursor : match.start()].strip():
                raise ReaderError(f"Unsupported Rahlfs content on row {number}")
            cursor = match.end()
            identity = f"rahlfs:{witness}:{source_book}:{chapter}:{verse}:{position}"
            if not match.group("word"):
                tokens.append(
                    Token(
                        identity,
                        match.group()[3:-4] if match.group("marker") else "",
                        kind="source-marker" if match.group("marker") else "source-break",
                        language="grc",
                        source_record=match.group(),
                    )
                )
                continue
            surface, lexeme, morph, references = (
                match.group(k) for k in ("surface", "lexeme", "morph", "links")
            )
            links = tuple(
                f"G{int(code):04d}"
                for code in re.findall(r"<S>(\d+)</S>", references)
                if 0 < int(code) < 70000
            )
            tokens.append(
                Token(
                    id=identity,
                    surface=surface,
                    lemma=f"rahlfs:{lexeme}",
                    morph=morph,
                    language="grc",
                    source_record=match.group(),
                    lexical_keys=links or (f"rahlfs:{lexeme}",),
                )
            )
        if columns[3][cursor:].strip():
            raise ReaderError(f"Unsupported Rahlfs content on row {number}")
        if not tokens:
            raise ReaderError(f"Empty Rahlfs verse on row {number}")
        verses.append(Verse(book, chapter, verse, tuple(tokens), (line,)))
    if not verses:
        raise ReaderError(f"No Rahlfs records found for {book}")
    return verses


def parse_tbesg(data: bytes) -> tuple[dict[str, Entry], dict[str, list[str]]]:
    """Import STEP's short Gloss and metadata, excluding the long Meaning field."""
    entries = {}
    mapping: dict[str, list[str]] = defaultdict(list)
    for number, line in enumerate(data.decode("utf-8-sig").splitlines(), 1):
        if not re.match(r"^G\d", line):
            continue
        columns = line.split("\t")
        if len(columns) < 8:
            raise ReaderError(f"Malformed TBESG row {number}")
        extended, disambiguated, _, headword, transliteration, morphology, gloss = columns[:7]
        identity = re.match(r"G\d{4,5}[A-Za-z]*", disambiguated)
        if not re.fullmatch(r"G\d{4,5}[A-Za-z]*", extended) or not identity:
            raise ReaderError(f"Invalid TBESG identity on row {number}")
        key = "step-greek:" + identity.group()
        entry = Entry(key, headword.strip(), transliteration.strip(), morphology.strip(), gloss.strip(), "")
        if key in entries and entries[key] != entry:
            raise ReaderError(f"Conflicting TBESG records: {key}")
        entries[key] = entry
        if key not in mapping[extended]:
            mapping[extended].append(key)
    if not entries:
        raise ReaderError("No TBESG entries found")
    return entries, dict(mapping)


def javascript_object(data: bytes, variable: str) -> dict:
    """Read the upstream JSON object literal without executing JavaScript."""
    text = data.decode("utf-8-sig")
    match = re.search(rf"\b{re.escape(variable)}\s*=\s*(\{{.*\}})\s*;?\s*$", text, re.S)
    try:
        result = json.loads(match.group(1)) if match else None
    except ValueError as error:
        raise ReaderError(f"Invalid {variable} source object") from error
    if not isinstance(result, dict):
        raise ReaderError(f"Missing {variable} source object")
    return result


def morphgnt_crosswalk(
    lookups: bytes, wordlist: bytes, strong_mapping: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Follow only the published MorphGNT → word-list → Strong's crosswalk.

    Exact Unicode lookup is intentional. Undocumented spellings, the word-list's
    local Strong extensions, and absent links remain unmatched; no spelling joins.
    """
    lemmas = javascript_object(lookups, "gntLookups")
    words = javascript_object(wordlist, "greekWordList")
    result = {}
    for lemma, key in lemmas.items():
        if not isinstance(key, str) or not isinstance(words.get(key, {}), dict):
            raise ReaderError("Unsupported Open Scriptures Greek crosswalk record")
        strong = words.get(key, {}).get("strong", "")
        if isinstance(strong, str) and strong.isdigit():
            candidates = strong_mapping.get(f"G{int(strong):04d}", [])
            if candidates:
                result[f"morphgnt:{lemma}"] = candidates.copy()
    return result
