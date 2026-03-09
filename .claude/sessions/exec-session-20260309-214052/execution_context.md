# Execution Context

## Wave 1
Tasks completed: #14 (PASS), #15 (PASS)

### Learnings
- Hatch requires `dynamic = ["version"]` in `[project]` for `hatch version` write operations; static `version` field blocks bumps
- The `[tool.hatch.version]` section was already configured with `path = "src/gltools/__init__.py"`
- `uv run` prefix needed for hatch commands due to dev dependency group setup
- git-cliff (v2.12.0) installed via Homebrew as a system tool, not a Python dependency
- CHANGELOG.md uses HTML comments to mark auto-generated sections
- No git tags exist yet — all commits appear as [Unreleased]
- 1 pre-existing test failure in tests/test_config/test_keyring.py::TestFileStorage::test_warns_on_wrong_permissions — unrelated to current work

### Key Decisions
- [Task #14] Changed pyproject.toml from static `version = "0.1.0"` to `dynamic = ["version"]`
- [Task #14] Created CONTRIBUTING.md for release procedure documentation
- [Task #15] Selected git-cliff as changelog tool (Rust binary via brew, not Python dep)
- [Task #15] cliff.toml maps conventional commit types to Keep a Changelog sections
- [Task #15] Non-conventional commits grouped under "Other" rather than filtered out

### Files Modified
- pyproject.toml (modified — dynamic versioning)
- CONTRIBUTING.md (created — release procedure + conventional commits docs)
- cliff.toml (created — git-cliff config)
- CHANGELOG.md (modified — auto-generated [Unreleased] section)
- CLAUDE.md (modified — git-cliff in tech stack and key commands)

## Wave 2
Tasks completed: #16 (PASS)

### Learnings
- `astral-sh/setup-uv@v4` is the official GitHub Action for installing uv in CI
- `uv sync --group dev` installs all dev dependencies in CI (preferred over `uv pip install -e .`)
- `${GITHUB_REF#refs/tags/v}` strips the `v` prefix from a tag ref in GitHub Actions
- `GITHUB_OUTPUT` is the current way to pass values between steps (replaces deprecated `::set-output`)
- `::error::` GitHub Actions annotation surfaces errors prominently in the UI
- Version extraction from `__init__.py` uses inline Python one-liner to avoid shell quoting issues in YAML

### Key Decisions
- [Task #16] Lint, test, and check-version jobs run in parallel (all independent prerequisites for build)
- [Task #16] Build job depends on all three: `needs: [lint, test, check-version]`
- [Task #16] Used `permissions: contents: read` for minimal security posture
- [Task #16] `if-no-files-found: error` on artifact upload ensures build failures are caught

### Files Modified
- .github/workflows/release.yml (created — tag-triggered release pipeline)

## Wave 3
Tasks completed: #17 (PASS), #18 (PASS)

### Learnings
- `pypa/gh-action-pypi-publish@release/v1` defaults to uploading all files in dist/, no explicit glob needed
- The action handles OIDC token exchange internally when `id-token: write` permission is set
- PyPI Trusted Publisher requires exact match on owner, repo, workflow name, and environment name
- `softprops/action-gh-release@v2` supports `body_path` for multiline release notes and `generate_release_notes` as fallback
- `fetch-depth: 0` on checkout is needed for `git tag` to see all tags for previous-tag detection
- `sed -n` can extract changelog sections between version headers for release notes
- For first release (no previous tag), `commits/{tag}` URL shows all commits up to that point

### Key Decisions
- [Task #17] Used `pypa/gh-action-pypi-publish@release/v1` (pinned to release branch)
- [Task #17] Added artifact verification step checking for both .tar.gz and .whl before publishing
- [Task #17] Job-level `permissions: id-token: write` (least privilege, not workflow-level)
- [Task #17] `environment: pypi` enables GitHub environment protection rules (approval gates)
- [Task #18] Used `softprops/action-gh-release@v2` for GitHub Release creation
- [Task #18] File-based approach (`body_path`) for release body to preserve multiline content
- [Task #18] Fallback to `generate_release_notes: true` when changelog section not found
- [Task #18] Job-level `permissions: contents: write` for release creation (overrides workflow-level read)

### Files Modified
- .github/workflows/release.yml (modified — added publish and github-release jobs)
- CONTRIBUTING.md (modified — added PyPI Trusted Publisher setup documentation)
