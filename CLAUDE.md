# gltools - GitLab CLI & TUI Tool

## Project Overview
Python CLI + TUI for GitLab, supporting MR/Issue/CI workflows with JSON output for agent integration. Alpha (v0.1.0), ~58 source files, ~1370 tests.

## Tech Stack
- **Python 3.12+**, src layout (`src/gltools/`), PEP 695 generics, `X | Y` union syntax
- **Build**: Hatch (hatchling backend), UV for deps
- **CLI**: Typer with Rich formatting
- **TUI**: Textual (widget-as-screen pattern, not native Screen stack)
- **HTTP**: httpx (async), respx for mocking
- **Models**: Pydantic v2 with `ConfigDict(extra="ignore", populate_by_name=True)`
- **Config**: Pydantic Settings, TOML (`~/.config/gltools/config.toml`), 4-layer precedence
- **Auth**: PAT + OAuth2 (Authorization Code + PKCE, Device Grant); keyring with file fallback (600 perms)
- **Lint**: Ruff (line-length 120, py312 target)
- **Test**: pytest, pytest-asyncio (auto mode), respx

## Key Commands
```bash
uv pip install -e .                    # Install editable
uv run pytest                          # Run tests
uv run ruff check src/ tests/          # Lint
uv run ruff format src/ tests/         # Format
uv run hatch build                     # Build wheel/sdist
gltools --help                         # CLI help
```

## Architecture
```
src/gltools/
├── cli/          # Typer commands (app.py, mr.py, issue.py, ci.py, auth.py, doctor.py, plugin.py, formatting.py)
├── tui/          # Textual app (app.py, commands.py, screens/, widgets/)
├── services/     # Business logic (merge_request.py, issue.py, ci.py, auth.py)
├── client/       # API layer (http.py, gitlab.py, exceptions.py, managers/)
├── models/       # Pydantic models (base.py, merge_request.py, issue.py, pipeline.py, job.py, output.py, user.py)
├── config/       # Settings (settings.py, git_remote.py, keyring.py, oauth.py)
├── logging.py    # Logging infrastructure (setup, formatters, token masking filter)
└── plugins/      # Plugin system (protocol.py)
```

### Layer Flow
CLI/TUI → Services → Client (GitLabClient facade → Managers) → GitLabHTTPClient → GitLab API

## Critical Files
| File | Purpose |
|------|---------|
| `cli/app.py` | Root Typer app, global options (`ctx.obj`), `async_command` decorator, `--verbose`/`--debug`/`--log-file` flags |
| `cli/doctor.py` | `gltools doctor` diagnostic: DNS, TCP, SSL, latency, auth, config, API version checks |
| `logging.py` | `setup_logging()`, `RichFormatter`, `JSONFormatter`, `SensitiveDataFilter`, `mask_sensitive_data()` |
| `cli/formatting.py` | JSON/text output routing, Rich tables, dry-run display |
| `cli/mr.py` | 9 MR commands (list/view/create/merge/approve/diff/note/close/reopen/update) |
| `cli/ci.py` | 8 CI commands (status/list/run/retry/cancel/jobs/logs/artifacts) |
| `client/http.py` | Async HTTP with retry (3 attempts, exp backoff), rate limiting, pagination, streaming, structured request/response logging |
| `client/gitlab.py` | Facade composing 4 resource managers |
| `client/exceptions.py` | 7-class hierarchy with `_mask_token()` for safe logging |
| `config/settings.py` | `GitLabConfig` — CLI flags > env vars > TOML profiles > defaults. Includes `auth_type` and `client_id` fields. |
| `config/oauth.py` | OAuth2 protocol: PKCE, callback server, device flow, token exchange, refresh |
| `models/output.py` | `PaginatedResponse[T]`, `CommandResult`, `DryRunResult`, `ErrorResult` |
| `models/__init__.py` | Forward ref resolution: `PipelineRef` + `MergeRequest.model_rebuild()` |
| `services/merge_request.py` | MR business logic, 3-level project resolution, dry-run |
| `tui/app.py` | Textual app: widget-as-screen routing, keybindings, auth gate |

## Key Patterns
- **Entry point**: `gltools = "gltools.cli.app:app"` (Typer app)
- **Global CLI options**: stored in `ctx.obj` dict (`output_format`, `host`, `token`, `profile`, `quiet`, `verbose`, `debug`, `log_level`, `log_file`)
- **`async_command` decorator**: wraps async handlers with `asyncio.run()` for Typer (MR/Issue use it; CI uses inline `asyncio.run()` instead)
- **`_build_service(ctx)` factory**: each CLI module creates config → client → service; caller does `finally: await client.close()`
- **Service layer**: takes `GitLabClient` + `GitLabConfig`, resolves project via 3-level precedence (`--project` → `config.default_project` → `detect_gitlab_remote()`)
- **Dry-run**: service returns `DryRunResult(method, url, body)` without API call; CLI checks `isinstance(result, DryRunResult)`
- **Manager pattern**: takes `GitLabHTTPClient`, uses `_encode_project()` helper, returns Pydantic models via `model_validate()`
- **Forward refs**: `PipelineRef` defined in `models/__init__.py` before `MergeRequest` import, then `model_rebuild()` resolves string annotations
- **Output envelopes**: `PaginatedResponse[T]` (PEP 695), `CommandResult`, `DryRunResult`, `ErrorResult`
- **Streaming**: `@asynccontextmanager` wrapping `stream_get()` for large payloads (e.g., job logs)
- **TUI screens**: `Widget` subclasses mounted into `#screen-container` Static slot (not Textual's native `Screen` stack)
- **TUI navigation**: custom `Message` subclasses (`MRSelected`, `ItemSelected`) for inter-widget communication
- **TUI async**: `@work(exclusive=True)` and `run_worker()` for non-blocking service calls
- **Config precedence**: CLI flags > env vars (`GLTOOLS_*`) > TOML file > defaults. Env vars temporarily cleared in `from_config()` to prevent BaseSettings double-application.
- **OAuth2 auth**: `--method web` (Authorization Code + PKCE) and `--method device` (Device Grant). Default `--method pat` for backward compat.
- **Bearer vs PAT**: `GitLabHTTPClient` switches between `Authorization: Bearer` and `PRIVATE-TOKEN` based on `auth_type` param.
- **Token refresh**: `token_refresher` callback on `GitLabHTTPClient` transparently refreshes OAuth tokens on 401 (once per request, outside retry budget).
- **Refresh tokens**: Stored via `store_refresh_token()`/`get_refresh_token()` in keyring.py, cleaned up on `delete_token()`.
- **`_make_token_refresher(config)`**: Helper in each CLI module (mr.py, issue.py, ci.py) that builds the refresh callback from config.
- **Logging**: `setup_logging()` called from `main()` callback; `--verbose` (INFO), `--debug` (DEBUG), `--log-file` (JSON file). Default WARNING (silent). `SensitiveDataFilter` applied at handler level masks all tokens. Services log execution trace at DEBUG.
- **Doctor command**: `gltools doctor` runs 7 check types. `CheckResult` dataclass with `category` field for grouped reporting. `DoctorReport` aggregates results. Standalone check functions for testability.
- **Token masking**: `mask_sensitive_data()` in `logging.py` is a superset of `_mask_token()` in `client/exceptions.py`. Both kept for backward compatibility.

## Known Inconsistencies
- **CI layer**: `CIService` takes `project_id` directly (resolved in CLI) unlike MR/Issue services. CI lacks `--project` flag. CI uses inline `asyncio.run()` instead of `@async_command`.
- **Duplicate code**: `_handle_gitlab_error()` near-identical in `mr.py` and `issue.py`. `_get_current_branch()` duplicated in `mr.py` and `services/ci.py`. `_encode_project()` duplicated in MR/Issue managers (missing from Pipeline/Job managers). `_make_token_refresher()` duplicated in `mr.py`, `issue.py`, `ci.py`.
- **TUI stubs**: `MRListScreen._load_data()` and `IssueListScreen._load_data()` are stubs (filter collection works, but no service calls).
- **Auth output**: `auth.py` builds JSON manually instead of using `formatting.py` helpers.
- **Plugin TUI**: `register_tui_plugins()` exists but is never called from app startup.

## Ruff Rules to Watch
- **B008**: `typer.Option` default exemption doesn't apply with `Path` type — use `str | None` and convert inside function body
- **B904**: re-raise with `from None`
- **SIM105**: `contextlib.suppress(Exception)` preferred over `try/except/pass`
- **SIM117**: Combined `with` statements using parenthesized form
- **UP041**: `TimeoutError` not `socket.timeout` in Python 3.12+
- **TCH003**: stdlib type imports in `TYPE_CHECKING` block
- **UP017**: `datetime.UTC` not `timezone.utc`
- **UP046**: PEP 695 type syntax for generics
- **Pydantic**: do NOT use `from __future__ import annotations` in model files

## Test Patterns
- **conftest.py**: `mock_router` (respx) and `http_client` fixtures
- **fixtures/responses.py**: factory functions with `_deep_merge()` for test data overrides
- **TUI tests**: `app.run_test(size=(W,H))` + `pilot.press()` / `pilot.pause()`
- **Widget isolation**: local `App` subclasses wrapping the widget under test
- **Service mocking**: `patch()` + `AsyncMock` in dashboard tests
- **Plugin tests**: mock `entry_points` via `@patch("gltools.plugins.entry_points")`
- **HTTP tests**: respx `@respx.mock` decorator on async methods
- **caplog isolation**: `setup_logging()` sets `propagate=False` on gltools root logger; tests needing `caplog` require autouse fixture to reset `propagate=True`
- **Doctor tests**: standalone check functions mocked independently; `CliRunner` with respx for integration
