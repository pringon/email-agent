"""Centralized logging configuration for the email agent."""

import json
import logging
import os
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """JSON log formatter for log aggregator compatibility.

    Produces one JSON object per line (NDJSON) with fields:
    timestamp, level, logger, message, and optionally exception.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def configure_logging(level_override: str | None = None) -> None:
    """Configure logging based on environment variables.

    Args:
        level_override: If set, takes precedence over LOG_LEVEL env var.

    Environment variables:
        LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR).
            Defaults to INFO.
        LOG_FORMAT: Output format. "json" for JSON lines,
            anything else for human-readable. Defaults to "text".
    """
    level_name = (level_override or os.getenv("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    log_format = os.getenv("LOG_FORMAT", "text").lower()

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setLevel(level)

    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    root_logger.addHandler(handler)

    # Quiet down noisy third-party libraries
    for name in ("googleapiclient", "google.auth", "urllib3", "openai", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)
