"""Typed configuration loaded from YAML.

Every default lives in the packaged ``default.yaml``. A user file (``--config`` or the
``YOUTUBE_RECAP_CONFIG`` environment variable) only needs the keys it changes; it is deep-merged
over the defaults and then validated into frozen pydantic models.
"""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CONFIG_ENV_VAR = "YOUTUBE_RECAP_CONFIG"


class _Section(BaseModel):
    # Unknown keys are almost always typos; fail loudly instead of ignoring them.
    model_config = ConfigDict(extra="forbid", frozen=True)


class SearchConfig(_Section):
    default_results: int = Field(gt=0)
    max_results: int = Field(gt=0)


class RecapConfig(_Section):
    default_videos: int = Field(gt=0)
    max_videos: int = Field(gt=0)
    default_search_pool: int = Field(gt=0)
    max_transcript_chars: int = Field(gt=0)


class TranscriptConfig(_Section):
    languages: tuple[str, ...] = Field(min_length=1)
    fallback: Literal["translate", "original", "none"]


class RetryConfig(_Section):
    attempts: int = Field(ge=1)
    initial_backoff_seconds: float = Field(ge=0)
    max_backoff_seconds: float = Field(ge=0)
    multiplier: float = Field(ge=1)


class NetworkConfig(_Section):
    timeout_seconds: float = Field(gt=0)
    use_os_trust_store: bool
    retry: RetryConfig


class RateLimitConfig(_Section):
    enabled: bool
    requests_per_second: float = Field(gt=0)
    burst: int = Field(ge=1)


class CacheConfig(_Section):
    enabled: bool
    directory: Path
    search_ttl_seconds: float = Field(ge=0)
    transcript_ttl_seconds: float = Field(ge=0)

    @field_validator("directory")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        return value.expanduser()


class ModelConfig(_Section):
    model: str = Field(min_length=1)
    effort: Literal["low", "medium", "high", "xhigh", "max"]
    max_tokens: int = Field(gt=0)


class EvaluationConfig(_Section):
    summarizer: ModelConfig
    judge: ModelConfig
    summary_max_words: int = Field(gt=0)
    server_side_fallback: bool


class LoggingConfig(_Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]
    format: Literal["text", "json"]


class AppConfig(_Section):
    search: SearchConfig
    recap: RecapConfig
    transcripts: TranscriptConfig
    network: NetworkConfig
    rate_limit: RateLimitConfig
    cache: CacheConfig
    evaluation: EvaluationConfig
    logging: LoggingConfig


class ConfigError(ValueError):
    """The configuration file is missing, unreadable, or fails validation."""


def _read_yaml(text: str, source: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{source}: invalid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{source}: top level must be a mapping, got {type(data).__name__}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` with ``override`` applied; nested mappings merge, other values replace."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def default_config_text() -> str:
    """Return the packaged ``default.yaml`` as text."""
    return resources.files("youtube_recap").joinpath("default.yaml").read_text(encoding="utf-8")


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load defaults, merge the user file (``path`` or ``$YOUTUBE_RECAP_CONFIG``), validate."""
    data = _read_yaml(default_config_text(), "default.yaml")
    user_path = path or os.environ.get(CONFIG_ENV_VAR)
    if user_path:
        file = Path(user_path).expanduser()
        try:
            text = file.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read config file {file}: {exc}") from exc
        data = _deep_merge(data, _read_yaml(text, str(file)))
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration:\n{exc}") from exc
