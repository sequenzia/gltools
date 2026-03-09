# Codebase Changes Report

## Metadata

| Field | Value |
|-------|-------|
| **Date** | 2026-03-09 |
| **Time** | 18:50 EDT |
| **Branch** | main |
| **Author** | Stephen Sequenzia |
| **Base Commit** | `35a5589` |
| **Latest Commit** | uncommitted |
| **Repository** | git@github.com:sequenzia/gltools.git |

**Scope**: Fix TUI pipeline loading — URL-encode project IDs in Pipeline/Job managers

**Summary**: Fixed "failed to load pipelines: not found: resource" error in the TUI by adding URL encoding for project IDs in Pipeline and Job managers (matching existing MR/Issue manager pattern) and correcting TUI screens to use encoded project paths from git remote detection.

## Overview

- **Files affected**: 6
- **Lines added**: +67
- **Lines removed**: -19
- **Commits**: 0 (uncommitted)

## Files Changed

| File | Status | Lines | Description |
|------|--------|-------|-------------|
| `src/gltools/client/managers/pipelines.py` | Modified | +34 / -8 | Add `_encode_project()` and path helper methods for URL-safe project IDs |
| `src/gltools/client/managers/jobs.py` | Modified | +31 / -9 | Add `_encode_project()` and path helper method for URL-safe project IDs |
| `src/gltools/tui/screens/ci_status.py` | Modified | +1 / -1 | Use `project_path_encoded` instead of raw `project_path` |
| `src/gltools/tui/screens/dashboard.py` | Modified | +1 / -1 | Use `project_path_encoded` instead of raw `project_path` |
| `tests/test_client/test_pipelines.py` | Modified | +8 / -0 | Add test for string project ID URL encoding |
| `tests/test_client/test_jobs.py` | Modified | +9 / -0 | Add test for string project ID URL encoding |

## Change Details

### Modified

- **`src/gltools/client/managers/pipelines.py`** — Added `_encode_project()` helper function (matching existing pattern in MR/Issue managers) and `_base_path()`/`_pipeline_path()` methods to consistently URL-encode project IDs containing slashes (e.g., `group/project` → `group%2Fproject`) across all 5 pipeline API methods (`list`, `get`, `create`, `retry`, `cancel`).

- **`src/gltools/client/managers/jobs.py`** — Added `_encode_project()` helper and `_job_path()` method to URL-encode project IDs across all 4 job API methods (`list`, `get`, `logs`, `artifacts`). Previously, unencoded paths like `group/project` produced malformed API URLs resulting in 404 errors.

- **`src/gltools/tui/screens/ci_status.py`** — Changed `remote_info.project_path` to `remote_info.project_path_encoded` in `_load_pipelines()` to pass URL-encoded project paths to the CI service, matching the CLI's behavior.

- **`src/gltools/tui/screens/dashboard.py`** — Changed `remote_info.project_path` to `remote_info.project_path_encoded` in the dashboard's pipeline loading for consistency and correctness.

- **`tests/test_client/test_pipelines.py`** — Added `test_list_with_string_project_id` verifying that `PipelineManager.list("my-group/my-project")` correctly encodes to `my-group%2Fmy-project` in the API URL.

- **`tests/test_client/test_jobs.py`** — Added `test_list_with_string_project_id` verifying that `JobManager.list("my-group/my-project", 100)` correctly encodes to `my-group%2Fmy-project` in the API URL.

## Git Status

### Unstaged Changes

| Status | File |
|--------|------|
| M | `src/gltools/client/managers/jobs.py` |
| M | `src/gltools/client/managers/pipelines.py` |
| M | `src/gltools/tui/screens/ci_status.py` |
| M | `src/gltools/tui/screens/dashboard.py` |
| M | `tests/test_client/test_jobs.py` |
| M | `tests/test_client/test_pipelines.py` |

## Session Commits

No commits in this session. All changes are uncommitted.
