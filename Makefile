.PHONY: help format lint check run test clean

# Use `uv run` if using uv, `.venv/bin/` if using a plain venv, or leave empty for global tools
RUN ?= uv run

help:
	@echo "Available targets:"
	@echo "  make format  - Auto-fix lint issues and format code with Ruff"
	@echo "  make lint    - Run Ruff linter and formatting check (no file edits)"
	@echo "  make check   - Run lint checks and tests"
	@echo "  make run     - Start the NiceGUI app"
	@echo "  make clean   - Remove cache and build artifacts"

format:
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

check: lint test

test:
	$(RUN) pytest

run:
	$(RUN) python -m familytree.web.app

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} +