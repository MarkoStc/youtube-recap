"""Run the evaluation and render the results table.

Two conditions per video, each summarized by the same model and judged the same way:

- ``recap``: exactly the text the ``recap`` tool returns for that video (header, transcript
  cut at ``recap.max_transcript_chars``, cut marker).
- ``full``: the whole transcript, uncut. The gap between the two is what truncation costs.

Each key point is also tagged ``kept`` or ``cut`` by where its quote sits in the
transcript, so the report shows whether misses come from truncation or from summarizing.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from youtube_recap import formatting
from youtube_recap.evaluation.dataset import Dataset, EvalCase, quote_position
from youtube_recap.evaluation.graders import Judge, Summarizer
from youtube_recap.models import RecapItem, Transcript, Video
from youtube_recap.service import RecapService

logger = logging.getLogger(__name__)

Condition = Literal["recap", "full"]
CONDITIONS: tuple[Condition, ...] = ("recap", "full")


@dataclass(frozen=True)
class PointResult:
    text: str
    covered: bool
    reason: str
    location: Literal["kept", "cut", "unknown"]  # quote inside the recap's kept text?


@dataclass(frozen=True)
class CaseResult:
    video_id: str
    title: str
    condition: Condition
    transcript_chars: int
    material_chars: int
    summary: str
    summarizer_model: str
    judge_model: str
    points: list[PointResult]

    @property
    def covered(self) -> int:
        return sum(p.covered for p in self.points)


@dataclass(frozen=True)
class EvalRun:
    started_at: str
    max_transcript_chars: int
    results: list[CaseResult]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class EvalRunner:
    def __init__(self, service: RecapService, summarizer: Summarizer, judge: Judge) -> None:
        self._service = service
        self._summarizer = summarizer
        self._judge = judge

    def run(self, dataset: Dataset, conditions: Sequence[Condition] = CONDITIONS) -> EvalRun:
        started = datetime.now(UTC).isoformat(timespec="seconds")
        results: list[CaseResult] = []
        for case in dataset.cases:
            transcript = self._service.transcript(case.video_id)
            for condition in conditions:
                logger.info("eval %s [%s]", case.video_id, condition)
                results.append(self._run_case(case, transcript, condition))
        limit = self._service.config.recap.max_transcript_chars
        return EvalRun(started_at=started, max_transcript_chars=limit, results=results)

    def _material(self, case: EvalCase, transcript: Transcript, condition: Condition) -> str:
        if condition == "full":
            return transcript.text
        video = Video(case.video_id, case.title, "unknown", None, None)
        cut, truncated = self._service.cut_for_recap(transcript)
        return formatting.format_recap(case.title, [RecapItem(video, cut, truncated=truncated)])

    def _run_case(self, case: EvalCase, transcript: Transcript, condition: Condition) -> CaseResult:
        material = self._material(case, transcript, condition)
        summary = self._summarizer.summarize(material)
        judgement = self._judge.judge(summary.text, case.key_points)
        kept_text, _ = self._service.cut_for_recap(transcript)
        points = []
        for kp, verdict in zip(case.key_points, judgement.verdicts, strict=True):
            location: Literal["kept", "cut", "unknown"]
            if quote_position(kept_text.text, kp.quote) is not None:
                location = "kept"
            elif quote_position(transcript.text, kp.quote) is not None:
                location = "cut"
            else:
                logger.warning("quote not found in %s: %r", case.video_id, kp.quote)
                location = "unknown"
            points.append(PointResult(kp.text, verdict.covered, verdict.reason, location))
        return CaseResult(
            video_id=case.video_id,
            title=case.title,
            condition=condition,
            transcript_chars=len(transcript.text),
            material_chars=len(material),
            summary=summary.text,
            summarizer_model=summary.model,
            judge_model=judgement.model,
            points=points,
        )


def _pct(covered: int, total: int) -> str:
    return f"{100 * covered / total:.0f}% ({covered}/{total})" if total else "n/a"


def render_markdown(run: EvalRun) -> str:
    """Summary table by condition, split by where the key point sits, plus a per-video table."""
    conditions = [c for c in CONDITIONS if any(r.condition == c for r in run.results)]
    models = sorted(
        {r.summarizer_model for r in run.results} | {r.judge_model for r in run.results}
    )
    lines = [
        f"Run started {run.started_at}. Recap cap: {run.max_transcript_chars:,} characters. "
        f"Models: {', '.join(models)}.",
        "",
        "| Condition | All key points | Points in kept text | Points after the cut |",
        "| --- | --- | --- | --- |",
    ]
    for condition in conditions:
        points = [p for r in run.results if r.condition == condition for p in r.points]
        kept = [p for p in points if p.location == "kept"]
        cut = [p for p in points if p.location == "cut"]
        lines.append(
            f"| {condition} | {_pct(sum(p.covered for p in points), len(points))} "
            f"| {_pct(sum(p.covered for p in kept), len(kept))} "
            f"| {_pct(sum(p.covered for p in cut), len(cut))} |"
        )
    lines += ["", "| Video | Transcript chars | " + " | ".join(conditions) + " |"]
    lines.append("| --- | --- |" + " --- |" * len(conditions))
    by_video: dict[str, dict[str, CaseResult]] = {}
    for r in run.results:
        by_video.setdefault(r.video_id, {})[r.condition] = r
    for per_condition in by_video.values():
        first = next(iter(per_condition.values()))
        cells = [
            _pct(per_condition[c].covered, len(per_condition[c].points))
            if c in per_condition
            else "n/a"
            for c in conditions
        ]
        lines.append(f"| {first.title} | {first.transcript_chars:,} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
