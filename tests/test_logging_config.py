"""Tests for centralized logging configuration."""

import json
import logging
import os
from unittest.mock import patch

import pytest

from src.logging_config import JSONFormatter, configure_logging


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Reset root logger state after each test."""
    root = logging.getLogger()
    original_level = root.level
    original_handlers = root.handlers[:]
    yield
    root.setLevel(original_level)
    root.handlers = original_handlers


class TestConfigureLogging:
    """Tests for configure_logging()."""

    def test_defaults_to_info_text(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        assert not isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_log_level_from_env(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=True):
            configure_logging()
        assert logging.getLogger().level == logging.DEBUG

    def test_log_level_warning(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}, clear=True):
            configure_logging()
        assert logging.getLogger().level == logging.WARNING

    def test_level_override_takes_precedence(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}, clear=True):
            configure_logging(level_override="DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_invalid_level_falls_back_to_info(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "NOTREAL"}, clear=True):
            configure_logging()
        assert logging.getLogger().level == logging.INFO

    def test_json_format(self):
        with patch.dict(os.environ, {"LOG_FORMAT": "json"}, clear=True):
            configure_logging()
        root = logging.getLogger()
        assert isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_text_format_explicit(self):
        with patch.dict(os.environ, {"LOG_FORMAT": "text"}, clear=True):
            configure_logging()
        root = logging.getLogger()
        assert not isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_clears_existing_handlers(self):
        root = logging.getLogger()
        root.addHandler(logging.StreamHandler())
        root.addHandler(logging.StreamHandler())
        assert len(root.handlers) >= 2

        with patch.dict(os.environ, {}, clear=True):
            configure_logging()
        assert len(root.handlers) == 1

    def test_suppresses_noisy_third_party_loggers(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_logging()
        for name in ("googleapiclient", "google.auth", "urllib3", "openai", "httpx"):
            assert logging.getLogger(name).level == logging.WARNING


class TestJSONFormatter:
    """Tests for JSONFormatter."""

    def test_produces_valid_json(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello %s",
            args=("world",),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Hello world"
        assert "timestamp" in data
        assert "exception" not in data

    def test_includes_exception_info(self):
        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Something failed",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "ERROR"
        assert data["message"] == "Something failed"
        assert "exception" in data
        assert "ValueError: test error" in data["exception"]

    def test_timestamp_is_iso_format(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        # ISO format ends with timezone info
        assert "T" in data["timestamp"]
        assert "+" in data["timestamp"] or "Z" in data["timestamp"]
