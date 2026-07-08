.PHONY: install test lint format run-morning run-evening dry-run clean clean-data release-prod

install:
	python3 -m venv venv
	./venv/bin/pip install -e ".[dev]"

test:
	./venv/bin/pytest -v

lint:
	./venv/bin/ruff check .

format:
	./venv/bin/ruff format .

run-morning:
	./venv/bin/python main.py --period morning

run-evening:
	./venv/bin/python main.py --period evening

dry-run:
	./venv/bin/python main.py --period morning --dry-run

release-prod: lint test
	bash deploy-prod.sh

clean:
	rm -rf venv/ .pytest_cache/ .ruff_cache/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} +

clean-data:
	rm -rf data/
