"""Thin wrapper around the Claude API so the graders can be tested with a fake model."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from youtube_recap.config import ModelConfig
from youtube_recap.errors import YouTubeRecapError

logger = logging.getLogger(__name__)

try:  # optional dependency (the `eval` extra)
    import anthropic

    _SDK_ERRORS: tuple[type[Exception], ...] = (anthropic.APIError,)
except ImportError:  # pragma: no cover - depends on installed extras
    _SDK_ERRORS = ()

# Server-side fallback: on a policy refusal the API re-runs the request on another model,
# chosen by refusal category. See the Claude API docs on refusals and fallback.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class EvaluationError(YouTubeRecapError):
    """The model refused, returned no text, or returned output that does not parse."""


@dataclass(frozen=True)
class Generation:
    text: str
    model: str  # the model that actually answered (differs from the request after a fallback)


class TextModel(Protocol):
    def generate(
        self, system: str, prompt: str, json_schema: dict[str, Any] | None = None
    ) -> Generation:
        """Return the model's text answer; with ``json_schema``, the text is JSON matching it."""
        ...


class AnthropicModel:
    """Calls the Messages API with one model configuration."""

    def __init__(self, config: ModelConfig, fallback: bool, client: Any | None = None) -> None:
        self._config = config
        self._fallback = fallback
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on installed extras
                raise EvaluationError(
                    "the evaluation needs the anthropic package: uv sync --extra eval"
                ) from exc
            # Credentials come from ANTHROPIC_API_KEY or an `ant auth login` profile.
            client = anthropic.Anthropic()
        # Any: tests pass a fake with the same create() shape as anthropic.Anthropic.
        self._client: Any = client

    def generate(
        self, system: str, prompt: str, json_schema: dict[str, Any] | None = None
    ) -> Generation:
        output_config: dict[str, Any] = {"effort": self._config.effort}
        if json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}
        extra: dict[str, Any] = {}
        if self._fallback:
            extra = {"betas": [_FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = self._client.beta.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config=output_config,
                **extra,
            )
        except _SDK_ERRORS as exc:
            raise EvaluationError(f"Claude API call failed: {exc}") from exc
        except TypeError as exc:
            # The SDK raises TypeError when it finds no credentials at request time.
            if "authentication" not in str(exc):
                raise
            raise EvaluationError(
                "no Claude API credentials: set ANTHROPIC_API_KEY or run `ant auth login`"
            ) from exc
        if response.stop_reason == "refusal":
            raise EvaluationError(f"{response.model} refused: {response.stop_details}")
        if response.stop_reason == "max_tokens":
            raise EvaluationError(f"{response.model} hit max_tokens={self._config.max_tokens}")
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise EvaluationError(f"{response.model} returned no text")
        logger.info(
            "%s: %d input / %d output tokens",
            response.model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return Generation(text=text, model=response.model)
