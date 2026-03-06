"""TUI interface for gltools."""

from __future__ import annotations

from gltools.tui.app import GLToolsApp


def launch_tui(
    *,
    profile: str | None = None,
    host: str | None = None,
    token: str | None = None,
) -> None:
    """Launch the gltools TUI application.

    Args:
        profile: Configuration profile name override.
        host: GitLab host URL override.
        token: GitLab personal access token override.
    """
    app = GLToolsApp(profile=profile, host=host, token=token)
    app.run()


__all__ = ["GLToolsApp", "launch_tui"]
