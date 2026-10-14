# 4. Layers with Protocols and constructor injection

Date: 2026-10-14
Status: Accepted

## Context

The first version kept everything in `server.py`: module-level functions, a module-level
`FastMCP` instance, and direct calls into yt-dlp. Tests had to monkeypatch library classes.

## Decision

Split into layers, each depending only on the one below:

| Module | Knows about |
| --- | --- |
| `server.py` | MCP, `RecapService`, `formatting` |
| `service.py` | ranking, limits, truncation; the `VideoSearcher` and `TranscriptSource` Protocols |
| `youtube.py` | yt-dlp, youtube-transcript-api, retries, timeouts, error translation |
| `models.py` | plain frozen dataclasses shared by all layers |

Dependencies are passed to constructors (`RecapService(config, searcher, transcripts)`,
`build_server(service)`). There is no DI framework.

## Consequences

- Service tests use small fakes that implement the Protocols. Tool tests run the real MCP
  layer over an in-memory client session.
- Caching and rate limiting can wrap an adapter without touching the service.
- A second backend (for example the YouTube Data API) only needs a new adapter class.
