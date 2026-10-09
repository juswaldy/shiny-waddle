"""Validated application configuration and source-preserving records."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReaderError(Exception):
    """An actionable input, source, or build failure."""


class Cancelled(ReaderError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def plain_text(value: str) -> str:
    if any(unicodedata.category(c) in {"Cc", "Cs"} for c in value):
        raise ValueError("Control characters are not allowed")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class Decision(StrictModel):
    action: Literal["include", "exclude"] = "include"
    entry_id: str | None = None
    gloss: str | None = Field(default=None, min_length=1, max_length=1200)
    reason: str = Field(default="Reader selection", min_length=1, max_length=300)

    @field_validator("gloss", "reason")
    @classmethod
    def text(cls, value):
        return plain_text(value) if value is not None else value


class Layout(StrictModel):
    paper: Literal["reader", "reference", "a4", "a5", "letter", "custom"] = "reader"
    paper_width_mm: float | None = Field(default=None, ge=21, le=1000)
    paper_height_mm: float | None = Field(default=None, ge=21, le=1000)
    verse_layout: Literal["continuous", "verse-per-line"] = "continuous"
    body_pt: float = Field(default=18.0, ge=12, le=26)
    leading_pt: float = Field(default=23.5, ge=16, le=38)
    notes_pt: float = Field(default=9.0, ge=7.5, le=14)
    first_folio: int = Field(default=1, ge=1, le=99999)
    hebrew_font: Literal["Ezra SIL", "SBL Hebrew"] = "Ezra SIL"

    @model_validator(mode="after")
    def validate_layout(self):
        if self.paper == "custom" and (self.paper_width_mm is None or self.paper_height_mm is None):
            raise ValueError("Custom paper requires both paper_width_mm and paper_height_mm")
        if self.leading_pt < self.body_pt * 1.12:
            raise ValueError("Line spacing must leave room for Hebrew vowel marks")
        return self


class ProjectConfig(StrictModel):
    schema_version: Literal[2] = 2
    name: str = Field(default="Proverbs reader", min_length=1, max_length=100)
    book: str = Field(default="Prov", pattern=r"^[A-Za-z0-9]{2,12}$")
    passage: str = Field(default="1:29-2:12", max_length=50)
    selection: Literal["all", "book-frequency", "reference"] = "reference"
    frequency_max: int = Field(default=10, ge=1, le=100000)
    known_entries: list[str] = Field(default_factory=list, max_length=10000)
    cantillation: Literal["preserve", "hide", "consonants", "consonants-maqqef-sof-pasuq"] = "hide"
    readings: Literal["both", "qere", "ketiv"] = "both"
    decisions: dict[str, Decision] = Field(default_factory=dict, max_length=10000)
    layout: Layout = Field(default_factory=Layout)

    @field_validator("name")
    @classmethod
    def text(cls, value):
        return plain_text(value)

    @field_validator("passage")
    @classmethod
    def passage_format(cls, value):
        parse_passage(value)
        return value

    @model_validator(mode="after")
    def reference_book(self):
        if self.selection == "reference" and self.book != "Prov":
            raise ValueError("The reference help selection is available for Proverbs only")
        return self


def parse_passage(value: str) -> tuple[tuple[int, int], tuple[int, int]]:
    match = re.fullmatch(r"([1-9]\d{0,2}):([1-9]\d{0,2})(?:[-–](?:([1-9]\d{0,2}):)?([1-9]\d{0,2}))?", value)
    if not match:
        raise ValueError("Use a passage such as 1:29-2:12 or 2:1-12")
    chapter, verse, last_chapter, last_verse = match.groups()
    start = (int(chapter), int(verse))
    end = (int(last_chapter or chapter), int(last_verse or verse))
    if end < start:
        raise ValueError("Passage end must follow its start")
    return start, end


@dataclass(frozen=True)
class Token:
    id: str
    surface: str
    lemma: str = ""
    morph: str = ""
    kind: str = "word"
    reading: str = "normal"
    language: str = "hbo"
    source_xml: str = ""

    def json(self):
        return asdict(self)


@dataclass(frozen=True)
class Verse:
    book: str
    chapter: int
    verse: int
    tokens: tuple[Token, ...]
    annotations: tuple[str, ...] = ()

    @property
    def reference(self):
        return f"{self.book}.{self.chapter}.{self.verse}"

    def json(self):
        return asdict(self)


@dataclass(frozen=True)
class Entry:
    id: str
    headword: str
    transliteration: str
    morphology: str
    gloss: str
    definition: str


@dataclass
class ReaderDocument:
    config: dict
    verses: list[dict]
    helps: dict[str, dict]
    review: list[dict]
    registry: dict[str, dict]
    sources: dict
    schema_version: int = 2
    warnings: list[str] = field(default_factory=list)

    def json(self):
        return asdict(self)
