#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__ = 'GPL v3'
__copyright__ = '2026, Chats + contributors'
__docformat__ = 'restructuredtext en'

import json
import re
import time
from datetime import UTC, datetime
from typing import Any

from calibre import as_unicode, prepare_string_for_xml
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.date import parse_date, utcnow
from calibre.utils.localization import canonicalize_lang
from polyglot.urllib import urlencode, urlparse


class FicHub(Source):  # type: ignore[misc]
    """Metadata source plugin for FicHub API.

    Fetches fanfiction metadata from FicHub API, supporting FFNet, AO3, and other sources.
    """

    name: str = 'FicHub'
    version: tuple[int, int, int] = (0, 1, 0)
    minimum_calibre_version: tuple[int, int, int] = (2, 80, 0)
    'Fetches fanfiction metadata from FicHub API'
    description: str = 'Fetches fanfiction metadata from FicHub API'

    capabilities: frozenset[str] = frozenset({'identify'})
    touched_fields: frozenset[str] = frozenset(
        {
            'title',
            'authors',
            'tags',
            'series',
            'series_index',
            'publisher',
            'pubdate',
            'comments',
            'languages',
            'identifier:fichub_id',
            'identifier:ao3',
            'identifier:ffnet',
        }
    )
    supports_gzip_transfer_encoding: bool = True
    has_html_comments: bool = True

    # Identifier constants
    IDENTIFIER_FICHUB_ID: str = 'fichub_id'
    IDENTIFIER_AO3: str = 'ao3'
    IDENTIFIER_FFNET: str = 'ffnet'

    # API configuration
    API_META: str = 'https://fichub.net/api/v0/meta'
    URL_RE: re.Pattern[str] = re.compile(r'^https?://', re.I)
    PREFERRED_IDENTIFIER_KEYS: tuple[str, ...] = ('url', 'uri', 'fichub')

    # Retry configuration for transient errors
    MAX_RETRIES: int = 5
    INITIAL_BACKOFF: int = 60  # seconds
    MAX_RETRY_AFTER: int = 300  # cap server-provided Retry-After to 5 minutes

    def get_book_url(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, identifiers: dict[str, Any] | None
    ) -> tuple[str, str, str] | None:
        story_url: str | None = self._extract_story_url(identifiers or {})
        if story_url:
            return ('url', story_url, story_url)
        return None

    def identify(
        self,
        log: Any,
        result_queue: Any,
        abort: Any,
        title: str | None = None,
        authors: list[str] | None = None,
        identifiers: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> None:
        # store log object for helper methods and remember timeout
        self.log: Any = log
        self.timeout: int = timeout
        log(
            'FicHub: identify called with title=%r authors=%r identifiers=%r timeout=%r',
            title,
            authors,
            identifiers,
            timeout,
        )

        if abort.is_set():
            log('FicHub: abort flag set before processing identifiers')
            return

        # Extract story URL from identifiers with preference order
        identifiers = (identifiers or {}).copy()
        story_url: str | None = self._extract_story_url(identifiers)
        if not story_url:
            log.error('FicHub: No URL found in identifiers; expected `url:` or URL-like identifier value')
            return

        log('FicHub: Using story URL from identifiers:', story_url)
        payload: dict[str, Any] | None
        err: str | None
        payload, err = self._fetch_metadata(log, story_url, timeout)
        if err:
            log('FicHub: metadata fetch returned error, aborting identify')
            return
        if abort.is_set():
            log('FicHub: abort flag detected after metadata fetch')
            return
        if not isinstance(payload, dict):
            log.error('FicHub: Unexpected API payload (not an object)')
            return

        mi: Metadata | None = self._to_metadata(payload, story_url, log)
        if mi is None:
            log('FicHub: _to_metadata returned None, skipping result')
            return
        if abort.is_set():
            log('FicHub: abort flag detected after converting metadata')
            return

        mi.source_relevance = 0
        result_queue.put(mi)
        log('FicHub: queued 1 metadata result')
        if abort.is_set():
            log('FicHub: abort flag set after queuing result')
            return

    def _extract_story_url(self, identifiers: dict[str, Any] | None) -> str | None:
        """Extract story URL from identifiers dictionary.

        Checks preferred identifier keys first before scanning all keys.
        This implements the priority order: url > uri > fichub > others
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _extract_story_url called with %r', identifiers)

        if not isinstance(identifiers, dict):
            if log:
                log('FicHub: identifiers is not a dict, returning None')
            return None

        # First pass: check preferred identifier keys in order
        for key in self.PREFERRED_IDENTIFIER_KEYS:
            # we've already asserted identifiers is a dict
            val: str = str(identifiers.get(key))
            url = self._normalize_url_candidate(val)
            if url:
                if log:
                    log('FicHub: _extract_story_url matched preferred key %r -> %r', key, url)
                return url

        # Second pass: scan all remaining identifier keys for a URL
        for k, val in identifiers.items():
            url = self._normalize_url_candidate(val)
            if url:
                if log:
                    log('FicHub: _extract_story_url matched generic key %r -> %r', k, url)
                return url
        if log:
            log('FicHub: _extract_story_url found no valid URL')
        return None

    def _normalize_url_candidate(self, val: str) -> str | None:
        """Normalize and validate a URL candidate from an identifier value.

        The input might be any object; we only return a string if we can
        successfully coerce it to text and it looks like an HTTP(S) URL.
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _normalize_url_candidate checking %r', val)

        try:
            val = val.strip()
        except Exception as e:
            if log:
                log('FicHub: _normalize_url_candidate failed to strip value: %r', e)
            return None

        # Validate URL schema
        if self.URL_RE.match(val):
            if log:
                log('FicHub: _normalize_url_candidate accepted %r', val)
            return val
        if log:
            log('FicHub: _normalize_url_candidate rejected %r', val)
        return None

    def _fetch_metadata(
        self, log: Any, story_url: str, timeout: int | float
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Fetch metadata from FicHub API with retry logic for transient errors.

        Args:
            log: Logger instance
            story_url: Story URL to fetch metadata for
            timeout: Request timeout in seconds

        Returns:
            Tuple of (payload dict, error string). If successful, error is None.
        """
        log('FicHub: _fetch_metadata called for %r (timeout %s)', story_url, timeout)
        query = urlencode({'q': story_url})
        endpoint = f'{self.API_META}?{query}'

        # Retry loop with exponential backoff for transient failures
        backoff = self.INITIAL_BACKOFF
        for attempt in range(self.MAX_RETRIES):
            log(f'FicHub: Requesting API endpoint (attempt {attempt + 1}): {endpoint}')

            br = self.browser
            try:
                response = br.open_novisit(endpoint, timeout=timeout)
            except Exception as e:
                # Network error - may be transient
                log.exception('FicHub: metadata request failed')
                if attempt < self.MAX_RETRIES - 1:
                    log(f'FicHub: Retrying after {backoff}s due to network error')
                    time.sleep(backoff)
                    backoff *= 2  # exponential backoff
                    continue
                log('FicHub: _fetch_metadata giving up after network errors')
                return (None, as_unicode(e))

            # Check for HTTP 429 (rate limiting) and respect Retry-After
            if hasattr(response, 'code') and response.code == 429:
                retry_after = None
                # First, try to get retry-after from the response header
                if hasattr(response, 'headers'):
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        try:
                            retry_after = int(retry_after)
                        except (ValueError, TypeError):
                            retry_after = None
                else:
                    try:
                        raw = response.read()
                        body = json.loads(raw.decode('utf-8'))
                        retry_after = body.get('retry_after')
                        if retry_after:
                            try:
                                retry_after = int(retry_after)
                            except (ValueError, TypeError):
                                retry_after = None
                    except Exception:
                        pass

                # Cap the retry-after to a reasonable maximum
                if retry_after is None:
                    retry_after = backoff
                retry_after = min(retry_after, self.MAX_RETRY_AFTER) + 2  # add small buffer

                if attempt < self.MAX_RETRIES - 1:
                    log(f'FicHub: HTTP 429 Too Many Requests; retrying after {retry_after}s')
                    time.sleep(retry_after)
                    continue

                log('FicHub: HTTP 429 Too Many Requests; max retries exceeded')
                return (None, 'FicHub API rate limited; please try again later')

            # Read the response body
            raw = response.read()

            # Successfully received response, now parse it
            try:
                data = json.loads(raw.decode('utf-8'))
            except Exception as e:
                log.error('FicHub: failed to parse JSON response')
                log.exception(e)
                return (None, 'Failed to parse FicHub response as JSON')

            # Check FicHub error envelope: ret!=0 indicates an error
            if isinstance(data, dict) and int(data.get('ret', 0) or 0) != 0:
                ret_code = int(data.get('ret', 0) or 0)

                # ret=2: Fic not found (permanent error - don't retry)
                if ret_code == 2:
                    msg = data.get('msg') or 'Fic not found'
                    log.error('FicHub: Fic not found:', story_url)
                    return (None, f'FicHub: {as_unicode(msg)}')

                # ret=1: Upstream error (transient - may retry)
                if ret_code == 1 and attempt < self.MAX_RETRIES - 1:
                    msg = data.get('msg') or 'upstream error'
                    log(f'FicHub: Upstream error, retrying after {backoff}s: {as_unicode(msg)}')
                    time.sleep(backoff)
                    backoff *= 2
                    continue

                # Other errors or max retries exceeded
                msg = data.get('msg') or data.get('res') or 'unknown API error'
                log.error('FicHub: API returned an error:', msg)
                return (None, f'FicHub API error: {as_unicode(msg)}')

            # Success: return parsed data
            log('FicHub: API response parsed successfully')
            return (data, None)
        # all retry attempts exhausted, fall back
        log('FicHub: _fetch_metadata exhausted retries without result')
        return (None, None)

    def _to_metadata(self, payload: dict[str, Any], submitted_url: str, log: Any) -> Metadata | None:
        """Convert FicHub API payload to Calibre Metadata object.

        Args:
            payload: API response payload
            submitted_url: Original story URL submitted
            log: Logger instance

        Returns:
            Metadata object or None if title is missing
        """
        log('FicHub: _to_metadata invoked; payload keys: %s', list(payload.keys()))
        raw_meta: dict[str, Any] = payload.get('rawExtendedMeta') or {}

        title = self._first_non_empty(
            payload.get('title'),
            raw_meta.get('title'),
        )
        if not title:
            log.error('FicHub: payload missing title, cannot create metadata result')
            return None

        # Extract author(s) - may be single string or list
        authors = self._extract_authors(payload, raw_meta)
        log('FicHub: authors extracted -> %r', authors)
        mi = Metadata(title, authors)

        # Set identifiers: store URLs and source-specific IDs
        canonical_url = self._first_non_empty(payload.get('source'), submitted_url)
        if payload.get('id'):
            mi.set_identifier(self.IDENTIFIER_FICHUB_ID, str(payload.get('id')))

        # Add source-specific identifier (ao3 or ffnet) if available
        source_key = self._source_identifier_key(canonical_url)
        source_story_id = self._first_non_empty(raw_meta.get('id'), payload.get('sourceLocalId'))
        if source_key and source_story_id:
            mi.set_identifier(source_key, str(source_story_id))

        # Extract and normalize language
        language = self._first_non_empty(
            raw_meta.get('language'),
            payload.get('language'),
            self._extract_from_ao3_stats(raw_meta, 'language'),
        )
        cl = canonicalize_lang(language)
        if cl:
            mi.set('language', cl)

        # Parse publication date from metadata
        pubdate = self._parse_pubdate(payload, raw_meta)
        if pubdate is not None:
            mi.set('pubdate', pubdate)

        # Set publisher based on source domain
        mi.publisher = self._publisher_name(canonical_url)

        # Collect and deduplicate tags from various sources
        tags = self._collect_tags(payload, raw_meta)
        if tags:
            mi.set('tags', tags)

        # Extract series information if available.  _extract_series now returns
        # (primary_name, primary_index, additional_series_list) to support
        # payloads that contain multiple series entries.
        series_name, series_index, additional_series = self._extract_series(payload, raw_meta)
        if series_name:
            mi.series = series_name
            if series_index is not None:
                # series_index should be a number; set on the dedicated property
                log(f'FicHub: setting series_index to {series_index!r}')
                try:
                    mi.set('series_index', float(series_index) or 1.00)
                except (ValueError, TypeError):
                    log(f'FicHub: could not convert series_index to float: {series_index!r}')

            # If the source reported multiple series, record the extras as tags
            # of the form "series:Name" so they are preserved in the metadata
            # and searchable.
            if additional_series:
                try:
                    existing_tags = list(mi.tags) if mi.tags else []
                except Exception:
                    existing_tags = []
                for s in additional_series:
                    tag: str = 'series:' + str(s)
                    if tag.lower() not in (t.lower() for t in existing_tags):
                        existing_tags.append(tag)
                if existing_tags:
                    mi.set('tags', existing_tags)

        mi.comments = self._build_comments(payload, raw_meta)

        log('FicHub: mapped metadata fields for:', title)
        return mi

    def _extract_series(
        self, payload: dict[str, Any], raw_meta: dict[str, Any]
    ) -> tuple[str | None, float | None, list[str]]:
        """Extract series name and index from metadata.

        Searches multiple field names as they vary between FFNet and AO3 formats.

        Returns:
            Tuple of (primary_series_name, primary_series_index, additional_series_list)
            Where additional_series_list is a list of other series names (may be empty).
        """
        log = getattr(self, 'log', None)
        if log:
            log(
                'FicHub: _extract_series called with payload keys %s, raw_meta keys %s',
                list(payload.keys()),
                list(raw_meta.keys()),
            )
        # Try multiple field names for series name(s) (format varies by source).
        raw_series = (
            raw_meta.get('series')
            if raw_meta.get('series') is not None
            else payload.get('series') or payload.get('seriesName')
        )
        if raw_series is None:
            if log:
                log('FicHub: no series name found')
            return None, None, []

        # Normalize into a list of series names
        if isinstance(raw_series, (list, tuple)):
            series_list = [str(x).strip() for x in raw_series if x and str(x).strip()]
        else:
            # some sources provide a single string
            series_list = [str(raw_series).strip()] if str(raw_series).strip() else []

        if not series_list:
            if log:
                log('FicHub: series list empty after normalization')
            return None, None, []

        primary = series_list[0]

        # Try multiple field names for series index/number.  The index may be a
        # single value or a list aligned with the series list.
        raw_idx = (
            raw_meta.get('seriesIndex')
            if raw_meta.get('seriesIndex') is not None
            else payload.get('seriesIndex') or payload.get('seriesNumber')
        )
        idx_val = None
        if raw_idx is None:
            idx_val = None
        elif isinstance(raw_idx, (list, tuple)):
            # If aligned lists are provided, use the one at the primary position
            try:
                idx_val = raw_idx[0]
            except Exception:
                idx_val = None
        else:
            idx_val = raw_idx

        # Convert to float for Calibre if possible (series_index expects numeric type)
        primary_index = None
        try:
            if idx_val is not None:
                primary_index = float(idx_val)
        except Exception as e:
            if log:
                log('FicHub: failed to convert series index %r to float: %r', idx_val, e)
            primary_index = None

        # Other series (beyond the primary) are preserved for downstream handling
        additional = series_list[1:]
        return primary, primary_index, additional

    def _collect_tags(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> list[str]:
        """Collect and deduplicate tags from various metadata sources.

        Handles both FFNet and AO3 metadata formats, collecting fandoms, genres,
        characters, relationships, warnings, and other metadata as tags.

        Uses case-insensitive deduplication while preserving original casing.
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _collect_tags called')
        tags = []
        seen = set()  # Track seen tags in lowercase for deduplication

        def add(tag: Any) -> None:
            """Add a tag with deduplication and normalization."""
            if not tag:
                return
            t: str = str(tag).strip()
            if not t:
                return
            # Normalize commas to semicolons for consistency
            t = t.replace(',', ';')
            # Check for duplicate (case-insensitive)
            if t.lower() not in seen:
                seen.add(t.lower())
                tags.append(t)

        # FFNet format: raw_fandom and fandom stubs
        add(raw_meta.get('raw_fandom'))
        fandom_stubs = raw_meta.get('fandom_stubs') or ()
        if isinstance(fandom_stubs, (list, tuple)):
            for item in fandom_stubs:
                # Convert hyphenated series names to spaces (e.g. "Harry-Potter" -> "Harry Potter")
                add(str(item).replace('-', ' '))

        # Tags common to both formats: genres, characters, ships/relationships
        for key in ('genres', 'characters', 'ships', 'relationships'):
            val = raw_meta.get(key)
            if not val:
                continue
            # Handle both list and string formats
            if isinstance(val, (list, tuple)):
                for item in val:
                    add(str(item))
            else:
                # Split string by common delimiters
                parts = [x.strip() for x in re.split(r'[/,]', str(val))]
                for part in parts:
                    add(part)

        # AO3 format: category, fandom, rating, warning, freeform
        # These are typically lists in AO3 responses
        for key in ('category', 'fandom', 'rating', 'warning', 'freeform'):
            val = raw_meta.get(key)
            if isinstance(val, (list, tuple)):
                for item in val:
                    add(str(item))

        # Add story status as a prefixed tag for easy filtering
        status = self._first_non_empty(payload.get('status'), raw_meta.get('status'))
        if status:
            add('status:' + str(status).lower())

        if log:
            log('FicHub: _collect_tags produced %r', tags)
        return tags

    def _build_comments(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> str:
        """Build rich HTML comments with description and metadata.

        Formats description and key metadata fields as HTML for display in Calibre.
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _build_comments starting')
        # Extract description and wrap in paragraph tags if not already HTML
        desc = self._first_non_empty(payload.get('description'), raw_meta.get('description'))
        if desc and not self._is_html(desc):
            desc = f'<p>{prepare_string_for_xml(desc)}</p>'
        elif not desc:
            desc = ''

        # Build metadata section as HTML definition list for better formatting
        lines = []

        # Primary metadata: source, status, length, update time
        primary_meta = [
            ('Source URL', self._first_non_empty(payload.get('source'))),
            ('Status', self._first_non_empty(payload.get('status'), raw_meta.get('status'))),
            ('Chapters', self._first_non_empty(payload.get('chapters'), raw_meta.get('chapters'))),
            ('Words', self._first_non_empty(payload.get('words'), raw_meta.get('words'))),
            ('Updated', self._first_non_empty(payload.get('updated'), raw_meta.get('updated'))),
        ]

        # Add primary metadata
        for label, val in primary_meta:
            if val is not None and str(val).strip():
                lines.append(
                    f'<p><b>{prepare_string_for_xml(label)}:</b> {prepare_string_for_xml(as_unicode(val))}</p>'
                )

        # Add AO3-specific statistics if available
        stats = raw_meta.get('stats')
        if isinstance(stats, dict):
            stats_lines = self._format_ao3_stats(stats)
            if stats_lines:
                lines.append('<hr/>')
                lines.extend(stats_lines)

        # Add additional metadata if present
        extra = self._first_non_empty(payload.get('extraMeta'))
        if extra:
            lines.append(f'<p><em>{prepare_string_for_xml(as_unicode(extra))}</em></p>')

        result = '{}{}'.format(desc, ''.join(lines))
        if log:
            log('FicHub: _build_comments produced %d characters of HTML', len(result))
        return result

    def _format_ao3_stats(self, stats: dict[str, Any]) -> list[str]:
        """Format AO3 statistics for display in comments.

        Args:
            stats: Stats dict from AO3 metadata

        Returns:
            List of HTML strings with formatted stats
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _format_ao3_stats called with stats keys %r', list(stats.keys()))
        lines = []
        # Map stats field names to display labels
        stat_fields = [
            ('kudos', 'Kudos'),
            ('comments', 'Comments'),
            ('bookmarks', 'Bookmarks'),
            ('hits', 'Hits'),
        ]

        for field, label in stat_fields:
            val = stats.get(field)
            if val is not None:
                lines.append(f'<p><b>{label}:</b> {prepare_string_for_xml(as_unicode(val))}</p>')
        if log:
            log('FicHub: _format_ao3_stats returning %r', lines)
        return lines

    def _parse_pubdate(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> datetime | None:
        """Parse publication date from metadata.

        Tries multiple date formats and sources, handling both ISO strings and
        Unix timestamps as provided by different sources (FFNet vs AO3).
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _parse_pubdate called')
        # Try ISO format date from FicHub first (common format)
        created = payload.get('created')
        if created:
            try:
                # Use mid-month as fallback for missing day (assume_utc for no timezone)
                default: datetime = utcnow().replace(day=15)
                parsed: datetime = parse_date(created, assume_utc=True, default=default)
                if log:
                    log('FicHub: parsed pubdate from created field: %r', parsed)
                return parsed
            except Exception as e:
                if log:
                    log('FicHub: failed to parse created date %r: %r', created, e)
                pass

        # Try Unix timestamp from extended metadata (FFNet format)
        published = raw_meta.get('published')
        if published is None:
            if log:
                log('FicHub: no published field in raw_meta')
            return None
        try:
            # Handle string timestamps that are numeric
            if isinstance(published, str) and published.isdigit():
                published = int(published)
            # Convert Unix timestamp to datetime
            if isinstance(published, (int, float)):
                dt: datetime = datetime.fromtimestamp(published, tz=UTC)
                if log:
                    log('FicHub: parsed pubdate from timestamp %r -> %r', published, dt)
                return dt
            # Try parsing as a date string
            default = utcnow().replace(day=15)
            parsed = parse_date(str(published), assume_utc=True, default=default)
            if log:
                log('FicHub: parsed pubdate from string %r -> %r', published, parsed)
            return parsed
        except Exception as e:
            if log:
                log('FicHub: error parsing published field %r: %r', published, e)
            return None

    def _source_identifier_key(self, canonical_url: str | None) -> str | None:
        """Get the identifier key for a source URL.

        Maps domains to Calibre identifier keys (ao3, ffnet, etc.)
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _source_identifier_key called with %r', canonical_url)
        if not canonical_url:
            if log:
                log('FicHub: canonical_url is None or empty')
            return None
        try:
            host = (urlparse(canonical_url).netloc or '').lower()
        except Exception as e:
            if log:
                log('FicHub: error parsing url %r: %r', canonical_url, e)
            return None

        # Match known fanfiction archive domains
        if 'archiveofourown.org' in host:
            if log:
                log('FicHub: matched AO3 host %r', host)
            return self.IDENTIFIER_AO3
        if 'fanfiction.net' in host:
            if log:
                log('FicHub: matched FFNet host %r', host)
            return self.IDENTIFIER_FFNET
        if log:
            log('FicHub: no known source identifier for host %r', host)
        return None

    def _is_html(self, text: Any) -> bool:
        """Check if text appears to be HTML formatted.

        Uses regex to detect HTML tags for safe handling of descriptions.
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _is_html checking text type %s', type(text))
        if not isinstance(text, str):
            return False
        # Look for HTML-like tags (e.g., <p>, <br/>, <div>)
        result = bool(re.search(r'<[a-z]+[^>]*>', text, re.IGNORECASE))
        if log:
            log('FicHub: _is_html result %s for %r', result, text[:30])
        return result

    def _publisher_name(self, canonical_url: str | None) -> str | None:
        """Get the publisher/platform name for a source URL.

        Maps known fanfiction platforms to their official names.
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _publisher_name called with %r', canonical_url)
        if not canonical_url:
            return None
        try:
            host = (urlparse(canonical_url).netloc or '').lower()
        except Exception as e:
            if log:
                log('FicHub: _publisher_name failed to parse url %r: %r', canonical_url, e)
            return None

        # Map known platforms to their names
        if 'archiveofourown.org' in host:
            return 'Archive of Our Own'
        if 'fanfiction.net' in host:
            return 'FanFiction.net'
        # Fallback to domain name for unknown platforms
        if host:
            return host
        return None

    def _extract_authors(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> list[str]:
        """Extract author(s) from payload.

        Handles both single author (string) and multiple authors (list).
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _extract_authors called')
        # Try to get authors from multiple sources
        authors_val = self._first_non_empty(
            payload.get('authors'),  # May be a list
            payload.get('author'),  # May be a string
            raw_meta.get('authors'),
            raw_meta.get('author'),
        )
        if log:
            log('FicHub: candidate authors_val=%r', authors_val)

        if not authors_val:
            if log:
                log('FicHub: no authors found, defaulting to Unknown')
            return ['Unknown']

        # Handle list of authors
        if isinstance(authors_val, (list, tuple)):
            result = []
            for author in authors_val:
                author_str = str(author).strip() if author else None
                if author_str:
                    result.append(author_str)
            if log:
                log('FicHub: extracted authors list %r', result or ['Unknown'])
            return result or ['Unknown']

        # Handle single author string (may be comma/semicolon separated)
        author_str = str(authors_val).strip()
        if not author_str:
            if log:
                log('FicHub: single author string empty after strip, using Unknown')
            return ['Unknown']

        # Try to split multiple authors if separated by common delimiters
        if ',' in author_str or ';' in author_str:
            parts = re.split(r'[,;]', author_str)
            result = [p.strip() for p in parts if p.strip()]
            if log:
                log('FicHub: split multiple authors -> %r', result or [author_str])
            return result or [author_str]

        if log:
            log('FicHub: single author string -> [%r]', author_str)
        return [author_str]

    def _first_non_empty(self, *vals: Any) -> Any | None:
        """Return the first non-empty value from the given list."""
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _first_non_empty checking %r', vals)
        for val in vals:
            if val is None:
                continue
            sval = str(val).strip()
            if sval:
                if log:
                    log('FicHub: _first_non_empty returning %r', val)
                return val
        if log:
            log('FicHub: _first_non_empty found no non-empty values')
        return None

    def _extract_from_ao3_stats(self, raw_meta: dict[str, Any], field: str) -> Any | None:
        """Extract values from AO3 stats object if present.

        AO3 metadata includes a nested stats dict with fields like language,
        word count, chapter count, and engagement metrics.
        """
        log = getattr(self, 'log', None)
        if log:
            log('FicHub: _extract_from_ao3_stats looking for %r', field)
        stats = raw_meta.get('stats')
        if isinstance(stats, dict):
            val = stats.get(field)
            if log:
                log('FicHub: _extract_from_ao3_stats found %r', val)
            return val
        if log:
            log('FicHub: _extract_from_ao3_stats no stats dict present')
        return None
