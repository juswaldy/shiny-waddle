"""Render the version-1 specimen contract; no corpus import or sense inference."""

import unicodedata
from importlib.resources import files
from string import Template

_TEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_latex(text: str) -> str:
    """Escape plain text in one pass without normalizing Unicode."""
    return "".join(_TEX_ESCAPES.get(character, character) for character in text)


def _record(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label}: expected fields {', '.join(sorted(fields))}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: expected a nonempty string")
    if any(unicodedata.category(c) in {"Cc", "Cs"} for c in value):
        raise ValueError(f"{label}: control characters and surrogates are unsupported")
    return value


def _list(value: object, label: str, *, nonempty: bool = False) -> list:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{label}: expected {'a nonempty' if nonempty else 'a'} list")
    return value


def validate_document(document: object) -> dict:
    """Validate rendering integrity; this does not verify scholarly content."""
    doc = _record(
        document,
        {
            "schema_version",
            "title",
            "language",
            "source_notice",
            "entries",
            "verses",
        },
        "document",
    )
    if type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
        raise ValueError("schema_version: only integer version 1 is supported")
    if doc["language"] != "hbo":
        raise ValueError("language: this specimen renderer supports hbo only")
    for field in ("title", "source_notice"):
        _text(doc[field], field)

    entry_ids: set[str] = set()
    for entry in _list(doc["entries"], "entries"):
        _record(entry, {"id", "headword", "gloss"}, "entry")
        for field in ("id", "headword", "gloss"):
            _text(entry[field], f"entry.{field}")
        if entry["id"] in entry_ids:
            raise ValueError(f"duplicate entry ID: {entry['id']}")
        entry_ids.add(entry["id"])

    token_ids: set[str] = set()
    references: set[str] = set()
    for verse in _list(doc["verses"], "verses", nonempty=True):
        _record(verse, {"reference", "tokens"}, "verse")
        reference = _text(verse["reference"], "verse.reference")
        if reference in references:
            raise ValueError(f"duplicate verse reference: {reference}")
        references.add(reference)
        for token in _list(verse["tokens"], "verse.tokens", nonempty=True):
            _record(token, {"id", "surface", "entry_id"}, "token")
            _text(token["id"], "token.id")
            _text(token["surface"], "token.surface")
            if token["id"] in token_ids:
                raise ValueError(f"duplicate token ID: {token['id']}")
            token_ids.add(token["id"])
            entry_id = token["entry_id"]
            if entry_id is not None:
                _text(entry_id, "token.entry_id")
                if entry_id not in entry_ids:
                    raise ValueError(f"unknown entry ID for {token['id']}: {entry_id}")
    return doc


def render_document(document: object) -> str:
    """Generate deterministic TeX from explicit, already selected lexical helps."""
    doc = validate_document(document)
    entries = {entry["id"]: entry for entry in doc["entries"]}
    verses: list[str] = []
    notes: list[str] = []
    for verse in doc["verses"]:
        words: list[str] = []
        for token in verse["tokens"]:
            word = escape_latex(token["surface"])
            if token["entry_id"] is not None:
                entry = entries[token["entry_id"]]
                number = len(notes) + 1
                word += rf"\textsuperscript{{\textenglish{{{number}}}}}"
                notes.append(
                    rf"\noindent\textsuperscript{{{number}}} "
                    rf"\texthebrew{{{escape_latex(entry['headword'])}}} "
                    rf"--- {escape_latex(entry['gloss'])}\par"
                )
            words.append(word)
        verses.append(
            "\\begin{hebrew}\n\\fontsize{20}{32}\\selectfont\n"
            + rf"\textenglish{{{escape_latex(verse['reference'])}}}\quad "
            + " ".join(words)
            + "\n\\end{hebrew}\n"
        )
    template = files("bible_reader").joinpath("templates/reader.tex").read_text(encoding="utf-8")
    return Template(template).substitute(
        title=escape_latex(doc["title"]),
        source_notice=escape_latex(doc["source_notice"]),
        verses="\n".join(verses),
        notes="\n".join(notes) if notes else "No lexical helps selected.",
    )
