.PHONY: test lint fmt ingest transform backtest train-artifact snapshot dashboard

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy src tests

fmt:
	uv run ruff format .

# pipeline targets are wired in Task 12; keep stubs failing loudly until then
ingest transform backtest train-artifact snapshot:
	@echo "wired in Task 12" && exit 1

dashboard:
	uv run streamlit run src/cenergia/dashboard/app.py
