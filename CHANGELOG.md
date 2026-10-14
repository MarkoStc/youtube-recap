# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Test suite with fake YouTube backends, coverage, and strict mypy.
- GitHub Actions CI: lint, type check, tests on Python 3.11 to 3.13, dependency audit,
  Docker image build.
- Multi-stage Dockerfile running as a non-root user.
- pre-commit hooks, Makefile, LICENSE (MIT), contributing guide, issue and PR templates,
  Dependabot.
- Typed YAML configuration (`default.yaml` in the package, overrides through
  `YOUTUBE_RECAP_CONFIG`), validated with pydantic.
- Logging to stderr in text or JSON format.
- Retries with exponential backoff for timeouts, dropped connections and HTTP errors;
  request timeouts for search and transcripts.
- Input validation: empty queries and malformed video ids are rejected as tool errors.
- On-disk cache for search results (1 hour) and transcripts (7 days), configurable.
- Architecture decision records in `docs/adr/`.
- Transcript language fallback (`transcripts.fallback`): when no requested language
  exists, use YouTube's machine translation, else the original language. Output says
  which language was returned and whether it was translated.
- Recap output marks cut transcripts (`[transcript cut after N characters]`).
- Command-line interface: `search`, `transcript`, `recap` (text or `--json`), `cache
  clear|path`, `config show`, `--version`, `--config`. With no command it runs the MCP
  server, so existing client registrations keep working. `python -m youtube_recap` works too.
- Token-bucket rate limit shared by all requests to YouTube (default 2 per second,
  bursts of 5), configurable under `rate_limit`.

### Changed

- Code split into adapters, service, models and formatting (see ADR 4).
- Tool count parameters default to config values and are clamped to configured limits.
- A network failure on one video no longer fails a whole recap.
- The OS trust store is installed when the server starts, not at import time.
- Search results without a video id are dropped instead of listed as `id=None`.
- `yt-dlp` floor raised to 2026.7.4; locked versions of anyio, cryptography, pyjwt,
  urllib3 and yt-dlp upgraded past published advisories.
- uv setting `native-tls` renamed to `system-certs`.

### Fixed

- README setup command no longer contains a path from the author's machine.

## [0.1.0] - 2026-10-13

### Added

- MCP server with `search_videos`, `get_transcript` and `recap` tools.

[Unreleased]: https://github.com/MarkoStc/youtube-recap/compare/v0-original...HEAD
[0.1.0]: https://github.com/MarkoStc/youtube-recap/tree/v0-original
