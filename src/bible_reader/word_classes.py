"""Display categories from OSHB morphology, independent of lexical-help selection."""

from typing import Literal

WordClass = Literal[
    "noun",
    "verb",
    "adjective",
    "adverb",
    "pronoun",
    "preposition",
    "conjunction",
    "particle",
    "suffix",
    "number",
    "name",
]

# OSHB's language prefix applies once to the whole slash-separated analysis.
# https://hb.openscriptures.org/parsing/HebrewMorphologyCodes.html
PARTS_OF_SPEECH = {
    "A": "adjective",
    "C": "conjunction",
    "D": "adverb",
    "N": "noun",
    "P": "pronoun",
    "R": "preposition",
    "S": "suffix",
    "T": "particle",
    "V": "verb",
}

WORD_CLASS_COLORS = {
    "noun": ("Nouns", "245A81"),
    "verb": ("Verbs", "A33432"),
    "adjective": ("Adjectives", "38633F"),
    "adverb": ("Adverbs", "8A5314"),
    "pronoun": ("Pronouns", "67458E"),
    "preposition": ("Prepositions", "216C70"),
    "conjunction": ("Conjunctions", "536475"),
    "particle": ("Particles", "595959"),
    "suffix": ("Suffixes", "697446"),
    "number": ("Numbers", "886316"),
    "name": ("Names", "9C3776"),
}


def word_class(morphology: str, language: str = "hbo") -> str | None:
    """Color an orthographic word by its main component; unknown/compound stays plain."""
    if language == "grc":
        if morphology.startswith("lxx."):
            pos = morphology[4:].split(".", 1)[0]
        else:
            pos = morphology.split(" ", 1)[0].rstrip("-")
        return {
            "N": "noun",
            "V": "verb",
            "A": "adjective",
            "D": "adverb",
            "P": "preposition",
            "C": "conjunction",
            "X": "particle",
            "I": "particle",
            "RA": "particle",
            "RD": "pronoun",
            "RI": "pronoun",
            "RP": "pronoun",
            "RR": "pronoun",
        }.get(pos)
    if not morphology.startswith(("H", "A")):
        return None
    components = morphology[1:].split("/")
    if any(not part or part[0] not in PARTS_OF_SPEECH for part in components):
        return None
    if "Np" in components:
        return "name"
    # Attached suffixes, conjunctions, prepositions and articles share the main
    # word's color. Standalone function words keep their own category.
    while len(components) > 1 and components[-1].startswith("S"):
        components.pop()
    while len(components) > 1 and (components[0].startswith(("C", "R")) or components[0] == "Td"):
        components.pop(0)
    if len(components) != 1:
        return None
    main = components[0]
    if main.startswith(("Ac", "Ao")):
        return "number"
    return PARTS_OF_SPEECH[main[0]]


def word_color(category: str | None, layout: dict) -> str | None:
    """Return a validated HTML hex color, or no color for Auto/unknown classes."""
    if layout.get("word_colors", "auto") == "auto" or category not in WORD_CLASS_COLORS:
        return None
    override = layout.get("word_color_overrides", {}).get(category)
    if override == "auto":
        return None
    return override or "#" + WORD_CLASS_COLORS[category][1]
