"""Alignment, explicit editorial selections, and chapter-local help identities."""

import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path

from .models import Decision, ProjectConfig, ReaderDocument, ReaderError, digest, parse_passage
from .sources import catalog, lemma_keys, load_book, load_lexicon

STEMS = {"q": "Qal", "N": "Nif", "p": "Piel", "P": "Pual", "h": "Hif", "H": "Hof", "t": "Hitp"}
CONSONANT_PUNCTUATION = {"consonants-only": "", "consonants": "־", "consonants-maqqef-sof-pasuq": "־׃"}
DISPLAY_TRANSFORMATIONS = {
    "preserve": "Display policy preserve: source Hebrew points, accents, and punctuation retained.",
    "hide": "Display policy hide: only Hebrew accents U+0591–U+05AF hidden; vowel points retained.",
    "consonants-only": "Display policy consonants-only: Hebrew combining marks and punctuation hidden.",
    "consonants": "Display policy consonants: Hebrew combining marks and punctuation hidden except maqqef.",
    "consonants-maqqef-sof-pasuq": (
        "Display policy consonants-maqqef-sof-pasuq: Hebrew combining marks and punctuation hidden "
        "except maqqef and sof pasuq."
    ),
}


def display_surface(raw: str, cantillation: str) -> str:
    """Transform display text only, without normalizing source Unicode."""
    value = raw.replace("/", "")
    if cantillation == "hide":
        value = "".join(c for c in value if not ("\u0591" <= c <= "\u05af"))
    elif cantillation in CONSONANT_PUNCTUATION:
        retained = CONSONANT_PUNCTUATION[cantillation]
        value = "".join(
            c
            for c in value
            if c in retained
            or not ("\u0590" <= c <= "\u05ff" and unicodedata.category(c).startswith(("M", "P")))
        )
    return value


def stem_label(morph: str) -> str:
    match = re.search(r"(?:^H|/|^)(V.?)", morph)
    return STEMS.get(match.group(1)[1:], "") if match else ""


def consonant_key(raw: str) -> str:
    """A separate spelling key; source and display surfaces remain untouched."""
    return display_surface(raw, "consonants-only")


def lexical_candidates(lemma: str, crosswalk: dict[str, list[str]]) -> list[str]:
    return crosswalk.get(lemma, crosswalk.get(lemma[:5], []))


def edit_decision(state: Path, config: ProjectConfig, anchor: str, decision: Decision, scope: str):
    """Expand an explicit reader choice to source-supported anchors in this book."""
    updated, reports = edit_decisions(state, config, [(anchor, decision, scope)])
    return updated, reports[0]


def edit_decisions(state: Path, config: ProjectConfig, edits: list[tuple[str, Decision, str]]):
    """Validate a review page together, without partially applying or overwriting choices."""
    if not edits:
        raise ReaderError("Choose at least one lexical decision to save.")
    if len({anchor for anchor, _, _ in edits}) != len(edits):
        raise ReaderError("A review page cannot submit the same source anchor twice.")
    book = load_book(state, config.book)
    _, crosswalk = load_lexicon(state)
    anchors = {
        f"{token.id}:{index}": (verse, token, lemma)
        for verse in book
        for token in verse.tokens
        if token.kind == "word"
        for index, lemma in enumerate(lemma_keys(token.lemma))
    }
    decisions = dict(config.decisions)
    pending: dict[str, Decision] = {}
    reports = []
    for anchor, decision, scope in edits:
        if scope not in {"occurrence", "book"}:
            raise ReaderError("Choose this occurrence or all occurrences in this book.")
        if anchor not in anchors:
            raise ReaderError(f"Editorial decision refers to a missing source anchor: {anchor}")
        _, origin, origin_lemma = anchors[anchor]
        origin_candidates = lexical_candidates(origin_lemma, crosswalk)
        if decision.entry_id and decision.entry_id not in origin_candidates:
            raise ReaderError(f"Stale or incompatible lexical decision: {anchor}")
        if (
            decision.gloss
            and not decision.entry_id
            and not (origin_lemma in crosswalk and len(origin_candidates) == 1)
        ):
            raise ReaderError(f"Choose a source entry before editing its gloss: {anchor}")
        if scope == "book" and (decision.action == "include" or decision.gloss) and not decision.entry_id:
            raise ReaderError(f"Choose a source entry before applying a help to all occurrences: {anchor}")
        key = consonant_key(origin.surface)
        if scope == "book" and not key:
            raise ReaderError("This source word has no consonants to match.")
        applied, skipped = [], []
        targets = anchors.items() if scope == "book" else [(anchor, anchors[anchor])]
        for target, (verse, token, lemma) in targets:
            if scope == "book" and (token.language != origin.language or consonant_key(token.surface) != key):
                continue
            if decision.entry_id and decision.entry_id not in lexical_candidates(lemma, crosswalk):
                skipped.append(
                    {
                        "anchor": target,
                        "reference": verse.reference,
                        "source_surface": token.surface,
                        "reason": "Chosen entry is not a source candidate for this occurrence",
                    }
                )
                continue
            earlier = pending.get(target)
            if earlier and (earlier.action, earlier.entry_id, earlier.gloss) != (
                decision.action,
                decision.entry_id,
                decision.gloss,
            ):
                raise ReaderError(
                    f"Conflicting page edits affect {target}. Use matching choices or save them separately."
                )
            pending[target] = decision
            applied.append(target)
        reports.append({"consonants": key, "applied": applied, "skipped": skipped})
    decisions.update({anchor: decision.model_dump() for anchor, decision in pending.items()})
    updated = ProjectConfig.model_validate({**config.model_dump(), "decisions": decisions})
    # Check gloss/source compatibility and the existing project before saving anything.
    build_document(state, updated)
    return updated, reports


def reference_map():
    return json.loads(files("bible_reader").joinpath("resources/reference-helps.json").read_text())


def build_document(state: Path, config: ProjectConfig) -> ReaderDocument:
    book = load_book(state, config.book)
    entries, crosswalk = load_lexicon(state)
    start, end = parse_passage(config.passage)
    available = {(v.chapter, v.verse) for v in book}
    if start not in available or end not in available:
        raise ReaderError("Passage endpoints do not exist in the selected source versification.")
    if config.selection == "reference" and not ((1, 29) <= start <= end <= (2, 12)):
        raise ReaderError(
            "Reference selection covers Proverbs 1:29–2:12. Choose All or Book frequency for other passages."
        )
    selected_chapters = set(range(start[0], end[0] + 1))
    reference = reference_map()["anchors"] if config.selection == "reference" else {}
    counts = Counter(
        key
        for verse in book
        for token in verse.tokens
        if token.kind == "word" and token.reading != "ketiv"
        for key in lemma_keys(token.lemma)
    )
    word_counts = Counter(
        (token.language, consonant_key(token.surface))
        for verse in book
        for token in verse.tokens
        if token.kind == "word" and lemma_keys(token.lemma)
    )
    registries: dict[int, dict[str, int]] = defaultdict(dict)
    helps = {}
    reviews = []
    rendered = []
    seen_decisions = set()
    for verse in book:
        if verse.chapter not in selected_chapters:
            continue
        in_passage = start <= (verse.chapter, verse.verse) <= end
        verse_record = {
            "reference": verse.reference,
            "chapter": verse.chapter,
            "verse": verse.verse,
            "tokens": [],
            "source_annotations": list(verse.annotations),
        }
        for token in verse.tokens:
            if token.reading != "normal" and config.readings not in {"both", token.reading}:
                continue
            surface = display_surface(token.surface, config.cantillation)
            record = {
                "id": token.id,
                "surface": surface,
                "source_surface": token.surface,
                "reading": token.reading,
                "kind": token.kind,
                "language": token.language,
                "helps": [],
            }
            for index, lemma in enumerate(lemma_keys(token.lemma)):
                anchor = f"{token.id}:{index}"
                exact = lemma in crosswalk
                candidate_ids = lexical_candidates(lemma, crosswalk)
                candidates = [asdict(entries[c]) for c in candidate_ids]
                decision = config.decisions.get(anchor)
                if decision:
                    seen_decisions.add(anchor)
                selected = (
                    config.selection == "all"
                    or (config.selection == "book-frequency" and counts[lemma] <= config.frequency_max)
                    or anchor in reference
                )
                reason = {
                    "all": "All lexical items",
                    "book-frequency": f"Book frequency {counts[lemma]}",
                    "reference": "Reference-page selection",
                }[config.selection]
                choice = candidate_ids[0] if len(candidate_ids) == 1 and exact else None
                if choice in config.known_entries:
                    selected, reason = False, "Known-word list"
                if decision:
                    selected, reason = decision.action == "include", decision.reason
                    if decision.entry_id:
                        if decision.entry_id not in candidate_ids:
                            raise ReaderError(f"Stale or incompatible lexical decision: {anchor}")
                        choice = decision.entry_id
                status = "resolved" if choice else ("ambiguous" if candidate_ids else "unmatched")
                stem = stem_label(token.morph)
                gloss = (
                    decision.gloss
                    if decision and decision.gloss
                    else (entries[choice].gloss if choice else "")
                )
                if decision and decision.gloss and not choice:
                    raise ReaderError(f"Choose a source entry before editing its gloss: {anchor}")
                semantic = digest([choice or lemma, stem, gloss])[:20]
                explicit_label = reference.get(anchor, {}).get("label")
                if decision and (
                    decision.gloss
                    or (
                        decision.entry_id
                        and decision.entry_id != (candidate_ids[0] if len(candidate_ids) == 1 else None)
                    )
                ):
                    explicit_label = None
                if explicit_label is not None:
                    semantic = f"reference-{explicit_label}"
                help_id = f"{config.book}.{verse.chapter}:{semantic}"
                label = None
                if selected:
                    registry = registries[verse.chapter]
                    if help_id not in registry:
                        # Explicit reference slots remain separate even for the same root.
                        used = set(registry.values())
                        if explicit_label is not None:
                            if explicit_label in used:
                                raise ReaderError(
                                    "Conflicting source helps share a reference label; review the reference mapping."
                                )
                            label = explicit_label
                        else:
                            reserved = {
                                v["label"] for v in reference.values() if v["chapter"] == verse.chapter
                            }
                            label = max(used | reserved | {0}) + 1
                        registry[help_id] = label
                    label = registry[help_id]
                    record["helps"].append(help_id)
                    helps[help_id] = {
                        "id": help_id,
                        "chapter": verse.chapter,
                        "label": label,
                        "entry_id": choice,
                        "headword": entries[choice].headword if choice else "",
                        "gloss": gloss,
                        "stem": stem,
                        "status": status,
                        "editorial": bool(decision and decision.gloss),
                        "source": "STEP Gloss; OSHB verb-stem code",
                        "lemma": lemma,
                    }
                if in_passage:
                    reviews.append(
                        {
                            "anchor": anchor,
                            "token_id": token.id,
                            "reference": verse.reference,
                            "chapter": verse.chapter,
                            "surface": surface,
                            "source_surface": token.surface,
                            "consonants": consonant_key(token.surface),
                            "word_occurrences": word_counts[(token.language, consonant_key(token.surface))],
                            "lemma": lemma,
                            "morphology": token.morph,
                            "reading": token.reading,
                            "candidates": candidates,
                            "entry_id": choice,
                            "gloss": gloss,
                            "status": status,
                            "selected": selected,
                            "reason": reason,
                            "label": label,
                            "help_id": help_id if selected else None,
                            "book_frequency": counts[lemma],
                            "method": "exact extended ID" if exact else "base ID candidates; review required",
                        }
                    )
            verse_record["tokens"].append(record)
        if in_passage:
            rendered.append(verse_record)
    stale = set(config.decisions) - seen_decisions
    # Decisions in other chapters remain valid project history; invalid source IDs never do.
    all_anchors = {f"{t.id}:{i}" for v in book for t in v.tokens for i, _ in enumerate(lemma_keys(t.lemma))}
    if stale - all_anchors:
        raise ReaderError(
            "Editorial decisions refer to missing source anchors; re-review after the source change."
        )
    used_helps = {h for v in rendered for t in v["tokens"] for h in t["helps"]}
    info = catalog()
    warnings = []
    if config.selection == "reference":
        warnings.append(
            "Reference labels/anchors are editorial mappings to the scan; glosses are STEP short Gloss fields and differ from the scan."
        )
    return ReaderDocument(
        config.model_dump(),
        rendered,
        {h: helps[h] for h in sorted(used_helps)},
        reviews,
        {str(k): v for k, v in registries.items()},
        {
            "text": info["books"][config.book],
            "lexicon": info["lexicon"],
            "oshb_revision": info["oshb_revision"],
            "step_revision": info["step_revision"],
            "attributions": info["attributions"],
            "transformations": info["transformations"] + [DISPLAY_TRANSFORMATIONS[config.cantillation]],
        },
        warnings=warnings,
    )


def require_resolved(document: ReaderDocument):
    problems = [r for r in document.review if r["selected"] and r["status"] != "resolved"]
    if problems:
        first = problems[0]
        raise ReaderError(
            f"Review {len(problems)} unresolved selected helps before building. First: {first['reference']} {first['surface']}."
        )
