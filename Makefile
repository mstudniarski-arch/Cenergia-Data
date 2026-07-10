.PHONY: test lint fmt ingest transform backtest train-artifact snapshot validate dashboard

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy src tests

fmt:
	uv run ruff format .

ingest:
	uv run python -m cenergia.pipeline ingest --start 2024-06-14

transform:
	uv run python -m cenergia.pipeline transform

backtest:
	uv run python -m cenergia.pipeline backtest --months 6

train-artifact:
	uv run python -m cenergia.pipeline train-artifact --holdout-days 30

snapshot:
	uv run python -m cenergia.pipeline snapshot

validate:
	uv run python -m cenergia.pipeline validate

dashboard:
	uv run streamlit run src/cenergia/dashboard/app.py
