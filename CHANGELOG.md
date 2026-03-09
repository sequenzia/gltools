# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- git-cliff: begin unreleased -->
## [Unreleased]

### Added

- implement gltools MVP - GitLab CLI and TUI tool
- **auth**: add OAuth2 browser-based login with PKCE and device flow
- **logging,doctor**: add structured logging and diagnostic command

### Fixed

- **config,auth**: resolve keyring access, thread safety, and auth client issues
- **tui**: wire MR, Issue, and CI screens to service layer
- **models**: parse milestone as nested object from GitLab API

### Documentation

- add gltools MVP specification
- **analysis**: add comprehensive codebase analysis and documentation
- add detailed config and authentication breakdown
- **spec**: add logging and debugging spec for self-hosted GitLab troubleshooting
- **spec**: add python releases specification

### Other

- Add MIT License to the project
<!-- git-cliff: end unreleased -->

## [0.1.0] - 2026-03-05

### Added

- Initial project scaffolding with src layout
- CLI framework using Typer with `gltools` entry point
- TUI framework using Textual (placeholder)
- HTTP client foundation with httpx
- Configuration management with pydantic-settings
- PyPI packaging with hatchling build system
- Support for `uvx gltools` zero-install execution
