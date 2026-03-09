"""CLI interface for gltools."""

import gltools.cli.auth  # noqa: F401 — register auth commands on auth_app
import gltools.cli.ci  # noqa: F401 — register CI commands on ci_app
import gltools.cli.doctor  # noqa: F401 — register doctor command on app
import gltools.cli.issue  # noqa: F401 — register issue commands on issue_app
import gltools.cli.mr  # noqa: F401 — register MR commands on mr_app
from gltools.cli.app import app

__all__ = ["app"]
