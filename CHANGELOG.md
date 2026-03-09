# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-03-09

### Miscellaneous

- **scripts**: add automated release script

## [0.1.3] - 2026-03-09

### Documentation

- **reports**: add change report for TUI pipeline encoding fix

### Fixed

- **tui**: URL-encode project IDs in Pipeline/Job managers and TUI screens

## [0.1.2] - 2026-03-09

### Documentation

- **readme**: add release process documentation

### Fixed

- **keyring**: downgrade unavailability messages to debug level

## [0.1.1] - 2026-03-09

### Added

- implement gltools MVP - GitLab CLI and TUI tool
- **auth**: add OAuth2 browser-based login with PKCE and device flow
- **logging,doctor**: add structured logging and diagnostic command
- **release**: add Python release pipeline with CI/CD workflow

### Documentation

- add gltools MVP specification
- **analysis**: add comprehensive codebase analysis and documentation
- add detailed config and authentication breakdown
- **reports**: add change report for config/auth fixes
- **reports**: add change report for TUI service wiring fix
- **reports**: add change report for OAuth2 browser-based login
- **spec**: add logging and debugging spec for self-hosted GitLab troubleshooting
- **reports**: add change report for logging and doctor command
- **reports**: add change report for milestone model fix
- **spec**: add python releases specification
- **reports**: add change report for release pipeline

### Fixed

- **config,auth**: resolve keyring access, thread safety, and auth client issues
- **tui**: wire MR, Issue, and CI screens to service layer
- **models**: parse milestone as nested object from GitLab API

### Other

- Add MIT License to the project


