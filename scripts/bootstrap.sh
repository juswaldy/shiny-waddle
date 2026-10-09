#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if ! command -v uv >/dev/null; then
  printf '%s\n' 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2
  exit 1
fi
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.uv-cache}"
uv sync --locked
.venv/bin/python scripts/setup_tex.py
printf '%s\n' 'Setup complete. Next: .venv/bin/bible-reader sources import --book Prov' '.venv/bin/bible-reader serve'
