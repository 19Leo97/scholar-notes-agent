.PHONY: install lint typecheck test check demo eval-retrieval

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check src tests

typecheck:
	mypy src

test:
	pytest -q

check: lint typecheck test

# Index the public demo vault (offline hash embeddings) and run a retrieval-only query
demo:
	research ingest examples/demo_vault --source demo
	research search "receptor NMDA coincidencia"

eval-retrieval:
	research eval retrieval
