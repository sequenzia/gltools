## Synthesized Analysis: gltools Codebase

### Architecture Overview

gltools is a well-structured Python CLI+TUI tool for GitLab, following a clean 4-layer architecture: CLI/TUI → Services → Client/Managers → HTTP. The codebase comprises 51 source files (~30k lines) with 957 tests across 47 test files, all committed as a single MVP feature commit.

The design philosophy prioritizes layered separation: the HTTP layer handles auth, retries, and pagination; typed resource managers wrap API endpoints; service classes orchestrate business logic with project resolution and dry-run support; and the CLI/TUI layers handle user interaction and output formatting. The plugin system provides an extensibility mechanism via entry points, though TUI plugin registration is not yet wired.

Modern Python 3.12+ features throughout — PEP 695 generics, X | Y union syntax, datetime.UTC. Pydantic v2 models use ConfigDict(extra="ignore") for forward-compatible API parsing. All HTTP operations are async (httpx), with Typer commands bridged via asyncio.run().

### Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| src/gltools/cli/app.py | Root Typer app, global options, async_command decorator | High |
| src/gltools/cli/formatting.py | JSON/text output routing, Rich tables | High |
| src/gltools/cli/mr.py | 9 MR commands | High |
| src/gltools/cli/ci.py | 8 CI commands | High |
| src/gltools/cli/issue.py | 7 Issue commands | High |
| src/gltools/client/http.py | Async HTTP client with retry, rate limiting, pagination, streaming | High |
| src/gltools/client/gitlab.py | Facade composing 4 resource managers | High |
| src/gltools/client/exceptions.py | 7-class exception hierarchy with token masking | High |
| src/gltools/config/settings.py | GitLabConfig with 4-layer precedence | High |
| src/gltools/models/output.py | Output envelopes: PaginatedResponse[T], CommandResult, DryRunResult, ErrorResult | High |
| src/gltools/services/merge_request.py | MR business logic with 3-level project resolution, dry-run | High |
| src/gltools/tui/app.py | Main Textual app: screen routing, keybindings, auth gate | High |

### Patterns & Conventions

- async_command decorator: Bridges async service calls to sync Typer commands via asyncio.run()
- _build_service(ctx, project) factory: Each CLI module creates its own
- 3-level project resolution: --project flag → config.default_project → detect_gitlab_remote()
- Dry-run pattern: Service returns DryRunResult early; CLI checks isinstance()
- Output envelopes: CommandResult, PaginatedResponse[T], ErrorResult
- Manager pattern: Takes GitLabHTTPClient, builds API paths with _encode_project()
- Forward reference resolution: PipelineRef in models/__init__.py, model_rebuild()
- Config precedence: CLI flags > env vars > TOML > defaults
- TUI screen-as-widget pattern (not native Screen stack)

### Challenges & Risks

| Challenge | Severity |
|-----------|----------|
| CI layer inconsistency (different pattern than MR/Issue) | Medium |
| Duplicate code across CLI modules (_handle_gitlab_error, _get_current_branch, _encode_project) | Medium |
| TUI list screen stubs (MRListScreen, IssueListScreen _load_data not wired) | Medium |
| Auth formatting bypass (manual JSON instead of formatting.py) | Low |
| Widget-as-screen TUI pattern (loses native navigation) | Low |
| Plugin TUI registration gap (register_tui_plugins never called) | Low |
| _encode_project inconsistency (missing from Pipeline/Job managers) | Low |

### Recommendations

1. Consolidate duplicate code: Extract shared helpers, unify _encode_project
2. Align CI service with MR/Issue pattern: Internal project resolution, @async_command
3. Wire TUI list screen services: Complete _load_data() stubs
4. Fix _encode_project in Pipeline/Job managers
5. Standardize auth output via formatting.py
6. Wire plugin TUI registration
