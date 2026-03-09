#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/sequenzia/gltools"
DRY_RUN=false
BUMP_TYPE=""

# --- Helpers ---

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] <patch|minor|major>

Automates the gltools release process:
  1. Bump version (hatch)
  2. Regenerate changelog (git-cliff)
  3. Commit & tag
  4. Push (with confirmation)

Options:
  --dry-run   Run pre-flight checks and show what would happen, but don't execute
  -h, --help  Show this help message
EOF
}

info() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
success() { printf '\033[1;32m==>\033[0m %s\n' "$1"; }
error() { printf '\033[1;31merror:\033[0m %s\n' "$1" >&2; exit 1; }

# --- Argument parsing ---

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage; exit 0 ;;
        patch|minor|major)
            [[ -n "$BUMP_TYPE" ]] && error "bump type already set to '$BUMP_TYPE'"
            BUMP_TYPE="$1"; shift ;;
        *) error "unknown argument: $1" ;;
    esac
done

[[ -z "$BUMP_TYPE" ]] && { usage >&2; exit 1; }

# --- Pre-flight checks ---

info "Running pre-flight checks..."

command -v uv >/dev/null 2>&1 || error "uv is not installed"
command -v git-cliff >/dev/null 2>&1 || error "git-cliff is not installed"

[[ -z "$(git status --porcelain)" ]] || error "working tree is not clean — commit or stash changes first"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[[ "$CURRENT_BRANCH" == "main" ]] || error "not on main branch (currently on '$CURRENT_BRANCH')"

info "Fetching latest from origin..."
git fetch origin main --quiet
LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse origin/main)"
[[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] || error "local main ($LOCAL_SHA) is not up-to-date with origin/main ($REMOTE_SHA) — pull first"

OLD_VERSION="$(uv run hatch version)"
success "Pre-flight checks passed (current version: $OLD_VERSION)"

# --- Dry-run summary ---

if [[ "$DRY_RUN" == true ]]; then
    echo ""
    info "Dry-run mode — no changes will be made"
    echo ""
    echo "  Would perform:"
    echo "    1. uv run hatch version $BUMP_TYPE"
    echo "    2. git-cliff --tag \"v<new-version>\" -o CHANGELOG.md"
    echo "    3. git add src/gltools/__init__.py CHANGELOG.md"
    echo "    4. git commit -m \"chore(release): prepare v<new-version>\""
    echo "    5. git tag \"v<new-version>\""
    echo "    6. git push origin main"
    echo "    7. git push origin \"v<new-version>\""
    echo ""
    exit 0
fi

# --- Release steps ---

info "Step 1/4: Bumping version ($BUMP_TYPE)..."
uv run hatch version "$BUMP_TYPE"
VERSION="$(uv run hatch version)"
info "Version bumped: $OLD_VERSION -> $VERSION"

info "Step 2/4: Regenerating changelog..."
git-cliff --tag "v$VERSION" -o CHANGELOG.md

info "Step 3/4: Committing release..."
git add src/gltools/__init__.py CHANGELOG.md
git commit -m "chore(release): prepare v$VERSION"

info "Step 4/4: Tagging v$VERSION..."
git tag "v$VERSION"

# --- Summary ---

echo ""
success "Release v$VERSION prepared"
echo ""
echo "  Version:  $OLD_VERSION -> $VERSION"
echo "  Tag:      v$VERSION"
echo "  Commit:   $(git rev-parse --short HEAD)"
echo ""

# --- Push confirmation ---

printf '\033[1;33m==>\033[0m Push commit and tag to origin? [Y/n] '
read -r REPLY
REPLY="${REPLY:-Y}"

if [[ "$REPLY" =~ ^[Yy]$ ]]; then
    info "Pushing to origin..."
    git push origin main
    git push origin "v$VERSION"
    echo ""
    success "Release v$VERSION pushed!"
    echo "  Monitor the pipeline at: $REPO_URL/actions"
else
    echo ""
    info "Push skipped. When ready, run:"
    echo "    git push origin main"
    echo "    git push origin \"v$VERSION\""
fi
