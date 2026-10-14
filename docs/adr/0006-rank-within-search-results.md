# 6. Rank by views within the first N search results

Date: 2026-10-14
Status: Accepted

## Context

"Recap the best videos on X" needs a ranking. YouTube's own search order mixes relevance,
recency and personalisation. The YouTube Data API can sort by view count but needs an API
key and has a daily quota.

## Decision

Use yt-dlp's `ytsearchN:` with flat extraction (`extract_flat`: one search page request,
no per-video page loads) and sort those N results by `view_count`, unknown counts last.
`recap` searches `search_pool` results and keeps the top `num_videos`.

## Consequences

- No API key, and one request per search.
- "Most viewed" means most viewed among the first N results for the query, not across all
  of YouTube. Tool docstrings and the README say so.
- A larger `search_pool` gives a better ranking at the cost of a slower search.
