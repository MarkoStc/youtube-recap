"""Tests for the recap-quality evaluation, with scripted fake models (no API calls)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from tests.conftest import FakeSearcher, FakeTranscripts
from youtube_recap.config import AppConfig, ConfigError, ModelConfig
from youtube_recap.evaluation.dataset import (
    Dataset,
    EvalCase,
    KeyPoint,
    load_dataset,
    quote_position,
)
from youtube_recap.evaluation.graders import Judge, Summarizer
from youtube_recap.evaluation.llm import AnthropicModel, EvaluationError, Generation
from youtube_recap.evaluation.runner import EvalRunner, render_markdown
from youtube_recap.service import RecapService

REPO = Path(__file__).resolve().parents[1]
VIDEO = "vvvvvvvvvvv"
CAP = 200


# ---- dataset -------------------------------------------------------------------------


def test_shipped_dataset_is_valid() -> None:
    dataset = load_dataset(REPO / "evals" / "recap_quality.yaml")
    assert len(dataset.cases) >= 5
    assert all(len(c.key_points) >= 5 for c in dataset.cases)
    assert len({c.video_id for c in dataset.cases}) == len(dataset.cases)


def test_bad_dataset_raises(tmp_path: Path) -> None:
    file = tmp_path / "d.yaml"
    file.write_text("cases: []\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid dataset"):
        load_dataset(file)
    with pytest.raises(ConfigError, match="cannot read"):
        load_dataset(tmp_path / "missing.yaml")


def test_quote_position_ignores_case_and_whitespace() -> None:
    assert quote_position("Hello\n  World  again", "hello world") == 0
    assert quote_position("abc", "zzz") is None


# ---- Anthropic wrapper ---------------------------------------------------------------


@dataclass
class FakeMessages:
    response: Any
    requests: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self.response


def _response(text: str = "ok", stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        stop_details=None,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


def _client(response: Any) -> tuple[Any, FakeMessages]:
    messages = FakeMessages(response)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


MODEL = ModelConfig(model="claude-opus-5-5", effort="medium", max_tokens=1000)


def test_anthropic_model_builds_request_with_schema_and_fallback() -> None:
    client, messages = _client(_response('{"a": 1}'))
    generation = AnthropicModel(MODEL, fallback=True, client=client).generate(
        "sys", "prompt", {"type": "object"}
    )
    assert generation == Generation(text='{"a": 1}', model="claude-opus-5-5")
    (request,) = messages.requests
    assert request["model"] == "claude-opus-5-5"
    assert request["system"] == "sys"
    assert request["messages"] == [{"role": "user", "content": "prompt"}]
    assert request["output_config"] == {
        "effort": "medium",
        "format": {"type": "json_schema", "schema": {"type": "object"}},
    }
    assert request["fallbacks"] == "default"
    assert request["betas"] == ["server-side-fallback-2026-07-01"]


def test_anthropic_model_without_fallback_or_schema() -> None:
    client, messages = _client(_response())
    AnthropicModel(MODEL, fallback=False, client=client).generate("sys", "prompt")
    (request,) = messages.requests
    assert "fallbacks" not in request and "betas" not in request
    assert request["output_config"] == {"effort": "medium"}


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_response(stop_reason="refusal"), "refused"),
        (_response(stop_reason="max_tokens"), "max_tokens"),
        (_response(text="  "), "no text"),
    ],
)
def test_anthropic_model_rejects_unusable_responses(response: Any, message: str) -> None:
    client, _ = _client(response)
    with pytest.raises(EvaluationError, match=message):
        AnthropicModel(MODEL, fallback=False, client=client).generate("s", "p")


class RaisingMessages:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def create(self, **kwargs: Any) -> Any:
        raise self.error


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (TypeError("Could not resolve authentication method."), "no Claude API credentials"),
        (
            anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")),
            "Claude API call failed",
        ),
    ],
)
def test_anthropic_model_translates_sdk_errors(error: Exception, message: str) -> None:
    client = SimpleNamespace(beta=SimpleNamespace(messages=RaisingMessages(error)))
    with pytest.raises(EvaluationError, match=message):
        AnthropicModel(MODEL, fallback=False, client=client).generate("s", "p")


def test_anthropic_model_does_not_hide_other_type_errors() -> None:
    client = SimpleNamespace(beta=SimpleNamespace(messages=RaisingMessages(TypeError("bug"))))
    with pytest.raises(TypeError, match="bug"):
        AnthropicModel(MODEL, fallback=False, client=client).generate("s", "p")


# ---- graders -------------------------------------------------------------------------


class ScriptedModel:
    """Summarizer: echoes the material. Judge: a point is covered if its text is in the summary."""

    def __init__(self, name: str = "fake-model") -> None:
        self.name = name
        self.calls: list[tuple[str, str]] = []

    def generate(
        self, system: str, prompt: str, json_schema: dict[str, Any] | None = None
    ) -> Generation:
        self.calls.append((system, prompt))
        if json_schema is None:
            return Generation(text=prompt, model=self.name)
        summary = prompt.split("<summary>\n", 1)[1].split("\n</summary>", 1)[0].lower()
        numbered = prompt.split("<key_points>\n", 1)[1].split("\n</key_points>", 1)[0]
        verdicts = []
        for line in numbered.splitlines():
            index, text = line.split(". ", 1)
            verdicts.append(
                {"key_point": int(index), "covered": text.lower() in summary, "reason": "x"}
            )
        return Generation(text=json.dumps({"verdicts": verdicts[::-1]}), model=self.name)


class ConstantModel:
    def __init__(self, text: str) -> None:
        self.text = text

    def generate(
        self, system: str, prompt: str, json_schema: dict[str, Any] | None = None
    ) -> Generation:
        return Generation(text=self.text, model="m")


def test_summarizer_puts_word_limit_in_system_prompt() -> None:
    model = ScriptedModel()
    assert Summarizer(model, max_words=42).summarize(" text ").text == "text"
    assert "at most 42 words" in model.calls[0][0]


def test_judge_returns_verdicts_in_key_point_order() -> None:
    points = [KeyPoint(text="alpha", quote="a"), KeyPoint(text="omega", quote="o")]
    judgement = Judge(ScriptedModel("judge-x")).judge("only alpha here", points)
    assert [v.covered for v in judgement.verdicts] == [True, False]
    assert judgement.model == "judge-x"


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"verdicts": [{"key_point": 1, "covered": true, "reason": "r"}]}',  # one missing
        '{"other": []}',
    ],
)
def test_judge_rejects_malformed_output(text: str) -> None:
    points = [KeyPoint(text="a", quote="a"), KeyPoint(text="b", quote="b")]
    with pytest.raises(EvaluationError):
        Judge(ConstantModel(text)).judge("s", points)


# ---- runner and report ---------------------------------------------------------------


@pytest.fixture
def eval_service(config: AppConfig) -> RecapService:
    # "alpha" sits inside the recap cap, "omega" only after it.
    text = "alpha " + "filler " * 60 + "omega"
    recap = config.recap.model_copy(update={"max_transcript_chars": CAP})
    small = config.model_copy(update={"recap": recap})
    return RecapService(small, FakeSearcher(), FakeTranscripts(texts={VIDEO: text}))


DATASET = Dataset(
    cases=(
        EvalCase(
            video_id=VIDEO,
            title="Test video",
            key_points=(
                KeyPoint(text="alpha", quote="alpha"),
                KeyPoint(text="omega", quote="omega"),
                KeyPoint(text="never said", quote="not in transcript"),
            ),
        ),
    )
)


def test_runner_compares_recap_and_full(eval_service: RecapService) -> None:
    run = EvalRunner(eval_service, Summarizer(ScriptedModel(), 100), Judge(ScriptedModel())).run(
        DATASET
    )
    recap, full = run.results
    assert (recap.condition, full.condition) == ("recap", "full")
    assert [p.location for p in recap.points] == ["kept", "cut", "unknown"]
    assert [p.covered for p in recap.points] == [True, False, False]
    assert [p.covered for p in full.points] == [True, True, False]
    assert "[transcript cut after 200 characters]" in recap.summary
    assert full.material_chars == full.transcript_chars
    assert run.max_transcript_chars == CAP


def test_runner_single_condition(eval_service: RecapService) -> None:
    runner = EvalRunner(eval_service, Summarizer(ScriptedModel(), 100), Judge(ScriptedModel()))
    run = runner.run(DATASET, ("full",))
    assert [r.condition for r in run.results] == ["full"]


def test_markdown_report(eval_service: RecapService) -> None:
    runner = EvalRunner(eval_service, Summarizer(ScriptedModel(), 100), Judge(ScriptedModel()))
    table = render_markdown(runner.run(DATASET))
    assert "| recap | 33% (1/3) | 100% (1/1) | 0% (0/1) |" in table
    assert "| full | 67% (2/3) | 100% (1/1) | 100% (1/1) |" in table
    assert "| Test video | " in table
    assert "Models: fake-model." in table
