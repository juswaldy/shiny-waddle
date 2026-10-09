PYTHON ?= .venv/bin/python
RUFF ?= .venv/bin/ruff
export PYTHONPATH := src

.PHONY: setup check lint demo pdf serve browser

setup:
	bash scripts/bootstrap.sh

check: lint
	$(PYTHON) -m pytest -q

lint:
	$(RUFF) check src tests scripts
	$(RUFF) format --check src tests scripts

demo:
	$(PYTHON) -m bible_reader examples/demo.reader.json --output build/demo.tex

pdf:
	$(PYTHON) -m bible_reader build

serve:
	$(PYTHON) -m bible_reader serve

browser:
	$(PYTHON) scripts/browser_smoke.py
