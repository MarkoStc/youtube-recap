# Connecting MCP clients

`youtube-recap` speaks MCP over stdio: the client starts the process and exchanges
JSON-RPC messages on its stdin and stdout. Every client below needs the same two things:
the command that starts the server, and (optionally) the `YOUTUBE_RECAP_CONFIG`
environment variable pointing at your config overrides.

In the examples, replace `/path/to/youtube-recap` with the folder you cloned.

## Claude Code

```sh
claude mcp add youtube-recap -- uv run --directory /path/to/youtube-recap youtube-recap
```

With a config file:

```sh
claude mcp add youtube-recap -e YOUTUBE_RECAP_CONFIG=/path/to/my-config.yaml \
  -- uv run --directory /path/to/youtube-recap youtube-recap
```

Check it with `claude mcp list`, then ask for example: *"Search YouTube for 'how
transformers work' and recap the top 3 videos."*

## Claude Desktop

Edit `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`,
Windows: `%APPDATA%\Claude\`) and restart the app:

```json
{
  "mcpServers": {
    "youtube-recap": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/youtube-recap", "youtube-recap"],
      "env": { "YOUTUBE_RECAP_CONFIG": "/path/to/my-config.yaml" }
    }
  }
}
```

Leave out `env` to use the defaults.

## MCP Inspector

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) is a web UI for
calling a server's tools by hand. It needs Node.js:

```sh
npx @modelcontextprotocol/inspector uv run --directory /path/to/youtube-recap youtube-recap
```

Open the URL it prints, choose **Tools → List Tools**, and call `search_videos` with a
query. Server logs appear in the Inspector's stderr panel (stdout is the protocol).

## Docker

```sh
docker build -t youtube-recap .
docker run -i --rm youtube-recap                 # -i keeps stdin open for MCP
```

To keep the cache between runs and pass a config file:

```sh
docker run -i --rm \
  -v youtube-recap-cache:/home/app/.cache/youtube-recap \
  -v /path/to/my-config.yaml:/config.yaml:ro -e YOUTUBE_RECAP_CONFIG=/config.yaml \
  youtube-recap
```

Any client can use the container as its command, for example in Claude Code:

```sh
claude mcp add youtube-recap -- docker run -i --rm youtube-recap
```

The CLI works in the container too: `docker run --rm youtube-recap search "lofi" -n 3`.

## Without an MCP client

The same features are available on the command line:

```sh
uv run youtube-recap search "how transformers work" -n 5
uv run youtube-recap transcript eMlx5fFNoYc -l en
uv run youtube-recap recap "how transformers work" -n 2 --json
uv run youtube-recap config show
```

## Config overrides

A config file only needs the keys it changes. Run `youtube-recap config show` for every
key and its current value. Example:

```yaml
transcripts:
  languages: [de, en]
  fallback: original
recap:
  max_transcript_chars: 12000
cache:
  enabled: false
logging:
  format: json
```
