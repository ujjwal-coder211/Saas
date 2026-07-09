"""
src/utils/logger.py

Structured JSON logging so output can be shipped straight into
ELK / Datadog / any log-aggregation pipeline without a custom parser.
"""

import json
import logging
import sys
import time


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def get_logger(name: str, level: str = "INFO", json_output: bool = True,
                log_file: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = JsonFormatter() if json_output else PlainFormatter()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def log_with_fields(logger: logging.Logger, level: str, message: str, **fields):
    """Log a message with structured extra fields (shows up in JSON output)."""
    getattr(logger, level.lower())(message, extra={"extra_fields": fields})
