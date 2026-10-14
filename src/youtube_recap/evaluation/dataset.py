"""The fixed evaluation set: videos and the reference key points a good recap should cover."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from youtube_recap.config import ConfigError


class KeyPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    # Short verbatim phrase from the transcript, used to locate the point.
    quote: str = Field(min_length=1)


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    key_points: tuple[KeyPoint, ...] = Field(min_length=1)


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cases: tuple[EvalCase, ...] = Field(min_length=1)


def load_dataset(path: Path) -> Dataset:
    """Read and validate a dataset YAML file."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read dataset {path}: {exc}") from exc
    try:
        return Dataset.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid dataset {path}:\n{exc}") from exc


def normalize(text: str) -> str:
    """Lower-case and collapse whitespace, for locating quotes in transcripts."""
    return " ".join(text.split()).lower()


def quote_position(transcript: str, quote: str) -> int | None:
    """Character offset of ``quote`` in the normalized transcript, or None if absent."""
    index = normalize(transcript).find(normalize(quote))
    return None if index < 0 else index
