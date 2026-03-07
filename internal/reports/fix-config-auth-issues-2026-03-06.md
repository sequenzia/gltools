# Codebase Changes Report

## Metadata

| Field | Value |
|-------|-------|
| **Date** | 2026-03-06 |
| **Time** | 22:45 EST |
| **Branch** | main |
| **Author** | Stephen Sequenzia |
| **Base Commit** | d050fe0 |
| **Latest Commit** | uncommitted |
| **Repository** | git@github.com:sequenzia/gltools.git |

**Scope**: Fix three known issues from the config & auth breakdown report

**Summary**: Fixed CLI commands not accessing keyring-stored tokens (high severity), added thread safety to env var handling in `from_config()` (medium severity), and replaced the bare httpx client in auth validation with `GitLabHTTPClient` for retry/rate-limit support (low severity).

## Overview

All three known issues identified in `internal/docs/config-auth-breakdown-2026-03-06.md` have been resolved. The keyring fallback was centralized in `from_config()` so all callers (CLI, TUI, future code) automatically benefit, redundant TUI workarounds were removed, and the auth service now uses the shared HTTP client infrastructure.

- **Files affected**: 6
- **Lines added**: +177
- **Lines removed**: -77
- **Commits**: 0 (uncommitted)

## Files Changed

| File | Status | Lines | Description |
|------|--------|-------|-------------|
| `src/gltools/config/settings.py` | Modified | +34 / -11 | Added keyring fallback and threading lock in `from_config()` |
| `src/gltools/services/auth.py` | Modified | +38 / -38 | Replaced bare httpx with `GitLabHTTPClient` in `validate_token()` |
| `src/gltools/tui/app.py` | Modified | +3 / -3 | Removed redundant keyring fallback in `on_mount()` |
| `src/gltools/tui/screens/dashboard.py` | Modified | +3 / -3 | Removed redundant keyring fallback in `_create_client()` |
| `tests/test_config/test_settings.py` | Modified | +94 / -0 | Added keyring fallback tests, thread safety test, autouse mock fixture |
| `tests/test_services/test_auth.py` | Modified | +82 / -82 | Rewrote `TestValidateToken` to mock `GitLabHTTPClient` |

## Change Details

### Modified

- **`src/gltools/config/settings.py`** — Added `import threading` and a module-level `_from_config_lock`. In `from_config()`, added a keyring fallback block after the 3-layer merge (file < env < CLI) that calls `get_token(profile)` when no token is found from any other source. Wrapped the env var pop/restore critical section with `_from_config_lock` to prevent thread-safety issues.

- **`src/gltools/services/auth.py`** — Removed `import httpx`. Rewrote `validate_token()` to use `GitLabHTTPClient` with `RetryConfig(max_retries=2, base_delay=0.5)` instead of a bare `httpx.AsyncClient`. Maps `GitLabAuthError` to `None` return, and `GitLabConnError`/`GitLabTimeout` to builtin `ConnectionError` to preserve the method's API contract. Client is always closed via `finally` block.

- **`src/gltools/tui/app.py`** — Removed `from gltools.config.keyring import get_token` import. Changed `on_mount()` to use `self._config.token` directly instead of the `or get_token(...)` fallback, since `from_config()` now handles keyring lookup.

- **`src/gltools/tui/screens/dashboard.py`** — Removed `from gltools.config.keyring import get_token` deferred import from `_create_client()`. Changed to use `self._config.token` directly.

- **`tests/test_config/test_settings.py`** — Added autouse `mock_keyring_get_token` fixture that patches `gltools.config.keyring.get_token` to return `None`, preventing real keyring queries during tests. Added `TestKeyringFallback` class with 6 tests covering: keyring token used when no other source, CLI/env/file tokens override keyring, `None` keyring keeps empty token, and correct profile passed to keyring. Added `TestThreadSafety` class with a concurrent `ThreadPoolExecutor` test.

- **`tests/test_services/test_auth.py`** — Replaced `import httpx` with imports for `GitLabAuthError`, `GitLabConnError`, `GitLabTimeout`. Added `_mock_client()` helper method. Rewrote all 4 `TestValidateToken` tests to mock `GitLabHTTPClient` instead of `httpx.AsyncClient`, including `close()` assertion on each test. Existing `TestLogin`, `TestGetStatus`, `TestLogout`, and `TestSaveHostToConfig` classes unchanged.

## Git Status

### Unstaged Changes

| Status | File |
|--------|------|
| M | `src/gltools/config/settings.py` |
| M | `src/gltools/services/auth.py` |
| M | `src/gltools/tui/app.py` |
| M | `src/gltools/tui/screens/dashboard.py` |
| M | `tests/test_config/test_settings.py` |
| M | `tests/test_services/test_auth.py` |

## Test Results

All 964 tests pass (7 new tests added). No regressions.

```
964 passed in 10.61s
```
