.PHONY: check lint format typecheck test

check: lint typecheck test

lint:
	poetry run python -m ruff check .
	poetry run python -m ruff format --check .

format:
	poetry run python -m ruff check --fix .
	poetry run python -m ruff format .

typecheck:
	poetry run python -m mypy
	poetry run python -m pyright

test:
	poetry run python -m pytest
