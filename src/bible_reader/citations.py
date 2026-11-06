"""Edition notes shared by the citation page and plain-text credits export."""

import re

from .models import ReaderDocument

MODIFIED_HELPS_NOTICE = (
    "Lexical helps have been modified for this edition. "
    "Changes may include source-entry choices, gloss wording, or inclusion."
)
GREEK_CHARACTER = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")


def lexical_helps_modified(document: ReaderDocument) -> bool:
    decisions = document.config.get("decisions", {})
    # Older portable readers lack per-row change evidence. Conservatively
    # disclose their saved decisions within the exported passage.
    return any(row.get("help_modified", row.get("anchor") in decisions) for row in document.review)


def citation_notes(document: ReaderDocument) -> list[str]:
    notes = []
    if document.config.get("citation_notes_mode", "append") == "append" and lexical_helps_modified(document):
        notes.append(MODIFIED_HELPS_NOTICE)
    custom = document.config.get("citation_notes", "").strip()
    if custom:
        notes.append(custom)
    return notes


def citation_needs_greek(document: ReaderDocument) -> bool:
    return any(GREEK_CHARACTER.search(note) for note in citation_notes(document))
