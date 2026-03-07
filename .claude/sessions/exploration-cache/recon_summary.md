## Reconnaissance Summary

- **Project**: gltools - Python CLI+TUI for GitLab (v0.1.0, alpha)
- **Primary language/framework**: Python 3.12+, Typer (CLI), Textual (TUI), httpx (HTTP), Pydantic v2 (models)
- **Build**: Hatch/hatchling, UV for deps, Ruff for lint
- **Codebase size**: 51 source files in src/gltools/, 46 test files in tests/
- **Architecture**: 4-layer: CLI/TUI → Services → Client (managers) → HTTP
- **Key directories**: cli/ (7 files), tui/ (9 files), client/ (7 files), models/ (8 files), config/ (4 files), services/ (4 files), plugins/ (2 files)
