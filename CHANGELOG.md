# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2](https://github.com/chatterchats/fichub-calibre-metadata/releases/tag/v0.1.2) - 2026-04-11

### Fixed

- Fixed a calibre integration bug where `identify()` reassigned the result of `clean_downloaded_metadata()` even though calibre mutates metadata objects in place and may return `None`.
- Prevented successful FicHub API lookups from failing during result queueing after metadata cleanup.

### Changed

- Updated CI and release workflows to use newer GitHub Actions versions compatible with the current runner runtime.
- Fixed the release workflow ZIP output path for the stripped plugin build directory.
- Expanded `.gitignore` coverage for generated local artifacts.

## [0.1.1](https://github.com/chatterchats/fichub-calibre-metadata/releases/tag/v0.1.1) - 2026-04-11

### Changed

- Migrated local type checking from `mypy` to `pyright`.
- Refactored the plugin into dedicated `http.py` and `metadata.py` modules while keeping `main.py` as the calibre entry point.
- Modernized local tooling around `uv`, `ruff`, `pytest`, `pyright`, and `prek`.
- Added release packaging support for the refactored runtime files.
- Normalized tracked text file formatting across repository metadata and workflow files.

### Fixed

- Improved retry, abort, and metadata mapping behavior around FicHub API requests.
- Added calibre-facing URL integration with `id_from_url()` and `get_book_url_name()`.
- Returned user-facing errors from `identify()` and cleaned downloaded metadata before queueing results.
- Strengthened test stubs and regression coverage for the updated plugin behavior.

## [0.1.0](https://github.com/chatterchats/fichub-calibre-metadata/releases/tag/v0.1.0) - 2026-03-10

### Added

- Initial FicHub-backed Calibre metadata source plugin implementation.
- Project entry points and plugin import metadata files.
- Test suite with local stubs for `calibre` and `polyglot` dependencies.
- Development tooling and quality configuration for Ruff, mypy, pytest, coverage, and pre-commit.
- GitHub workflows for CI and release automation.
- Community and project documentation (`README`, `LICENSE`, `CONTRIBUTING`, `SECURITY`, pull request and issue templates).
