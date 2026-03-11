# Contributing

Thanks for contributing to this project.

## Development Setup

1. Install Calibre 2.80+.
2. Use Python 3.12 locally to match CI.
3. Clone the repository and create a virtual environment if needed.

## Local Validation

Run these checks before opening a pull request:

```powershell
python -m compileall -q calibre_plugin
```

```powershell
mkdir dist
Compress-Archive -Path calibre_plugin\__init__.py,calibre_plugin\main.py,calibre_plugin\plugin-import-name-fichub.txt -DestinationPath dist\FicHub_Metadata_Source.zip -Force
```

## Pull Request Process

1. Fork the repo and create a branch from `master`.
2. Keep changes focused and include tests or validation steps where possible.
3. Update documentation when behavior changes.
4. Open a pull request with:
   - A clear summary of what changed
   - Why the change is needed
   - How you validated it

## Coding Guidelines

- Keep plugin behavior compatible with Calibre metadata source APIs.
- Prefer small, readable functions and explicit error handling.
- Do not commit generated artifacts or local environment files.

## Release Notes

- User-visible changes should be added under `Unreleased` in `CHANGELOG.md`.
- Maintainers cut releases by pushing tags that match `v*` (example: `v0.1.0`).
