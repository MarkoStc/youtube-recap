"""Recap-quality evaluation: summarize transcripts with an LLM, then judge key-point coverage.

Not part of the server path (see docs/adr/0003-client-side-summarization.md). Needs the
``eval`` extra (``uv sync --extra eval``) and Claude API credentials.
"""
