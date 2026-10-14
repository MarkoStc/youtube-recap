# 5. One packaged YAML config, merged with user overrides

Date: 2026-10-14
Status: Accepted

## Context

Limits (results per search, videos per recap, transcript length) were constants spread
across function signatures and module globals.

## Decision

- All defaults live in `src/youtube_recap/default.yaml`, shipped inside the package.
- A user file, named by `--config` or `YOUTUBE_RECAP_CONFIG`, holds only the keys it
  changes. It is deep-merged over the defaults.
- The merged data is validated into frozen pydantic models with `extra="forbid"`, so a
  typo such as `max_reslts` is an error, not a silent no-op.
- Pydantic models carry constraints (`gt=0`, allowed values) but no default values, so
  there is one source for each number.
- Tool parameters are `int | None`; `None` means "use the configured default".

## Consequences

- MCP clients see no hard-coded numbers in tool schemas; changing a default is a YAML edit.
- Every new setting needs a YAML entry and a model field. Missing either fails at startup,
  and `test_defaults_load_and_validate` catches it in CI.
