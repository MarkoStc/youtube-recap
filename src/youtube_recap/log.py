"""Logging setup. Everything goes to stderr: on stdio, stdout carries the MCP protocol."""

from __future__ import annotations

import json
import logging
import sys
from typing import TextIO

from youtube_recap.config import LoggingConfig

_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class JsonFormatter(logging.Formatter):
    """One JSON object per line: time, level, logger, message, and exception if any."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(config: LoggingConfig, stream: TextIO | None = None) -> None:
    """Route the ``youtube_recap`` loggers to ``stream`` (stderr by default)."""
    handler = logging.StreamHandler(stream or sys.stderr)
    formatter = JsonFormatter() if config.format == "json" else logging.Formatter(_TEXT_FORMAT)
    handler.setFormatter(formatter)
    package_logger = logging.getLogger("youtube_recap")
    package_logger.handlers[:] = [handler]
    package_logger.setLevel(config.level)
    package_logger.propagate = False
