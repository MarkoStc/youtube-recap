"""Tests for YAML config loading, merging and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from youtube_recap.config import CONFIG_ENV_VAR, ConfigError, load_config


def test_defaults_load_and_validate() -> None:
    config = load_config()
    assert config.search.default_results <= config.search.max_results
    assert config.recap.default_videos <= config.recap.max_videos
    assert config.transcripts.languages


def test_user_file_overrides_only_given_keys(tmp_path: Path) -> None:
    file = tmp_path / "c.yaml"
    file.write_text("recap:\n  max_transcript_chars: 123\n", encoding="utf-8")
    config = load_config(file)
    defaults = load_config()
    assert config.recap.max_transcript_chars == 123
    assert config.recap.default_videos == defaults.recap.default_videos
    assert config.search == defaults.search


def test_env_var_points_at_user_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "c.yaml"
    file.write_text("transcripts:\n  languages: [de, en]\n", encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV_VAR, str(file))
    assert load_config().transcripts.languages == ("de", "en")


def test_empty_user_file_keeps_defaults(tmp_path: Path) -> None:
    file = tmp_path / "c.yaml"
    file.write_text("", encoding="utf-8")
    assert load_config(file) == load_config()


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("search:\n  max_reslts: 5\n", "max_reslts"),  # typo
        ("recap:\n  max_videos: 0\n", "max_videos"),
        ("transcripts:\n  languages: []\n", "languages"),
        ("- a\n- b\n", "mapping"),
        ("search: [unclosed\n", "invalid YAML"),
    ],
)
def test_invalid_files_raise_config_error(tmp_path: Path, text: str, message: str) -> None:
    file = tmp_path / "c.yaml"
    file.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_config(file)


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml")


def test_config_is_immutable() -> None:
    config = load_config()
    with pytest.raises(ValueError):
        config.search.max_results = 1  # type: ignore[misc]


def test_cache_directory_expands_home(tmp_path: Path) -> None:
    file = tmp_path / "c.yaml"
    file.write_text("cache:\n  directory: ~/somewhere\n", encoding="utf-8")
    assert load_config(file).cache.directory == Path.home() / "somewhere"
