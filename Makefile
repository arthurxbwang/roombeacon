.PHONY: test lint build test-web
PYTHON ?= .venv/bin/python

test:
	cd backend && ../$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check backend

build:
	cd frontend && npm run build

test-web: build
	cd frontend && npm test
