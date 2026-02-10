.PHONY: install install-dev lint format typecheck test test-cov test-integration run clean

install:
	uv pip install --system -r requirements.txt

install-dev: install
	uv pip install --system -e ".[dev]"

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

typecheck:
	mypy src/ --ignore-missing-imports --no-strict-optional --allow-untyped-defs

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=75

test-integration:
	pytest tests/integration/ -v -m integration

run:
	python app.py

clean:
	rm -rf .coverage htmlcov/ .mypy_cache/ .ruff_cache/ .pytest_cache/
	rm -rf dist/ build/ *.egg-info/ src/*.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
