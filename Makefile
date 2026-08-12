.PHONY: install test lint format check-config run-morning run-evening dry-run clean clean-data

install:
	python3 -m venv venv
	./venv/bin/pip install -e ".[dev]"

test:
	./venv/bin/pytest -v

lint:
	./venv/bin/ruff check .

format:
	./venv/bin/ruff format .

check-config:
	./venv/bin/python -c 'from app.config import load_config; print(load_config())'

run-morning:
	./venv/bin/python main.py --period morning

run-evening:
	./venv/bin/python main.py --period evening

dry-run:
	./venv/bin/python main.py --period morning --dry-run


clean:
	rm -rf venv/ .pytest_cache/ .ruff_cache/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} +

clean-data:
	rm -rf data/
