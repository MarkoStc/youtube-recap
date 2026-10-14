"""Command-line interface. With no command it runs the MCP server, as before.

youtube-recap                      run the MCP server over stdio (same as `serve`)
youtube-recap search QUERY         ranked search results
youtube-recap transcript VIDEO_ID  one transcript
youtube-recap recap QUERY          transcripts of the most-viewed results
youtube-recap cache clear|path     manage the on-disk cache
youtube-recap config show          print the effective configuration as YAML
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

import yaml

from youtube_recap import __version__, formatting
from youtube_recap.app import build_service, prepare_runtime
from youtube_recap.cache import DiskCache
from youtube_recap.config import (
    CONFIG_ENV_VAR,
    AppConfig,
    ConfigError,
    ModelConfig,
    load_config,
)
from youtube_recap.errors import InvalidInputError, YouTubeRecapError
from youtube_recap.service import RecapService

if TYPE_CHECKING:
    from youtube_recap.evaluation.llm import TextModel

ModelFactory = Callable[[ModelConfig, bool], "TextModel"]
DEFAULT_DATASET = Path("evals/recap_quality.yaml")
DEFAULT_RESULTS = Path("evals/results")

EXIT_OK = 0
EXIT_ERROR = 1  # YouTube failures, unavailable transcripts
EXIT_USAGE = 2  # bad arguments or configuration (argparse uses 2 as well)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="youtube-recap",
        description="Search YouTube, rank by views, and fetch transcripts to summarize.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        metavar="PATH",
        help=f"YAML file merged over the defaults (default: ${CONFIG_ENV_VAR})",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("serve", help="run the MCP server over stdio (the default)")

    search = sub.add_parser("search", help="list videos for a query, most viewed first")
    search.add_argument("query")
    search.add_argument("-n", "--max-results", type=int, help="number of results")
    search.add_argument("--json", action="store_true", help="print JSON instead of text")

    transcript = sub.add_parser("transcript", help="print the transcript of one video")
    transcript.add_argument("video_id")
    transcript.add_argument(
        "-l",
        "--language",
        action="append",
        dest="languages",
        metavar="CODE",
        help="preferred language code; repeat for fallbacks in order",
    )
    transcript.add_argument("--json", action="store_true", help="print JSON instead of text")

    recap = sub.add_parser("recap", help="transcripts of the most-viewed videos for a query")
    recap.add_argument("query")
    recap.add_argument("-n", "--num-videos", type=int, help="videos to keep")
    recap.add_argument("--pool", type=int, dest="search_pool", help="results to rank")
    recap.add_argument("--json", action="store_true", help="print JSON instead of text")

    cache = sub.add_parser("cache", help="manage the on-disk cache")
    cache.add_argument("action", choices=["clear", "path"])

    config = sub.add_parser("config", help="inspect the configuration")
    config.add_argument("action", choices=["show"])

    evaluate = sub.add_parser(
        "eval",
        help="score recap quality with an LLM judge (needs the eval extra and Claude API access)",
    )
    evaluate.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="key points YAML (default: %(default)s)",
    )
    evaluate.add_argument(
        "--out", type=Path, default=DEFAULT_RESULTS, help="results folder (default: %(default)s)"
    )
    evaluate.add_argument(
        "--condition",
        action="append",
        choices=["recap", "full"],
        dest="conditions",
        help="run only this condition; repeat for both (default: both)",
    )
    evaluate.add_argument("--limit", type=int, help="only the first N videos (for a cheap trial)")
    return parser


def _print_json(data: object, out: TextIO) -> None:
    json.dump(data, out, indent=2, ensure_ascii=False)
    out.write("\n")


def _cmd_search(args: argparse.Namespace, service: RecapService, out: TextIO) -> int:
    videos = service.search(args.query, args.max_results)
    if args.json:
        _print_json([asdict(v) | {"url": v.url} for v in videos], out)
    else:
        out.write(formatting.format_video_list(args.query, videos) + "\n")
    return EXIT_OK


def _cmd_transcript(args: argparse.Namespace, service: RecapService, out: TextIO) -> int:
    transcript = service.transcript(args.video_id, args.languages)
    if args.json:
        _print_json(asdict(transcript), out)
    else:
        requested = args.languages or service.config.transcripts.languages
        out.write(formatting.format_transcript(transcript, requested) + "\n")
    return EXIT_OK


def _cmd_recap(args: argparse.Namespace, service: RecapService, out: TextIO) -> int:
    items = service.recap(args.query, args.num_videos, args.search_pool)
    if args.json:
        _print_json([asdict(i) for i in items], out)
    else:
        out.write(formatting.format_recap(args.query, items) + "\n")
    return EXIT_OK


_SERVICE_COMMANDS: dict[str, Callable[[argparse.Namespace, RecapService, TextIO], int]] = {
    "search": _cmd_search,
    "transcript": _cmd_transcript,
    "recap": _cmd_recap,
}


def _cmd_eval(
    args: argparse.Namespace,
    config: AppConfig,
    service: RecapService,
    model_factory: ModelFactory,
    out: TextIO,
) -> int:
    # Imported here so the other commands work without the optional anthropic package.
    from youtube_recap.evaluation.dataset import Dataset, load_dataset
    from youtube_recap.evaluation.graders import Judge, Summarizer
    from youtube_recap.evaluation.runner import EvalRunner, render_markdown

    dataset = load_dataset(args.dataset)
    if args.limit is not None:
        dataset = Dataset(cases=dataset.cases[: max(1, args.limit)])
    ev = config.evaluation
    summarizer = Summarizer(
        model_factory(ev.summarizer, ev.server_side_fallback), ev.summary_max_words
    )
    judge = Judge(model_factory(ev.judge, ev.server_side_fallback))
    result = EvalRunner(service, summarizer, judge).run(
        dataset, tuple(args.conditions or ("recap", "full"))
    )
    table = render_markdown(result)
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = result.started_at.replace(":", "").replace("-", "")
    (args.out / f"run-{stamp}.json").write_text(
        json.dumps(result.to_json(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (args.out / "latest.md").write_text(table, encoding="utf-8")
    out.write(table)
    return EXIT_OK


def _anthropic_model(config: ModelConfig, fallback: bool) -> TextModel:
    from youtube_recap.evaluation.llm import AnthropicModel

    return AnthropicModel(config, fallback)


def _cmd_cache(args: argparse.Namespace, config: AppConfig, out: TextIO) -> int:
    cache = DiskCache(config.cache.directory)
    if args.action == "path":
        out.write(f"{cache.directory}\n")
    else:
        out.write(f"removed {cache.clear()} cached entries from {cache.directory}\n")
    return EXIT_OK


def _cmd_config(config: AppConfig, out: TextIO) -> int:
    yaml.safe_dump(config.model_dump(mode="json"), out, sort_keys=False)
    return EXIT_OK


def run(
    argv: Sequence[str] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
    service_factory: Callable[[AppConfig], RecapService] = build_service,
    serve: Callable[[AppConfig], None] | None = None,
    model_factory: ModelFactory = _anthropic_model,
) -> int:
    """Parse ``argv`` and run the command; return the process exit code.

    ``service_factory``, ``serve`` and ``model_factory`` are injectable so tests run
    without network, stdio or API calls.
    """
    out = out or sys.stdout
    err = err or sys.stderr
    args = _build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        err.write(f"error: {exc}\n")
        return EXIT_USAGE

    command = args.command or "serve"
    if command == "serve":
        if serve is None:
            from youtube_recap.server import serve as serve_stdio  # MCP only when serving

            serve = serve_stdio
        serve(config)
        return EXIT_OK
    if command == "cache":
        return _cmd_cache(args, config, out)
    if command == "config":
        return _cmd_config(config, out)

    prepare_runtime(config)
    try:
        if command == "eval":
            return _cmd_eval(args, config, service_factory(config), model_factory, out)
        return _SERVICE_COMMANDS[command](args, service_factory(config), out)
    except (InvalidInputError, ConfigError) as exc:
        err.write(f"error: {exc}\n")
        return EXIT_USAGE
    except YouTubeRecapError as exc:
        err.write(f"error: {exc}\n")
        return EXIT_ERROR


def main() -> None:
    """Console-script entry point."""
    sys.exit(run())
