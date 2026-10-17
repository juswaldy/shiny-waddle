"""Audit every locally installed pinned Greek book; never acquire sources."""

import argparse
import json
from collections import Counter
from pathlib import Path

from bible_reader.sources import book_artifact, catalog, load_book, load_lexicon, token_keys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path(".reader"))
    parser.add_argument("--output", type=Path, default=Path("build/greek-source-audit.json"))
    args = parser.parse_args()
    info = catalog()["greek"]
    mappings = {}
    report = {"books": {}, "totals": Counter()}
    for code, selected in info["books"].items():
        if not book_artifact(args.state, code)[0].exists():
            continue
        verses = load_book(args.state, code)
        source = selected["source"]
        if source not in mappings:
            mappings[source] = load_lexicon(args.state, code)[1]
        words = sum(t.kind == "word" for v in verses for t in v.tokens)
        if (len(verses), words) != (selected["verse_count"], selected["word_count"]):
            raise RuntimeError(f"Pinned counts changed: {code}")
        identities = [t.id for v in verses for t in v.tokens]
        if len(set(identities)) != len(identities):
            raise RuntimeError(f"Duplicate identities: {code}")
        coverage = Counter()
        for verse in verses:
            for token in verse.tokens:
                if token.language != "grc":
                    raise RuntimeError(f"Lost Greek language: {token.id}")
                for key in token_keys(token):
                    candidates = mappings[source].get(key, [])
                    coverage[
                        "resolved" if len(candidates) == 1 else "ambiguous" if candidates else "unmatched"
                    ] += 1
        report["books"][code] = {
            "verses": len(verses),
            "words": words,
            "coverage": dict(coverage),
            "revision": selected["revision"],
        }
        report["totals"].update({"books": 1, "verses": len(verses), "words": words, **coverage})
        print(f"Verified {code}: {len(verses)} verses, {words} words", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["totals"]))


if __name__ == "__main__":
    main()
