"""The two LLM roles: a summarizer that writes a recap, and a judge that checks key points."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from youtube_recap.evaluation.dataset import KeyPoint
from youtube_recap.evaluation.llm import EvaluationError, TextModel

SUMMARIZER_SYSTEM = (
    "You write recaps of YouTube videos for someone who has not watched them. You get the "
    "text an MCP tool returned: a header line and the video's transcript, which may be cut "
    "short. Recap the main ideas in the order the video presents them and keep specific "
    "facts, names and numbers. Use at most {max_words} words of plain prose. Write only "
    "the recap."
)

JUDGE_SYSTEM = (
    "You check whether a summary states given key points. A key point is covered if the "
    "summary states its main claim, in any wording. Mentioning the topic without the claim, "
    "or stating something that contradicts it, is not covered. Use only the summary; do not "
    "use your own knowledge of the subject. Return one verdict per key point, in order."
)

_VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key_point": {"type": "integer"},
                    "covered": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["key_point", "covered", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Summary:
    text: str
    model: str


@dataclass(frozen=True)
class Verdict:
    covered: bool
    reason: str


@dataclass(frozen=True)
class Judgement:
    verdicts: list[Verdict]
    model: str


class Summarizer:
    def __init__(self, model: TextModel, max_words: int) -> None:
        self._model = model
        self._system = SUMMARIZER_SYSTEM.format(max_words=max_words)

    def summarize(self, material: str) -> Summary:
        generation = self._model.generate(self._system, material)
        return Summary(text=generation.text.strip(), model=generation.model)


class Judge:
    def __init__(self, model: TextModel) -> None:
        self._model = model

    def judge(self, summary: str, key_points: Sequence[KeyPoint]) -> Judgement:
        """Return one verdict per key point, in the given order."""
        numbered = "\n".join(f"{i}. {kp.text}" for i, kp in enumerate(key_points, start=1))
        prompt = f"<summary>\n{summary}\n</summary>\n\n<key_points>\n{numbered}\n</key_points>"
        generation = self._model.generate(JUDGE_SYSTEM, prompt, _VERDICT_SCHEMA)
        verdicts = _parse_verdicts(generation.text, len(key_points))
        return Judgement(verdicts=verdicts, model=generation.model)


def _parse_verdicts(text: str, expected: int) -> list[Verdict]:
    try:
        raw = json.loads(text)["verdicts"]
        by_index = {int(v["key_point"]): Verdict(bool(v["covered"]), str(v["reason"])) for v in raw}
    except (ValueError, KeyError, TypeError) as exc:
        raise EvaluationError(f"judge output does not parse: {exc}: {text[:200]!r}") from exc
    if sorted(by_index) != list(range(1, expected + 1)):
        raise EvaluationError(
            f"judge returned verdicts for {sorted(by_index)}, expected 1..{expected}"
        )
    return [by_index[i] for i in range(1, expected + 1)]
