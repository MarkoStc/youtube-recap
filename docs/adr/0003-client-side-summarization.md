# 3. The server retrieves; the MCP client summarizes

Date: 2026-10-14
Status: Accepted

## Context

A "recap" needs two steps: get the transcripts, then write a summary. The server could call
an LLM API itself, or return the transcripts and let the MCP client (Claude) summarize.

## Decision

The server returns text only. It never calls an LLM and needs no API key.

## Consequences

- No secrets in the server, no per-call LLM cost, and the summary uses whatever model and
  instructions the user already has in their client.
- The client's context window limits how much transcript text is useful, so the server
  caps each transcript (`recap.max_transcript_chars`) and the number of videos.
- Recap quality depends on the client model. Measuring it needs a separate tool that calls
  a model itself; such a tool stays out of the server path and its dependencies stay
  optional.
