# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

`youtube-recap` is an **MCP server** that searches YouTube, ranks videos by view count,
fetches their transcripts, and returns them so an MCP client (Claude) can summarize.
The server does retrieval; the *summarizing* happens client-side.

## Architecture

Requests flow one way: `server.py` (MCP tools) → `service.py` (`RecapService`) →
`youtube.py` adapters → yt-dlp / youtube-transcript-api. Results flow back as the
dataclasses in `models.py` and are turned into text by `formatting.py`.

- `service.py` holds the logic (ranking, clamping counts, truncation) and depends only on
  the `VideoSearcher` and `TranscriptSource` Protocols in `youtube.py`. Tests inject fakes
  through the constructor; there is no monkeypatching of libraries.
- `server.py`: `build_server(service)` registers the tools on a fresh `FastMCP`;
  `main()` installs the OS trust store, loads config and runs stdio.
- `config.py` + `default.yaml`: every limit and default lives in the packaged YAML.
  User files (`YOUTUBE_RECAP_CONFIG`) are deep-merged over it and validated into frozen
  pydantic models (`extra="forbid"`). Do not put numeric defaults in code or tool signatures;
  tool parameters are `int | None` and `None` means "use config".
- Adapters raise `TranscriptUnavailableError` (`errors.py`); tools turn it into a
  `[transcript unavailable: <id>: <reason>]` line instead of an MCP error, so one missing
  transcript never fails a whole recap.

## Environment / tooling

- **uv** for everything; **Python 3.11+** (`.python-version` pins 3.12 for dev).
- Dev deps: ruff, mypy (strict, pydantic plugin), pytest, pytest-cov, pre-commit.

## Commands

```sh
uv sync                     # install / update env + lockfile
uv run youtube-recap        # run the server over stdio
uv run ruff format .        # format
uv run ruff check .         # lint (must stay clean)
uv run mypy                 # strict type check (src + tests)
uv run pytest --cov         # tests; no network
uv run pytest tests/test_service.py::test_recap_keeps_top_videos_and_truncates  # one test
```

`tests/test_server.py` drives the tools through a real in-memory MCP client session
(`mcp.shared.memory.create_connected_server_and_client_session`); async tests use the
`anyio` marker. `make check` runs lint, mypy and tests (no `make` on Windows: run the
`uv` lines).

CI (`.github/workflows/ci.yml`) runs lint, mypy and pytest on Python 3.11 to 3.13, builds
the Docker image, and runs `pip-audit` on the exported lockfile. A failing audit means a
locked package has a known CVE: fix with `uv lock --upgrade-package <name>`.

## Hard constraints / gotchas

- **This network intercepts TLS.** uv trusts the system store through
  `system-certs = true` under `[tool.uv]` (the older name `native-tls` is deprecated).
  At runtime `main()` calls `truststore.inject_into_ssl()`; it patches `ssl`, urllib3 and
  requests in place, so import order does not matter (see `docs/adr/`).
- On this Windows machine, uv cannot extract the `pywin32` wheel (an `mcp` dependency):
  "Access is denied" when it renames the unpacked folder, likely antivirus. Workaround:
  `uv sync --inexact --no-install-package pywin32`, then `.venv\Scripts\python -m ensurepip`
  and `.venv\Scripts\python -m pip install pywin32==312`. After that use `uv run --no-sync`.
- "Most-viewed" means most-viewed among the first N `ytsearch` results (yt-dlp flat
  search, which reads metadata without loading each video page), not across all of
  YouTube. `recap` searches `max(search_pool, num_videos)` results, keeps the top
  `num_videos`.
- `pyproject.toml` sets `readme = "README.md"`, so README.md must exist for the build.
- On stdio, stdout carries the MCP protocol. Never `print`; log to stderr.

## Conventions

- Tool docstrings are shown to the model; keep them accurate when behaviour changes.
- `uv run pre-commit install` once; hooks run ruff, mypy and `uv lock --check`.
- Conventional Commits, one branch per change, CHANGELOG entry under `Unreleased`.
