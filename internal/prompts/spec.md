gltools is a set of tools for working with GitLab. The core functionality provided by gltools is a Python-based CLI and TUI that can be used to interact with GitLab repositories, issues, merge requests, and more. These are the requirements for the MVP of gltools:

- A Python-based CLI that mimics the functionality of the current glab CLI tool (https://docs.gitlab.com/cli)
- A Python-based TUI that provides a user-friendly interface for the same functionality as the CLI
- It must work with public GitLab instances as well as self-hosted enterprise GitLab instances
- The CLI and TUI should support authentication with GitLab using personal access tokens
- The CLI should be optimized for coding agents while the TUI should be optimized for human users
- The CLI and TUI should be designed to be easily extensible for future features and integrations
- The CLI and TUI should be well-documented, with clear instructions for installation, usage
- The project should have one set of internal interfaces that both the CLI and TUI can use to interact with GitLab, to avoid code duplication and ensure consistency between the two interfaces

Technical Stack:
- Python 3.12 or later
- Typer for the CLI framework
- Textual for the TUI framework
- httpx for making HTTP requests to the GitLab API
- Pydantic for data validation
- Pydantic Settings for configuration management
- Pytest for testing
- UV for dependency management
- Hatch for packaging and distribution

Documentation:
- Gitlab REST API documentation: https://docs.gitlab.com/api/rest
