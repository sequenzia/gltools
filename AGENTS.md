# AGENTS.md - Agent Integration Guide

## Overview

gltools is designed with first-class support for coding agents and automation scripts. The CLI provides structured JSON output, dry-run previews, and predictable exit codes.

## Agent-Friendly Features

### Structured JSON Output
- Pass `--json` globally for consistent JSON envelopes on all commands
- Set `GLTOOLS_OUTPUT_FORMAT=json` as default
- Responses: `{"status": "success", "data": {...}}` or `{"status": "error", "error": "...", "code": N}`
- Paginated lists include `pagination: {page, per_page, total, total_pages}`

### Dry-Run Support
- All mutating commands support `--dry-run` to preview the API call without executing
- Returns method, URL, and params for verification before committing

### Project Auto-Detection
- Project resolved from git remote automatically (tries `origin` first)
- Override with `--project group/name` or `GLTOOLS_DEFAULT_PROJECT`

### Exit Codes
- `0` = success
- `1` = error (auth failure, not found, API error)

## Key Commands for Agents

| Task | Command |
|------|---------|
| List open MRs | `gltools --json mr list --state opened` |
| View MR details | `gltools --json mr view <iid>` |
| Create MR | `gltools --json mr create --title "..." --target main` |
| Merge MR | `gltools --json mr merge <iid> --squash` |
| Check CI status | `gltools --json ci status --ref <branch>` |
| View job logs | `gltools --json ci logs <job_id>` |
| Preview action | `gltools --json mr merge <iid> --dry-run` |

## Architecture Notes for Contributors

### Adding New Commands
1. Add Typer command in `src/gltools/cli/<resource>.py`
2. Add service method in `src/gltools/services/<resource>.py`
3. Add manager method in `src/gltools/client/managers/<resource>.py`
4. Add/update Pydantic model in `src/gltools/models/<resource>.py`
5. Use `formatting.py` helpers for output (not manual JSON)
6. Wrap async handlers with `@async_command` decorator

### Key Conventions
- Service methods accept `dry_run: bool` for mutating operations
- Services resolve project internally via `_resolve_project()`
- Managers use `_encode_project()` for URL-safe project paths
- Output wrapped in `CommandResult`, `PaginatedResponse[T]`, or `ErrorResult`
