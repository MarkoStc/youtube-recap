# 1. Record architecture decisions

Date: 2026-10-14
Status: Accepted

## Context

Some choices in this repo look odd without their reason (for example, why the server never
calls an LLM, or why TLS goes through `truststore`). The reasons get lost in commit messages.

## Decision

Record each decision that shapes the code as a short ADR (Architecture Decision Record) in
`docs/adr/`, numbered in order: context, decision, consequences. An ADR is not edited after
it is accepted; a later ADR supersedes it and says so.

## Consequences

Reviewers and future contributors can find the reason for a design in one place. Writing
one costs a few minutes per decision.
