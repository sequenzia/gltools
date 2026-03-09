# Execution Context

## Project Patterns
- src layout: `src/gltools/` is the package root
- Typer for CLI (`gltools.cli.app:app`), global options in `ctx.obj`
- Hatch build system with hatchling, UV for deps
- Ruff: line-length 120, py312, TCH003, UP017, UP046, B904, SIM105, SIM117, UP041
- BaseGitLabModel: ConfigDict(extra="ignore", populate_by_name=True)
- Manager pattern: take GitLabHTTPClient in constructor, _encode_project helper, respx for mocking
- Output formatting: Rich tables for text, model_dump_json for JSON, Console(force_terminal=None) for auto TTY
- Response factories in tests/fixtures/responses.py with _deep_merge for nested overrides
- Ruff B008: `typer.Option` exemption doesn't apply with `Path` type — use `str | None` and convert inside function
- Service trace logging: DEBUG level for method entry/exit, include key identifiers
- Config state logging: INFO level at service construction
- Logger naming: `logging.getLogger("gltools.{module_path}")` matching source tree
- Test caplog isolation: autouse fixture to reset propagate=True
- Doctor command: CheckResult with category field for grouped reporting

## Key Decisions
- Config: `~/.config/gltools/config.toml`, Pydantic Settings with manual env merge
- Token masking: `mask_sensitive_data()` in logging.py is superset of `_mask_token()` in exceptions.py
- Doctor: CheckResult dataclass, SSL self-signed = warn, version checking via /api/v4/version
- HTTP logging: isEnabledFor(DEBUG) guards for performance

## Known Issues
- Pydantic Settings env var precedence workaround (temporarily clearing env vars)
- setup_logging() sets propagate=False on gltools root logger — breaks caplog without fixture
- Pre-existing: test_keyring test_warns_on_wrong_permissions intermittently fails in full suite

## File Map
- `src/gltools/cli/app.py` - Main Typer app, --verbose/--debug/--log-file flags
- `src/gltools/cli/doctor.py` - Doctor: DNS, TCP, SSL, latency, auth, config, API version checks
- `src/gltools/logging.py` - Logging: setup_logging(), formatters, SensitiveDataFilter, mask_sensitive_data()
- `src/gltools/client/http.py` - GitLabHTTPClient with structured HTTP logging
- `src/gltools/services/merge_request.py` - MR service with DEBUG trace logging
- `src/gltools/services/issue.py` - Issue service with DEBUG trace logging
- `src/gltools/services/ci.py` - CI service with DEBUG trace logging
- `tests/test_logging.py` - 85 tests (formatters, masking, concurrent)
- `tests/test_cli/test_app.py` - CLI tests including logging flags
- `tests/test_cli/test_doctor.py` - 85 tests for doctor command
- `tests/test_client/test_http.py` - HTTP tests including logging
- `tests/test_services/test_service_logging.py` - 19 service trace tests
- `tests/test_cli/test_config_logging.py` - 7 config state tests

## Task History
### Prior Sessions Summary
Tasks 1-39 all PASSED across 12 waves. Built complete gltools codebase.

### Task [5]-[9]: Phase 1 Logging Infrastructure - ALL PASS
- Logging module, CLI flags, token masking, HTTP logging, execution trace logging

### Task [10]: Add tests for logging infrastructure - PASS
- Gap analysis found coverage was 98%+ from tasks 5-9; added 4 concurrent/timing tests

### Task [11]: Implement gltools doctor command - PASS
- CheckResult dataclass, DoctorReport, 5 check types, standalone testable functions

### Task [12]: Add configuration and API compatibility checks to doctor - PASS
- Config file validation, profile resolution trace, API version check via /api/v4/version
- CheckResult.category for grouped rendering, GITLAB_VERSION_FEATURES for compat warnings
- 35 new tests added (85 total for doctor)
