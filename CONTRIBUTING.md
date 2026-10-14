# Contributing

## Setup

Requires [uv](https://docs.astral.sh/uv/). It installs the pinned Python (see `.python-version`).

```sh
uv sync
uv run pre-commit install
```

## Before you open a pull request

```sh
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest --cov
```

CI runs the same steps on Python 3.11, 3.12 and 3.13, builds the Docker image, and runs
`pip-audit` on the locked runtime dependencies.

Tests never call YouTube. Fakes for yt-dlp and youtube-transcript-api live in
`tests/conftest.py`. Add a fake there instead of calling the network from a test.

## Branches and commits

- One branch per change: `feat/...`, `fix/...`, `refactor/...`, `test/...`, `docs/...`,
  `ci/...`, `chore/...`.
- [Conventional Commits](https://www.conventionalcommits.org/): `fix: drop entries without an id`.
- Pull requests link their issue (`Closes #N`) and are squash-merged.
- Add a line under `Unreleased` in `CHANGELOG.md` for any change a user would notice.
