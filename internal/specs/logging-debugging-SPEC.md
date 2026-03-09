# Logging & Debugging PRD

**Version**: 1.0
**Author**: Stephen Sequenzia
**Date**: 2026-03-09
**Status**: Draft
**Spec Type**: New product
**Spec Depth**: High-level overview
**Description**: Add logging and debugging capabilities to gltools to help diagnose issues with self-hosted GitLab instances.

---

## Executive Summary

gltools currently provides limited visibility when commands fail, making it difficult to diagnose issues — especially with self-hosted GitLab instances that may have different configurations, network constraints, or API behaviors. This spec defines a logging and debugging system that gives users full observability into what gltools is doing, what went wrong, and how to fix it.

## Problem Statement

### The Problem
Users running gltools against self-hosted GitLab instances encounter failures across multiple categories — connection/network issues, authentication failures, unexpected API responses, and silent failures — with no way to diagnose the root cause. The tool provides insufficient error context, making troubleshooting a frustrating trial-and-error process.

### Current State
- Errors surface as generic messages without underlying cause details
- No way to see HTTP request/response details for failed API calls
- No visibility into resolved configuration state (host, auth method, project)
- No mechanism to verify connectivity, token validity, or API compatibility before running commands
- The `_mask_token()` utility exists in `client/exceptions.py` but is only used for exception messages

### Impact
- Users waste time debugging issues that could be quickly diagnosed with proper logging
- Self-hosted GitLab users may abandon gltools due to poor troubleshooting experience
- Support burden increases as users can't self-diagnose common problems (expired tokens, SSL issues, version mismatches)

## Proposed Solution

### Overview
Add a structured logging system to gltools with configurable verbosity, file output, and a dedicated diagnostic command. The system provides human-readable output to the terminal and machine-parseable JSON for file logs, with strict token/credential masking throughout.

### Key Features
| Feature | Description | Priority |
|---------|-------------|----------|
| Verbose CLI flag | `--verbose` / `--debug` global flags to enable detailed output on any command | P0 |
| Configurable log levels | Support DEBUG, INFO, WARNING, ERROR levels with sensible defaults | P0 |
| File logging | Write structured JSON logs to a file for sharing and offline analysis | P0 |
| Token masking | Sanitize all tokens, credentials, and sensitive headers in log output | P0 |
| Diagnostic command | `gltools doctor` command that checks connectivity, auth, config, and API compatibility | P1 |

## Success Metrics

| Metric | Current | Target | How Measured |
|--------|---------|--------|--------------|
| Self-diagnosed failures | ~0% (users can't diagnose) | >80% of common failures diagnosable via logs | User feedback, reduced support requests |
| Time to diagnose | Minutes to hours of trial-and-error | Seconds to minutes via log inspection or `gltools doctor` | User feedback |
| Token exposure incidents | N/A | 0 tokens leaked in log output | Automated testing, code review |

## User Personas

### Primary User: Self-Hosted GitLab CLI User
- **Role**: Developer or DevOps engineer using gltools against a self-hosted GitLab instance
- **Goals**: Quickly identify why a command failed and resolve the issue without external help
- **Pain Points**: Opaque error messages, no visibility into HTTP communication, can't verify config/auth state, different GitLab versions behave differently

## Scope

### In Scope
- Global `--verbose` / `--debug` CLI flags
- Configurable log levels (DEBUG, INFO, WARNING, ERROR)
- Dual-format output: human-readable (colored) to terminal, JSON to file
- Token and credential masking in all log output
- File logging with configurable path
- `gltools doctor` diagnostic command:
  - Connectivity check (host reachable, SSL valid, latency)
  - Authentication check (token valid, scopes, expiration)
  - Configuration check (well-formed config, required fields, profile resolution)
  - API compatibility check (GitLab version detection, known API differences)
- Step-by-step execution trace for CLI commands
- Rich error context with root cause and suggestions

### Out of Scope
- Remote log shipping (Sentry, Datadog, etc.)
- TUI debugging (CLI only for this release)
- Performance profiling / timing of operations

## Implementation Phases

### Phase 1: Core Logging Infrastructure
**Goal**: Establish the logging foundation that all CLI commands can use.
- Python `logging` module integration with gltools-specific configuration
- Global `--verbose` and `--debug` CLI flags wired into log level control
- Structured log formatter: human-readable for terminal (with colors via Rich), JSON for file output
- `--log-file` flag to direct logs to a file
- Token/credential masking applied to all log handlers (extend existing `_mask_token()`)
- HTTP request/response logging in `client/http.py` (method, URL, status, headers with masked tokens, body summaries)
- Configuration state logging at command startup (resolved host, auth method, project, profile)
- Step-by-step execution trace logging in service layer

### Phase 2: Diagnostic Command
**Goal**: Provide a single command that validates the entire gltools setup.
- `gltools doctor` command implementation
- Connectivity check: host resolution, TCP connect, SSL handshake, latency measurement
- Authentication check: token validation via GitLab API, scope enumeration, expiry detection
- Configuration check: TOML parsing validation, required field verification, profile resolution trace
- API compatibility check: GitLab version detection via `/api/v4/version`, known incompatibility warnings
- Summary report with pass/fail status for each check and actionable fix suggestions

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Token leakage in logs | High | Medium | Comprehensive masking layer applied at the log handler level; mask tokens, Bearer headers, private-token headers; automated tests verifying no token appears in log output |
| Log noise obscuring useful info | Medium | Medium | Sensible default level (WARNING); DEBUG reserved for full trace; structured formatting with clear prefixes |
| Performance impact when logging enabled | Low | Low | Logging disabled by default; file I/O buffered; minimal overhead when not active |

## Dependencies

- **Python `logging` module**: Standard library, no new dependency needed
- **Rich library**: Already a dependency (via Typer), can be used for colored terminal log output
- **GitLab `/api/v4/version` endpoint**: Required for API compatibility check in `gltools doctor`

## Stakeholder Sign-off

| Role | Name | Status |
|------|------|--------|
| Author | Stephen Sequenzia | Pending |

---

*Document generated by SDD Tools*
