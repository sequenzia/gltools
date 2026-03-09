"""Diagnostic command for validating GitLab connectivity and authentication."""

from __future__ import annotations

import json
import os
import socket
import ssl
import stat
import time
import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from pathlib import Path

import httpx
import typer  # noqa: TC002 — used at runtime in function signatures
from rich.console import Console

from gltools.cli.app import app, async_command
from gltools.client.http import GitLabHTTPClient, RetryConfig

console = Console()
err_console = Console(stderr=True)

# Minimum GitLab version required for full API compatibility
MINIMUM_GITLAB_VERSION = (15, 0)

# Known API features and the minimum version they require
GITLAB_VERSION_FEATURES: dict[tuple[int, int], list[str]] = {
    (13, 0): ["Basic MR/Issue/Pipeline APIs"],
    (14, 0): ["Merge request approvals API", "CI job token scope"],
    (15, 0): ["CI/CD components", "Suggested reviewers API"],
    (16, 0): ["CI/CD catalog", "Remote development workspaces API"],
    (17, 0): ["Duo AI features API", "Virtual registry API"],
}


@dataclass
class CheckResult:
    """Result of a single diagnostic check."""

    name: str
    status: str  # "pass", "warn", "fail"
    details: str
    suggestion: str | None = None
    category: str = "general"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON output."""
        result: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "details": self.details,
            "category": self.category,
        }
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


@dataclass
class DoctorReport:
    """Aggregated report of all diagnostic checks."""

    checks: list[CheckResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON output."""
        # Group checks by category
        categories: dict[str, list[dict[str, Any]]] = {}
        for check in self.checks:
            cat = check.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(check.to_dict())

        failed_checks = [c for c in self.checks if c.status == "fail"]
        suggestions = [c.suggestion for c in failed_checks if c.suggestion]

        return {
            "status": "success",
            "data": {
                "checks": [c.to_dict() for c in self.checks],
                "categories": categories,
                "summary": {
                    "total": len(self.checks),
                    "passed": sum(1 for c in self.checks if c.status == "pass"),
                    "warnings": sum(1 for c in self.checks if c.status == "warn"),
                    "failed": sum(1 for c in self.checks if c.status == "fail"),
                },
                "suggestions": suggestions,
            },
        }


def _parse_host(host: str) -> tuple[str, str, int]:
    """Parse a host URL into (scheme, hostname, port).

    Returns:
        Tuple of (scheme, hostname, port).

    Raises:
        ValueError: If the URL format is invalid.
    """
    parsed = urlparse(host)
    scheme = parsed.scheme
    hostname = parsed.hostname

    if not scheme or not hostname:
        raise ValueError(f"Invalid host URL format: '{host}'. Expected format: https://gitlab.example.com")

    if scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme '{scheme}' in host URL. Use 'http' or 'https'.")

    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80

    return scheme, hostname, port


# ---------------------------------------------------------------------------
# Configuration checks
# ---------------------------------------------------------------------------


def check_config_file(config_path: Path | None = None) -> list[CheckResult]:
    """Validate the TOML config file: existence, syntax, required fields, permissions.

    Returns a list of CheckResult for each aspect checked.
    """
    from gltools.config.settings import get_config_path

    if config_path is None:
        config_path = get_config_path()

    results: list[CheckResult] = []

    # 1. Check file existence
    if not config_path.is_file():
        results.append(
            CheckResult(
                name="Config File",
                status="warn",
                details=f"Config file not found at {config_path}",
                suggestion=(
                    "Create a config file with: mkdir -p ~/.config/gltools && "
                    "cat > ~/.config/gltools/config.toml << 'EOF'\n"
                    '[profiles.default]\nhost = "https://gitlab.com"\nEOF'
                ),
                category="config",
            )
        )
        return results

    # 2. Check TOML syntax
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        results.append(
            CheckResult(
                name="Config File Syntax",
                status="pass",
                details=f"Valid TOML at {config_path}",
                category="config",
            )
        )
    except tomllib.TOMLDecodeError as exc:
        error_msg = str(exc)
        results.append(
            CheckResult(
                name="Config File Syntax",
                status="fail",
                details=f"Invalid TOML in {config_path}: {error_msg}",
                suggestion="Fix the TOML syntax error in your config file. Check for unclosed quotes or brackets.",
                category="config",
            )
        )
        return results

    # 3. Check required fields
    profiles = data.get("profiles", {})
    if not profiles:
        results.append(
            CheckResult(
                name="Config Required Fields",
                status="warn",
                details="No profiles defined in config file",
                suggestion=(
                    "Add a [profiles.default] section with 'host' and configure a token via `gltools auth login`."
                ),
                category="config",
            )
        )
    else:
        default_profile = profiles.get("default", {})
        if default_profile:
            host_set = bool(default_profile.get("host"))
            if host_set:
                results.append(
                    CheckResult(
                        name="Config Required Fields",
                        status="pass",
                        details="Default profile has 'host' configured",
                        category="config",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name="Config Required Fields",
                        status="warn",
                        details="Default profile missing 'host' field",
                        suggestion="Add 'host = \"https://gitlab.example.com\"' to [profiles.default].",
                        category="config",
                    )
                )
        else:
            results.append(
                CheckResult(
                    name="Config Required Fields",
                    status="warn",
                    details="No default profile found; available profiles: " + ", ".join(sorted(profiles.keys())),
                    suggestion="Add a [profiles.default] section or use --profile to select an existing profile.",
                    category="config",
                )
            )

    # 4. Check file permissions
    try:
        file_stat = config_path.stat()
        mode = file_stat.st_mode & 0o777
        # Warn if world-readable (others have read permission)
        if mode & stat.S_IROTH:
            results.append(
                CheckResult(
                    name="Config File Permissions",
                    status="warn",
                    details=f"Config file is world-readable (permissions: {oct(mode)})",
                    suggestion=f"Restrict permissions with: chmod 600 {config_path}",
                    category="config",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="Config File Permissions",
                    status="pass",
                    details=f"Config file permissions: {oct(mode)}",
                    category="config",
                )
            )
    except OSError as exc:
        results.append(
            CheckResult(
                name="Config File Permissions",
                status="warn",
                details=f"Cannot check config file permissions: {exc}",
                category="config",
            )
        )

    return results


def check_profile_resolution(
    *,
    profile_name: str = "default",
    cli_host: str | None = None,
    cli_token: str | None = None,
    config_path: Path | None = None,
) -> CheckResult:
    """Trace profile resolution and report the active configuration sources.

    Shows which profile is active and where each setting is coming from.
    """
    from gltools.config.settings import get_config_path

    if config_path is None:
        config_path = get_config_path()

    trace_parts: list[str] = [f"Active profile: {profile_name}"]

    # Check env var for profile
    env_profile = os.environ.get("GLTOOLS_PROFILE")
    if env_profile:
        trace_parts.append(f"Profile source: GLTOOLS_PROFILE env var ({env_profile})")

    # Determine host source
    env_host = os.environ.get("GLTOOLS_HOST")
    if cli_host:
        trace_parts.append(f"Host source: CLI flag ({cli_host})")
    elif env_host:
        trace_parts.append("Host source: GLTOOLS_HOST env var")
    else:
        # Check config file
        file_host = None
        if config_path.is_file():
            try:
                with open(config_path, "rb") as f:
                    data = tomllib.load(f)
                file_host = data.get("profiles", {}).get(profile_name, {}).get("host")
            except Exception:
                pass

        if file_host:
            trace_parts.append(f"Host source: config file ({profile_name} profile)")
        else:
            trace_parts.append("Host source: default (https://gitlab.com)")

    # Determine token source
    env_token = os.environ.get("GLTOOLS_TOKEN")
    if cli_token:
        trace_parts.append("Token source: CLI flag")
    elif env_token:
        trace_parts.append("Token source: GLTOOLS_TOKEN env var")
    else:
        trace_parts.append("Token source: keyring or config file")

    return CheckResult(
        name="Profile Resolution",
        status="pass",
        details="; ".join(trace_parts),
        category="config",
    )


# ---------------------------------------------------------------------------
# API version compatibility check
# ---------------------------------------------------------------------------


def _parse_gitlab_version(version_string: str) -> tuple[int, int] | None:
    """Parse a GitLab version string (e.g., '16.5.2-ee') into (major, minor)."""
    # Strip enterprise edition suffix and pre-release tags
    clean = version_string.strip().split("-")[0].split("+")[0]
    parts = clean.split(".")
    if len(parts) >= 2:
        try:
            return (int(parts[0]), int(parts[1]))
        except ValueError:
            return None
    return None


def check_api_version(hostname: str, port: int, scheme: str, timeout: float = 10.0) -> CheckResult:
    """Detect GitLab version and check API compatibility.

    Calls GET /api/v4/version (unauthenticated, may fail on locked-down instances).
    """
    url = f"{scheme}://{hostname}:{port}/api/v4/version"
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout), verify=False) as client:  # noqa: S501
            response = client.get(url)

        if response.status_code == 401:
            return CheckResult(
                name="GitLab API Version",
                status="warn",
                details="Version endpoint requires authentication (HTTP 401)",
                suggestion="Version check skipped. The instance may restrict unauthenticated API access.",
                category="api_compat",
            )

        if response.status_code == 403:
            return CheckResult(
                name="GitLab API Version",
                status="warn",
                details="Version endpoint access forbidden (HTTP 403)",
                suggestion="Version check skipped. The instance restricts access to the version endpoint.",
                category="api_compat",
            )

        if response.status_code != 200:
            return CheckResult(
                name="GitLab API Version",
                status="warn",
                details=f"Version endpoint returned HTTP {response.status_code}",
                suggestion="Could not determine GitLab version. Some features may not work as expected.",
                category="api_compat",
            )

        data = response.json()
        version_str = data.get("version", "unknown")
        revision = data.get("revision", "")

        parsed = _parse_gitlab_version(version_str)
        if parsed is None:
            return CheckResult(
                name="GitLab API Version",
                status="warn",
                details=f"Could not parse version string: {version_str}",
                suggestion="Unexpected version format. Some features may not work as expected.",
                category="api_compat",
            )

        major, minor = parsed
        details = f"GitLab {version_str}"
        if revision:
            details += f" (revision: {revision})"

        # Check against minimum version
        if (major, minor) < MINIMUM_GITLAB_VERSION:
            # Find features that won't work
            missing_features: list[str] = []
            for min_ver, features in sorted(GITLAB_VERSION_FEATURES.items()):
                if (major, minor) < min_ver:
                    missing_features.extend(features)

            suggestion_parts = [
                f"GitLab {major}.{minor} is below minimum supported version "
                f"{MINIMUM_GITLAB_VERSION[0]}.{MINIMUM_GITLAB_VERSION[1]}."
            ]
            if missing_features:
                suggestion_parts.append("Features that may not work: " + ", ".join(missing_features))
            suggestion_parts.append("Consider upgrading your GitLab instance.")

            return CheckResult(
                name="GitLab API Version",
                status="warn",
                details=details,
                suggestion=" ".join(suggestion_parts),
                category="api_compat",
            )

        return CheckResult(
            name="GitLab API Version",
            status="pass",
            details=details,
            category="api_compat",
        )

    except httpx.TimeoutException:
        return CheckResult(
            name="GitLab API Version",
            status="warn",
            details=f"Version check timed out ({timeout}s)",
            suggestion="The server may be slow. Version compatibility could not be verified.",
            category="api_compat",
        )
    except httpx.ConnectError as exc:
        return CheckResult(
            name="GitLab API Version",
            status="warn",
            details=f"Cannot connect to version endpoint: {exc}",
            suggestion="Version check skipped due to connectivity issues.",
            category="api_compat",
        )
    except Exception as exc:
        return CheckResult(
            name="GitLab API Version",
            status="warn",
            details=f"Version check failed: {exc}",
            suggestion="Could not determine GitLab version. Some features may not work as expected.",
            category="api_compat",
        )


# ---------------------------------------------------------------------------
# Connectivity checks (unchanged)
# ---------------------------------------------------------------------------


def check_dns(hostname: str) -> CheckResult:
    """Check DNS resolution for the given hostname."""
    try:
        addresses = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if addresses:
            ip = addresses[0][4][0]
            return CheckResult(
                name="DNS Resolution",
                status="pass",
                details=f"Resolved {hostname} to {ip}",
                category="connectivity",
            )
        return CheckResult(
            name="DNS Resolution",
            status="fail",
            details=f"No addresses found for {hostname}",
            suggestion=f"Check that '{hostname}' is a valid hostname. Verify your DNS settings.",
            category="connectivity",
        )
    except socket.gaierror as exc:
        return CheckResult(
            name="DNS Resolution",
            status="fail",
            details=f"Cannot resolve {hostname}: {exc}",
            suggestion=f"Check that '{hostname}' is a valid hostname. Verify your DNS settings and network connection.",
            category="connectivity",
        )
    except Exception as exc:
        return CheckResult(
            name="DNS Resolution",
            status="fail",
            details=f"DNS lookup error: {exc}",
            suggestion="Check your network connection and DNS settings.",
            category="connectivity",
        )


def check_tcp_connection(hostname: str, port: int, timeout: float = 5.0) -> CheckResult:
    """Check TCP connectivity to the host on the given port."""
    try:
        sock = socket.create_connection((hostname, port), timeout=timeout)
        sock.close()
        return CheckResult(
            name="TCP Connection",
            status="pass",
            details=f"Connected to {hostname}:{port}",
            category="connectivity",
        )
    except TimeoutError:
        return CheckResult(
            name="TCP Connection",
            status="fail",
            details=f"Connection to {hostname}:{port} timed out after {timeout}s",
            suggestion="The host may be down or a firewall is blocking the connection.",
            category="connectivity",
        )
    except OSError as exc:
        return CheckResult(
            name="TCP Connection",
            status="fail",
            details=f"Cannot connect to {hostname}:{port}: {exc}",
            suggestion="Check that the host is reachable and the port is correct.",
            category="connectivity",
        )
    except Exception as exc:
        return CheckResult(
            name="TCP Connection",
            status="fail",
            details=f"Connection error: {exc}",
            suggestion="Check your network connection.",
            category="connectivity",
        )


def check_ssl_certificate(hostname: str, port: int = 443, timeout: float = 5.0) -> CheckResult:
    """Check SSL certificate validity for the host."""
    try:
        context = ssl.create_default_context()
        with (
            socket.create_connection((hostname, port), timeout=timeout) as sock,
            context.wrap_socket(sock, server_hostname=hostname) as ssock,
        ):
            cert = ssock.getpeercert()
            if cert:
                subject = dict(x[0] for x in cert.get("subject", ()))
                cn = subject.get("commonName", "unknown")
                not_after = cert.get("notAfter", "unknown")
                return CheckResult(
                    name="SSL Certificate",
                    status="pass",
                    details=f"Valid certificate for {cn} (expires: {not_after})",
                    category="connectivity",
                )
            return CheckResult(
                name="SSL Certificate",
                status="warn",
                details="No certificate information available",
                suggestion="The server may not be providing a proper SSL certificate.",
                category="connectivity",
            )
    except ssl.SSLCertVerificationError as exc:
        if "self-signed" in str(exc).lower() or "self signed" in str(exc).lower():
            return CheckResult(
                name="SSL Certificate",
                status="warn",
                details=f"Self-signed certificate detected: {exc}",
                suggestion="Consider adding the CA certificate to your trust store, or use a proper certificate.",
                category="connectivity",
            )
        return CheckResult(
            name="SSL Certificate",
            status="warn",
            details=f"Certificate verification failed: {exc}",
            suggestion="The SSL certificate may be expired, self-signed, or from an untrusted CA.",
            category="connectivity",
        )
    except ssl.SSLError as exc:
        return CheckResult(
            name="SSL Certificate",
            status="warn",
            details=f"SSL error: {exc}",
            suggestion="Check that the server supports TLS and has a valid certificate.",
            category="connectivity",
        )
    except TimeoutError:
        return CheckResult(
            name="SSL Certificate",
            status="fail",
            details=f"SSL handshake timed out connecting to {hostname}:{port}",
            suggestion="The host may be down or a firewall is blocking the connection.",
            category="connectivity",
        )
    except OSError as exc:
        return CheckResult(
            name="SSL Certificate",
            status="fail",
            details=f"Cannot check SSL certificate: {exc}",
            suggestion="Ensure the host is reachable on the correct port.",
            category="connectivity",
        )
    except Exception as exc:
        return CheckResult(
            name="SSL Certificate",
            status="fail",
            details=f"SSL check error: {exc}",
            suggestion="An unexpected error occurred during SSL verification.",
            category="connectivity",
        )


def check_latency(hostname: str, port: int, scheme: str, timeout: float = 10.0) -> CheckResult:
    """Measure HTTP round-trip latency to the host."""
    url = f"{scheme}://{hostname}:{port}/api/v4/version"
    try:
        start = time.monotonic()
        with httpx.Client(timeout=httpx.Timeout(timeout), verify=False) as client:  # noqa: S501
            response = client.get(url)
        elapsed_ms = (time.monotonic() - start) * 1000

        if elapsed_ms < 500:
            status = "pass"
        elif elapsed_ms < 2000:
            status = "warn"
        else:
            status = "warn"

        return CheckResult(
            name="Latency",
            status=status,
            details=f"Round-trip time: {elapsed_ms:.0f}ms (HTTP {response.status_code})",
            suggestion="High latency may affect CLI responsiveness." if elapsed_ms >= 500 else None,
            category="connectivity",
        )
    except httpx.TimeoutException:
        return CheckResult(
            name="Latency",
            status="fail",
            details=f"Request to {url} timed out after {timeout}s",
            suggestion="The host may be down or experiencing high load.",
            category="connectivity",
        )
    except httpx.ConnectError as exc:
        return CheckResult(
            name="Latency",
            status="fail",
            details=f"Cannot connect to {url}: {exc}",
            suggestion="Check that the host URL is correct and reachable.",
            category="connectivity",
        )
    except Exception as exc:
        return CheckResult(
            name="Latency",
            status="fail",
            details=f"Latency check failed: {exc}",
            suggestion="An unexpected error occurred during the latency check.",
            category="connectivity",
        )


# ---------------------------------------------------------------------------
# Authentication check
# ---------------------------------------------------------------------------


async def check_authentication(
    host: str,
    token: str,
    auth_type: str,
    *,
    profile: str = "default",
    client_id: str | None = None,
) -> CheckResult:
    """Validate authentication by calling GET /api/v4/user."""
    token_refresher = None
    if auth_type == "oauth" and client_id:
        token_refresher = _build_doctor_token_refresher(host, client_id, profile)

    client = GitLabHTTPClient(
        host=host,
        token=token,
        auth_type=auth_type,
        token_refresher=token_refresher,
        retry_config=RetryConfig(max_retries=0),
        timeout=10.0,
    )

    try:
        response = await client.get("/user")
        data = response.json()
        username = data.get("username", "unknown")
        name = data.get("name", "")

        token_display = "OAuth2" if auth_type == "oauth" else "PAT"

        details_parts = [f"Authenticated as {username}"]
        if name:
            details_parts[0] += f" ({name})"
        details_parts.append(f"Token type: {token_display}")

        # Check for token expiry info (GitLab includes this for PATs in some versions)
        if "expires_at" in data and data["expires_at"]:
            details_parts.append(f"Expires: {data['expires_at']}")

        return CheckResult(
            name="Authentication",
            status="pass",
            details="; ".join(details_parts),
            category="auth",
        )
    except Exception as exc:
        exc_str = str(exc)
        if "401" in exc_str or "Authentication failed" in exc_str:
            suggestion = "Token may be expired or invalid."
            if auth_type == "oauth":
                suggestion += " Run `gltools auth login --method web` to re-authenticate."
            else:
                suggestion += " Run `gltools auth login` to configure a new token."
            return CheckResult(
                name="Authentication",
                status="fail",
                details="Authentication failed (401 Unauthorized)",
                suggestion=suggestion,
                category="auth",
            )
        if "403" in exc_str or "Permission denied" in exc_str:
            return CheckResult(
                name="Authentication",
                status="fail",
                details="Permission denied (403 Forbidden)",
                suggestion="Your token may lack the required scopes. Ensure your token has 'api' scope.",
                category="auth",
            )
        if "timed out" in exc_str.lower() or "timeout" in exc_str.lower():
            return CheckResult(
                name="Authentication",
                status="fail",
                details=f"Authentication request timed out: {exc}",
                suggestion="The server may be slow or unreachable. Try again later.",
                category="auth",
            )
        if "connect" in exc_str.lower():
            return CheckResult(
                name="Authentication",
                status="fail",
                details=f"Cannot connect to API: {exc}",
                suggestion="Check your network connection and the configured host URL.",
                category="auth",
            )
        return CheckResult(
            name="Authentication",
            status="fail",
            details=f"Authentication check failed: {exc}",
            suggestion="Run `gltools auth login` to configure authentication.",
            category="auth",
        )
    finally:
        await client.close()


def _build_doctor_token_refresher(host: str, client_id: str, profile: str) -> Any:
    """Build a token refresher callback for the doctor command."""

    async def _refresh() -> str:
        from gltools.config.keyring import get_refresh_token, store_refresh_token, store_token
        from gltools.config.oauth import refresh_access_token

        refresh_tok = get_refresh_token(profile=profile)
        if not refresh_tok:
            msg = "No refresh token available. Re-run `gltools auth login --method web`."
            raise RuntimeError(msg)

        result = await refresh_access_token(host, client_id, refresh_tok)
        store_token(result.access_token, profile=profile)
        if result.refresh_token:
            store_refresh_token(result.refresh_token, profile=profile)
        return result.access_token

    return _refresh


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _render_text_report(report: DoctorReport) -> None:
    """Render a text-formatted diagnostic report to the console."""
    out = Console(force_terminal=None)

    out.print("\n[bold]gltools doctor[/bold] - Diagnostic Report\n")

    status_icons = {
        "pass": "[green]PASS[/green]",
        "warn": "[yellow]WARN[/yellow]",
        "fail": "[red]FAIL[/red]",
    }

    # Group checks by category for display
    category_labels = {
        "config": "Configuration",
        "connectivity": "Connectivity",
        "auth": "Authentication",
        "api_compat": "API Compatibility",
        "general": "General",
    }

    # Gather unique categories in order seen
    seen_categories: list[str] = []
    for check in report.checks:
        if check.category not in seen_categories:
            seen_categories.append(check.category)

    for cat in seen_categories:
        cat_checks = [c for c in report.checks if c.category == cat]
        label = category_labels.get(cat, cat.title())
        out.print(f"\n  [bold underline]{label}[/bold underline]")
        for check in cat_checks:
            icon = status_icons.get(check.status, check.status)
            out.print(f"    {icon}  [bold]{check.name}[/bold]: {check.details}")
            if check.suggestion:
                out.print(f"           [dim]Suggestion: {check.suggestion}[/dim]")

    # Summary
    summary = report.to_dict()["data"]["summary"]
    out.print(
        f"\n[bold]Summary:[/bold] {summary['passed']} passed, "
        f"{summary['warnings']} warnings, {summary['failed']} failed "
        f"(out of {summary['total']} checks)"
    )

    # Prioritized suggestions for failures
    failed_checks = [c for c in report.checks if c.status == "fail" and c.suggestion]
    if failed_checks:
        out.print("\n[bold red]Action Required:[/bold red]")
        for i, check in enumerate(failed_checks, 1):
            out.print(f"  {i}. [bold]{check.name}[/bold]: {check.suggestion}")

    out.print()


def _render_json_report(report: DoctorReport) -> None:
    """Render a JSON-formatted diagnostic report to the console."""
    out = Console(force_terminal=None)
    out.print_json(json.dumps(report.to_dict(), indent=2))


# ---------------------------------------------------------------------------
# Doctor command
# ---------------------------------------------------------------------------


@app.command(name="doctor")
@async_command
async def doctor(
    ctx: typer.Context,
) -> None:
    """Run diagnostic checks on GitLab connectivity, config, auth, and API compatibility."""
    from gltools.config.settings import GitLabConfig

    obj = ctx.ensure_object(dict)
    use_json = obj.get("output_format") == "json"

    report = DoctorReport()

    # --- Configuration checks ---
    try:
        config_results = check_config_file()
        report.checks.extend(config_results)
    except Exception as exc:
        report.checks.append(
            CheckResult(
                name="Config File",
                status="warn",
                details=f"Config validation error: {exc}",
                category="config",
            )
        )

    # Resolve config (needed for connectivity/auth checks)
    config = None
    try:
        config = GitLabConfig.from_config(
            profile=obj.get("profile"),
            cli_overrides={
                "host": obj.get("host"),
                "token": obj.get("token"),
                "output_format": obj.get("output_format"),
            },
        )
    except Exception as exc:
        report.checks.append(
            CheckResult(
                name="Configuration",
                status="fail",
                details=f"Cannot load configuration: {exc}",
                suggestion="Check your config file at ~/.config/gltools/config.toml",
                category="config",
            )
        )

    # Profile resolution trace (even if config failed, trace what we can)
    try:
        profile_name = obj.get("profile") or os.environ.get("GLTOOLS_PROFILE", "default")
        profile_result = check_profile_resolution(
            profile_name=profile_name,
            cli_host=obj.get("host"),
            cli_token=obj.get("token"),
        )
        report.checks.append(profile_result)
    except Exception as exc:
        report.checks.append(
            CheckResult(
                name="Profile Resolution",
                status="warn",
                details=f"Profile resolution trace error: {exc}",
                category="config",
            )
        )

    # If config failed, render what we have and return
    if config is None:
        if use_json:
            _render_json_report(report)
        else:
            _render_text_report(report)
        return

    host = config.host

    # Validate host URL format
    try:
        scheme, hostname, port = _parse_host(host)
    except ValueError as exc:
        report.checks.append(
            CheckResult(
                name="Host URL",
                status="fail",
                details=str(exc),
                suggestion="Set a valid host URL with --host or in your config file.",
                category="connectivity",
            )
        )
        if use_json:
            _render_json_report(report)
        else:
            _render_text_report(report)
        return

    # --- Connectivity checks ---

    # 1. DNS resolution
    dns_result = check_dns(hostname)
    report.checks.append(dns_result)

    # Only continue connectivity checks if DNS passed
    if dns_result.status != "fail":
        # 2. TCP connection
        tcp_result = check_tcp_connection(hostname, port)
        report.checks.append(tcp_result)

        # Only check SSL and latency if TCP passed
        if tcp_result.status != "fail":
            # 3. SSL certificate (only for HTTPS)
            if scheme == "https":
                ssl_result = check_ssl_certificate(hostname, port)
                report.checks.append(ssl_result)

            # 4. Latency measurement
            latency_result = check_latency(hostname, port, scheme)
            report.checks.append(latency_result)

            # 5. API version compatibility
            try:
                version_result = check_api_version(hostname, port, scheme)
                report.checks.append(version_result)
            except Exception as exc:
                report.checks.append(
                    CheckResult(
                        name="GitLab API Version",
                        status="warn",
                        details=f"Version check error: {exc}",
                        suggestion="Could not determine GitLab version.",
                        category="api_compat",
                    )
                )

    # --- Authentication check ---
    if not config.token:
        report.checks.append(
            CheckResult(
                name="Authentication",
                status="warn",
                details="No token configured",
                suggestion="Run `gltools auth login` to configure authentication.",
                category="auth",
            )
        )
    elif dns_result.status == "fail":
        report.checks.append(
            CheckResult(
                name="Authentication",
                status="fail",
                details="Skipped: host is unreachable (DNS failed)",
                suggestion="Fix connectivity issues first, then re-run `gltools doctor`.",
                category="auth",
            )
        )
    else:
        auth_result = await check_authentication(
            host=host,
            token=config.token,
            auth_type=config.auth_type,
            profile=config.profile,
            client_id=config.client_id,
        )
        report.checks.append(auth_result)

    # --- Output ---
    if use_json:
        _render_json_report(report)
    else:
        _render_text_report(report)
