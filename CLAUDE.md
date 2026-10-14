# CLAUDE.md

Context for future agent sessions working on this repo.

## Purpose

`youtube-recap` is an **MCP server** that searches YouTube, ranks videos by view count,
fetches their transcripts, and returns them so an MCP client (Claude) can summarize.
The server does retrieval; the *summarizing* happens client-side.

## Layout

```
pyproject.toml          project metadata, deps, ruff + uv config
uv.lock                 committed lockfile
src/youtube_recap/
  __init__.py           re-exports main()
  server.py             FastMCP server + the three tools
README.md               user-facing docs
```

## Environment / tooling

- **uv** for everything; **Python 3.11+** (`.venv` built on 3.12).
- Runtime deps: `mcp` (FastMCP), `yt-dlp`, `youtube-transcript-api`, `truststore`.
- Dev deps: `ruff` (lint + format).

## Command cheat-sheet

```sh
uv sync                     # install / update env + lockfile
uv run youtube-recap        # run the server over stdio
uv run ruff format .        # format
uv run ruff check .         # lint (must stay clean)
uv run mypy                 # strict type check (src + tests)
uv run pytest --cov         # tests; network is faked in tests/conftest.py
uv run pytest tests/test_server.py::test_recap_keeps_top_videos_and_truncates  # one test
```

CI (`.github/workflows/ci.yml`) runs the same lint, mypy and pytest steps on Python
3.11 to 3.13, plus `pip-audit` on the exported lockfile. A failing audit means a locked
package has a known CVE: fix with `uv lock --upgrade-package <name>`.

Smoke test (no MCP client needed — call a tool function directly):

```sh
uv run python -c "from youtube_recap import server; print(server.search_videos('lofi', 3))"
```

## Hard constraints / gotchas

- **This network intercepts TLS.** uv fails with `invalid peer certificate: UnknownIssuer`
  unless it trusts the system cert store. Handled via `system-certs = true` under `[tool.uv]`
  in `pyproject.toml` (the older name `native-tls` is deprecated in uv 0.12). Keep it.
- On this Windows machine, uv cannot extract the `pywin32` wheel (an `mcp` dependency):
  "Access is denied" when it renames the unpacked folder, likely antivirus. Workaround:
  `uv sync --no-install-package pywin32`, then `.venv\Scripts\python -m ensurepip` and
  `.venv\Scripts\python -m pip install pywin32==312`. After that use `uv run --no-sync`.
- The same TLS problem hits Python at runtime. `server.py` calls `truststore.inject_into_ssl()`
  before importing `yt_dlp` or `youtube_transcript_api`, so they use the OS trust store. Keep
  that call above those imports (hence the `# noqa: E402` markers); ruff's import sorting
  must not move them.
- "Most-viewed" means most-viewed among the first N `ytsearch` results (yt-dlp search
  with `extract_flat`, which reads metadata without loading each video page), not across
  all of YouTube. `recap` searches `max(search_pool, num_videos)` results, then keeps the top
  `num_videos`.
- `pyproject.toml` sets `readme = "README.md"`, so **README.md must exist before
  `uv sync`** can build the project, or hatchling errors out.
- Transcripts use the `youtube-transcript-api` >=1.0 instance API (`.fetch`); missing
  captions return a `[transcript unavailable: ...]` placeholder instead of raising.
- `recap` truncates each transcript to `_MAX_TRANSCRIPT_CHARS` (8000) to bound token use.

## Conventions

- Public MCP tools are the `@mcp.tool()`-decorated functions in `server.py`; helpers are
  module-private (`_name`). Keep tool docstrings useful — the client shows them to the model.
- `uv run pre-commit install` once; the hooks run ruff, mypy and `uv lock --check`.
  `make check` runs lint, mypy and tests (Linux/macOS; on Windows run the `uv` lines).
