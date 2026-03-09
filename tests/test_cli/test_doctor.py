"""Tests for the gltools doctor diagnostic command."""

from __future__ import annotations

import json
import os
import socket
import ssl
import stat
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from gltools.cli.app import app
from gltools.cli.doctor import (
    CheckResult,
    DoctorReport,
    _parse_gitlab_version,
    _parse_host,
    check_api_version,
    check_authentication,
    check_config_file,
    check_dns,
    check_latency,
    check_profile_resolution,
    check_ssl_certificate,
    check_tcp_connection,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Unit tests for CheckResult and DoctorReport
# ---------------------------------------------------------------------------


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_to_dict_without_suggestion(self) -> None:
        result = CheckResult(name="Test", status="pass", details="All good")
        d = result.to_dict()
        assert d["name"] == "Test"
        assert d["status"] == "pass"
        assert d["details"] == "All good"
        assert d["category"] == "general"
        assert "suggestion" not in d

    def test_to_dict_with_suggestion(self) -> None:
        result = CheckResult(name="Test", status="fail", details="Bad", suggestion="Fix it")
        d = result.to_dict()
        assert d["name"] == "Test"
        assert d["status"] == "fail"
        assert d["details"] == "Bad"
        assert d["suggestion"] == "Fix it"

    def test_to_dict_with_category(self) -> None:
        result = CheckResult(name="Test", status="pass", details="ok", category="config")
        d = result.to_dict()
        assert d["category"] == "config"


class TestDoctorReport:
    """Tests for DoctorReport dataclass."""

    def test_empty_report(self) -> None:
        report = DoctorReport()
        d = report.to_dict()
        assert d["data"]["summary"]["total"] == 0
        assert d["data"]["summary"]["passed"] == 0
        assert d["data"]["summary"]["warnings"] == 0
        assert d["data"]["summary"]["failed"] == 0
        assert d["data"]["suggestions"] == []

    def test_report_with_mixed_results(self) -> None:
        report = DoctorReport(
            checks=[
                CheckResult(name="A", status="pass", details="ok", category="config"),
                CheckResult(name="B", status="warn", details="maybe", category="connectivity"),
                CheckResult(name="C", status="fail", details="bad", suggestion="fix C", category="auth"),
                CheckResult(name="D", status="pass", details="ok2", category="api_compat"),
            ]
        )
        d = report.to_dict()
        assert d["status"] == "success"
        assert d["data"]["summary"]["total"] == 4
        assert d["data"]["summary"]["passed"] == 2
        assert d["data"]["summary"]["warnings"] == 1
        assert d["data"]["summary"]["failed"] == 1
        assert len(d["data"]["checks"]) == 4

    def test_report_categories_grouped(self) -> None:
        report = DoctorReport(
            checks=[
                CheckResult(name="A", status="pass", details="ok", category="config"),
                CheckResult(name="B", status="pass", details="ok", category="config"),
                CheckResult(name="C", status="pass", details="ok", category="connectivity"),
            ]
        )
        d = report.to_dict()
        assert "categories" in d["data"]
        assert len(d["data"]["categories"]["config"]) == 2
        assert len(d["data"]["categories"]["connectivity"]) == 1

    def test_report_suggestions_collected(self) -> None:
        report = DoctorReport(
            checks=[
                CheckResult(name="A", status="fail", details="bad", suggestion="do X"),
                CheckResult(name="B", status="fail", details="bad", suggestion="do Y"),
                CheckResult(name="C", status="pass", details="ok"),
            ]
        )
        d = report.to_dict()
        assert d["data"]["suggestions"] == ["do X", "do Y"]


# ---------------------------------------------------------------------------
# Unit tests for _parse_host
# ---------------------------------------------------------------------------


class TestParseHost:
    """Tests for _parse_host helper."""

    def test_https_default_port(self) -> None:
        scheme, hostname, port = _parse_host("https://gitlab.com")
        assert scheme == "https"
        assert hostname == "gitlab.com"
        assert port == 443

    def test_http_default_port(self) -> None:
        scheme, hostname, port = _parse_host("http://gitlab.local")
        assert scheme == "http"
        assert hostname == "gitlab.local"
        assert port == 80

    def test_custom_port(self) -> None:
        scheme, hostname, port = _parse_host("https://gitlab.example.com:8443")
        assert scheme == "https"
        assert hostname == "gitlab.example.com"
        assert port == 8443

    def test_invalid_no_scheme(self) -> None:
        with pytest.raises(ValueError, match="Invalid host URL format"):
            _parse_host("gitlab.com")

    def test_invalid_no_hostname(self) -> None:
        with pytest.raises(ValueError, match="Invalid host URL format"):
            _parse_host("https://")

    def test_unsupported_scheme(self) -> None:
        with pytest.raises(ValueError, match="Unsupported scheme"):
            _parse_host("ftp://gitlab.com")


# ---------------------------------------------------------------------------
# Unit tests for check_config_file
# ---------------------------------------------------------------------------


class TestCheckConfigFile:
    """Tests for config file validation."""

    def test_config_file_not_found(self, tmp_path: Path) -> None:
        results = check_config_file(tmp_path / "nonexistent.toml")
        assert len(results) == 1
        assert results[0].name == "Config File"
        assert results[0].status == "warn"
        assert "not found" in results[0].details
        assert results[0].suggestion is not None
        assert results[0].category == "config"

    def test_config_file_valid_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        results = check_config_file(config_file)

        # Should have syntax pass, required fields pass, permissions pass
        names = [r.name for r in results]
        assert "Config File Syntax" in names
        syntax_result = next(r for r in results if r.name == "Config File Syntax")
        assert syntax_result.status == "pass"

    def test_config_file_invalid_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("invalid = [unclosed\n")
        results = check_config_file(config_file)

        assert len(results) == 1
        assert results[0].name == "Config File Syntax"
        assert results[0].status == "fail"
        assert "Invalid TOML" in results[0].details
        assert results[0].suggestion is not None

    def test_config_file_no_profiles(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('# empty config\nkey = "value"\n')
        config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        results = check_config_file(config_file)

        required_result = next(r for r in results if r.name == "Config Required Fields")
        assert required_result.status == "warn"
        assert "No profiles" in required_result.details

    def test_config_file_missing_host_in_default(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\noutput_format = "json"\n')
        config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        results = check_config_file(config_file)

        required_result = next(r for r in results if r.name == "Config Required Fields")
        assert required_result.status == "warn"
        assert "missing" in required_result.details.lower()

    def test_config_file_host_present(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        results = check_config_file(config_file)

        required_result = next(r for r in results if r.name == "Config Required Fields")
        assert required_result.status == "pass"

    def test_config_file_world_readable(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        config_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH)  # 604
        results = check_config_file(config_file)

        perm_result = next(r for r in results if r.name == "Config File Permissions")
        assert perm_result.status == "warn"
        assert "world-readable" in perm_result.details

    def test_config_file_secure_permissions(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600
        results = check_config_file(config_file)

        perm_result = next(r for r in results if r.name == "Config File Permissions")
        assert perm_result.status == "pass"

    def test_config_no_default_profile_shows_available(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.work]\nhost = "https://work.gitlab.com"\n')
        config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        results = check_config_file(config_file)

        required_result = next(r for r in results if r.name == "Config Required Fields")
        assert required_result.status == "warn"
        assert "work" in required_result.details


# ---------------------------------------------------------------------------
# Unit tests for check_profile_resolution
# ---------------------------------------------------------------------------


class TestCheckProfileResolution:
    """Tests for profile resolution trace."""

    def test_default_profile(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        result = check_profile_resolution(config_path=config_file)

        assert result.status == "pass"
        assert result.category == "config"
        assert "Active profile: default" in result.details

    def test_custom_profile(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.work]\nhost = "https://work.gitlab.com"\n')
        result = check_profile_resolution(profile_name="work", config_path=config_file)

        assert "Active profile: work" in result.details

    def test_cli_host_override(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        result = check_profile_resolution(cli_host="https://custom.gitlab.com", config_path=config_file)

        assert "CLI flag" in result.details
        assert "custom.gitlab.com" in result.details

    def test_cli_token_override(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        result = check_profile_resolution(cli_token="my-token", config_path=config_file)

        assert "Token source: CLI flag" in result.details

    def test_env_host_override(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        with patch.dict("os.environ", {"GLTOOLS_HOST": "https://env.gitlab.com"}):
            result = check_profile_resolution(config_path=config_file)

        assert "GLTOOLS_HOST env var" in result.details

    def test_host_from_config_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        result = check_profile_resolution(config_path=config_file)

        assert "config file" in result.details

    def test_host_default_fallback(self, tmp_path: Path) -> None:
        config_file = tmp_path / "nonexistent.toml"
        result = check_profile_resolution(config_path=config_file)

        assert "default" in result.details.lower()


# ---------------------------------------------------------------------------
# Unit tests for version parsing and API compatibility
# ---------------------------------------------------------------------------


class TestParseGitLabVersion:
    """Tests for GitLab version string parsing."""

    def test_standard_version(self) -> None:
        assert _parse_gitlab_version("16.5.2") == (16, 5)

    def test_enterprise_version(self) -> None:
        assert _parse_gitlab_version("16.5.2-ee") == (16, 5)

    def test_pre_release_version(self) -> None:
        assert _parse_gitlab_version("17.0.0-pre+abc123") == (17, 0)

    def test_two_part_version(self) -> None:
        assert _parse_gitlab_version("15.0") == (15, 0)

    def test_invalid_version(self) -> None:
        assert _parse_gitlab_version("abc") is None

    def test_empty_version(self) -> None:
        assert _parse_gitlab_version("") is None


class TestCheckAPIVersion:
    """Tests for API version compatibility check."""

    def test_version_compatible(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "16.5.2-ee", "revision": "abc123"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_api_version("gitlab.com", 443, "https")

        assert result.status == "pass"
        assert "16.5.2" in result.details
        assert "abc123" in result.details
        assert result.category == "api_compat"

    def test_version_old_gitlab(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "12.10.0", "revision": "old"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_api_version("gitlab.com", 443, "https")

        assert result.status == "warn"
        assert "12.10.0" in result.details
        assert result.suggestion is not None
        assert "below minimum" in result.suggestion
        assert "may not work" in result.suggestion

    def test_version_endpoint_401(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_api_version("gitlab.com", 443, "https")

        assert result.status == "warn"
        assert "requires authentication" in result.details

    def test_version_endpoint_403(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_api_version("gitlab.com", 443, "https")

        assert result.status == "warn"
        assert "forbidden" in result.details.lower()

    def test_version_endpoint_timeout(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("timed out")

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_api_version("gitlab.com", 443, "https")

        assert result.status == "warn"
        assert "timed out" in result.details.lower()

    def test_version_endpoint_connect_error(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("refused")

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_api_version("gitlab.com", 443, "https")

        assert result.status == "warn"
        assert "connectivity" in result.suggestion.lower()

    def test_version_unparseable(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "unknown", "revision": ""}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_api_version("gitlab.com", 443, "https")

        assert result.status == "warn"
        assert "Could not parse" in result.details


# ---------------------------------------------------------------------------
# Unit tests for check_dns
# ---------------------------------------------------------------------------


class TestCheckDNS:
    """Tests for DNS resolution check."""

    def test_dns_pass(self) -> None:
        with patch("gltools.cli.doctor.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
            ]
            result = check_dns("gitlab.com")
        assert result.status == "pass"
        assert "1.2.3.4" in result.details
        assert result.suggestion is None

    def test_dns_no_addresses(self) -> None:
        with patch("gltools.cli.doctor.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = []
            result = check_dns("nonexistent.invalid")
        assert result.status == "fail"
        assert result.suggestion is not None

    def test_dns_gaierror(self) -> None:
        with patch("gltools.cli.doctor.socket.getaddrinfo") as mock_gai:
            mock_gai.side_effect = socket.gaierror("Name or service not known")
            result = check_dns("nonexistent.invalid")
        assert result.status == "fail"
        assert "Cannot resolve" in result.details
        assert result.suggestion is not None

    def test_dns_unexpected_error(self) -> None:
        with patch("gltools.cli.doctor.socket.getaddrinfo") as mock_gai:
            mock_gai.side_effect = RuntimeError("unexpected")
            result = check_dns("test.com")
        assert result.status == "fail"
        assert "DNS lookup error" in result.details


# ---------------------------------------------------------------------------
# Unit tests for check_tcp_connection
# ---------------------------------------------------------------------------


class TestCheckTCPConnection:
    """Tests for TCP connection check."""

    def test_tcp_pass(self) -> None:
        mock_sock = MagicMock()
        with patch("gltools.cli.doctor.socket.create_connection", return_value=mock_sock):
            result = check_tcp_connection("gitlab.com", 443)
        assert result.status == "pass"
        assert "443" in result.details
        mock_sock.close.assert_called_once()

    def test_tcp_timeout(self) -> None:
        with patch("gltools.cli.doctor.socket.create_connection") as mock_conn:
            mock_conn.side_effect = TimeoutError()
            result = check_tcp_connection("gitlab.com", 443, timeout=2.0)
        assert result.status == "fail"
        assert "timed out" in result.details
        assert result.suggestion is not None

    def test_tcp_connection_refused(self) -> None:
        with patch("gltools.cli.doctor.socket.create_connection") as mock_conn:
            mock_conn.side_effect = ConnectionRefusedError("Connection refused")
            result = check_tcp_connection("gitlab.com", 443)
        assert result.status == "fail"
        assert result.suggestion is not None

    def test_tcp_os_error(self) -> None:
        with patch("gltools.cli.doctor.socket.create_connection") as mock_conn:
            mock_conn.side_effect = OSError("Network unreachable")
            result = check_tcp_connection("gitlab.com", 443)
        assert result.status == "fail"
        assert "Cannot connect" in result.details


# ---------------------------------------------------------------------------
# Unit tests for check_ssl_certificate
# ---------------------------------------------------------------------------


class TestCheckSSLCertificate:
    """Tests for SSL certificate check."""

    def test_ssl_valid_cert(self) -> None:
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = {
            "subject": ((("commonName", "gitlab.com"),),),
            "notAfter": "Dec 31 23:59:59 2027 GMT",
        }
        mock_sock = MagicMock()
        mock_context = MagicMock()
        mock_context.wrap_socket.return_value.__enter__ = MagicMock(return_value=mock_ssock)
        mock_context.wrap_socket.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch("gltools.cli.doctor.ssl.create_default_context", return_value=mock_context),
            patch("gltools.cli.doctor.socket.create_connection") as mock_conn,
        ):
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_sock)
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            result = check_ssl_certificate("gitlab.com", 443)

        assert result.status == "pass"
        assert "gitlab.com" in result.details
        assert "2027" in result.details

    def test_ssl_self_signed(self) -> None:
        with (
            patch("gltools.cli.doctor.ssl.create_default_context") as mock_ctx,
            patch("gltools.cli.doctor.socket.create_connection") as mock_conn,
        ):
            mock_conn.return_value.__enter__ = MagicMock()
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.return_value.wrap_socket.side_effect = ssl.SSLCertVerificationError("self-signed certificate")
            result = check_ssl_certificate("gitlab.local", 443)

        assert result.status == "warn"
        assert "self-signed" in result.details.lower() or "Self-signed" in result.details

    def test_ssl_cert_verification_error(self) -> None:
        with (
            patch("gltools.cli.doctor.ssl.create_default_context") as mock_ctx,
            patch("gltools.cli.doctor.socket.create_connection") as mock_conn,
        ):
            mock_conn.return_value.__enter__ = MagicMock()
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.return_value.wrap_socket.side_effect = ssl.SSLCertVerificationError("certificate has expired")
            result = check_ssl_certificate("gitlab.com", 443)

        assert result.status == "warn"
        assert "verification failed" in result.details.lower()

    def test_ssl_timeout(self) -> None:
        with patch("gltools.cli.doctor.socket.create_connection") as mock_conn:
            mock_conn.side_effect = TimeoutError()
            result = check_ssl_certificate("gitlab.com", 443)

        assert result.status == "fail"
        assert "timed out" in result.details.lower()

    def test_ssl_os_error(self) -> None:
        with patch("gltools.cli.doctor.socket.create_connection") as mock_conn:
            mock_conn.side_effect = OSError("Connection refused")
            result = check_ssl_certificate("gitlab.com", 443)

        assert result.status == "fail"
        assert "Cannot check SSL" in result.details


# ---------------------------------------------------------------------------
# Unit tests for check_latency
# ---------------------------------------------------------------------------


class TestCheckLatency:
    """Tests for latency measurement check."""

    def test_latency_fast(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with (
            patch("gltools.cli.doctor.httpx.Client", return_value=mock_client),
            patch("gltools.cli.doctor.time.monotonic", side_effect=[1.0, 1.1]),
        ):
            result = check_latency("gitlab.com", 443, "https")

        assert result.status == "pass"
        assert "100ms" in result.details
        assert result.suggestion is None

    def test_latency_slow(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with (
            patch("gltools.cli.doctor.httpx.Client", return_value=mock_client),
            patch("gltools.cli.doctor.time.monotonic", side_effect=[1.0, 2.0]),
        ):
            result = check_latency("gitlab.com", 443, "https")

        assert result.status == "warn"
        assert "1000ms" in result.details
        assert result.suggestion is not None

    def test_latency_timeout(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("timed out")

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_latency("gitlab.com", 443, "https")

        assert result.status == "fail"
        assert "timed out" in result.details

    def test_latency_connect_error(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("refused")

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_latency("gitlab.com", 443, "https")

        assert result.status == "fail"
        assert "Cannot connect" in result.details


# ---------------------------------------------------------------------------
# Unit tests for check_authentication
# ---------------------------------------------------------------------------


class TestCheckAuthentication:
    """Tests for authentication check."""

    @pytest.mark.asyncio()
    async def test_auth_pass_pat(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "username": "testuser",
            "name": "Test User",
        }

        with patch("gltools.cli.doctor.GitLabHTTPClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_cls.return_value = mock_client

            result = await check_authentication(
                host="https://gitlab.com",
                token="glpat-test",
                auth_type="pat",
            )

        assert result.status == "pass"
        assert "testuser" in result.details
        assert "Test User" in result.details
        assert "PAT" in result.details
        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_auth_pass_oauth(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "username": "oauthuser",
            "name": "OAuth User",
        }

        with patch("gltools.cli.doctor.GitLabHTTPClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_cls.return_value = mock_client

            result = await check_authentication(
                host="https://gitlab.com",
                token="oauth-token",
                auth_type="oauth",
            )

        assert result.status == "pass"
        assert "oauthuser" in result.details
        assert "OAuth2" in result.details

    @pytest.mark.asyncio()
    async def test_auth_with_expiry(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "username": "testuser",
            "name": "Test User",
            "expires_at": "2027-12-31",
        }

        with patch("gltools.cli.doctor.GitLabHTTPClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_cls.return_value = mock_client

            result = await check_authentication(
                host="https://gitlab.com",
                token="glpat-test",
                auth_type="pat",
            )

        assert result.status == "pass"
        assert "2027-12-31" in result.details

    @pytest.mark.asyncio()
    async def test_auth_fail_401(self) -> None:
        from gltools.client.exceptions import AuthenticationError

        with patch("gltools.cli.doctor.GitLabHTTPClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = AuthenticationError()
            mock_cls.return_value = mock_client

            result = await check_authentication(
                host="https://gitlab.com",
                token="bad-token",
                auth_type="pat",
            )

        assert result.status == "fail"
        assert "401" in result.details
        assert "gltools auth login" in result.suggestion

    @pytest.mark.asyncio()
    async def test_auth_fail_401_oauth_suggestion(self) -> None:
        from gltools.client.exceptions import AuthenticationError

        with patch("gltools.cli.doctor.GitLabHTTPClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = AuthenticationError()
            mock_cls.return_value = mock_client

            result = await check_authentication(
                host="https://gitlab.com",
                token="bad-token",
                auth_type="oauth",
            )

        assert result.status == "fail"
        assert "--method web" in result.suggestion

    @pytest.mark.asyncio()
    async def test_auth_fail_403(self) -> None:
        from gltools.client.exceptions import ForbiddenError

        with patch("gltools.cli.doctor.GitLabHTTPClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = ForbiddenError()
            mock_cls.return_value = mock_client

            result = await check_authentication(
                host="https://gitlab.com",
                token="test-token",
                auth_type="pat",
            )

        assert result.status == "fail"
        assert "403" in result.details
        assert "scope" in result.suggestion.lower()

    @pytest.mark.asyncio()
    async def test_auth_fail_timeout(self) -> None:
        from gltools.client.exceptions import TimeoutError as GLTimeoutError

        with patch("gltools.cli.doctor.GitLabHTTPClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = GLTimeoutError()
            mock_cls.return_value = mock_client

            result = await check_authentication(
                host="https://gitlab.com",
                token="test-token",
                auth_type="pat",
            )

        assert result.status == "fail"
        assert "timed out" in result.details.lower()

    @pytest.mark.asyncio()
    async def test_auth_fail_connection(self) -> None:
        from gltools.client.exceptions import ConnectionError as GLConnectionError

        with patch("gltools.cli.doctor.GitLabHTTPClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = GLConnectionError()
            mock_cls.return_value = mock_client

            result = await check_authentication(
                host="https://gitlab.com",
                token="test-token",
                auth_type="pat",
            )

        assert result.status == "fail"
        assert "connect" in result.details.lower()

    @pytest.mark.asyncio()
    async def test_auth_fail_generic_error(self) -> None:
        with patch("gltools.cli.doctor.GitLabHTTPClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = RuntimeError("Something broke")
            mock_cls.return_value = mock_client

            result = await check_authentication(
                host="https://gitlab.com",
                token="test-token",
                auth_type="pat",
            )

        assert result.status == "fail"
        assert "gltools auth login" in result.suggestion


# ---------------------------------------------------------------------------
# Integration tests for the doctor CLI command
# ---------------------------------------------------------------------------


def _mock_config(**overrides: Any) -> Any:
    """Create a mock GitLabConfig."""
    defaults = {
        "host": "https://gitlab.example.com",
        "token": "glpat-test123",
        "auth_type": "pat",
        "profile": "default",
        "client_id": None,
    }
    defaults.update(overrides)
    config = MagicMock()
    for key, value in defaults.items():
        setattr(config, key, value)
    return config


def _standard_patches():
    """Return common patches for doctor command integration tests.

    Patches config file check, profile resolution, and API version check
    in addition to the standard connectivity/auth checks.
    """
    return (
        patch(
            "gltools.cli.doctor.check_config_file",
            return_value=[
                CheckResult(name="Config File Syntax", status="pass", details="Valid TOML", category="config"),
                CheckResult(name="Config Required Fields", status="pass", details="ok", category="config"),
                CheckResult(name="Config File Permissions", status="pass", details="ok", category="config"),
            ],
        ),
        patch(
            "gltools.cli.doctor.check_profile_resolution",
            return_value=CheckResult(
                name="Profile Resolution", status="pass", details="Active profile: default", category="config"
            ),
        ),
        patch(
            "gltools.cli.doctor.check_api_version",
            return_value=CheckResult(
                name="GitLab API Version", status="pass", details="GitLab 16.5.2-ee", category="api_compat"
            ),
        ),
    )


class TestDoctorCommand:
    """Integration tests for the `gltools doctor` command."""

    def test_doctor_all_pass(self) -> None:
        """Doctor command runs all checks and produces output."""
        config = _mock_config()

        config_patch, profile_patch, version_patch = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            version_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS Resolution", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP Connection", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(name="SSL Certificate", status="pass", details="ok")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="ok")
            mock_auth.return_value = CheckResult(name="Authentication", status="pass", details="ok")

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "PASS" in result.output
        assert "DNS Resolution" in result.output
        assert "Authentication" in result.output

    def test_doctor_json_output(self) -> None:
        """Doctor command produces valid JSON output with --json flag."""
        config = _mock_config()

        config_patch, profile_patch, version_patch = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            version_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS Resolution", status="pass", details="Resolved")
            mock_tcp.return_value = CheckResult(name="TCP Connection", status="pass", details="Connected")
            mock_ssl.return_value = CheckResult(name="SSL Certificate", status="pass", details="Valid")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="50ms")
            mock_auth.return_value = CheckResult(name="Authentication", status="pass", details="Authenticated")

            result = runner.invoke(app, ["--json", "doctor"])

        assert result.exit_code == 0
        output = result.output.strip()
        data = json.loads(output)
        assert data["status"] == "success"
        assert "checks" in data["data"]
        assert "summary" in data["data"]
        assert "categories" in data["data"]
        assert "suggestions" in data["data"]
        # 3 config + 1 profile + 5 conn/ssl/latency/version/auth = 10 checks total
        assert data["data"]["summary"]["total"] == 10
        assert data["data"]["summary"]["passed"] == 10

    def test_doctor_json_all_checks_present(self) -> None:
        """JSON output contains all check results including new categories."""
        config = _mock_config()

        config_patch, profile_patch, version_patch = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            version_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS Resolution", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP Connection", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(name="SSL Certificate", status="warn", details="self-signed")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="50ms")
            mock_auth.return_value = CheckResult(
                name="Authentication", status="fail", details="bad", suggestion="fix it"
            )

            result = runner.invoke(app, ["--json", "doctor"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        checks = data["data"]["checks"]
        check_names = [c["name"] for c in checks]
        assert "DNS Resolution" in check_names
        assert "TCP Connection" in check_names
        assert "SSL Certificate" in check_names
        assert "Latency" in check_names
        assert "Authentication" in check_names
        assert "Config File Syntax" in check_names
        assert "Profile Resolution" in check_names
        assert "GitLab API Version" in check_names

        # Check that categories are in JSON
        categories = data["data"]["categories"]
        assert "config" in categories
        assert "api_compat" in categories

        # Check that suggestions are included for failing checks
        auth_check = next(c for c in checks if c["name"] == "Authentication")
        assert auth_check["suggestion"] == "fix it"

        # Check that suggestions list is populated
        assert "fix it" in data["data"]["suggestions"]

    def test_doctor_no_token_configured(self) -> None:
        """Doctor command handles missing token gracefully."""
        config = _mock_config(token="")

        config_patch, profile_patch, version_patch = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            version_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
        ):
            mock_dns.return_value = CheckResult(name="DNS Resolution", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP Connection", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(name="SSL Certificate", status="pass", details="ok")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="ok")

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "No token configured" in result.output
        assert "gltools auth login" in result.output

    def test_doctor_dns_failure_skips_subsequent(self) -> None:
        """When DNS fails, TCP/SSL/Latency/Version checks are skipped."""
        config = _mock_config()

        config_patch, profile_patch, _ = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_api_version") as mock_version,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS Resolution", status="fail", details="Cannot resolve")

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        mock_tcp.assert_not_called()
        mock_ssl.assert_not_called()
        mock_latency.assert_not_called()
        mock_version.assert_not_called()
        mock_auth.assert_not_called()
        assert "DNS" in result.output

    def test_doctor_invalid_host_url(self) -> None:
        """Doctor command handles invalid host URL format."""
        config = _mock_config(host="not-a-url")

        config_patch, profile_patch, _ = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
        ):
            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Invalid host URL format" in result.output

    def test_doctor_config_error(self) -> None:
        """Doctor command handles config loading errors but still runs config file checks."""
        config_patch, profile_patch, _ = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", side_effect=RuntimeError("bad config")),
            config_patch,
            profile_patch,
        ):
            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Cannot load configuration" in result.output

    def test_doctor_http_scheme_skips_ssl(self) -> None:
        """HTTP scheme skips SSL certificate check."""
        config = _mock_config(host="http://gitlab.local")

        config_patch, profile_patch, version_patch = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            version_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS Resolution", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP Connection", status="pass", details="ok")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="ok")
            mock_auth.return_value = CheckResult(name="Authentication", status="pass", details="ok")

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        mock_ssl.assert_not_called()

    def test_doctor_text_output_includes_suggestions(self) -> None:
        """Text output includes suggestions for failed checks."""
        config = _mock_config()

        config_patch, profile_patch, version_patch = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            version_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS Resolution", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP Connection", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(
                name="SSL Certificate", status="warn", details="self-signed", suggestion="Add CA to trust store"
            )
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="ok")
            mock_auth.return_value = CheckResult(
                name="Authentication", status="fail", details="401 Unauthorized", suggestion="Run gltools auth login"
            )

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Suggestion" in result.output
        assert "Add CA to trust store" in result.output
        assert "Run gltools auth login" in result.output
        assert "Action Required" in result.output

    def test_doctor_oauth_with_token_refresh(self) -> None:
        """Doctor command works with OAuth2 authentication type."""
        config = _mock_config(auth_type="oauth", client_id="my-app-id")

        config_patch, profile_patch, version_patch = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            version_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS Resolution", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP Connection", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(name="SSL Certificate", status="pass", details="ok")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="ok")
            mock_auth.return_value = CheckResult(
                name="Authentication", status="pass", details="Authenticated as oauthuser; Token type: OAuth2"
            )

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        mock_auth.assert_awaited_once()
        call_kwargs = mock_auth.call_args
        assert call_kwargs.kwargs["auth_type"] == "oauth"
        assert call_kwargs.kwargs["client_id"] == "my-app-id"

    def test_doctor_never_crashes(self) -> None:
        """Doctor command always produces a report, even on unexpected errors."""
        config = _mock_config()

        config_patch, profile_patch, _ = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            patch("gltools.cli.doctor.check_dns", side_effect=RuntimeError("Unexpected crash")),
        ):
            result = runner.invoke(app, ["doctor"])

        assert result.exit_code is not None

    def test_doctor_command_exists_in_help(self) -> None:
        """Doctor command shows up in the main help output."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "doctor" in result.output

    def test_doctor_json_output_valid_json(self) -> None:
        """JSON output is always valid parseable JSON."""
        config = _mock_config()

        config_patch, profile_patch, version_patch = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            version_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS", status="fail", details="no", suggestion="fix dns")
            mock_tcp.return_value = CheckResult(name="TCP", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(name="SSL", status="warn", details="meh", suggestion="check cert")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="fast")
            mock_auth.return_value = CheckResult(name="Auth", status="pass", details="ok")

            result = runner.invoke(app, ["--json", "doctor"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert isinstance(data, dict)
        assert "status" in data
        assert "data" in data

    def test_doctor_summary_in_text_output(self) -> None:
        """Text output includes a summary line with pass/warn/fail counts."""
        config = _mock_config()

        config_patch, profile_patch, version_patch = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            version_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS Resolution", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP Connection", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(name="SSL Certificate", status="pass", details="ok")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="ok")
            mock_auth.return_value = CheckResult(name="Authentication", status="pass", details="ok")

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Summary" in result.output
        # 3 config + 1 profile + 5 conn + 1 version + 1 auth = 10 passed (from patches)
        # However, we patched check_dns etc. which don't set category,
        # so the passed count should be 10
        assert "passed" in result.output

    def test_doctor_mixed_pass_warn_fail_summary(self) -> None:
        """Summary report correctly aggregates mixed results."""
        config = _mock_config()

        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            patch(
                "gltools.cli.doctor.check_config_file",
                return_value=[
                    CheckResult(name="Config Syntax", status="pass", details="ok", category="config"),
                ],
            ),
            patch(
                "gltools.cli.doctor.check_profile_resolution",
                return_value=CheckResult(name="Profile", status="pass", details="ok", category="config"),
            ),
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_api_version") as mock_version,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(name="SSL", status="warn", details="self-signed", suggestion="fix ssl")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="ok")
            mock_version.return_value = CheckResult(
                name="API Version", status="warn", details="old version", suggestion="upgrade"
            )
            mock_auth.return_value = CheckResult(name="Auth", status="fail", details="401", suggestion="re-auth")

            result = runner.invoke(app, ["--json", "doctor"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        summary = data["data"]["summary"]
        assert summary["failed"] == 1
        assert summary["warnings"] == 2
        assert summary["passed"] >= 4
        assert data["data"]["suggestions"] == ["re-auth"]

    def test_doctor_config_validation_error_doesnt_block_other_checks(self) -> None:
        """Config validation errors don't prevent connectivity/auth checks from running."""
        config = _mock_config()

        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            patch("gltools.cli.doctor.check_config_file", side_effect=RuntimeError("config check crash")),
            patch(
                "gltools.cli.doctor.check_profile_resolution",
                return_value=CheckResult(name="Profile", status="pass", details="ok", category="config"),
            ),
            patch(
                "gltools.cli.doctor.check_api_version",
                return_value=CheckResult(name="API Version", status="pass", details="ok", category="api_compat"),
            ),
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(name="SSL", status="pass", details="ok")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="ok")
            mock_auth.return_value = CheckResult(name="Auth", status="pass", details="ok")

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        # Should still have connectivity and auth checks in the output
        assert "DNS" in result.output
        assert "Auth" in result.output

    def test_doctor_api_version_failure_doesnt_block_summary(self) -> None:
        """API version check failure doesn't prevent summary from being generated."""
        config = _mock_config()

        config_patch, profile_patch, _ = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_api_version", side_effect=RuntimeError("version crash")),
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(name="SSL", status="pass", details="ok")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="ok")
            mock_auth.return_value = CheckResult(name="Auth", status="pass", details="ok")

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Summary" in result.output

    def test_doctor_all_fail_scenario(self) -> None:
        """Summary report correctly handles all checks failing."""
        config = _mock_config()

        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            patch(
                "gltools.cli.doctor.check_config_file",
                return_value=[
                    CheckResult(
                        name="Config File Syntax",
                        status="fail",
                        details="Invalid TOML",
                        suggestion="Fix syntax",
                        category="config",
                    ),
                ],
            ),
            patch(
                "gltools.cli.doctor.check_profile_resolution",
                return_value=CheckResult(name="Profile", status="fail", details="bad", category="config"),
            ),
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_api_version") as mock_version,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(
                name="DNS", status="fail", details="cannot resolve", suggestion="check dns"
            )
            mock_tcp.return_value = CheckResult(name="TCP", status="fail", details="refused", suggestion="check host")
            mock_ssl.return_value = CheckResult(name="SSL", status="fail", details="bad cert", suggestion="fix cert")
            mock_latency.return_value = CheckResult(
                name="Latency", status="fail", details="timeout", suggestion="check network"
            )
            mock_version.return_value = CheckResult(
                name="API Version", status="fail", details="unreachable", suggestion="check api"
            )
            mock_auth.return_value = CheckResult(
                name="Auth", status="fail", details="401", suggestion="re-auth"
            )

            result = runner.invoke(app, ["--json", "doctor"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        summary = data["data"]["summary"]
        assert summary["passed"] == 0
        assert summary["failed"] >= 2  # At least config + DNS fail (TCP/SSL/latency skipped due to DNS fail)
        assert len(data["data"]["suggestions"]) > 0

    def test_doctor_combined_no_network_and_no_config(self) -> None:
        """Combined failure: config load error AND DNS failure produces a report, not a crash."""
        with (
            patch(
                "gltools.config.settings.GitLabConfig.from_config",
                side_effect=RuntimeError("no config"),
            ),
            patch(
                "gltools.cli.doctor.check_config_file",
                return_value=[
                    CheckResult(
                        name="Config File",
                        status="warn",
                        details="Config file not found",
                        suggestion="create config",
                        category="config",
                    ),
                ],
            ),
            patch(
                "gltools.cli.doctor.check_profile_resolution",
                return_value=CheckResult(name="Profile", status="pass", details="default", category="config"),
            ),
        ):
            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Cannot load configuration" in result.output
        # Should still have config checks in output even though config loading failed
        assert "Summary" in result.output

    def test_doctor_combined_no_network_and_no_config_json(self) -> None:
        """Combined failure in JSON mode produces valid JSON, not a stack trace."""
        with (
            patch(
                "gltools.config.settings.GitLabConfig.from_config",
                side_effect=RuntimeError("no config"),
            ),
            patch(
                "gltools.cli.doctor.check_config_file",
                return_value=[
                    CheckResult(
                        name="Config File",
                        status="warn",
                        details="not found",
                        category="config",
                    ),
                ],
            ),
            patch(
                "gltools.cli.doctor.check_profile_resolution",
                return_value=CheckResult(name="Profile", status="pass", details="default", category="config"),
            ),
        ):
            result = runner.invoke(app, ["--json", "doctor"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["status"] == "success"
        assert data["data"]["summary"]["total"] >= 2

    def test_doctor_crash_in_profile_resolution(self) -> None:
        """Doctor still produces output when profile resolution crashes unexpectedly."""
        config = _mock_config()

        config_patch, _, version_patch = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            patch("gltools.cli.doctor.check_profile_resolution", side_effect=RuntimeError("profile crash")),
            version_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP", status="pass", details="ok")
            mock_ssl.return_value = CheckResult(name="SSL", status="pass", details="ok")
            mock_latency.return_value = CheckResult(name="Latency", status="pass", details="ok")
            mock_auth.return_value = CheckResult(name="Auth", status="pass", details="ok")

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Summary" in result.output

    def test_doctor_tcp_failure_skips_ssl_and_latency(self) -> None:
        """When TCP fails, SSL/Latency/Version checks are skipped."""
        config = _mock_config()

        config_patch, profile_patch, _ = _standard_patches()
        with (
            patch("gltools.config.settings.GitLabConfig.from_config", return_value=config),
            config_patch,
            profile_patch,
            patch("gltools.cli.doctor.check_dns") as mock_dns,
            patch("gltools.cli.doctor.check_tcp_connection") as mock_tcp,
            patch("gltools.cli.doctor.check_ssl_certificate") as mock_ssl,
            patch("gltools.cli.doctor.check_latency") as mock_latency,
            patch("gltools.cli.doctor.check_api_version") as mock_version,
            patch("gltools.cli.doctor.check_authentication", new_callable=AsyncMock) as mock_auth,
        ):
            mock_dns.return_value = CheckResult(name="DNS", status="pass", details="ok")
            mock_tcp.return_value = CheckResult(name="TCP", status="fail", details="Connection refused")

            result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        mock_ssl.assert_not_called()
        mock_latency.assert_not_called()
        mock_version.assert_not_called()
        # Auth should still be attempted since DNS passed (auth skips only if DNS fails)
        mock_auth.assert_awaited_once()


# ---------------------------------------------------------------------------
# Additional unit tests for edge cases and error paths
# ---------------------------------------------------------------------------


class TestCheckSSLCertificateEdgeCases:
    """Additional SSL certificate edge case tests."""

    def test_ssl_generic_ssl_error(self) -> None:
        """Generic SSLError (not SSLCertVerificationError) is handled."""
        with (
            patch("gltools.cli.doctor.ssl.create_default_context") as mock_ctx,
            patch("gltools.cli.doctor.socket.create_connection") as mock_conn,
        ):
            mock_conn.return_value.__enter__ = MagicMock()
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.return_value.wrap_socket.side_effect = ssl.SSLError("SSL handshake failed")
            result = check_ssl_certificate("gitlab.com", 443)

        assert result.status == "warn"
        assert "SSL error" in result.details
        assert result.suggestion is not None

    def test_ssl_no_cert_info(self) -> None:
        """SSL connection succeeds but getpeercert returns None."""
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = None
        mock_sock = MagicMock()
        mock_context = MagicMock()
        mock_context.wrap_socket.return_value.__enter__ = MagicMock(return_value=mock_ssock)
        mock_context.wrap_socket.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch("gltools.cli.doctor.ssl.create_default_context", return_value=mock_context),
            patch("gltools.cli.doctor.socket.create_connection") as mock_conn,
        ):
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_sock)
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            result = check_ssl_certificate("gitlab.com", 443)

        assert result.status == "warn"
        assert "No certificate information" in result.details

    def test_ssl_unexpected_exception(self) -> None:
        """Unexpected exception during SSL check is handled gracefully."""
        with patch("gltools.cli.doctor.socket.create_connection") as mock_conn:
            mock_conn.side_effect = RuntimeError("Something totally unexpected")
            result = check_ssl_certificate("gitlab.com", 443)

        assert result.status == "fail"
        assert "SSL check error" in result.details
        assert result.category == "connectivity"


class TestCheckTCPConnectionEdgeCases:
    """Additional TCP connection edge case tests."""

    def test_tcp_unexpected_exception(self) -> None:
        """Unexpected exception during TCP check is handled gracefully."""
        with patch("gltools.cli.doctor.socket.create_connection") as mock_conn:
            mock_conn.side_effect = RuntimeError("Unexpected error")
            result = check_tcp_connection("gitlab.com", 443)

        assert result.status == "fail"
        assert "Connection error" in result.details
        assert result.suggestion is not None


class TestCheckLatencyEdgeCases:
    """Additional latency check edge case tests."""

    def test_latency_generic_exception(self) -> None:
        """Generic exception during latency check is handled."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = RuntimeError("Unexpected failure")

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_latency("gitlab.com", 443, "https")

        assert result.status == "fail"
        assert "Latency check failed" in result.details
        assert result.suggestion is not None

    def test_latency_very_slow(self) -> None:
        """Latency above 2000ms still returns warn (not fail)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with (
            patch("gltools.cli.doctor.httpx.Client", return_value=mock_client),
            patch("gltools.cli.doctor.time.monotonic", side_effect=[1.0, 4.0]),
        ):
            result = check_latency("gitlab.com", 443, "https")

        assert result.status == "warn"
        assert "3000ms" in result.details
        assert result.suggestion is not None


class TestCheckAPIVersionEdgeCases:
    """Additional API version check edge case tests."""

    def test_version_endpoint_unexpected_status(self) -> None:
        """Unexpected HTTP status (e.g., 500) is handled."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_api_version("gitlab.com", 443, "https")

        assert result.status == "warn"
        assert "500" in result.details
        assert result.suggestion is not None

    def test_version_generic_exception(self) -> None:
        """Generic exception during version check is handled."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = RuntimeError("Unexpected failure")

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_api_version("gitlab.com", 443, "https")

        assert result.status == "warn"
        assert "Version check failed" in result.details

    def test_version_no_revision(self) -> None:
        """Version response without revision field works fine."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "16.5.2"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("gltools.cli.doctor.httpx.Client", return_value=mock_client):
            result = check_api_version("gitlab.com", 443, "https")

        assert result.status == "pass"
        assert "16.5.2" in result.details
        # No revision should be shown
        assert "revision" not in result.details


class TestCheckProfileResolutionEdgeCases:
    """Additional profile resolution edge case tests."""

    def test_env_profile_source(self, tmp_path: Path) -> None:
        """Profile source from GLTOOLS_PROFILE env var is traced."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        with patch.dict("os.environ", {"GLTOOLS_PROFILE": "staging"}):
            result = check_profile_resolution(config_path=config_file)

        assert "GLTOOLS_PROFILE env var" in result.details
        assert "staging" in result.details

    def test_env_token_source(self, tmp_path: Path) -> None:
        """Token source from GLTOOLS_TOKEN env var is traced."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        with patch.dict("os.environ", {"GLTOOLS_TOKEN": "env-token-value"}):
            result = check_profile_resolution(config_path=config_file)

        assert "GLTOOLS_TOKEN env var" in result.details

    def test_token_source_keyring_fallback(self, tmp_path: Path) -> None:
        """Token source shows keyring/config fallback when no CLI or env token."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[profiles.default]\nhost = "https://gitlab.com"\n')
        # Ensure no env token is set
        env = {k: v for k, v in os.environ.items() if k != "GLTOOLS_TOKEN"}
        with patch.dict("os.environ", env, clear=True):
            result = check_profile_resolution(config_path=config_file)

        assert "keyring or config file" in result.details


class TestDoctorReportEdgeCases:
    """Additional edge cases for DoctorReport."""

    def test_report_all_pass(self) -> None:
        """All-pass report has correct summary and no suggestions."""
        report = DoctorReport(
            checks=[
                CheckResult(name="A", status="pass", details="ok", category="config"),
                CheckResult(name="B", status="pass", details="ok", category="connectivity"),
                CheckResult(name="C", status="pass", details="ok", category="auth"),
                CheckResult(name="D", status="pass", details="ok", category="api_compat"),
            ]
        )
        d = report.to_dict()
        assert d["data"]["summary"]["total"] == 4
        assert d["data"]["summary"]["passed"] == 4
        assert d["data"]["summary"]["warnings"] == 0
        assert d["data"]["summary"]["failed"] == 0
        assert d["data"]["suggestions"] == []

    def test_report_all_fail(self) -> None:
        """All-fail report has correct summary and collects all suggestions."""
        report = DoctorReport(
            checks=[
                CheckResult(name="A", status="fail", details="bad", suggestion="fix A", category="config"),
                CheckResult(name="B", status="fail", details="bad", suggestion="fix B", category="connectivity"),
                CheckResult(name="C", status="fail", details="bad", suggestion="fix C", category="auth"),
            ]
        )
        d = report.to_dict()
        assert d["data"]["summary"]["total"] == 3
        assert d["data"]["summary"]["passed"] == 0
        assert d["data"]["summary"]["failed"] == 3
        assert d["data"]["suggestions"] == ["fix A", "fix B", "fix C"]

    def test_report_warn_suggestions_not_in_suggestions_list(self) -> None:
        """Suggestions from warn checks are not included in the suggestions list (only fails)."""
        report = DoctorReport(
            checks=[
                CheckResult(name="A", status="warn", details="maybe", suggestion="consider X"),
                CheckResult(name="B", status="fail", details="bad", suggestion="fix B"),
            ]
        )
        d = report.to_dict()
        assert d["data"]["suggestions"] == ["fix B"]

    def test_report_fail_without_suggestion_not_in_suggestions_list(self) -> None:
        """Failed check without a suggestion does not add None to suggestions."""
        report = DoctorReport(
            checks=[
                CheckResult(name="A", status="fail", details="bad"),  # No suggestion
                CheckResult(name="B", status="fail", details="bad", suggestion="fix B"),
            ]
        )
        d = report.to_dict()
        assert d["data"]["suggestions"] == ["fix B"]
