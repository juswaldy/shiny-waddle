"""Application CLI with backward compatibility for the synthetic v1 specimen."""

import argparse
import json
import sys
from pathlib import Path

from .render import render_document


def main() -> int:
    commands = {
        "doctor",
        "init",
        "sources",
        "helps",
        "inspect",
        "align",
        "build",
        "transform",
        "serve",
        "worker",
    }
    if (
        len(sys.argv) == 1
        or sys.argv[1] in commands
        or sys.argv[1].startswith("--state")
        or sys.argv[1] in {"-h", "--help"}
    ):
        from .cli import main as application_main

        return application_main()
    parser = argparse.ArgumentParser(description="Render a version-1 reader JSON document to LaTeX.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("input and output must be different files")
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
        rendered = render_document(document)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(1, f"bible-reader: {error}\n")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
