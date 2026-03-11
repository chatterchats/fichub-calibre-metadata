# FicHub Metadata Source for Calibre

Automatic fanfiction metadata fetching for Calibre from multiple sources via the [FicHub API](https://fichub.net/).

**Supported Platforms:** Archive of Our Own (AO3), FanFiction.net (FFNet), and other sources through FicHub

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Supported Metadata Fields](#supported-metadata-fields)
- [Identifier Priority](#identifier-priority)
- [Error Handling](#error-handling)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)

---

## Features

- **Multi-source support**: Fetches metadata from AO3, FanFiction.net, and other platforms via FicHub
- **Rich metadata extraction**: Titles, authors, publication dates, tags, series information, and more
- **Smart author parsing**: Handles single and multiple authors, with intelligent parsing
- **Automatic retry logic**: Exponential backoff for transient API failures
- **Platform detection**: Automatically identifies and tags metadata with source platform
- **Enhanced comments**: Includes story statistics (chapters, words, status) and AO3 engagement metrics
- **Series support**: Extracts and maps series information with proper indexing
- **Language detection**: Automatically detects and normalizes story language
- **Tag deduplication**: Intelligent collection and deduplication of story tags and metadata

---

## Requirements

- **Calibre 2.80.0+** (older versions may not work)
- **Python 3.6+** (included with Calibre)
- **Internet connection** (for API calls to FicHub)

---

## Installation

### From Source

1. **Clone or download this repository**

2. **Create a plugin zip file** with the plugin root files:

   ```powershell
   # From the FicHub directory
   Compress-Archive -Path calibre_plugin\__init__.py,calibre_plugin\main.py,calibre_plugin\plugin-import-name-fichub.txt `
     -DestinationPath FicHub_Metadata_Source.zip -Force
   ```

3. **Load into Calibre**:
   - Open Calibre → `Preferences` → `Plugins` → `Load plugin from file`
   - Select `FicHub_Metadata_Source.zip`
   - Restart Calibre

4. **Enable in metadata sources**:
   - Open Calibre → `Preferences` → `Metadata download` → `Customize metadata sources`
   - Check the `FicHub` plugin
   - Optionally reorder sources by priority

### Verify Installation

The plugin is correctly installed if:

- It appears in `Preferences → Plugins → Installed Plugins` as "FicHub"
- It's listed in the metadata download sources

---

## Usage

### Basic Workflow

1. **Add a book** or edit an existing book in your library
2. **Open the "Edit metadata"** dialog
3. **Add a story URL** to the book's identifiers:
   - Click the "Identifiers" edit button
   - Add `url:` followed by your story URL
   - Example: `url:https://archiveofourown.org/works/12345678`
4. **Download metadata** using the metadata download feature:
   - Click the book
   - `Edit metadata` → `Download metadata`
   - Select `FicHub` as the source
5. **Review and apply** the fetched metadata

### Supported URL Formats

```text
https://archiveofourown.org/works/12345678
https://www.fanfiction.net/s/5782108/1/Story-Title
https://forums.spacebattles.com/threads/story.12345/
https://www.tthfanfic.org/story.php?id=123456
```

---

## Configuration

### Identifier Priority

The plugin scans identifiers in this priority order:

1. `url` - Direct URL identifier (highest priority)
2. `uri` - Alternative URL identifier  
3. `fichub` - FicHub-specific identifier
4. Any other identifier containing a valid URL

**Example identifiers in Calibre:**

```text
url:https://archiveofourown.org/works/123456
uri:https://www.fanfiction.net/s/5782108/1/
fichub:https://fichub.com/fic/123456
```

### Advanced Features

#### Automatic Retry Logic

- Transient API failures are automatically retried up to 5 attempts
- Uses exponential backoff starting at 60 seconds
- HTTP 429 rate-limiting honors `Retry-After` (capped at 5 minutes plus a small buffer)
- Only retries network errors and upstream failures
- Permanent errors (404 not found) fail immediately

#### Metadata Processing

- Authors are intelligently parsed from single strings or lists
- Tags are deduplicated while preserving original casing
- Series indices are converted to floating-point numbers
- Publication dates are normalized across different source formats
- Descriptions are automatically wrapped in HTML if needed

---

## Supported Metadata Fields

| Field | Source | Notes |
| --- | --- | --- |
| **Title** | `title` / `rawExtendedMeta.title` | Primary identifier |
| **Authors** | `author` / `authors` | Supports multiple authors |
| **Publication Date** | `created` / `rawExtendedMeta.published` | Normalized to UTC |
| **Language** | `rawExtendedMeta.language` | Auto-normalized to Calibre format |
| **Publisher** | Source domain | Maps AO3, FFNet, etc. |
| **Series** | `series` / `rawExtendedMeta.series` | With optional index |
| **Tags** | Multiple fields | Fandoms, genres, characters, warnings, etc. |
| **Comments** | Description + stats | HTML-formatted with metadata block |
| **Identifiers** | See section below | Platform-specific and FicHub IDs |

### Extracted Identifiers

| Identifier | Value | Source |
| --- | --- | --- |
| `fichub` | Full story URL | FicHub metadata |
| `fichub_id` | FicHub internal ID | FicHub metadata |
| `ao3` | AO3 work ID | For Archive of Our Own works |
| `ffnet` | FFNet story ID | For FanFiction.net stories |

---

## Error Handling

The plugin implements robust error handling:

### API Error Codes

| Code | Meaning | Action |
| --- | --- | --- |
| `ret=0` | Success | Metadata extracted |
| `ret=1` | Upstream error | Retried with backoff |
| `ret=2` | Not found | Fails immediately (no retry) |
| Network error | Connection failed | Retried with backoff |

### Common Error Messages

#### "FicHub: No URL found in identifiers"

- Solution: Add a URL to the book's identifiers (see [Usage](#usage) section)

#### "FicHub: unable to load fic"

- Solution: Verify the URL is correct and accessible
- Check if the story has been deleted or made private

#### "FicHub: Fic not found"

- Solution: The story URL may be malformed or the story doesn't exist
- Try accessing the URL directly in a browser

#### Network timeout

- Solution: Check your internet connection
- The plugin will automatically retry using configured backoff

---

## Troubleshooting

### No metadata returned

1. **Verify book URL:**
   - Make sure the identifier is `url:https://...` (with the `url:` prefix)
   - Copy the identifier exactly from the story page

2. **Check Calibre logs**
   - `Preferences → Miscellaneous → Log viewer`
   - Search for "FicHub" to see plugin messages

3. **Test the URL**
   - Paste the URL in a browser to verify it's accessible
   - Try the FicHub API directly: `https://fichub.net/api/v0/meta?q=YOUR_URL`

### Incomplete metadata

Some stories may not have all fields available:

- Not all platforms provide publication dates
- Series information is only available on certain sites
- Language detection depends on platform data

### Plugin crashes or errors

1. Ensure you're running **Calibre 2.80.0 or later**
2. Check the Calibre log viewer for detailed error messages
3. Try removing and reinstalling the plugin (see [Installation](#installation))

### Performance issues

- Metadata download respects the FicHub API rate limits
- If requests are slow, the FicHub service may be under load
- The plugin includes smart retry logic for transient failures

---

## Contributing

Contributions are welcome.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and pull request expectations.
For vulnerability reports, see [SECURITY.md](SECURITY.md).

### Development Notes

- The plugin uses Calibre's Source plugin API
- Metadata extraction is handled by the `_to_metadata()` method
- Error handling is built into `_fetch_metadata()` with retry logic

### CI/CD

This repository includes GitHub Actions workflows under `.github/workflows/`:

- `ci.yml`: Runs on pull requests and pushes to `main`/`master`. It validates plugin files, checks Python syntax, builds the plugin ZIP, and uploads it as a workflow artifact.
- `release.yml`: Runs on tag pushes matching `v*` and can also be run manually from the Actions tab. It builds `FicHub_Metadata_Source.zip` and attaches it to a GitHub Release.

To publish a release:

1. Create and push a version tag (for example `v0.1.0`)
2. GitHub Actions will build and publish the ZIP automatically

---

## License

This project is licensed under the **GPL v3** License - see [LICENSE](LICENSE) file for details.

This is compatible with Calibre's plugin system which also uses GPL.

---

## Support

### Getting Help

- **See troubleshooting above** for common issues
- **Check Calibre's log viewer** for detailed error messages
- **Verify your internet connection** if API calls are failing

### Reporting Issues

When reporting an issue, please include:

- Calibre version (Help → About Calibre)
- Plugin version (visible in Preferences → Plugins)
- The story URL you're trying to fetch
- Relevant error messages from the Calibre log viewer
- Steps to reproduce the issue

### FicHub API

For information about the FicHub API itself, visit

- **FicHub Home**: [https://fichub.net/](https://fichub.net/)
- **API Endpoint Reference**: [https://fichub.net/api](https://fichub.net/api)

---

## Related Projects

- [Calibre](https://calibre-ebook.com/) - E-book management system
- [FicHub](https://fichub.net/) - Fanfiction metadata aggregation API
- [Archive of Our Own](https://archiveofourown.org/) - Fanfiction archive
- [FanFiction.net](https://www.fanfiction.net/) - Fanfiction archive
