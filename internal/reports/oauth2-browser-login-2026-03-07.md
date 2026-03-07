# Codebase Changes Report

## Metadata

| Field | Value |
|-------|-------|
| **Date** | 2026-03-07 |
| **Time** | 00:29 EST |
| **Branch** | main |
| **Author** | Stephen Sequenzia |
| **Base Commit** | 5833338 |
| **Latest Commit** | uncommitted |
| **Repository** | git@github.com:sequenzia/gltools.git |

**Scope**: OAuth2 browser-based login

**Summary**: Added OAuth2 authentication support to gltools with Authorization Code + PKCE (browser redirect) and Device Authorization Grant (headless/SSH) flows, alongside transparent token refresh on 401 responses. All changes are backward compatible with existing PAT authentication.

## Overview

This change introduces a complete OAuth2 login system across all layers of the application — from protocol implementation to CLI commands, with full test coverage.

- **Files affected**: 16
- **Lines added**: +1,080
- **Lines removed**: -196
- **Commits**: 0 (all changes uncommitted)

## Files Changed

| File | Status | Lines | Description |
|------|--------|-------|-------------|
| `src/gltools/config/oauth.py` | Added | +268 | OAuth2 protocol module with PKCE, callback server, device flow, token exchange, refresh |
| `tests/test_config/test_oauth.py` | Added | +248 | Tests for OAuth module covering all flows and error cases |
| `src/gltools/services/auth.py` | Modified | +81 / -2 | Added `oauth_login()`, `auth_type` to dataclasses, generalized config saving |
| `tests/test_services/test_auth.py` | Modified | +227 / -2 | Tests for OAuth login, auth_type in status, save profile config |
| `src/gltools/cli/auth.py` | Modified | +171 / -50 | Added `--method` option (`pat`/`web`/`device`), auth_type in status output |
| `tests/test_cli/test_auth.py` | Modified | +166 | Tests for `--method` flag, OAuth login flows, auth_type in JSON output |
| `src/gltools/client/http.py` | Modified | +47 / -10 | Bearer auth header switching, token refresh on 401, while-loop retry refactor |
| `tests/test_client/test_http.py` | Modified | +151 / -3 | Tests for Bearer auth, token refresh, refresh-only-once, refresher failure |
| `src/gltools/config/keyring.py` | Modified | +151 / -40 | Refresh token storage/retrieval/deletion, generic file I/O helpers |
| `tests/test_config/test_keyring.py` | Modified | +130 / -1 | Tests for refresh token CRUD and delete_token cleanup |
| `src/gltools/cli/mr.py` | Modified | +28 / -2 | Wired auth_type + token_refresher in `_build_service`, added `_make_token_refresher` |
| `src/gltools/cli/issue.py` | Modified | +41 / -2 | Same as mr.py — OAuth wiring in service builder |
| `src/gltools/cli/ci.py` | Modified | +32 / -2 | Same pattern for CI service builder |
| `src/gltools/client/gitlab.py` | Modified | +21 / -4 | Pass-through `auth_type` and `token_refresher` to HTTP client |
| `src/gltools/config/settings.py` | Modified | +14 / -12 | Added `auth_type` and `client_id` fields to `GitLabConfig` |
| `CLAUDE.md` | Modified | +16 / -6 | Updated project docs with OAuth patterns and architecture |

## Change Details

### Added

- **`src/gltools/config/oauth.py`** — New OAuth2 protocol module implementing two GitLab-compatible flows: Authorization Code + PKCE (opens browser, captures redirect via ephemeral localhost server) and Device Authorization Grant (displays code + URL for headless environments). Also provides `refresh_access_token()` for transparent token renewal. Uses only stdlib (`http.server`, `hashlib`, `secrets`, `webbrowser`, `threading`) plus existing `httpx`.

- **`tests/test_config/test_oauth.py`** — 13 test cases covering PKCE pair generation/uniqueness, callback server lifecycle, timeout behavior, authorization code flow success/state-mismatch, device flow success/unsupported-version, token refresh success/failure, and token exchange error handling.

### Modified

- **`src/gltools/config/keyring.py`** — Added parallel refresh token storage functions (`store_refresh_token`, `get_refresh_token`, `delete_refresh_token`) mirroring the existing access token pattern. Refactored file I/O into generic `_write_file`/`_read_file`/`_delete_file` helpers that both access and refresh token functions use. `delete_token()` now also cleans up the corresponding refresh token.

- **`src/gltools/config/settings.py`** — Added two new fields to `GitLabConfig`: `auth_type: str = "pat"` and `client_id: str | None = None`. Both are string-typed so they pass through the existing `load_profile_from_toml` filter. Fully backward compatible — missing fields default to PAT behavior.

- **`src/gltools/client/http.py`** — `GitLabHTTPClient` constructor accepts `auth_type` and `token_refresher` parameters. `_build_client()` switches between `Authorization: Bearer` (OAuth) and `PRIVATE-TOKEN` (PAT) headers. The retry loop was refactored from `for` to `while` to allow 401 token refresh without consuming the retry budget. On 401, if a `token_refresher` is present, it's called once; on success the client is rebuilt with the new token and the request retried.

- **`src/gltools/client/gitlab.py`** — `GitLabClient` constructor now accepts and passes through `auth_type` and `token_refresher` to the underlying `GitLabHTTPClient`.

- **`src/gltools/services/auth.py`** — Added `auth_type` field to both `AuthStatus` and `LoginResult` dataclasses. Added `oauth_login()` method that orchestrates the OAuth flow, validates the obtained token, stores access + refresh tokens, and saves OAuth config to TOML. Renamed `_save_host_to_config` to `_save_profile_config` to also persist `auth_type` and `client_id`. `validate_token()` now accepts an `auth_type` parameter. `get_status()` reads and reports `auth_type` from profile data.

- **`src/gltools/cli/auth.py`** — `login` command now accepts `--method`/`-m` option with values `pat` (default, unchanged behavior), `web` (Authorization Code + PKCE), or `device` (Device Grant). OAuth methods prompt for Application ID instead of token. Status command displays `auth_type` in both text and JSON output. JSON login response includes `auth_type`.

- **`src/gltools/cli/mr.py`**, **`src/gltools/cli/issue.py`**, **`src/gltools/cli/ci.py`** — `_build_service()` now reads `config.auth_type` and `config.client_id`, builds a `token_refresher` callback for OAuth clients, and passes both through to `GitLabClient`. Each file has an identical `_make_token_refresher()` helper.

- **`CLAUDE.md`** — Updated project overview (file/test counts), auth description, architecture diagram, critical files table, key patterns, and known inconsistencies to reflect OAuth2 support.

## Git Status

### Unstaged Changes

| Status | File |
|--------|------|
| Modified | `CLAUDE.md` |
| Modified | `src/gltools/cli/auth.py` |
| Modified | `src/gltools/cli/ci.py` |
| Modified | `src/gltools/cli/issue.py` |
| Modified | `src/gltools/cli/mr.py` |
| Modified | `src/gltools/client/gitlab.py` |
| Modified | `src/gltools/client/http.py` |
| Modified | `src/gltools/config/keyring.py` |
| Modified | `src/gltools/config/settings.py` |
| Modified | `src/gltools/services/auth.py` |
| Modified | `tests/test_cli/test_auth.py` |
| Modified | `tests/test_client/test_http.py` |
| Modified | `tests/test_config/test_keyring.py` |
| Modified | `tests/test_services/test_auth.py` |

### Untracked Files

| File |
|------|
| `src/gltools/config/oauth.py` |
| `tests/test_config/test_oauth.py` |

## Session Commits

No commits in this session. All changes are uncommitted.
