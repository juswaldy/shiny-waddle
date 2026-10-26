"""Portable, source-bound editorial decisions for an entire book."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from . import editorial, sources
from .models import Decision, ProjectConfig, ReaderError, StrictModel

# Whole-book decisions can exceed the app's original 2 MB project limit.
MAX_HELP_FILE_BYTES = 64_000_000


class HelpSources(StrictModel):
    text_source: Literal["oshb", "sblgnt", "rahlfs"]
    text_revision: str
    text_sha256: str
    lexicon_source: Literal["step", "step-greek"]
    lexicon_revision: str
    crosswalk_sha256: dict[str, str] = Field(default_factory=dict)
    lexicon_sha256: str


class BookHelps(StrictModel):
    format: Literal["bible-reader-book-helps"]
    schema_version: Literal[1]
    book: str
    sources: HelpSources
    gloss_selection: Literal["reviewed", "first-entry"]
    decisions: dict[str, Decision] = Field(max_length=100000)


def help_sources(book: str) -> HelpSources:
    info = sources.catalog()
    if book not in info["books"]:
        raise ReaderError(f"Unsupported book: {book}")
    selected = info["books"][book]
    if selected.get("language") == "grc":
        greek = info["greek"]
        return HelpSources(
            text_source=selected["source"],
            text_revision=selected["revision"],
            text_sha256=selected["artifact"]["sha256"],
            lexicon_source="step-greek",
            lexicon_revision=greek["lexicon"]["revision"],
            lexicon_sha256=greek["lexicon"]["sha256"],
            crosswalk_sha256={a["filename"]: a["sha256"] for a in greek["crosswalk"]["assets"]}
            if selected["source"] == "sblgnt"
            else {},
        )
    return HelpSources(
        text_source="oshb",
        text_revision=info["oshb_revision"],
        text_sha256=info["books"][book]["sha256"],
        lexicon_source="step",
        lexicon_revision=info["step_revision"],
        lexicon_sha256=info["lexicon"]["sha256"],
    )


def validate_book_helps(state: Path, config: ProjectConfig):
    """Check every saved anchor, including other chapters and both K/Q readings.

    Unresolved choices and historical name decisions remain inspectable. The
    reader's existing name-omission rule still applies when rendering them.
    """
    book = editorial.load_book(state, config.book)
    _, crosswalk = editorial.load_lexicon(state, config.book)
    anchors = {
        f"{token.id}:{index}": lemma
        for verse in book
        for token in verse.tokens
        if token.kind == "word"
        for index, lemma in enumerate(sources.token_keys(token))
    }
    for anchor, decision in config.decisions.items():
        if anchor not in anchors:
            raise ReaderError(f"Editorial decision refers to a missing source anchor: {anchor}")
        lemma = anchors[anchor]
        if decision.entry_id and decision.entry_id not in editorial.lexical_candidates(lemma, crosswalk):
            raise ReaderError(f"Stale or incompatible lexical decision: {anchor}")
        choice = decision.entry_id or editorial.default_entry_id(lemma, crosswalk, config.gloss_selection)
        if decision.gloss and not choice and editorial.lexical_candidates(lemma, crosswalk):
            raise ReaderError(f"Choose a source entry before editing its gloss: {anchor}")


def save_book_helps(state: Path, config: ProjectConfig) -> BookHelps:
    validate_book_helps(state, config)
    return BookHelps(
        format="bible-reader-book-helps",
        schema_version=1,
        book=config.book,
        sources=help_sources(config.book),
        gloss_selection=config.gloss_selection,
        decisions=config.decisions,
    )


def load_book_helps(state: Path, config: ProjectConfig, helps: BookHelps) -> ProjectConfig:
    if helps.book != config.book:
        raise ReaderError(f"This help file is for {helps.book}; the current edition uses {config.book}.")
    if helps.sources != help_sources(config.book):
        raise ReaderError("This help file uses different text or lexicon sources, revisions, or checksums.")
    updated = ProjectConfig.model_validate(
        {
            **config.model_dump(),
            "gloss_selection": helps.gloss_selection,
            "decisions": helps.decisions,
        }
    )
    validate_book_helps(state, updated)
    return updated


def read_book_helps(path: Path) -> BookHelps:
    if path.stat().st_size > MAX_HELP_FILE_BYTES:
        raise ReaderError("Book help files must be at most 64 MB.")
    return BookHelps.model_validate_json(path.read_text(encoding="utf-8-sig"))
