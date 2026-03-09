# Python Releases PRD

**Version**: 1.0
**Author**: Stephen Sequenzia
**Date**: 2026-03-09
**Status**: Draft
**Spec Type**: New Feature
**Spec Depth**: High-Level Overview
**Description**: Add release workflow for gltools including version bumping, changelog generation from commits, PyPI publishing via GitHub Actions, and GitHub Releases with changelog notes.

---

## Executive Summary

Add a complete release pipeline to gltools that automates version bumping, changelog generation, PyPI publishing, and GitHub Release creation. The workflow is triggered by pushing a `v*` git tag and runs entirely in GitHub Actions using Trusted Publisher (OIDC) for secure, tokenless PyPI authentication.

## Problem Statement

### The Problem

gltools currently has no release workflow. Publishing a new version requires manual steps — editing the version string, writing changelog entries, building the package, uploading to PyPI, and creating a release on GitHub. This is error-prone, time-consuming, and discourages frequent releases.

### Current State

- Version is hardcoded in `src/gltools/__init__.py` (`__version__ = "0.1.0"`)
- Hatch reads the version via `[tool.hatch.version]` but no bump commands are part of the workflow
- `CHANGELOG.md` exists using Keep a Changelog format but is manually maintained
- No CI/CD pipeline exists (no `.gitlab-ci.yml` or GitHub Actions workflows)
- Package can be built locally with `hatch build` but publishing is entirely manual

### Impact

Without an automated release pipeline, releases are infrequent and risky. Manual steps increase the chance of mistakes (wrong version, missing changelog entries, forgotten tags). This slows down delivery to users who install via `pip install gltools` or `uvx gltools`.

## Proposed Solution

### Overview

Implement a tag-triggered GitHub Actions release pipeline. The developer bumps the version locally using `hatch version`, auto-generates changelog entries from conventional commits, commits the changes, pushes a `v*` tag, and GitHub Actions handles building, publishing to PyPI, and creating a GitHub Release with the changelog excerpt.

### Key Features

| Feature | Description | Priority |
|---------|-------------|----------|
| Version Bumping | Use `hatch version` to bump major/minor/patch in `__init__.py` | P0 |
| Changelog Generation | Auto-generate changelog entries from conventional commit messages into Keep a Changelog format | P0 |
| GitHub Actions Workflow | Tag-triggered pipeline: lint → test → build → publish → release | P0 |
| PyPI Publishing | Publish sdist and wheel to PyPI using Trusted Publisher (OIDC) | P0 |
| GitHub Release | Create a GitHub Release with changelog excerpt and link to full commit history | P1 |

## Success Metrics

| Metric | Current | Target | How Measured |
|--------|---------|--------|--------------|
| Release automation | 0% (fully manual) | 100% (tag push triggers full pipeline) | GitHub Actions workflow exists and succeeds |
| Time to release | ~30 min manual process | < 5 min developer effort (bump + tag + push) | Wall clock time for developer steps |
| Changelog accuracy | Manual, often incomplete | Auto-generated from commits | Changelog entries match commit history |
| PyPI availability | Not published | Published on every release | Package available on pypi.org |

## User Personas

### Primary User: Project Maintainer

- **Role**: Developer maintaining and releasing gltools
- **Goals**: Ship new versions quickly and reliably with minimal manual steps
- **Pain Points**: Manual release process is tedious, error-prone, and discourages frequent releases

## Scope

### In Scope

- `hatch version` integration for version bumping
- Changelog auto-generation from conventional commit messages
- Maintaining existing Keep a Changelog format and Semantic Versioning in `CHANGELOG.md`
- GitHub Actions workflow triggered by `v*` tag push
- Pipeline stages: lint, test, build, publish to PyPI, create GitHub Release
- PyPI Trusted Publisher (OIDC) authentication setup
- GitHub Release creation with changelog excerpt and commit history link
- Build verification (tests + linting) before publishing

### Out of Scope

- Pre-release versions (alpha/beta/rc, e.g., `0.2.0a1`)
- Multi-package publishing (other registries beyond PyPI)
- Automated dependency updates (Dependabot/Renovate)
- GitLab CI/CD pipeline (GitHub Actions only)
- Automated commit-based release triggering (manual tag push only)

## Implementation Phases

### Phase 1: Foundation

**Goal**: Set up version bumping and changelog generation tooling

- Configure `hatch version` workflow (document the bump → commit → tag flow)
- Select and integrate a changelog generation tool that reads conventional commits and outputs Keep a Changelog format
- Update `CHANGELOG.md` structure to support auto-generation alongside the existing `[0.1.0]` entry
- Ensure conventional commit format is documented for contributors

### Phase 2: CI/CD Pipeline

**Goal**: Automate the build, publish, and release pipeline

- Create `.github/workflows/release.yml` triggered by `v*` tag push
- Add lint and test stages as gates before publishing
- Configure `hatch build` to produce sdist and wheel
- Set up PyPI Trusted Publisher (OIDC) for tokenless publishing
- Add PyPI publish step using the official `pypa/gh-action-pypi-publish` action
- Add GitHub Release creation step with changelog excerpt extraction
- Include a link to the full commit diff between the previous and current tag in the release notes

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Inconsistent commit messages break changelog generation | Med | Med | Document conventional commit format; consider a commit-msg hook or CI check |
| Trusted Publisher OIDC misconfiguration | High | Low | Follow PyPI's official setup guide; test with TestPyPI first |
| Tag pushed without version bump | High | Med | Add a CI check that verifies the tag version matches `__version__` |
| Changelog tool doesn't match Keep a Changelog format | Med | Low | Evaluate tools against existing `CHANGELOG.md` format before selection |

## Dependencies

- **PyPI Account**: Project must be registered on pypi.org with Trusted Publisher configured for the GitHub repository
- **GitHub Repository Settings**: GitHub Actions must be enabled with appropriate permissions for OIDC token requests
- **Conventional Commits Adoption**: Team must adopt conventional commit message format for changelog generation to work
- **TestPyPI (recommended)**: Use TestPyPI for validating the publish workflow before the first real release

## Checkpoint Gates

- [ ] **Tool Selection**: Agree on changelog generation tool before Phase 1 implementation begins
- [ ] **TestPyPI Validation**: Successfully publish a test release to TestPyPI before enabling production PyPI publishing
- [ ] **Tag-Version Consistency**: Verify CI check catches mismatches between git tag and `__version__`

---

*Document generated by SDD Tools*
