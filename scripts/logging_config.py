"""Application-wide rotating logs stored in the user's Local AppData."""

from __future__ import annotations

import logging
import faulthandler
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "CCTVLogAnalyzer"
LOGGER_NAME = "cctv_log_analyzer"
_NATIVE_FAULT_STREAM = None


def enable_native_fault_log():
    """Keep a real file descriptor alive even for a console-less executable."""
    global _NATIVE_FAULT_STREAM
    if _NATIVE_FAULT_STREAM is None:
        stream = (log_dir() / 'native-crash.log').open('ab', buffering=0)
        try:
            faulthandler.enable(file=stream, all_threads=True)
        except Exception:
            stream.close()
            raise
        _NATIVE_FAULT_STREAM = stream


def log_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    directory = base / APP_NAME / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class _ErrorOnly(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.ERROR


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_dvr_configured", False):
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(threadName)s | "
        "%(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    app_handler = RotatingFileHandler(
        log_dir() / "app.log", maxBytes=5 * 1024 * 1024,
        backupCount=5, encoding="utf-8")
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(formatter)
    logger.addHandler(app_handler)

    error_handler = RotatingFileHandler(
        log_dir() / "error.log", maxBytes=5 * 1024 * 1024,
        backupCount=5, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(_ErrorOnly())
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
    logger._dvr_configured = True
    logger.info("Logging initialized | python=%s | executable=%s",
                sys.version.split()[0], sys.executable)
    try:
        enable_native_fault_log()
    except (OSError, RuntimeError) as exc:
        logger.warning('Native fault diagnostics unavailable: %s', exc)
    return logger


def install_exception_hook(logger: logging.Logger):
    previous = sys.excepthook

    def handle(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Unhandled application exception", exc_info=(
            exc_type, exc_value, exc_traceback))
        previous(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle
