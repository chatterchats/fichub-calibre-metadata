# FicHub Metadata Source for calibre

Metadata download plugin for [calibre](https://calibre-ebook.com/) that fetches fanfiction metadata through the [FicHub API](https://fichub.net/).

It currently targets Archive of Our Own and FanFiction.net URLs explicitly, while still accepting any FicHub-supported story URL as an input identifier.

## Features

- Download story metadata from FicHub using a calibre metadata source plugin
- Support AO3 and FanFiction.net identifier extraction for better calibre URL integration
- Map title, authors, tags, publisher, publication date, language, comments, series, and source-specific identifiers
- Retry transient API failures with backoff and abort-aware cancellation
- Render rich HTML comments with story stats and extra metadata

## Requirements

- calibre `2.80.0+`
- Python `3.12+` for local development
- Internet access to `https://fichub.net/api/v0/meta`

## Installation

### Install a released plugin ZIP

1. Download `FicHub_Metadata_Source.zip` from the latest release.
2. In calibre, open `Preferences` -> `Plugins` -> `Load plugin from file`.
3. Select the ZIP file and restart calibre.
4. Enable `FicHub` in `Preferences` -> `Metadata download` -> `Customize metadata sources`.

### Build a plugin ZIP from source

The plugin ZIP must contain these files from `calibre_plugin/`:

- `__init__.py`
- `main.py`
- `http.py`
- `metadata.py`
- `plugin-import-name-fichub.txt`

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

## Usage

### Add a supported story identifier

In calibre, add one of the following identifiers to a book:

- `url:https://archiveofourown.org/works/12345678`
- `url:https://www.fanfiction.net/s/1234567/1/Story-Title`

The plugin also scans `uri` and `fichub`, then falls back to any identifier value containing an `http://` or `https://` URL.

### Download metadata

1. Select the book in calibre.
2. Open `Edit metadata` -> `Download metadata`.
3. Let calibre query the `FicHub` source.
4. Review the returned metadata and apply it.

## Metadata Mapped

The plugin currently declares these touched fields:

- `title`
- `authors`
- `tags`
- `series`
- `series_index`
- `publisher`
- `pubdate`
- `comments`
- `languages`
- `identifier:fichub_id`
- `identifier:ao3`
- `identifier:ffnet`

It also uses calibre URL integration helpers so calibre can associate AO3 and FanFiction.net story IDs with canonical story URLs.

## Development

### Tooling

This project uses:

- `uv` for environment and lockfile management
- `pytest` for tests
- `ruff` for linting and formatting
- `pyright` for static typing
- `prek` for git hooks

Install the dev environment with `uv`:

```bash
uv sync
```

### Common commands

Run tests:

```bash
uv run pytest -q
```


Run linting:


```bash
uv run ruff check calibre_plugin tests
uv run ruff format --check calibre_plugin tests
```

Run type checking:

```bash
uv run pyright
```


Install hooks:

```bash
uv run prek install
```


## CI and Releases

- CI validates plugin files, compiles the package, and builds a plugin ZIP
- Releases are triggered from tags matching `v*`
- The release workflow copies plugin sources into a temporary build directory and strips Python docstrings before creating the release ZIP

## Troubleshooting

### calibre says no metadata was found

- Confirm the story URL works in a browser
- Confirm the identifier is present in calibre
- Prefer `url:` identifiers for direct story URLs
- Check calibre's job details/log output for the plugin-specific error message

### The API works manually but calibre still fails

- Make sure the installed plugin ZIP is current
- If the plugin version shown in calibre does not match the latest tag, remove and reinstall the plugin ZIP

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and contribution expectations.

## License

Licensed under GPL-3.0-only. See [LICENSE](LICENSE).
