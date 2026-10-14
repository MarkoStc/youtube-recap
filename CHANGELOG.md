# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-14

### Added

- Command-line interface: `search`, `transcript`, `recap` (text or `--json`),
  `cache clear|path`, `config show`, `eval`, `--version`, `--config`. With no command it
  runs the MCP server, so existing client registrations keep working.
  `python -m youtube_recap` works too.
- Typed YAML configuration (`default.yaml` in the package, overrides through `--config`
  or `YOUTUBE_RECAP_CONFIG`), validated with pydantic.
- Transcript language fallback (`transcripts.fallback`): when no requested language
  exists, use YouTube's machine translation, else the original language. Output says
  which language was returned and whether it was translated.
- On-disk cache for search results (1 hour) and transcripts (7 days), configurable.
- Token-bucket rate limit shared by all requests to YouTube (default 2 per second,
  bursts of 5), configurable.
- Retries with exponential backoff for timeouts, dropped connections and HTTP errors;
  request timeouts for search and transcripts.
- Input validation: empty queries and malformed video ids are rejected as tool errors.
- Logging to stderr in text or JSON format.
- Recap quality evaluation (`youtube-recap eval`, optional `eval` extra): 6 videos with
  54 reference key points, a summarizer and an LLM judge, comparing the recap tool's cut
  transcripts with full ones. See `evals/README.md`. No results recorded yet.
- Test suite (in-memory MCP client sessions for the tools, fakes for YouTube and Claude),
  strict mypy, coverage.
- GitHub Actions CI: lint, type check, tests on Python 3.11 to 3.13, Docker image build
  and smoke test, `pip-audit` on locked dependencies.
- Multi-stage Dockerfile running as a non-root user.
- pre-commit hooks, Makefile, MIT license, contributing guide, issue and PR templates,
  Dependabot, `.editorconfig`, `.env.example`.
- Documentation: client setup (`docs/clients.md`), architecture decision records
  (`docs/adr/`), rewritten README.

### Changed

- Code split into adapters, service, models and formatting (ADR 4).
- Tool count parameters default to config values and are clamped to configured limits.
- Recap headers show the transcript language, and cut transcripts end with
  `[transcript cut after N characters]`.
- Missing transcripts read `[transcript unavailable: <video id>: <reason>]`.
- A network failure on one video no longer fails a whole recap.
- The OS trust store is installed when the program starts, not at import time, and can be
  turned off (`network.use_os_trust_store`).
- `yt-dlp` floor raised to 2026.7.4; locked versions of anyio, cryptography, pyjwt,
  urllib3 and yt-dlp upgraded past published advisories.
- uv setting `native-tls` renamed to `system-certs`.

### Fixed

- `recap(num_videos=-1)` returned all but the last video; counts are now clamped to 1 or more.
- Search results without a video id are dropped instead of listed as `id=None`.
- README setup command no longer contains a path from the author's machine.
- Project description no longer says the server summarizes videos.

### Removed

- Fallback for youtube-transcript-api versions before 1.0 (the dependency already
  required 1.0).

## [0.1.0] - 2026-10-13

### Added

- MCP server with `search_videos`, `get_transcript` and `recap` tools.

[Unreleased]: https://github.com/MarkoStc/youtube-recap/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/MarkoStc/youtube-recap/compare/v0-original...v1.0.0
[0.1.0]: https://github.com/MarkoStc/youtube-recap/tree/v0-original
