# 2. Verify TLS with the OS trust store

Date: 2026-10-14
Status: Accepted

## Context

The project was first developed on a network that intercepts TLS with a corporate root
certificate. That certificate is in the Windows certificate store but not in `certifi`,
the bundle that `requests` and yt-dlp use by default. Every HTTPS call failed with
`CERTIFICATE_VERIFY_FAILED`.

The first version called `truststore.inject_into_ssl()` at module import time, before
importing yt-dlp and youtube-transcript-api, with `# noqa: E402` on the imports.

## Decision

- Use [`truststore`](https://github.com/sethmlarson/truststore), which makes Python's `ssl`
  module verify against the OS store (Windows, macOS Keychain, or the Linux system bundle).
- Call it once in the entry point (`prepare_runtime`), not at import time. `inject_into_ssl`
  replaces `ssl.SSLContext` and also patches the references held by urllib3 and requests,
  and yt-dlp creates its SSL contexts per request, so import order does not matter.
- Make it a config switch, `network.use_os_trust_store` (default `true`).
- For uv itself, set `system-certs = true` under `[tool.uv]`.

## Consequences

- Importing the package has no global side effects; tests and library users are not
  affected.
- On a normal network the OS store and `certifi` agree, so behaviour is unchanged.
- Anyone who wants `certifi` behaviour sets `use_os_trust_store: false`.
