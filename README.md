# youtube-recap

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant **search
YouTube, pick the most relevant videos, pull their transcripts, and summarize them** —
all from a single chat request like *"find the best videos on X and give me a recap"*.

It exposes three tools over stdio:

| Tool | What it does |
| --- | --- |
| `search_videos(query, max_results=10)` | Search YouTube; returns matches ranked by view count with channel & duration. |
| `get_transcript(video_id, languages=["en"])` | Fetch the full plain-text transcript for one video. |
| `recap(query, num_videos=3, search_pool=10)` | Search, keep the most-viewed videos, and return their transcripts to summarize. |

The summarizing is done by the MCP client (e.g. Claude) reading the transcripts the
server returns.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```sh
uv sync
```

This creates `.venv/` and a committed `uv.lock` for reproducible installs.

## Dev workflow

```sh
uv run youtube-recap        # run the MCP server (stdio)
uv run ruff format .        # format
uv run ruff check .         # lint
uv run python -c "from youtube_recap import server; print(server.search_videos('lofi', 3))"  # smoke test
```

## Use it from Claude Code

Register the server. Replace `/path/to/youtube-recap` with the folder you cloned:

```sh
claude mcp add youtube-recap -- uv run --directory /path/to/youtube-recap youtube-recap
```

Then ask, e.g.: *"Search YouTube for 'how transformers work' and recap the top 3 videos."*

## Notes

- Search & metadata come from `yt-dlp` (no API key needed).
- Transcripts come from `youtube-transcript-api`; videos without captions return a
  clear placeholder rather than failing the whole recap.
