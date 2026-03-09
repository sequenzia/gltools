"""Logging configuration for gltools.

Provides dual-format logging: human-readable Rich output for terminal,
structured JSON for file output. Supports configurable log levels with
WARNING as the default. All log output is sanitized to prevent token
and credential leaks.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.text import Text

# Root logger name for the gltools hierarchy
LOGGER_NAME = "gltools"

# Compiled regex patterns for sensitive data masking
_MASK_PATTERNS: list[re.Pattern[str]] = [
    # PRIVATE-TOKEN header values
    re.compile(r"(PRIVATE-TOKEN[:\s]+)\S+", re.IGNORECASE),
    # Authorization: Bearer token values
    re.compile(r"(Authorization[:\s]+Bearer\s+)\S+", re.IGNORECASE),
    # glpat- prefixed tokens anywhere
    re.compile(r"glpat-\S+"),
    # OAuth2 refresh tokens in key=value or JSON-like contexts
    re.compile(r'(refresh_token["\s:=]+)\S+', re.IGNORECASE),
    # Token-like values in URL query parameters (private_token, access_token, etc.)
    re.compile(r"([?&](?:private_token|access_token|token|job_token)=)[^&\s]+", re.IGNORECASE),
]

_MASK_REPLACEMENT = "[MASKED]"


def mask_sensitive_data(text: str) -> str:
    """Replace tokens and credentials in text with masked versions.

    Handles PRIVATE-TOKEN headers, Authorization Bearer tokens,
    glpat- prefixed tokens, OAuth2 refresh tokens, and token-like
    URL query parameters.
    """
    result = text
    for pattern in _MASK_PATTERNS:
        # Patterns with groups preserve the prefix and mask the value
        if pattern.groups:
            result = pattern.sub(rf"\1{_MASK_REPLACEMENT}", result)
        else:
            result = pattern.sub(_MASK_REPLACEMENT, result)
    return result

# Valid log level names mapped to logging constants
_VALID_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

_DEFAULT_LEVEL = logging.WARNING

# Sentinel attribute to identify handlers we installed
_HANDLER_TAG = "_gltools_handler"


class SensitiveDataFilter(logging.Filter):
    """Log filter that sanitizes tokens and credentials from all log output.

    Applied at the handler level so ALL log output is sanitized regardless
    of which logger emits the message. Masks sensitive values in the log
    message string, format args, and any extra fields.

    Designed to fail-open: if masking raises an exception, the original
    record is passed through unmodified so logging is never interrupted.
    """

    # Standard LogRecord attributes that should not be scanned as "extra" fields
    _STANDARD_ATTRS: frozenset[str] = frozenset({
        "name", "msg", "args", "created", "relativeCreated",
        "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "pathname", "filename", "module", "levelno", "levelname",
        "thread", "threadName", "process", "processName", "message",
        "msecs", "taskName",
    })

    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitize sensitive data in the log record. Always returns True."""
        with contextlib.suppress(Exception):
            self._mask_record(record)
        return True

    def _mask_record(self, record: logging.LogRecord) -> None:
        """Apply masking to message, args, and extra fields."""
        # Mask the message template
        if isinstance(record.msg, str):
            record.msg = mask_sensitive_data(record.msg)

        # Mask format args
        if record.args is not None:
            record.args = self._mask_args(record.args)

        # Mask extra fields (non-standard attributes)
        for key in list(record.__dict__):
            if key not in self._STANDARD_ATTRS and not key.startswith("_"):
                value = record.__dict__[key]
                if isinstance(value, str):
                    record.__dict__[key] = mask_sensitive_data(value)

    @staticmethod
    def _mask_args(
        args: tuple[object, ...] | dict[str, object] | object,
    ) -> tuple[object, ...] | dict[str, object] | object:
        """Mask sensitive data in log format arguments."""
        if isinstance(args, tuple):
            return tuple(
                mask_sensitive_data(a) if isinstance(a, str) else a
                for a in args
            )
        if isinstance(args, dict):
            return {
                k: mask_sensitive_data(v) if isinstance(v, str) else v
                for k, v in args.items()
            }
        # Single argument (not a tuple or dict)
        if isinstance(args, str):
            return (mask_sensitive_data(args),)
        return args


class RichFormatter(logging.Formatter):
    """Human-readable formatter using Rich for colored terminal output.

    Produces output in the format: [LEVEL] component: message
    Level colors: DEBUG=dim, INFO=blue, WARNING=yellow, ERROR=red.
    """

    _LEVEL_STYLES: dict[str, str] = {
        "DEBUG": "dim",
        "INFO": "blue",
        "WARNING": "yellow bold",
        "ERROR": "red bold",
    }

    def __init__(self) -> None:
        super().__init__()
        self._console = Console(stderr=True, force_terminal=None)

    def format(self, record: logging.LogRecord) -> str:
        style = self._LEVEL_STYLES.get(record.levelname, "")
        level_text = Text(f"[{record.levelname}]", style=style)

        # Use the logger name relative to gltools as the component
        component = record.name
        if component.startswith(f"{LOGGER_NAME}."):
            component = component[len(LOGGER_NAME) + 1 :]

        message_text = Text(f" {component}: {record.getMessage()}")

        combined = Text()
        combined.append_text(level_text)
        combined.append_text(message_text)

        # Render to string with markup/styles
        with self._console.capture() as capture:
            self._console.print(combined, highlight=False, end="")
        return capture.get()


class JSONFormatter(logging.Formatter):
    """Structured JSON formatter for file output.

    Produces one JSON object per line with fields:
    timestamp, level, logger, message, and any extra context.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include extra context if present (skip standard LogRecord attrs)
        standard_attrs = {
            "name", "msg", "args", "created", "relativeCreated",
            "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "pathname", "filename", "module", "levelno", "levelname",
            "thread", "threadName", "process", "processName", "message",
            "msecs", "taskName",
        }
        extra = {k: v for k, v in record.__dict__.items() if k not in standard_attrs and not k.startswith("_")}
        if extra:
            entry["extra"] = extra

        return json.dumps(entry, default=str)


def _parse_log_level(level: str | None) -> int:
    """Parse a log level string into a logging constant.

    Returns the corresponding logging level, or WARNING for
    empty, None, or invalid values. Emits a warning to stderr
    for invalid level strings.
    """
    if not level:
        return _DEFAULT_LEVEL

    upper = level.strip().upper()
    resolved = _VALID_LEVELS.get(upper)
    if resolved is not None:
        return resolved

    # Invalid level: warn and fall back to WARNING
    print(
        f"Warning: Invalid log level '{level}'. Valid levels: {', '.join(_VALID_LEVELS)}. Falling back to WARNING.",
        file=sys.stderr,
    )
    return _DEFAULT_LEVEL


def _remove_gltools_handlers(logger: logging.Logger) -> None:
    """Remove all handlers tagged as gltools handlers from a logger."""
    to_remove = [h for h in logger.handlers if getattr(h, _HANDLER_TAG, False)]
    for h in to_remove:
        logger.removeHandler(h)
        h.close()


def setup_logging(
    *,
    level: str | None = None,
    log_file: str | Path | None = None,
) -> logging.Logger:
    """Configure the gltools logger hierarchy.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
            Defaults to WARNING if None, empty, or invalid.
        log_file: Optional path for JSON log file output.
            Parent directories are created automatically.
            File permission errors produce a warning but don't crash.

    Returns:
        The configured gltools root logger.
    """
    log_level = _parse_log_level(level)
    logger = logging.getLogger(LOGGER_NAME)

    # Remove existing gltools handlers to prevent duplication
    _remove_gltools_handlers(logger)

    logger.setLevel(log_level)
    # Prevent propagation to the root logger to avoid duplicate output
    logger.propagate = False

    # Create the sensitive data filter (shared across all handlers)
    sensitive_filter = SensitiveDataFilter()

    # Terminal handler with Rich formatter
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(RichFormatter())
    console_handler.addFilter(sensitive_filter)
    setattr(console_handler, _HANDLER_TAG, True)
    logger.addHandler(console_handler)

    # File handler with JSON formatter (optional)
    if log_file is not None:
        _add_file_handler(logger, Path(log_file), log_level, sensitive_filter)

    return logger


def _add_file_handler(
    logger: logging.Logger,
    log_path: Path,
    log_level: int,
    sensitive_filter: SensitiveDataFilter | None = None,
) -> None:
    """Add a JSON file handler to the logger.

    Creates parent directories if needed. Handles permission errors
    gracefully by printing a warning to stderr.
    """
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(JSONFormatter())
        if sensitive_filter is not None:
            file_handler.addFilter(sensitive_filter)
        setattr(file_handler, _HANDLER_TAG, True)
        logger.addHandler(file_handler)
    except PermissionError:
        print(
            f"Warning: Cannot write to log file '{log_path}': permission denied. File logging disabled.",
            file=sys.stderr,
        )
    except OSError as exc:
        print(
            f"Warning: Cannot open log file '{log_path}': {exc}. File logging disabled.",
            file=sys.stderr,
        )


def get_logger(name: str) -> logging.Logger:
    """Get a logger in the gltools hierarchy.

    Args:
        name: Component name (e.g., 'client.http'). Will be
            prefixed with 'gltools.' automatically.

    Returns:
        A logger instance for the specified component.
    """
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
