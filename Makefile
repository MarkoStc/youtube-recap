.PHONY: install lint format typecheck test audit run docker-build check

IMAGE ?= youtube-recap:dev

install:  ## Create .venv from uv.lock and install the git hooks
	uv sync --locked
	uv run pre-commit install

lint:  ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format:  ## Apply formatting and safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy

test:
	uv run pytest --cov

audit:  ## Check locked runtime dependencies for known vulnerabilities
	uv export --locked --no-dev --no-emit-project --no-hashes --format requirements-txt > .audit-requirements.txt
	uvx pip-audit --requirement .audit-requirements.txt --no-deps --disable-pip
	rm -f .audit-requirements.txt

run:  ## Run the MCP server over stdio
	uv run youtube-recap

docker-build:
	docker build -t $(IMAGE) .

check: lint typecheck test  ## Everything CI runs, except the audit
