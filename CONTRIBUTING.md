# Contributing

Thanks for contributing.

## Scope

This repository builds a calibre metadata source plugin that fetches fanfiction metadata through FicHub. Changes should preserve compatibility with calibre's metadata source plugin APIs and the plugin ZIP layout used by the release workflow.

## Development Environment

- Use Python `3.12+`
- Use `uv` for dependency management
- Use `prek` for local hooks

Set up the environment:

```bash
uv sync
uv run prek install
```


## Validate Before Opening a PR

Run the full local checks before submitting changes.

```bash
uv lock --check
uv run ruff check calibre_plugin tests
uv run ruff format --check calibre_plugin tests
uv run pyright
uv run pytest -q
```


## Build the Plugin ZIP Locally

The plugin ZIP must include all runtime files from `calibre_plugin/`.

Linux/macOS:

```bash
mkdir -p dist
(
  cd calibre_plugin &&
  zip -r ../dist/FicHub_Metadata_Source.zip \
    __init__.py main.py http.py metadata.py plugin-import-name-fichub.txt
)
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force dist | Out-Null
Compress-Archive `
  -Path `
    calibre_plugin\__init__.py,`
    calibre_plugin\main.py,`
    calibre_plugin\http.py,`
    calibre_plugin\metadata.py,`
    calibre_plugin\plugin-import-name-fichub.txt `
  -DestinationPath dist\FicHub_Metadata_Source.zip `
  -Force
```

## Coding Guidelines

- Keep runtime behavior compatible with calibre plugin expectations
- Prefer explicit error handling over silent failure
- Add or update tests for behavior changes
- Keep release-only transformations in CI/workflows, not in tracked source
- Do not commit generated artifacts from `dist/`, `build/`, or local tool caches

## Pull Requests

When opening a PR:

1. Keep the change focused
2. Explain what changed and why
3. List the validation commands you ran
4. Update `README.md`, `CONTRIBUTING.md`, or `CHANGELOG.md` when behavior or workflow changes

## Releases and Changelog

- Add user-visible unreleased changes to `CHANGELOG.md`
- Releases are published from tags matching `v*`
- Release ZIPs are assembled by GitHub Actions, not by hand-edited committed artifacts
