"""OAuth2 browser-based login flows for GitLab.

Supports Authorization Code + PKCE (browser redirect) and
Device Authorization Grant (headless/SSH). Uses only stdlib
and existing httpx dependency.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

logger = logging.getLogger(__name__)

# --- Data structures ---


class OAuthError(Exception):
    def __init__(self, message: str, error_code: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(message)


@dataclass
class OAuthTokenResponse:
    access_token: str
    token_type: str
    refresh_token: str | None = None
    expires_in: int | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class OAuthConfig:
    client_id: str
    host: str
    scopes: str = "api"


# --- PKCE utilities ---


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate (code_verifier, code_challenge) using S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    # Base64url encode without padding
    challenge = (
        digest.hex()  # not what we want — need base64url
    )
    # Proper base64url encoding
    import base64

    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# --- Callback server ---


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth redirect code+state."""

    server: _CallbackHTTPServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        error = params.get("error", [None])[0]
        if error:
            error_desc = params.get("error_description", [error])[0]
            self.server.error = error_desc
            self.server.callback_event.set()
            self._send_response("Authentication failed. You can close this tab.")
            return

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        if code and state:
            self.server.auth_code = code
            self.server.auth_state = state
            self.server.callback_event.set()
            self._send_response("Authentication successful! You can close this tab.")
        else:
            self._send_response("Missing authorization code. Please try again.")

    def _send_response(self, message: str) -> None:
        html = f"""<!DOCTYPE html>
<html><head><title>gltools</title></head>
<body style="font-family:system-ui;text-align:center;padding:60px">
<h2>{message}</h2>
</body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default stderr logging
        pass


class _CallbackHTTPServer(HTTPServer):
    """HTTPServer subclass holding callback results."""

    auth_code: str | None = None
    auth_state: str | None = None
    error: str | None = None
    callback_event: threading.Event

    def __init__(self) -> None:
        self.callback_event = threading.Event()
        super().__init__(("127.0.0.1", 0), _CallbackHandler)


class _CallbackServer:
    """Ephemeral localhost HTTP server for OAuth redirect capture."""

    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout
        self._server: _CallbackHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        self._server = _CallbackHTTPServer()
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self._server.server_address[1]

    def wait_for_callback(self) -> tuple[str, str]:
        """Block until callback received. Returns (code, state)."""
        assert self._server is not None
        if not self._server.callback_event.wait(timeout=self._timeout):
            raise OAuthError("Authentication timed out. Try again.")

        if self._server.error:
            raise OAuthError(
                f"Authorization denied: {self._server.error}",
                error_code="access_denied",
            )

        code = self._server.auth_code
        state = self._server.auth_state
        if not code or not state:
            raise OAuthError("No authorization code received.")
        return code, state

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=5)


# --- Token exchange helpers ---


async def _exchange_token(host: str, data: dict[str, str]) -> OAuthTokenResponse:
    """POST to /oauth/token and parse the response."""
    url = f"{host.rstrip('/')}/oauth/token"
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        response = await client.post(url, data=data)

    if response.status_code != 200:
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        error = body.get("error", "unknown_error")
        description = body.get("error_description", response.text)
        raise OAuthError(
            f"Token exchange failed: {description}",
            error_code=error,
        )

    body = response.json()
    return OAuthTokenResponse(
        access_token=body["access_token"],
        token_type=body.get("token_type", "bearer"),
        refresh_token=body.get("refresh_token"),
        expires_in=body.get("expires_in"),
        created_at=body.get("created_at", time.time()),
    )


# --- Authorization Code + PKCE flow ---


async def authorization_code_flow(config: OAuthConfig) -> OAuthTokenResponse:
    """Full browser-based OAuth login using Authorization Code + PKCE."""
    verifier, challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    callback = _CallbackServer()
    try:
        port = callback.start()
        redirect_uri = f"http://127.0.0.1:{port}/callback"

        params = urlencode(
            {
                "client_id": config.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "state": state,
                "scope": config.scopes,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        authorize_url = f"{config.host.rstrip('/')}/oauth/authorize?{params}"

        opened = webbrowser.open(authorize_url)
        if not opened:
            from rich.console import Console

            Console(stderr=True).print(
                f"\n[yellow]Could not open browser. Visit this URL to authenticate:[/yellow]\n{authorize_url}\n"
            )

        code, returned_state = callback.wait_for_callback()

        if returned_state != state:
            raise OAuthError("State mismatch — possible CSRF attack. Try again.")

        return await _exchange_token(
            config.host,
            {
                "grant_type": "authorization_code",
                "client_id": config.client_id,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
        )
    finally:
        callback.shutdown()


# --- Device Authorization Grant flow ---


async def device_authorization_flow(config: OAuthConfig) -> OAuthTokenResponse:
    """Device flow for headless environments. Requires GitLab 17.2+."""
    url = f"{config.host.rstrip('/')}/oauth/authorize_device"

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        response = await client.post(
            url,
            data={
                "client_id": config.client_id,
                "scope": config.scopes,
            },
        )

    if response.status_code in (404, 400):
        raise OAuthError(
            "Device authorization flow not supported. This requires GitLab 17.2+. Use --method web instead."
        )
    if response.status_code != 200:
        raise OAuthError(f"Device authorization request failed: {response.text}")

    body = response.json()
    device_code = body["device_code"]
    user_code = body["user_code"]
    verification_uri = body["verification_uri"]
    expires_in = body.get("expires_in", 900)
    interval = body.get("interval", 5)

    from rich.console import Console

    console = Console(stderr=True)
    console.print(f"\n[bold]Enter this code:[/bold] [cyan bold]{user_code}[/cyan bold]")
    console.print(f"[bold]At:[/bold] {verification_uri}\n")

    webbrowser.open(verification_uri)

    deadline = time.monotonic() + expires_in
    poll_interval = interval

    while time.monotonic() < deadline:
        await _async_sleep(poll_interval)

        try:
            result = await _exchange_token(
                config.host,
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": config.client_id,
                },
            )
            return result
        except OAuthError as exc:
            if exc.error_code == "authorization_pending":
                continue
            if exc.error_code == "slow_down":
                poll_interval += 5
                continue
            if exc.error_code == "expired_token":
                raise OAuthError("Device code expired. Run the command again.") from None
            if exc.error_code == "access_denied":
                raise OAuthError("Authorization was denied by the user.") from None
            raise

    raise OAuthError("Device authorization timed out. Run the command again.")


# --- Token refresh ---


async def refresh_access_token(host: str, client_id: str, refresh_token: str) -> OAuthTokenResponse:
    """Exchange a refresh token for new access + refresh tokens."""
    return await _exchange_token(
        host,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
    )


# --- Helpers ---


async def _async_sleep(seconds: float) -> None:
    """Async sleep wrapper for easier testing."""
    import asyncio

    await asyncio.sleep(seconds)
