# gltools - GitLab CLI & TUI Tool

## Project Overview
Python CLI + TUI for GitLab, supporting MR/Issue/CI workflows with JSON output for agent integration.

## Tech Stack
- **Python 3.12+**, src layout (`src/gltools/`)
- **Build**: Hatch (hatchling backend), UV for deps
- **CLI**: Typer with Rich formatting
- **TUI**: Textual
- **HTTP**: httpx (async), respx for mocking
- **Models**: Pydantic v2 with `ConfigDict(extra="ignore", populate_by_name=True)`
- **Config**: Pydantic Settings, TOML (`~/.config/gltools/config.toml`)
- **Auth**: keyring with file fallback
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
├── cli/          # Typer commands (app.py, mr.py, issue.py, ci.py, auth.py, plugin.py, formatting.py)
├── tui/          # Textual app (app.py, commands.py, screens/, widgets/)
├── services/     # Business logic (merge_request.py, issue.py, ci.py, auth.py)
├── client/       # API layer (http.py, gitlab.py, exceptions.py, managers/)
├── models/       # Pydantic models (base.py, merge_request.py, issue.py, pipeline.py, job.py, output.py)
├── config/       # Settings (settings.py, git_remote.py, keyring.py)
└── plugins/      # Plugin system (protocol.py)
```

## Key Patterns
- **Entry point**: `gltools = "gltools.cli.app:app"` (Typer app)
- **Global CLI options**: stored in `ctx.obj` dict
- **Service layer**: takes GitLabClient + GitLabConfig, resolves project via 3-level precedence
- **Dry-run**: returns `DryRunResult` without API call
- **Manager pattern**: takes `GitLabHTTPClient`, uses `_encode_project` helper
- **Forward refs**: `TYPE_CHECKING` + string annotation + `model_rebuild()` in `__init__.py`
- **Output envelopes**: `PaginatedResponse[T]`, `CommandResult`, `DryRunResult`, `ErrorResult`
- **Streaming**: `@asynccontextmanager` wrapping `stream_get()`

## Ruff Rules to Watch
- **B904**: re-raise with `from None`
- **TCH003**: stdlib type imports in `TYPE_CHECKING` block
- **UP017**: `datetime.UTC` not `timezone.utc`
- **UP046**: PEP 695 type syntax for generics
- **Pydantic**: do NOT use `from __future__ import annotations` in model files
