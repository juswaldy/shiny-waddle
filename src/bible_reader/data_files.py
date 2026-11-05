"""Validate portable reader snapshots without consulting installed source files."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .appendix import collect_lexicon
from .models import ProjectConfig, ReaderDocument, ReaderError, StrictModel, canonical_json
from .sources import catalog
from .word_classes import WordClass

MAX_PIPELINE_BYTES = 64_000_000
Number = Annotated[int, Field(ge=0, le=99999)]
Label = Annotated[int, Field(ge=1, le=1000000)]


class Record(BaseModel):
    # Keep source adapter fields, including future source metadata, intact.
    model_config = ConfigDict(extra="allow", strict=True)


class DataToken(Record):
    id: str
    surface: str
    source_surface: str
    kind: str
    reading: Literal["normal", "ketiv", "qere"]
    language: Literal["hbo", "arc", "grc"]
    helps: list[str]
    word_class: WordClass | None = None


class DataVerse(Record):
    reference: str
    chapter: Number
    verse: Number
    tokens: list[DataToken]


class DataHelp(Record):
    id: str
    chapter: Number
    label: Label
    entry_id: str | None
    headword: str
    gloss: str
    stem: str
    status: Literal["resolved", "editorial", "ambiguous", "unmatched"]
    editorial: bool
    source: str
    lemma: str


class DataReview(Record):
    selected: bool
    status: Literal["resolved", "editorial", "ambiguous", "unmatched"]
    reference: str
    surface: str
    help_id: str | None
    help_modified: bool = False


class NoticeAsset(Record):
    filename: str = Field(pattern=r"^(?:[A-Za-z0-9_-]+\.(?:md|html)|README\.md)$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class LexiconSource(Record):
    revision: str = ""


class DataSources(Record):
    language: Literal["hbo", "arc", "grc"] = "hbo"
    attributions: list[str]
    transformations: list[str]
    lexicon: LexiconSource
    text_revision: str = ""
    oshb_revision: str = ""
    step_revision: str = ""
    notices: dict[str, NoticeAsset] = Field(default_factory=dict)


class ReaderData(StrictModel):
    schema_version: Literal[2]
    config: ProjectConfig
    verses: list[DataVerse] = Field(min_length=1)
    helps: dict[str, DataHelp]
    review: list[DataReview]
    registry: dict[str, dict[str, Label]]
    sources: DataSources
    warnings: list[str] = Field(default_factory=list)
    lexicon_appendix: list[dict] = Field(default_factory=list)
    source_notices: dict[str, str] = Field(default_factory=dict)


def load_reader_data(value: dict) -> ReaderDocument:
    try:
        parsed = ReaderData.model_validate(value)
        data = parsed.model_dump(exclude_unset=True)
        data["config"] = parsed.config.model_dump()
        if len(canonical_json(data).encode("utf-8")) > MAX_PIPELINE_BYTES:
            raise ValueError("Reader data files must be at most 64 MB")
        document = ReaderDocument(**data)
        if document.config["book"] not in catalog()["books"]:
            raise ValueError("Unsupported source book")
        for chapter_registry in document.registry.values():
            if len(chapter_registry) != len(set(chapter_registry.values())):
                raise ValueError("Help labels must be unique within each chapter")
        used = set()
        references = set()
        for verse in document.verses:
            reference = f"{document.config['book']}.{verse['chapter']}.{verse['verse']}"
            if verse["reference"] != reference or reference in references:
                raise ValueError("Verse references must be unique and match their book/chapter/verse")
            references.add(reference)
            for token in verse["tokens"]:
                if len(token["helps"]) != len(set(token["helps"])):
                    raise ValueError("Duplicate token help reference")
                for identity in token["helps"]:
                    help = document.helps[identity]
                    if help["id"] != identity or help["chapter"] != verse["chapter"]:
                        raise ValueError("Help references must match their chapter and identity")
                    if document.registry[str(verse["chapter"])][identity] != help["label"]:
                        raise ValueError("Help labels must match the chapter registry")
                    used.add(identity)
        if used != set(document.helps):
            raise ValueError("Selected helps must match the tokens that use them")
        selected = {row["help_id"] for row in document.review if row["selected"]}
        if selected != used:
            raise ValueError("Review rows must cover every selected help")
        expected = (
            collect_lexicon(document.helps)
            if document.config["lexicon_appendix"] or document.config["lexicon_only"]
            else []
        )
        if document.lexicon_appendix != expected:
            raise ValueError("Lexicon entries must match the selected helps")
        return document
    except (ValidationError, ValueError, KeyError, TypeError) as error:
        raise ReaderError(f"Invalid reader data file: {error}") from error


def validate_tex(text: str) -> str:
    if not text.strip() or "\x00" in text or len(text.encode("utf-8")) > MAX_PIPELINE_BYTES:
        raise ReaderError("Choose a nonempty UTF-8 TeX file of at most 64 MB, without NUL characters.")
    return text
