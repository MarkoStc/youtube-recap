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

### Changed

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
