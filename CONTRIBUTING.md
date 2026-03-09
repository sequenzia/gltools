# Contributing to gltools

## Development Setup

```bash
# Clone the repository
git clone https://github.com/sequenzia/gltools.git
cd gltools

# Install in editable mode with dev dependencies
uv pip install -e .
uv pip install --group dev

# Run tests
uv run pytest

# Run linter
uv run ruff check src/ tests/

# Format code
uv run ruff format src/ tests/
```

## Conventional Commits

This project uses [Conventional Commits](https://www.conventionalcommits.org/) for all commit messages. This format enables automatic changelog generation and makes the git history easier to read.

### Commit Message Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Commit Types

| Type       | Description                                         | Changelog Section |
|------------|-----------------------------------------------------|-------------------|
| `feat`     | A new feature                                       | Added             |
| `fix`      | A bug fix                                           | Fixed             |
| `docs`     | Documentation only changes                          | Documentation     |
| `style`    | Code style changes (formatting, missing semicolons) | Changed           |
| `refactor` | Code change that neither fixes a bug nor adds a feature | Changed       |
| `perf`     | Performance improvement                             | Performance       |
| `test`     | Adding or updating tests                            | Testing           |
| `chore`    | Maintenance tasks (deps, CI, build)                 | Miscellaneous     |
| `revert`   | Reverting a previous commit                         | Reverted          |
| `ci`       | CI/CD configuration changes                         | Miscellaneous     |

### Scope

The scope is optional and indicates the area of the codebase affected:

- `cli` - CLI commands and interface
- `tui` - TUI screens and widgets
- `models` - Pydantic data models
- `client` - HTTP client and API layer
- `config` - Configuration and settings
- `auth` - Authentication (PAT, OAuth2)
- `services` - Service layer business logic
- `logging` - Logging infrastructure
- `doctor` - Doctor diagnostic command

### Examples

```bash
# Feature with scope
git commit -m "feat(cli): add merge request update command"

# Bug fix with scope
git commit -m "fix(models): parse milestone as nested object from GitLab API"

# Documentation without scope
git commit -m "docs: update installation instructions"

# Breaking change (add ! after type/scope)
git commit -m "feat(config)!: change default config file location"

# Multi-line commit with body
git commit -m "feat(auth): add OAuth2 browser-based login with PKCE and device flow

Implements Authorization Code flow with PKCE for browser-based login
and Device Authorization Grant for headless environments."
```

### What NOT to do

```bash
# Missing type
git commit -m "update readme"

# Past tense (use imperative mood)
git commit -m "feat: added new feature"

# Too vague
git commit -m "fix: fix bug"

# Type not lowercase
git commit -m "Feat: add feature"
```

## Changelog Generation

This project uses [git-cliff](https://git-cliff.org/) to automatically generate changelog entries from conventional commit messages. The configuration is in `cliff.toml`.

### Installing git-cliff

```bash
# macOS (Homebrew)
brew install git-cliff

# Cargo
cargo install git-cliff

# See https://git-cliff.org/docs/installation for other methods
```

### Usage

```bash
# Preview the full changelog
git-cliff

# Preview only unreleased changes
git-cliff --unreleased

# Update CHANGELOG.md in place
git-cliff -o CHANGELOG.md

# Generate changelog for a specific version
git-cliff --tag v0.2.0
```

### How It Works

1. git-cliff reads the git history and parses conventional commit messages
2. Commits are grouped by type into Keep a Changelog sections (Added, Fixed, Changed, etc.)
3. Non-conventional commits are grouped under "Other"
4. Empty sections are automatically omitted
5. The `[Unreleased]` section contains all changes since the last git tag

## Releasing a New Version

gltools uses [Hatch](https://hatch.pypa.io/) for version management. The single source of truth for the version is `src/gltools/__init__.py`.

### Version Bumping

Show the current version:

```bash
hatch version
```

Bump the version using one of:

```bash
hatch version patch   # 0.1.0 -> 0.1.1
hatch version minor   # 0.1.0 -> 0.2.0
hatch version major   # 0.1.0 -> 1.0.0
```

You can also set an explicit version:

```bash
hatch version "0.3.0"
```

### Release Procedure

Follow this bump, changelog, commit, tag flow for every release:

1. **Bump the version:**

   ```bash
   hatch version <patch|minor|major>
   ```

   This updates `__version__` in `src/gltools/__init__.py`.

2. **Generate the changelog:**

   ```bash
   git-cliff --tag "v$(hatch version)" -o CHANGELOG.md
   ```

3. **Review and commit:**

   ```bash
   git add src/gltools/__init__.py CHANGELOG.md
   git commit -m "chore(release): prepare v$(hatch version)"
   ```

4. **Tag the release:**

   ```bash
   git tag "v$(hatch version)"
   ```

5. **Push the commit and tag:**

   ```bash
   git push origin main
   git push origin "v$(hatch version)"
   ```

6. **Build the package (optional):**

   ```bash
   hatch build
   ```

### PyPI Publishing

The release workflow automatically publishes to PyPI using [Trusted Publisher](https://docs.pypi.org/trusted-publishers/) (OIDC) authentication. No API tokens or secrets are needed -- GitHub Actions authenticates directly with PyPI via OpenID Connect.

#### How It Works

When a version tag (`v*`) is pushed, the release workflow:

1. Runs lint, tests, and version consistency checks
2. Builds the sdist and wheel using `hatch build`
3. Publishes both artifacts to PyPI using `pypa/gh-action-pypi-publish`

The publish job uses the `pypi` GitHub environment, which can be configured with approval gates for an additional layer of control before packages are published.

#### One-Time PyPI Trusted Publisher Setup

Before the first release, you must configure the GitHub repository as a trusted publisher on PyPI:

1. **Log in to PyPI** at https://pypi.org/manage/account/publishing/
2. **Add a new pending publisher** (if the project does not exist on PyPI yet) or go to the project's Publishing settings (if it already exists)
3. **Fill in the trusted publisher form:**
   - **PyPI project name:** `gltools`
   - **Owner:** `sequenzia`
   - **Repository name:** `gltools`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
4. **Save** the trusted publisher configuration

#### One-Time GitHub Environment Setup

1. Go to the repository **Settings > Environments**
2. Create an environment named **`pypi`**
3. (Optional) Add **required reviewers** for manual approval before publishing
4. (Optional) Restrict deployment to the `main` branch using **deployment branch rules**

#### Error Handling

- **OIDC authentication failure:** The publish step will fail with a clear error if the Trusted Publisher is not configured on PyPI or if the OIDC token exchange fails. Verify the Trusted Publisher settings match exactly (owner, repo, workflow name, environment name).
- **Version already exists:** PyPI rejects uploads of versions that already exist. The publish step will fail with an HTTP 400 error. You cannot overwrite a published version -- bump the version and create a new tag instead.

### Version Scheme

This project follows [Semantic Versioning](https://semver.org/):

- **Major** (X.0.0): Breaking changes to the CLI interface or public API
- **Minor** (0.X.0): New features that are backward-compatible
- **Patch** (0.0.X): Bug fixes and minor improvements

## Code Standards

- **Python 3.12+** with type hints on all functions
- **Ruff** for linting and formatting (line length: 120)
- **pytest** for testing with pytest-asyncio in auto mode
- Follow existing patterns in the codebase
- See `CLAUDE.md` for detailed coding conventions

## Project Structure

```
src/gltools/
├── cli/          # Typer commands
├── tui/          # Textual app
├── services/     # Business logic
├── client/       # API layer
├── models/       # Pydantic models
├── config/       # Settings
├── logging.py    # Logging infrastructure
└── plugins/      # Plugin system
```
