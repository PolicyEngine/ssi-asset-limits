.PHONY: install test format lint data build verify

install:
	uv venv --python 3.13
	uv pip install -e ".[dev]"
	bun install

test:
	uv run pytest

format:
	uv run ruff format src tests

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

data:
	uv run ssi-asset-limits-data --output-dir public/data

build:
	bun run build

verify: lint test build
