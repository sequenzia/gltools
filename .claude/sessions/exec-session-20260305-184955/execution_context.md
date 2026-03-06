# Execution Context

## Project Patterns
- src layout: `src/gltools/` is the package root
- Typer for CLI (`gltools.cli.app:app`), global options in `ctx.obj`
- Hatch build system with hatchling, UV for deps
- Ruff: line-length 120, py312, TCH003, UP017, UP046, B904
- BaseGitLabModel: ConfigDict(extra="ignore", populate_by_name=True)
- Models re-exported via `src/gltools/models/__init__.py` with `__all__`
- Manager pattern: take GitLabHTTPClient in constructor, _encode_project helper, respx for mocking
- Output formatting: Rich tables for text, model_dump_json for JSON, Console(force_terminal=None) for auto TTY
- Response factories in tests/fixtures/responses.py with _deep_merge for nested overrides
- Ruff B904: re-raise exceptions with `from None`
- Streaming: @asynccontextmanager wrapping stream_get()

## Key Decisions
- Config: `~/.config/gltools/config.toml`, Pydantic Settings with manual env merge
- Exceptions: client/exceptions.py with token masking
- PipelineRef forward ref: TYPE_CHECKING + string annotation + model_rebuild()
- GitLab merge API uses `should_remove_source_branch` not `delete_source_branch`
- Diff endpoint is `/diffs` not `/diff`

## Known Issues
- Pydantic Settings env var precedence workaround (temporarily clearing env vars)
- Some pre-existing test failures between waves (resolved by later tasks)

## File Map
- `src/gltools/cli/app.py` - Main Typer app with global options, subcommand groups
- `src/gltools/cli/formatting.py` - Output formatting (JSON/text, Rich tables, colored status)
- `src/gltools/cli/plugin.py` - Plugin CLI commands
- `src/gltools/models/` - All Pydantic models (base, user, MR, issue, job, pipeline, output)
- `src/gltools/config/settings.py` - GitLabConfig, TOML loading
- `src/gltools/config/git_remote.py` - Git remote URL parsing
- `src/gltools/config/keyring.py` - Keyring integration with file fallback
- `src/gltools/client/http.py` - GitLabHTTPClient, PaginationInfo, RetryConfig
- `src/gltools/client/exceptions.py` - Custom exceptions with token masking
- `src/gltools/client/managers/merge_requests.py` - MergeRequestManager (9 methods)
- `src/gltools/client/managers/issues.py` - IssueManager (8 methods)
- `src/gltools/client/managers/pipelines.py` - PipelineManager (5 methods)
- `src/gltools/client/managers/jobs.py` - JobManager (4 methods + streaming)
- `src/gltools/plugins/` - Plugin protocol and discovery
- `tests/fixtures/responses.py` - Response factories for all API types
- `tests/conftest.py` - Shared fixtures (mock_router, http_client)

## Task History
### Prior Summary
Tasks 1-6, 7-10, 15-17, 26, 37 all PASSED (18 tasks). Built: project scaffolding, all models, config system, git remote detection, CLI framework, HTTP client, all resource managers (MR/Issue/Pipeline/Job), output formatting, test infrastructure, keyring integration, plugin system, PyPI packaging.

### Task [17]: Implement output formatting system - PASS
- Key: Rich tables, colored status, JSON/text modes, quiet support, 45 tests

### Task [11]: MergeRequest resource manager - PASS
- Key: 9 methods, _encode_project helper, should_remove_source_branch, 17 tests

### Task [12]: Issue resource manager - PASS
- Key: 8 methods, close/reopen via state_event, B904 fix, 17 tests

### Task [13]: Pipeline and Job resource managers - PASS
- Key: PipelineManager (5 methods) + JobManager (4 methods + streaming), 23 tests

### Task [15]: Set up test infrastructure with respx fixtures - PASS
- Key: Response factories with _deep_merge, mock_router fixture, 16 tests
