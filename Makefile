.PHONY: check lint format typecheck schema test

check: lint typecheck schema test

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

schema:
	poetry run python manage.py spectacular --validate --fail-on-warn --file /dev/null
