PY := .venv/bin/python

.PHONY: setup data data-offline validate test test-py test-web dev build docs

setup:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
	npm ci

# Fetch (cached) CFBD + weather data, then run the model; writes public/data/*.json + csv/
data:
	$(PY) -m pipeline.run
	$(PY) -m model.run

# Rebuild outputs from cache only (no API calls)
data-offline:
	$(PY) -m pipeline.run --offline
	$(PY) -m model.run

test: test-py test-web

test-py:
	$(PY) -m pytest

test-web:
	npx tsc -b
	npx vitest run

# Local site at http://localhost:5173 (uses whatever is in public/data)
dev:
	npm run dev

# Static site in dist/ (includes public/data)
build:
	npm run build

validate:
	$(PY) -m pipeline.manual

docs:
	$(PY) -m pipeline.docs
