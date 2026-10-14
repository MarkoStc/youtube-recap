from __future__ import annotations

import io
import json
import logging

from youtube_recap.config import LoggingConfig
from youtube_recap.log import configure_logging


def test_text_logs_go_to_given_stream() -> None:
    stream = io.StringIO()
    configure_logging(LoggingConfig(level="INFO", format="text"), stream)
    logging.getLogger("youtube_recap.test").info("hello %s", "there")
    logging.getLogger("youtube_recap.test").debug("hidden")
    out = stream.getvalue()
    assert "INFO youtube_recap.test: hello there" in out
    assert "hidden" not in out


def test_json_logs_are_one_object_per_line() -> None:
    stream = io.StringIO()
    configure_logging(LoggingConfig(level="DEBUG", format="json"), stream)
    log = logging.getLogger("youtube_recap.test")
    log.debug("first")
    try:
        raise ValueError("bad")
    except ValueError:
        log.exception("second")
    first, second = (
        json.loads(line) for line in stream.getvalue().splitlines() if line.startswith("{")
    )
    assert first["message"] == "first"
    assert first["level"] == "DEBUG"
    assert second["logger"] == "youtube_recap.test"
    assert "ValueError: bad" in second["exception"]


def test_reconfiguring_replaces_the_handler() -> None:
    configure_logging(LoggingConfig(level="INFO", format="text"), io.StringIO())
    configure_logging(LoggingConfig(level="INFO", format="text"), io.StringIO())
    assert len(logging.getLogger("youtube_recap").handlers) == 1
