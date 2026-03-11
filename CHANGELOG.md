# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Changed

- Migrated type checking from `mypy` to `pyright` across development tooling:
  - replaced `mypy` with `pyright` in `pyproject.toml` dev dependencies
  - switched the local pre-commit type-check hook to `uv run pyright`
  - added project-level `tool.pyright` configuration for strict checking with local test stubs
  - refreshed `uv.lock` to remove mypy-related packages and include pyright
- Updated plugin URL identifier handling in `FicHub`:
  - `get_book_url()` now returns the `url` identifier key
  - removed legacy `id_from_url()` override as overrid method is unused.
  - dropped `identifier:fichub` from `touched_fields`
- Improved tests and local stubs for stricter static typing:
  - added explicit typing to test doubles and test functions in `tests/test_main.py`
  - added typed signatures/attributes in `tests/stubs/calibre/*` helper modules

### Fixed

- Fixed pytest import-path setup by using absolute paths in `tests/conftest.py`, ensuring `calibre_plugin` and `tests/stubs` resolve consistently regardless of working directory.

## [0.1.0] - 2026-03-10

### Added

- Initial FicHub-backed Calibre metadata source plugin implementation.
- Project entry points and plugin import metadata files.
- Test suite with local stubs for `calibre` and `polyglot` dependencies.
- Development tooling and quality configuration for Ruff, mypy, pytest, coverage, and pre-commit.
- GitHub workflows for CI and release automation.
- Community and project documentation (`README`, `LICENSE`, `CONTRIBUTING`, `SECURITY`, pull request and issue templates).
