"""Tests for the command-line interface, with the service replaced by fakes."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
import yaml

from tests.conftest import FakeSearcher, FakeTranscripts
from youtube_recap import __version__, cli
from youtube_recap.config import AppConfig
from youtube_recap.errors import YouTubeUnavailableError
from youtube_recap.service import RecapService


class Result:
    def __init__(self, code: int, out: str, err: str) -> None:
        self.code, self.out, self.err = code, out, err


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    # The CLI installs logging and the trust store; keep tests free of global changes.
    monkeypatch.setattr(cli, "prepare_runtime", lambda config: None)


def _run(*argv: str, searcher: FakeSearcher | None = None) -> Result:
    out, err = io.StringIO(), io.StringIO()
    served: list[AppConfig] = []

    def factory(config: AppConfig) -> RecapService:
        return RecapService(config, searcher or FakeSearcher(), FakeTranscripts())

    code = cli.run(list(argv), out, err, service_factory=factory, serve=served.append)
    if not argv or argv[0] == "serve":
        assert len(served) == 1
    return Result(code, out.getvalue(), err.getvalue())


def test_no_command_serves() -> None:
    assert _run().code == cli.EXIT_OK


def test_serve_command() -> None:
    assert _run("serve").code == cli.EXIT_OK


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        cli.run(["--version"])
    assert info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_search_text() -> None:
    result = _run("search", "q", "-n", "2")
    assert result.code == cli.EXIT_OK
    assert result.out.index("High") < result.out.index("Low")


def test_search_json() -> None:
    result = _run("search", "q", "--json")
    data = json.loads(result.out)
    assert data[0]["id"] == "bbbbbbbbbbb"
    assert data[0]["url"] == "https://youtu.be/bbbbbbbbbbb"


def test_transcript_with_languages() -> None:
    result = _run("transcript", "aaaaaaaaaaa", "-l", "de", "-l", "en")
    assert result.out == "hello world\n"


def test_transcript_json() -> None:
    data = json.loads(_run("transcript", "aaaaaaaaaaa", "--json").out)
    assert data["text"] == "hello world"
    assert data["translated_from"] is None


def test_transcript_unavailable_exits_with_error() -> None:
    result = _run("transcript", "zzzzzzzzzzz")
    assert result.code == cli.EXIT_ERROR
    assert "TranscriptsDisabled" in result.err


def test_invalid_video_id_is_a_usage_error() -> None:
    result = _run("transcript", "nope")
    assert result.code == cli.EXIT_USAGE
    assert "not a YouTube video id" in result.err


def test_recap_text_and_json() -> None:
    assert _run("recap", "q", "-n", "1").out.startswith("## High")
    data = json.loads(_run("recap", "q", "-n", "2", "--pool", "3", "--json").out)
    assert [item["video"]["title"] for item in data] == ["High", "Low"]
    assert data[0]["truncated"] is True


def test_network_failure_exits_with_error() -> None:
    class Down(FakeSearcher):
        def search(self, query: str, limit: int) -> list:  # type: ignore[type-arg]
            raise YouTubeUnavailableError("search failed: offline")

    result = _run("search", "q", searcher=Down())
    assert result.code == cli.EXIT_ERROR
    assert "offline" in result.err


def test_bad_config_is_a_usage_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("search:\n  nope: 1\n", encoding="utf-8")
    result = _run("--config", str(bad), "search", "q")
    assert result.code == cli.EXIT_USAGE
    assert "invalid configuration" in result.err


def test_config_show_prints_merged_yaml(tmp_path: Path) -> None:
    override = tmp_path / "c.yaml"
    override.write_text("recap:\n  max_videos: 4\n", encoding="utf-8")
    shown = yaml.safe_load(_run("--config", str(override), "config", "show").out)
    assert shown["recap"]["max_videos"] == 4
    assert "search" in shown


def test_cache_path_and_clear(tmp_path: Path) -> None:
    override = tmp_path / "c.yaml"
    cache_dir = tmp_path / "cache"
    override.write_text(f"cache:\n  directory: {cache_dir.as_posix()}\n", encoding="utf-8")
    (cache_dir / "search").mkdir(parents=True)
    (cache_dir / "search" / "x.json").write_text("{}", encoding="utf-8")
    assert _run("--config", str(override), "cache", "path").out.strip() == str(cache_dir)
    assert "removed 1" in _run("--config", str(override), "cache", "clear").out
