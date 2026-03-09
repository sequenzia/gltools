"""Tests for gltools logging configuration."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from gltools.logging import (
    LOGGER_NAME,
    JSONFormatter,
    RichFormatter,
    SensitiveDataFilter,
    _parse_log_level,
    get_logger,
    mask_sensitive_data,
    setup_logging,
)


class TestParseLogLevel:
    """Test log level parsing and fallback behavior."""

    def test_valid_debug(self) -> None:
        assert _parse_log_level("DEBUG") == logging.DEBUG

    def test_valid_info(self) -> None:
        assert _parse_log_level("INFO") == logging.INFO

    def test_valid_warning(self) -> None:
        assert _parse_log_level("WARNING") == logging.WARNING

    def test_valid_error(self) -> None:
        assert _parse_log_level("ERROR") == logging.ERROR

    def test_case_insensitive(self) -> None:
        assert _parse_log_level("debug") == logging.DEBUG
        assert _parse_log_level("Info") == logging.INFO
        assert _parse_log_level("wArNiNg") == logging.WARNING

    def test_none_falls_back_to_warning(self) -> None:
        assert _parse_log_level(None) == logging.WARNING

    def test_empty_string_falls_back_to_warning(self) -> None:
        assert _parse_log_level("") == logging.WARNING

    def test_invalid_falls_back_to_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = _parse_log_level("TRACE")
        assert result == logging.WARNING
        captured = capsys.readouterr()
        assert "Invalid log level" in captured.err
        assert "TRACE" in captured.err
        assert "Falling back to WARNING" in captured.err

    def test_whitespace_stripped(self) -> None:
        assert _parse_log_level("  DEBUG  ") == logging.DEBUG


class TestRichFormatter:
    """Test human-readable Rich formatter output."""

    def test_format_contains_level_and_message(self) -> None:
        formatter = RichFormatter()
        record = logging.LogRecord(
            name="gltools.client.http",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Request sent to /api/v4/projects",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "[INFO]" in output
        assert "client.http" in output
        assert "Request sent to /api/v4/projects" in output

    def test_format_strips_gltools_prefix(self) -> None:
        formatter = RichFormatter()
        record = logging.LogRecord(
            name="gltools.services.merge_request",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Resolving project",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "services.merge_request" in output
        # Should not have redundant "gltools." prefix in component
        assert "gltools.services" not in output

    def test_format_root_logger_name(self) -> None:
        formatter = RichFormatter()
        record = logging.LogRecord(
            name="gltools",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Something happened",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "[WARNING]" in output
        assert "gltools" in output

    def test_format_all_levels(self) -> None:
        formatter = RichFormatter()
        for level_name, level_no in [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
        ]:
            record = logging.LogRecord(
                name="gltools.test",
                level=level_no,
                pathname="",
                lineno=0,
                msg="test message",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            assert f"[{level_name}]" in output


class TestJSONFormatter:
    """Test structured JSON formatter output."""

    def _make_record(
        self,
        msg: str = "test message",
        name: str = "gltools.client.http",
        level: int = logging.INFO,
    ) -> logging.LogRecord:
        return logging.LogRecord(
            name=name,
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_produces_valid_json(self) -> None:
        formatter = JSONFormatter()
        record = self._make_record()
        output = formatter.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_required_fields_present(self) -> None:
        formatter = JSONFormatter()
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        assert "timestamp" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "message" in parsed

    def test_field_values(self) -> None:
        formatter = JSONFormatter()
        record = self._make_record(msg="hello world", name="gltools.config", level=logging.ERROR)
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "ERROR"
        assert parsed["logger"] == "gltools.config"
        assert parsed["message"] == "hello world"

    def test_timestamp_is_iso_format(self) -> None:
        formatter = JSONFormatter()
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        ts = parsed["timestamp"]
        # Should be parseable as ISO 8601
        assert "T" in ts
        assert "+" in ts or "Z" in ts or ts.endswith("+00:00")

    def test_extra_context_included(self) -> None:
        formatter = JSONFormatter()
        record = self._make_record()
        record.request_id = "abc-123"
        record.method = "GET"
        parsed = json.loads(formatter.format(record))
        assert "extra" in parsed
        assert parsed["extra"]["request_id"] == "abc-123"
        assert parsed["extra"]["method"] == "GET"

    def test_no_extra_when_none(self) -> None:
        formatter = JSONFormatter()
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        assert "extra" not in parsed


class TestSetupLogging:
    """Test setup_logging configuration behavior."""

    def _cleanup_logger(self) -> None:
        """Remove all handlers from the gltools logger."""
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()

    @pytest.fixture(autouse=True)
    def clean_logger(self) -> None:
        """Ensure a clean logger state before and after each test."""
        self._cleanup_logger()
        yield  # type: ignore[misc]
        self._cleanup_logger()

    def test_returns_logger(self) -> None:
        logger = setup_logging()
        assert isinstance(logger, logging.Logger)
        assert logger.name == LOGGER_NAME

    def test_default_level_is_warning(self) -> None:
        logger = setup_logging()
        assert logger.level == logging.WARNING

    def test_set_debug_level(self) -> None:
        logger = setup_logging(level="DEBUG")
        assert logger.level == logging.DEBUG

    def test_set_info_level(self) -> None:
        logger = setup_logging(level="INFO")
        assert logger.level == logging.INFO

    def test_set_error_level(self) -> None:
        logger = setup_logging(level="ERROR")
        assert logger.level == logging.ERROR

    def test_invalid_level_falls_back_to_warning(self) -> None:
        logger = setup_logging(level="INVALID")
        assert logger.level == logging.WARNING

    def test_console_handler_added(self) -> None:
        logger = setup_logging()
        stream_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) >= 1

    def test_console_handler_uses_rich_formatter(self) -> None:
        logger = setup_logging()
        stream_handlers = [
            h for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1
        assert isinstance(stream_handlers[0].formatter, RichFormatter)

    def test_no_handler_duplication(self) -> None:
        """Multiple calls to setup_logging should not duplicate handlers."""
        setup_logging()
        setup_logging()
        setup_logging()
        logger = logging.getLogger(LOGGER_NAME)
        # Should have exactly 1 console handler (no file handler)
        gltools_handlers = [h for h in logger.handlers if getattr(h, "_gltools_handler", False)]
        assert len(gltools_handlers) == 1

    def test_level_change_on_repeated_setup(self) -> None:
        """Repeated calls should update the log level."""
        logger = setup_logging(level="DEBUG")
        assert logger.level == logging.DEBUG
        logger = setup_logging(level="ERROR")
        assert logger.level == logging.ERROR

    def test_propagation_disabled(self) -> None:
        logger = setup_logging()
        assert logger.propagate is False


class TestFileHandler:
    """Test file handler configuration."""

    @pytest.fixture(autouse=True)
    def clean_logger(self) -> None:
        """Ensure a clean logger state before and after each test."""
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        yield  # type: ignore[misc]
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()

    def test_file_handler_added(self, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        logger = setup_logging(log_file=log_file)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_file_handler_uses_json_formatter(self, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        logger = setup_logging(log_file=log_file)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert isinstance(file_handlers[0].formatter, JSONFormatter)

    def test_file_handler_writes_valid_json_lines(self, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        logger.info("first message")
        logger.warning("second message")

        # Flush handlers
        for h in logger.handlers:
            h.flush()

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "timestamp" in parsed
            assert "level" in parsed
            assert "logger" in parsed
            assert "message" in parsed

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        log_file = tmp_path / "nested" / "deep" / "app.log"
        setup_logging(log_file=log_file)
        assert log_file.parent.exists()

    def test_permission_error_does_not_crash(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # Create a read-only directory to trigger permission error on file creation
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o444)
        log_file = restricted / "app.log"

        # Should not raise
        logger = setup_logging(log_file=log_file)
        assert logger is not None

        captured = capsys.readouterr()
        # Should warn about the permission issue
        assert "permission denied" in captured.err.lower() or "Cannot" in captured.err

        # Cleanup: restore permissions so pytest can clean up tmp_path
        restricted.chmod(0o755)

    def test_no_file_handler_when_no_path(self) -> None:
        logger = setup_logging()
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0

    def test_no_handler_duplication_with_file(self, tmp_path: Path) -> None:
        """Multiple calls should not duplicate file handlers."""
        log_file = tmp_path / "app.log"
        setup_logging(log_file=log_file)
        setup_logging(log_file=log_file)
        setup_logging(log_file=log_file)
        logger = logging.getLogger(LOGGER_NAME)
        gltools_handlers = [h for h in logger.handlers if getattr(h, "_gltools_handler", False)]
        # 1 console handler + 1 file handler = 2
        assert len(gltools_handlers) == 2


class TestGetLogger:
    """Test get_logger helper."""

    def test_returns_child_logger(self) -> None:
        logger = get_logger("client.http")
        assert logger.name == "gltools.client.http"

    def test_inherits_from_gltools(self) -> None:
        setup_logging(level="DEBUG")
        child = get_logger("services.mr")
        # Child should inherit the level from the parent
        assert child.getEffectiveLevel() == logging.DEBUG


class TestMaskSensitiveData:
    """Test the mask_sensitive_data function for each token pattern."""

    def test_mask_private_token_header(self) -> None:
        text = "PRIVATE-TOKEN: glpat-abc123xyz"
        result = mask_sensitive_data(text)
        assert "glpat-abc123xyz" not in result
        assert "[MASKED]" in result
        assert "PRIVATE-TOKEN:" in result

    def test_mask_private_token_header_case_insensitive(self) -> None:
        text = "private-token: my-secret-token"
        result = mask_sensitive_data(text)
        assert "my-secret-token" not in result
        assert "[MASKED]" in result

    def test_mask_authorization_bearer(self) -> None:
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
        result = mask_sensitive_data(text)
        assert "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "[MASKED]" in result
        assert "Authorization: Bearer" in result

    def test_mask_authorization_bearer_case_insensitive(self) -> None:
        text = "authorization: bearer some-oauth-token"
        result = mask_sensitive_data(text)
        assert "some-oauth-token" not in result
        assert "[MASKED]" in result

    def test_mask_glpat_prefix_token(self) -> None:
        text = "Token is glpat-secret123 in message"
        result = mask_sensitive_data(text)
        assert "glpat-secret123" not in result
        assert "[MASKED]" in result

    def test_mask_glpat_token_standalone(self) -> None:
        text = "glpat-xxxxxxxxxxxxxxxxxxxx"
        result = mask_sensitive_data(text)
        assert "glpat-" not in result
        assert result == "[MASKED]"

    def test_mask_oauth_refresh_token_json_style(self) -> None:
        text = '"refresh_token": "some-refresh-secret-value"'
        result = mask_sensitive_data(text)
        assert "some-refresh-secret-value" not in result
        assert "[MASKED]" in result

    def test_mask_oauth_refresh_token_key_value(self) -> None:
        text = "refresh_token=abc123secret"
        result = mask_sensitive_data(text)
        assert "abc123secret" not in result
        assert "[MASKED]" in result

    def test_mask_url_private_token_param(self) -> None:
        text = "https://gitlab.example.com/api/v4/projects?private_token=my-secret"
        result = mask_sensitive_data(text)
        assert "my-secret" not in result
        assert "?private_token=[MASKED]" in result

    def test_mask_url_access_token_param(self) -> None:
        text = "https://gitlab.example.com/api?access_token=tok123&per_page=20"
        result = mask_sensitive_data(text)
        assert "tok123" not in result
        assert "access_token=[MASKED]" in result
        assert "per_page=20" in result

    def test_mask_url_token_param(self) -> None:
        text = "GET /api/v4/projects?token=secret123&page=1"
        result = mask_sensitive_data(text)
        assert "secret123" not in result
        assert "?token=[MASKED]" in result
        assert "page=1" in result

    def test_mask_url_job_token_param(self) -> None:
        text = "/api/v4/jobs/artifacts?job_token=ci-token-value"
        result = mask_sensitive_data(text)
        assert "ci-token-value" not in result
        assert "job_token=[MASKED]" in result

    def test_non_sensitive_data_unchanged(self) -> None:
        text = "Normal log message about merge request #42"
        assert mask_sensitive_data(text) == text

    def test_url_without_token_params_unchanged(self) -> None:
        text = "GET /api/v4/projects/123/merge_requests?state=opened&per_page=20"
        assert mask_sensitive_data(text) == text

    def test_empty_string_unchanged(self) -> None:
        assert mask_sensitive_data("") == ""

    def test_multiple_tokens_in_same_message(self) -> None:
        text = "Headers: PRIVATE-TOKEN: secret1, Authorization: Bearer secret2"
        result = mask_sensitive_data(text)
        assert "secret1" not in result
        assert "secret2" not in result
        assert result.count("[MASKED]") >= 2

    def test_glpat_token_embedded_in_url(self) -> None:
        text = "https://gitlab.example.com/api/v4?private_token=glpat-mytoken123"
        result = mask_sensitive_data(text)
        assert "glpat-mytoken123" not in result
        assert "[MASKED]" in result

    def test_partial_match_does_not_corrupt(self) -> None:
        """Strings like 'private_tokenizer' should not be treated as token params."""
        text = "The private_tokenizer module loaded successfully"
        # This should not match because there's no = after it
        result = mask_sensitive_data(text)
        assert "private_tokenizer" in result


class TestSensitiveDataFilter:
    """Test the SensitiveDataFilter logging filter."""

    def _make_record(
        self,
        msg: str = "test message",
        args: tuple[object, ...] | dict[str, object] | None = None,
        level: int = logging.INFO,
    ) -> logging.LogRecord:
        record = logging.LogRecord(
            name="gltools.test",
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=args,
            exc_info=None,
        )
        return record

    def test_masks_private_token_in_msg(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(msg="Header PRIVATE-TOKEN: glpat-secret123")
        f.filter(record)
        assert "glpat-secret123" not in record.msg
        assert "[MASKED]" in record.msg

    def test_masks_bearer_token_in_msg(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(msg="Authorization: Bearer jwt-token-value")
        f.filter(record)
        assert "jwt-token-value" not in record.msg
        assert "[MASKED]" in record.msg

    def test_masks_glpat_in_msg(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(msg="Using token glpat-xyzabc123")
        f.filter(record)
        assert "glpat-xyzabc123" not in record.msg

    def test_masks_token_in_tuple_args(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(
            msg="Request to %s with token %s",
            args=("/api/v4/projects", "glpat-secret-in-args"),
        )
        f.filter(record)
        assert isinstance(record.args, tuple)
        assert "glpat-secret-in-args" not in str(record.args)

    def test_masks_token_in_dict_args(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(msg="Headers: %(header)s")
        # Set dict args directly on the record (LogRecord constructor doesn't accept dicts cleanly)
        record.args = {"header": "PRIVATE-TOKEN: my-secret"}
        f.filter(record)
        assert isinstance(record.args, dict)
        assert "my-secret" not in str(record.args)

    def test_masks_token_in_extra_fields(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(msg="API call")
        record.auth_header = "Authorization: Bearer oauth-token-value"
        f.filter(record)
        assert "oauth-token-value" not in record.auth_header

    def test_non_sensitive_msg_unchanged(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(msg="Normal log message")
        f.filter(record)
        assert record.msg == "Normal log message"

    def test_non_sensitive_args_unchanged(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(
            msg="Processing %s with %d items",
            args=("project/repo", 42),
        )
        f.filter(record)
        assert record.args == ("project/repo", 42)

    def test_non_sensitive_extra_unchanged(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(msg="test")
        record.request_id = "req-abc-123"
        record.method = "GET"
        f.filter(record)
        assert record.request_id == "req-abc-123"
        assert record.method == "GET"

    def test_always_returns_true(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(msg="PRIVATE-TOKEN: secret")
        assert f.filter(record) is True

    def test_handles_none_args(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(msg="no args", args=None)
        assert f.filter(record) is True
        assert record.args is None

    def test_handles_non_string_msg(self) -> None:
        """Non-string msg objects should not crash the filter."""
        f = SensitiveDataFilter()
        record = self._make_record()
        record.msg = 12345  # type: ignore[assignment]
        assert f.filter(record) is True
        assert record.msg == 12345

    def test_handles_non_string_extra_values(self) -> None:
        f = SensitiveDataFilter()
        record = self._make_record(msg="test")
        record.status_code = 200
        record.latency = 1.5
        f.filter(record)
        assert record.status_code == 200
        assert record.latency == 1.5

    def test_filter_error_does_not_prevent_logging(self) -> None:
        """Fail-open: even if masking crashes, the record should pass through."""
        f = SensitiveDataFilter()
        record = self._make_record(msg="PRIVATE-TOKEN: secret")
        # Monkey-patch _mask_record to raise an exception
        original = f._mask_record
        def raise_error(r: logging.LogRecord) -> None:
            raise RuntimeError("masking failed")
        f._mask_record = raise_error  # type: ignore[assignment]
        # filter() should still return True
        assert f.filter(record) is True
        # msg was not modified since masking failed
        assert record.msg == "PRIVATE-TOKEN: secret"
        f._mask_record = original  # type: ignore[assignment]


class TestSensitiveDataFilterIntegration:
    """Integration tests: end-to-end verification that tokens do not appear in log output."""

    @pytest.fixture(autouse=True)
    def clean_logger(self) -> None:
        """Ensure a clean logger state before and after each test."""
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        yield  # type: ignore[misc]
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()

    def test_console_handler_has_sensitive_filter(self) -> None:
        logger = setup_logging(level="DEBUG")
        console_handlers = [
            h for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(console_handlers) == 1
        filters = console_handlers[0].filters
        assert any(isinstance(f, SensitiveDataFilter) for f in filters)

    def test_file_handler_has_sensitive_filter(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        filters = file_handlers[0].filters
        assert any(isinstance(f, SensitiveDataFilter) for f in filters)

    def test_no_token_in_file_output_private_token(self, tmp_path: Path) -> None:
        """End-to-end: PRIVATE-TOKEN values must not appear in file log output."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        logger.info("Request with PRIVATE-TOKEN: glpat-supersecret123")

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text()
        assert "glpat-supersecret123" not in content
        assert "[MASKED]" in content

    def test_no_token_in_file_output_bearer(self, tmp_path: Path) -> None:
        """End-to-end: Bearer tokens must not appear in file log output."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        logger.info("Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.secret")

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text()
        assert "eyJhbGciOiJSUzI1NiJ9.secret" not in content
        assert "[MASKED]" in content

    def test_no_token_in_file_output_glpat(self, tmp_path: Path) -> None:
        """End-to-end: glpat- tokens must not appear in file log output."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        logger.info("Using token glpat-abcdef123456")

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text()
        assert "glpat-abcdef123456" not in content
        assert "[MASKED]" in content

    def test_no_token_in_file_output_refresh_token(self, tmp_path: Path) -> None:
        """End-to-end: refresh tokens must not appear in file log output."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        logger.info('Token response: refresh_token="my-refresh-secret"')

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text()
        assert "my-refresh-secret" not in content
        assert "[MASKED]" in content

    def test_no_token_in_file_output_url_param(self, tmp_path: Path) -> None:
        """End-to-end: URL query parameter tokens must not appear in file log output."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        logger.info("GET https://gitlab.example.com/api?private_token=leaked-token")

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text()
        assert "leaked-token" not in content
        assert "[MASKED]" in content

    def test_no_token_in_file_output_via_args(self, tmp_path: Path) -> None:
        """End-to-end: tokens in format args must not appear in file log output."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        logger.info("Token: %s", "glpat-args-secret-token")

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text()
        assert "glpat-args-secret-token" not in content
        assert "[MASKED]" in content

    def test_no_token_in_file_output_via_extra(self, tmp_path: Path) -> None:
        """End-to-end: tokens in extra fields must not appear in file log output."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        logger.info("API call", extra={"auth": "Authorization: Bearer extra-secret"})

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text()
        assert "extra-secret" not in content
        assert "[MASKED]" in content

    def test_non_sensitive_data_preserved_in_file_output(self, tmp_path: Path) -> None:
        """End-to-end: normal messages pass through without modification."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        logger.info("Listing merge requests for project my-org/my-repo")

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text()
        assert "Listing merge requests for project my-org/my-repo" in content

    def test_zero_leak_comprehensive(self, tmp_path: Path) -> None:
        """Comprehensive leak test: log multiple messages with various tokens, verify zero leaks."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)

        secrets = [
            "glpat-leak1",
            "bearer-leak2",
            "private-leak3",
            "refresh-leak4",
            "url-leak5",
        ]

        logger.info("PRIVATE-TOKEN: %s", secrets[2])
        logger.info("Authorization: Bearer %s", secrets[1])
        logger.info("Found token %s in config", secrets[0])
        logger.info("refresh_token=%s", secrets[3])
        logger.info("GET /api?private_token=%s", secrets[4])

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text()
        for secret in secrets:
            assert secret not in content, f"Token '{secret}' leaked into log output"


class TestConcurrentLogging:
    """Verify logging behaves correctly under concurrent access."""

    @pytest.fixture(autouse=True)
    def clean_logger(self) -> None:
        """Ensure a clean logger state before and after each test."""
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
        yield  # type: ignore[misc]
        logger = logging.getLogger(LOGGER_NAME)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()

    def test_concurrent_logging_no_data_corruption(self, tmp_path: Path) -> None:
        """Multiple threads logging simultaneously should not corrupt output."""
        log_file = tmp_path / "concurrent.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        num_threads = 4
        messages_per_thread = 50

        def log_messages(thread_id: int) -> None:
            for i in range(messages_per_thread):
                logger.info("Thread-%d message-%d", thread_id, i)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(log_messages, tid) for tid in range(num_threads)]
            for f in futures:
                f.result()

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text().strip()
        lines = content.splitlines()
        # Each line should be valid JSON (no interleaved/corrupted lines)
        for idx, line in enumerate(lines):
            parsed = json.loads(line)
            assert "timestamp" in parsed
            assert "level" in parsed
            assert "message" in parsed, f"Line {idx} missing 'message' field"

        # All messages from all threads should be present
        assert len(lines) == num_threads * messages_per_thread

    def test_concurrent_logging_with_sensitive_data(self, tmp_path: Path) -> None:
        """Concurrent logging with tokens should still mask all sensitive data."""
        log_file = tmp_path / "concurrent_mask.log"
        logger = setup_logging(level="DEBUG", log_file=log_file)
        secrets = [f"glpat-concurrent-secret-{i}" for i in range(20)]

        def log_secrets(thread_id: int) -> None:
            for i in range(5):
                secret_idx = thread_id * 5 + i
                logger.info("Token: %s", secrets[secret_idx])

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(log_secrets, tid) for tid in range(4)]
            for f in futures:
                f.result()

        for h in logger.handlers:
            h.flush()

        content = log_file.read_text()
        for secret in secrets:
            assert secret not in content, f"Token '{secret}' leaked under concurrent logging"

    def test_setup_logging_repeated_concurrent_calls(self) -> None:
        """Calling setup_logging from multiple threads should not corrupt handler state."""
        errors: list[Exception] = []

        def call_setup(level: str) -> None:
            try:
                setup_logging(level=level)
            except Exception as exc:
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=4) as executor:
            levels = ["DEBUG", "INFO", "WARNING", "ERROR"] * 5
            futures = [executor.submit(call_setup, lvl) for lvl in levels]
            for f in futures:
                f.result()

        assert not errors
        # Logger should still be functional after concurrent setup calls
        logger = logging.getLogger(LOGGER_NAME)
        assert logger.level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR)
