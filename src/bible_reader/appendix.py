"""An alphabetized, source-traceable union of the passage's selected helps."""

import unicodedata

from .models import digest

FINAL_LETTERS = str.maketrans("ךםןףץ", "כמנפצ")


def hebrew_sort_key(headword: str) -> str:
    """Ignore marks/punctuation and collate final letters with their ordinary forms.

    This key is for sorting only; displayed headwords retain their source Unicode.
    """
    return "".join(
        char
        for char in unicodedata.normalize("NFD", headword).translate(FINAL_LETTERS)
        if unicodedata.category(char).startswith("L")
    )


def collect_lexicon(helps: dict[str, dict]) -> list[dict]:
    entries = {}
    for help_id, help in helps.items():
        key = (help["entry_id"] or help["lemma"], help["headword"], help["stem"], help["gloss"])
        if key not in entries:
            entries[key] = {
                "id": digest(key)[:20],
                **{
                    field: help[field]
                    for field in ("entry_id", "headword", "stem", "gloss", "source", "status")
                },
                "editorial": False,
                "help_ids": [],
            }
        entries[key]["help_ids"].append(help_id)
        entries[key]["editorial"] |= help["editorial"]
    for entry in entries.values():
        entry["help_ids"].sort()
    return sorted(
        entries.values(),
        key=lambda entry: (
            hebrew_sort_key(entry["headword"]),
            entry["entry_id"] or "",
            entry["stem"],
            entry["gloss"],
            entry["headword"],
            entry["id"],
        ),
    )
