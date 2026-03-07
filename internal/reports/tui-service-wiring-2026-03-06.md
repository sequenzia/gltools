# Codebase Changes Report

## Metadata

| Field | Value |
|-------|-------|
| **Date** | 2026-03-06 |
| **Time** | 23:34 EST |
| **Branch** | main |
| **Author** | Stephen Sequenzia |
| **Base Commit** | fa7a693 |
| **Latest Commit** | uncommitted |
| **Repository** | git@github.com:sequenzia/gltools.git |

**Scope**: TUI service wiring — connect MR, Issue, and CI screens to backend services

**Summary**: Replaced placeholder TUI screens with real screen widgets and wired their stub `_load_data()` methods to the service layer, enabling MR list, Issue list, and CI pipeline screens to fetch and display live data from GitLab.

## Overview

The TUI had two problems preventing data display: (1) `app.py` mounted placeholder `Static` subclasses instead of the real screen widgets from `screens/`, and (2) the real screen widgets had stub `_load_data()` methods that never called any services. This change removes the placeholders, switches to the real screens, and implements the service integration following the same pattern already working in the Dashboard screen.

- **Files affected**: 6
- **Lines added**: +149
- **Lines removed**: -128

## Files Changed

| File | Status | Lines | Description |
|------|--------|-------|-------------|
| `src/gltools/tui/app.py` | Modified | +10 / -88 | Removed 3 placeholder screen classes, import and mount real screen widgets |
| `src/gltools/tui/screens/ci_status.py` | Modified | +40 / -6 | Wired `_load_pipelines()` to CIService with client lifecycle and error handling |
| `src/gltools/tui/screens/issue_list.py` | Modified | +42 / -8 | Wired `_load_data()` to IssueService with filter support and error handling |
| `src/gltools/tui/screens/mr_list.py` | Modified | +41 / -8 | Wired `_load_data()` to MergeRequestService with filter support and error handling |
| `tests/test_tui/test_app.py` | Modified | +12 / -12 | Updated imports and assertions to reference new screen class names |
| `tests/test_tui/test_commands.py` | Modified | +4 / -4 | Updated imports from placeholder classes to real screen classes |

## Change Details

### Modified

- **`src/gltools/tui/app.py`** — Removed three placeholder screen classes (`MergeRequestScreen`, `IssueScreen`, `CIScreen`) that only displayed static loading text. Updated `_show_screen()` to instantiate the real screen widgets (`MRListScreen`, `IssueListScreen`, `CIStatusScreen`) from `tui/screens/`. Added imports for the real screen modules and replaced the `Widget` type annotation usage.

- **`src/gltools/tui/screens/mr_list.py`** — Replaced the stub `_load_data()` method with a working implementation that creates a `GitLabClient`, instantiates `MergeRequestService`, reads the current filter state via `get_filters()`, calls `service.list_mrs()` with the appropriate parameters (mapping "all" state to `None`), and populates the DataTable via `populate_table()`. Added logging and error notification via `app.notify()`. Client is properly closed in a `finally` block.

- **`src/gltools/tui/screens/issue_list.py`** — Same pattern as MR list, using `IssueService.list_issues()`. Maps filter fields including `assignee` and `milestone` from the filter bar to the service call parameters.

- **`src/gltools/tui/screens/ci_status.py`** — Replaced the stub `_load_pipelines()` with a working implementation that resolves the project (from config or git remote detection), creates a `CIService` with the appropriate managers, and calls `service.list_pipelines()`. Results are passed to `set_pipelines()` which handles the display and auto-refresh timer.

- **`tests/test_tui/test_app.py`** — Updated all imports and widget query assertions to use `MRListScreen`, `IssueListScreen`, and `CIStatusScreen` instead of the removed placeholder classes.

- **`tests/test_tui/test_commands.py`** — Updated two test methods that imported `MergeRequestScreen` from `gltools.tui.app` to import `MRListScreen` from `gltools.tui.screens.mr_list` instead.

## Git Status

### Unstaged Changes

| Status | File |
|--------|------|
| M | `src/gltools/tui/app.py` |
| M | `src/gltools/tui/screens/ci_status.py` |
| M | `src/gltools/tui/screens/issue_list.py` |
| M | `src/gltools/tui/screens/mr_list.py` |
| M | `tests/test_tui/test_app.py` |
| M | `tests/test_tui/test_commands.py` |

## Session Commits

No commits in this session. All changes are currently unstaged.
