# Recap quality evaluation

The server returns transcripts; an MCP client writes the recap (see
[ADR 3](../docs/adr/0003-client-side-summarization.md)). This harness measures how much
of a video a recap keeps, and how much of the loss comes from the server cutting each
transcript to `recap.max_transcript_chars` (8,000 characters by default).

## Method

For each video in [`recap_quality.yaml`](recap_quality.yaml), the harness fetches the
transcript through the normal pipeline and runs two conditions:

| Condition | What the summarizer reads |
| --- | --- |
| `recap` | Exactly what the `recap` tool returns for that video: header, transcript cut at the cap, cut marker |
| `full` | The whole transcript |

1. A **summarizer** model (stands in for the MCP client) writes a recap of at most
   `evaluation.summary_max_words` words (250 by default).
2. A **judge** model gets the recap and the video's reference key points and returns, as
   JSON that must match a schema, whether each key point is covered. It sees only the
   recap, not the transcript.
3. Each key point has a short verbatim `quote` from the transcript. If the quote is inside
   the text the recap keeps, the point is tagged `kept`, otherwise `cut`. The report splits
   coverage by that tag, so a reader can tell truncation losses from summarizing losses.

The score is **key-point coverage**: covered points divided by all points.

## What the numbers do and do not mean

- The reference key points were drafted by Claude Opus 5.5 from the full transcripts and
  have not been reviewed by a person. Review them before quoting any score.
- 6 videos and 54 key points is a small set. Differences of a few points between runs are
  noise; the `kept` versus `cut` split is the result worth reading.
- The judge is an LLM. Its `reason` field for every verdict is saved in the JSON results,
  so individual verdicts can be checked by hand.
- Both roles default to `claude-opus-5-5` (config `evaluation.summarizer` and
  `evaluation.judge`). With `server_side_fallback: true`, the API may answer a refused
  request with another model; the report lists every model that answered.

## Run it

Needs Claude API credentials (`ANTHROPIC_API_KEY`, or a profile from `ant auth login`).

```sh
uv sync --extra eval
uv run youtube-recap eval --limit 1          # one video, both conditions: 4 API calls
uv run youtube-recap eval                    # all 6 videos: 24 API calls
```

A full run sends about 150,000 characters of transcript in total (both conditions)
plus the judge prompts. Results go to `evals/results/`: `latest.md` (the tables) and
`run-<timestamp>.json` (every summary, verdict and reason).

## Results

No run has been recorded yet. The repository's README only shows numbers from a
`latest.md` that this command produced.
