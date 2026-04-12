from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from calibre import as_unicode, prepare_string_for_xml
from calibre.ebooks.metadata.book.base import Metadata
from calibre.utils.date import parse_date, utcnow
from calibre.utils.localization import canonicalize_lang
from polyglot.urllib import urlparse

_SPLIT_AUTHORS_RE = re.compile(r'[,;]')
_SPLIT_TAGS_RE = re.compile(r'[/,]')
_HTML_RE = re.compile(r'<[a-z]+[^>]*>', re.IGNORECASE)


class UrlCandidateStrategy(Protocol):
    """Protocol for URL extraction strategies.

    Implementations inspect an identifiers mapping and attempt to extract
    a valid URL using the provided normalizer.

    Methods:
        extract(identifiers, normalizer): Return the first valid URL found,
            or None if no URL can be extracted.
    """

    def extract(self, identifiers: dict[str, Any], normalizer: UrlNormalizer) -> str | None:
        """Extract a candidate URL from an identifier mapping.

        Args:
            identifiers (dict[str, Any]): Mapping containing identifier keys
                and values that may include URL-like data.
            normalizer (UrlNormalizer): Normalizer used to validate and clean
                candidate URL values.

        Returns:
            str | None: A normalized URL string if one is found; otherwise None.
        """
        ...


class MetadataTransformer(Protocol):
    """Protocol for objects that convert payload data into calibre metadata.

    Implementations transform a source payload and submitted URL into a
    `Metadata` object suitable for downstream processing.
    """

    def transform(self, payload: dict[str, Any], submitted_url: str, log: Any) -> Metadata | None:
        """Transform an input payload into a `Metadata` object.

        Args:
            payload (dict[str, Any]): Source data containing metadata fields.
            submitted_url (str): URL originally submitted by the caller.
            log (Any): Logger-like object used for error reporting and diagnostics.

        Returns:
            Metadata | None: A populated metadata object on success; otherwise None.
        """
        ...


class UrlNormalizer:
    """Normalize and validate URL values.

    This class converts arbitrary values to stripped strings and accepts only
    HTTP or HTTPS URLs.
    """

    URL_RE: re.Pattern[str] = re.compile(r'^https?://', re.I)

    def __init__(self, log: Any = None) -> None:
        """Initialize the URL normalizer.

        Args:
            log (Any): Optional logger-like object for diagnostics.

        Returns:
            None: This constructor initializes instance state only.
        """
        self.log = log

    def normalize(self, val: Any) -> str | None:
        """Convert a value to a normalized URL if it is valid.

        The method attempts to convert the input to a string, strips leading
        and trailing whitespace, and returns the value only if it begins with
        ``http://`` or ``https://``.

        Args:
            val (Any): Value to normalize into a URL string.

        Returns:
            str | None: A stripped URL string if valid; otherwise None.
        """
        try:
            text = str(val).strip()
        except Exception:
            return None
        return text if self.URL_RE.match(text) else None


class PreferredKeyUrlStrategy:
    """URL extraction strategy that searches specific identifier keys first.

    The configured keys are checked in order, and the first valid URL found
    is returned.
    """

    def __init__(self, preferred_keys: tuple[str, ...]) -> None:
        """Initialize the strategy with preferred identifier keys.

        Args:
            preferred_keys (tuple[str, ...]): Ordered tuple of keys to inspect
                for URL values.

        Returns:
            None: This constructor stores configuration only.
        """
        self.preferred_keys = preferred_keys

    def extract(self, identifiers: dict[str, Any], normalizer: UrlNormalizer) -> str | None:
        """Extract a URL from preferred identifier keys.

        Args:
            identifiers (dict[str, Any]): Mapping of identifiers to inspect.
            normalizer (UrlNormalizer): Normalizer used to validate candidate values.

        Returns:
            str | None: The first normalized URL found in the preferred keys,
            or None if no valid URL is present.
        """
        normalize = normalizer.normalize
        get = identifiers.get
        for key in self.preferred_keys:
            url = normalize(get(key))
            if url:
                return url
        return None


class GenericScanUrlStrategy:
    """URL extraction strategy that scans all identifier values.

    This strategy is a fallback that checks every value in the identifiers
    mapping until it finds a valid URL.
    """

    def extract(self, identifiers: dict[str, Any], normalizer: UrlNormalizer) -> str | None:
        """Extract a URL by scanning all identifier values.

        Args:
            identifiers (dict[str, Any]): Mapping of identifiers to inspect.
            normalizer (UrlNormalizer): Normalizer used to validate candidate values.

        Returns:
            str | None: The first normalized URL found, or None if none exist.
        """
        normalize = normalizer.normalize
        for value in identifiers.values():
            url = normalize(value)
            if url:
                return url
        return None


class UrlExtractor:
    """Extract URLs from an identifier mapping using multiple strategies.

    Strategies are applied in order, and extraction stops at the first valid URL.
    """

    def __init__(self, strategies: list[UrlCandidateStrategy], normalizer: UrlNormalizer) -> None:
        """Initialize the extractor with strategies and a normalizer.

        Args:
            strategies (list[UrlCandidateStrategy]): Ordered list of extraction
                strategies to apply.
            normalizer (UrlNormalizer): URL normalizer shared by all strategies.

        Returns:
            None: This constructor initializes instance state only.
        """
        self.strategies = strategies
        self.normalizer = normalizer

    def extract(self, identifiers: dict[str, Any] | None) -> str | None:
        """Extract a URL from an identifiers mapping.

        Args:
            identifiers (dict[str, Any] | None): Mapping containing identifier
                values that may include a URL.

        Returns:
            str | None: The first extracted normalized URL, or None if input is
            invalid or no URL is found.
        """
        if not isinstance(identifiers, dict):
            return None
        for strategy in self.strategies:
            url = strategy.extract(identifiers, self.normalizer)
            if url:
                return url
        return None


class DomainInfoService:
    """Resolve domain-specific metadata details from canonical URLs.

    This service maps known hosts to identifier keys and publisher names.
    """

    IDENTIFIER_AO3 = 'ao3'
    IDENTIFIER_FFNET = 'ffnet'

    def __init__(self, log: Any = None) -> None:
        """Initialize the domain information service.

        Args:
            log (Any): Optional logger-like object for diagnostics.

        Returns:
            None: This constructor initializes instance state only.
        """
        self.log = log

    def source_identifier_key(self, canonical_url: str | None) -> str | None:
        """Return the metadata identifier key for a known source domain.

        Args:
            canonical_url (str | None): Canonical source URL.

        Returns:
            str | None: Domain-specific identifier key such as ``ao3`` or
            ``ffnet`` if recognized; otherwise None.
        """
        host = self._host(canonical_url)
        if self._host_matches(host, 'archiveofourown.org'):
            return self.IDENTIFIER_AO3
        if self._host_matches(host, 'fanfiction.net'):
            return self.IDENTIFIER_FFNET
        return None

    def publisher_name(self, canonical_url: str | None) -> str | None:
        """Return a human-readable publisher name for a source URL.

        Known domains are mapped to friendly display names. Unknown domains
        return the host name itself.

        Args:
            canonical_url (str | None): Canonical source URL.

        Returns:
            str | None: Friendly publisher name, host name, or None if no host
            can be determined.
        """
        host = self._host(canonical_url)
        if not host:
            return None
        if self._host_matches(host, 'archiveofourown.org'):
            return 'Archive of Our Own'
        if self._host_matches(host, 'fanfiction.net'):
            return 'FanFiction.net'
        return host

    def _host(self, canonical_url: str | None) -> str:
        """Extract a lowercase host name from a URL.

        Args:
            canonical_url (str | None): URL from which to extract the host.

        Returns:
            str: Lowercase network location component, or an empty string if
            extraction fails.
        """
        if not canonical_url:
            return ''
        try:
            return (urlparse(canonical_url).netloc or '').lower()
        except Exception:
            return ''

    def _host_matches(self, host: str, expected: str) -> bool:
        """Determine whether a host matches an expected domain.

        A match succeeds for the exact domain or any subdomain of it.

        Args:
            host (str): Host name to test.
            expected (str): Expected root domain.

        Returns:
            bool: True if the host matches the expected domain; otherwise False.
        """
        return host == expected or host.endswith(f'.{expected}')


class MetadataMapper:
    """Transform source payload data into a populated calibre `Metadata` object.

    This class extracts titles, authors, identifiers, language, publication date,
    publisher, tags, series information, and HTML comments from the payload.
    """

    IDENTIFIER_FICHUB_ID = 'fichub_id'

    def __init__(self, domain_info: DomainInfoService, log: Any = None) -> None:
        """Initialize the metadata mapper.

        Args:
            domain_info (DomainInfoService): Service used to resolve domain-based
                identifier keys and publisher names.
            log (Any): Optional logger-like object for diagnostics.

        Returns:
            None: This constructor initializes instance state only.
        """
        self.domain_info = domain_info
        self.log = log
        self.comment_builder = HtmlCommentBuilder(self)

    def transform(self, payload: dict[str, Any], submitted_url: str, log: Any) -> Metadata | None:
        """Transform source payload data into a `Metadata` object.

        Args:
            payload (dict[str, Any]): Input payload containing metadata fields.
            submitted_url (str): Original source URL submitted by the caller.
            log (Any): Logger-like object used for diagnostics and error reporting.

        Returns:
            Metadata | None: A populated metadata object if a valid title is
            available; otherwise None.
        """
        self.log = log
        self.domain_info.log = log

        payload_get = payload.get
        raw_meta_candidate = payload_get('rawExtendedMeta')
        raw_meta = cast(dict[str, Any], raw_meta_candidate) if isinstance(raw_meta_candidate, dict) else {}
        raw_get = raw_meta.get

        title = self.first_non_empty(payload_get('title'), raw_get('title'))
        if not title:
            if log and hasattr(log, 'error'):
                log.error('FicHub: payload missing title, cannot create metadata result')
            return None

        mi = Metadata(title, self.extract_authors(payload, raw_meta))
        canonical_url = self.first_non_empty(payload_get('source'), submitted_url)

        payload_id = payload_get('id')
        if payload_id:
            mi.set_identifier(self.IDENTIFIER_FICHUB_ID, str(payload_id))

        source_key = self.domain_info.source_identifier_key(canonical_url)
        source_story_id = self.first_non_empty(raw_get('id'), payload_get('sourceLocalId'))
        if source_key and source_story_id:
            mi.set_identifier(source_key, str(source_story_id))

        language = self.first_non_empty(
            raw_get('language'),
            payload_get('language'),
            self.extract_from_ao3_stats(raw_meta, 'language'),
        )
        cl = canonicalize_lang(language)
        if cl:
            # Set both spellings for compatibility with calibre and local tests/stubs.
            mi.language = cl
            mi.languages = [cl]

        pubdate = self.parse_pubdate(payload, raw_meta)
        if pubdate is not None:
            mi.set('pubdate', pubdate)

        mi.publisher = self.domain_info.publisher_name(canonical_url)

        tags = self.collect_tags(payload, raw_meta)
        if tags:
            mi.set('tags', tags)

        series_name, series_index, additional_series = self.extract_series(payload, raw_meta)
        if series_name:
            mi.series = series_name
            if series_index is not None:
                mi.set('series_index', series_index or 1.0)
            if additional_series:
                existing_tags = list(mi.tags) if getattr(mi, 'tags', None) else []
                existing_lower = {t.lower() for t in existing_tags}
                for item in additional_series:
                    tag = 'series:' + str(item)
                    if tag.lower() not in existing_lower:
                        existing_lower.add(tag.lower())
                        existing_tags.append(tag)
                if existing_tags:
                    mi.set('tags', existing_tags)

        mi.comments = self.comment_builder.build(payload, raw_meta)
        return mi

    def first_non_empty(self, *vals: Any) -> Any | None:
        """Return the first non-empty value from the provided arguments.

        String values must contain non-whitespace content. Non-string values
        are converted to strings and must also be non-empty after stripping.

        Args:
            *vals (Any): Candidate values to inspect in order.

        Returns:
            Any | None: The first non-empty original value, or None if no such
            value exists.
        """
        for val in vals:
            if val is None:
                continue
            try:
                if isinstance(val, str):
                    if val.strip():
                        return val
                elif str(val).strip():
                    return val
            except Exception:
                continue
        return None

    def extract_authors(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> list[str]:
        """Extract a normalized list of author names.

        The method checks several possible author fields, supports list/tuple
        values, and splits delimited author strings on commas or semicolons.

        Args:
            payload (dict[str, Any]): Top-level payload dictionary.
            raw_meta (dict[str, Any]): Nested raw metadata dictionary.

        Returns:
            list[str]: List of author names. Returns ``['Unknown']`` if no valid
            author information is available.
        """
        authors_val = self.first_non_empty(
            payload.get('authors'),
            payload.get('author'),
            raw_meta.get('authors'),
            raw_meta.get('author'),
        )
        if not authors_val:
            return ['Unknown']
        if isinstance(authors_val, (list, tuple)):
            authors_iter = cast(list[Any] | tuple[Any, ...], authors_val)
            result = [text for text in (str(author).strip() for author in authors_iter) if text]
            return result or ['Unknown']

        author_str = str(authors_val).strip()
        if not author_str:
            return ['Unknown']
        if ',' in author_str or ';' in author_str:
            result = [p.strip() for p in _SPLIT_AUTHORS_RE.split(author_str) if p.strip()]
            return result or [author_str]
        return [author_str]

    def extract_series(
        self, payload: dict[str, Any], raw_meta: dict[str, Any]
    ) -> tuple[str | None, float | None, list[str]]:
        """Extract series information from payload data.

        The method resolves a primary series name, an optional numeric index,
        and any additional series entries.

        Args:
            payload (dict[str, Any]): Top-level payload dictionary.
            raw_meta (dict[str, Any]): Nested raw metadata dictionary.

        Returns:
            tuple[str | None, float | None, list[str]]: A tuple containing the
            primary series name, the numeric series index if parseable, and a
            list of additional series names.
        """
        raw_series = raw_meta.get('series')
        if raw_series is None:
            raw_series = payload.get('series') or payload.get('seriesName')
        if raw_series is None:
            return None, None, []

        if isinstance(raw_series, (list, tuple)):
            series_iter = cast(list[Any] | tuple[Any, ...], raw_series)
            series_list = [text for text in (str(x).strip() for x in series_iter) if text]
        else:
            text = str(raw_series).strip()
            series_list = [text] if text else []
        if not series_list:
            return None, None, []

        raw_idx = raw_meta.get('seriesIndex')
        if raw_idx is None:
            raw_idx = payload.get('seriesIndex') or payload.get('seriesNumber')
        idx_val: str | int | float | None
        if isinstance(raw_idx, (list, tuple)):
            raw_idx_items = cast(list[Any] | tuple[Any, ...], raw_idx)
            first_item = raw_idx_items[0] if raw_idx_items else None
            if isinstance(first_item, (str, int, float)):
                idx_val = first_item
            else:
                idx_val = None
        elif isinstance(raw_idx, (str, int, float)):
            idx_val = raw_idx
        else:
            idx_val = None

        primary_index: float | None = None
        if idx_val is not None:
            try:
                primary_index = float(idx_val)
            except Exception:
                primary_index = None

        return series_list[0], primary_index, series_list[1:]

    def collect_tags(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> list[str]:
        """Collect, normalize, and deduplicate tags from metadata fields.

        Tags are gathered from fandom, genre, character, relationship, category,
        rating, warning, freeform, and status-related fields.

        Args:
            payload (dict[str, Any]): Top-level payload dictionary.
            raw_meta (dict[str, Any]): Nested raw metadata dictionary.

        Returns:
            list[str]: Ordered list of unique normalized tag strings.
        """
        tags: list[str] = []
        seen: set[str] = set()
        raw_get = raw_meta.get

        def add(tag: Any) -> None:
            """Add a tag to the collection if it is non-empty and not duplicated.

            Args:
                tag (Any): Candidate tag value.

            Returns:
                None: The tag list is modified in place.
            """
            if not tag:
                return
            text = str(tag).strip()
            if not text:
                return
            text = text.replace(',', ';')
            lower = text.lower()
            if lower not in seen:
                seen.add(lower)
                tags.append(text)

        add(raw_get('raw_fandom'))

        fandom_stubs = raw_get('fandom_stubs') or ()
        if isinstance(fandom_stubs, (list, tuple)):
            fandom_iter = cast(list[Any] | tuple[Any, ...], fandom_stubs)
            for item in fandom_iter:
                add(str(item).replace('-', ' '))

        for key in ('genres', 'characters', 'ships', 'relationships'):
            val = raw_get(key)
            if not val:
                continue
            if isinstance(val, (list, tuple)):
                values_iter = cast(list[Any] | tuple[Any, ...], val)
                for item in values_iter:
                    add(item)
            else:
                for part in _SPLIT_TAGS_RE.split(str(val)):
                    part = part.strip()
                    if part:
                        add(part)

        for key in ('category', 'fandom', 'rating', 'warning', 'freeform'):
            val = raw_get(key)
            if isinstance(val, (list, tuple)):
                values_iter = cast(list[Any] | tuple[Any, ...], val)
                for item in values_iter:
                    add(item)

        status = self.first_non_empty(payload.get('status'), raw_get('status'))
        if status:
            add('status:' + str(status).lower())

        return tags

    def format_ao3_stats(self, stats: dict[str, Any]) -> list[str]:
        """Format selected AO3 statistics as HTML paragraphs.

        Supported fields are kudos, comments, bookmarks, and hits.

        Args:
            stats (dict[str, Any]): Statistics mapping.

        Returns:
            list[str]: List of HTML fragment strings representing formatted stats.
        """
        lines: list[str] = []
        for field, label in (
            ('kudos', 'Kudos'),
            ('comments', 'Comments'),
            ('bookmarks', 'Bookmarks'),
            ('hits', 'Hits'),
        ):
            val = stats.get(field)
            if val is not None:
                lines.append(f'<p><b>{label}:</b> {prepare_string_for_xml(as_unicode(val))}</p>')
        return lines

    def parse_pubdate(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> datetime | None:
        """Parse a publication date from payload fields.

        The method first checks the top-level ``created`` field. If unavailable
        or invalid, it falls back to ``raw_meta['published']`` and supports
        Unix timestamps as numeric values or digit-only strings.

        Args:
            payload (dict[str, Any]): Top-level payload dictionary.
            raw_meta (dict[str, Any]): Nested raw metadata dictionary.

        Returns:
            datetime | None: Timezone-aware publication datetime if parsing
            succeeds; otherwise None.
        """
        created = payload.get('created')
        if created:
            try:
                return parse_date(created, assume_utc=True, default=utcnow().replace(day=15))
            except Exception:
                pass

        published = raw_meta.get('published')
        if published is None:
            return None

        try:
            if isinstance(published, str) and published.isdigit():
                published = int(published)
            if isinstance(published, (int, float)):
                return datetime.fromtimestamp(published, tz=UTC)
            return parse_date(str(published), assume_utc=True, default=utcnow().replace(day=15))
        except Exception:
            return None

    def is_html(self, text: Any) -> bool:
        """Determine whether a value appears to contain HTML markup.

        Args:
            text (Any): Value to test.

        Returns:
            bool: True if the value is a string containing simple HTML-like tags;
            otherwise False.
        """
        return isinstance(text, str) and bool(_HTML_RE.search(text))

    def extract_from_ao3_stats(self, raw_meta: dict[str, Any], field: str) -> Any | None:
        """Extract a field value from the nested AO3 stats mapping.

        Args:
            raw_meta (dict[str, Any]): Nested raw metadata dictionary.
            field (str): Stats field name to retrieve.

        Returns:
            Any | None: Value from ``raw_meta['stats'][field]`` if present and
            the stats object is a dictionary; otherwise None.
        """
        stats = raw_meta.get('stats')
        if isinstance(stats, dict):
            return cast(dict[str, Any], stats).get(field)
        return None


class HtmlCommentBuilder:
    """Build HTML comments content for a `Metadata` object.

    The generated HTML combines a description, core metadata fields,
    optional AO3 statistics, and extra metadata notes.
    """

    def __init__(self, helper: MetadataMapper) -> None:
        """Initialize the HTML comment builder.

        Args:
            helper (MetadataMapper): Metadata mapper helper used for shared
                formatting and extraction logic.

        Returns:
            None: This constructor initializes instance state only.
        """
        self.helper = helper

    def build(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> str:
        """Build an HTML comments string from payload data.

        Args:
            payload (dict[str, Any]): Top-level payload dictionary.
            raw_meta (dict[str, Any]): Nested raw metadata dictionary.

        Returns:
            str: HTML string containing description and formatted metadata
            details. Returns an empty string if no comment content is available.
        """
        helper = self.helper
        first_non_empty = helper.first_non_empty
        desc = first_non_empty(payload.get('description'), raw_meta.get('description'))

        if desc and not helper.is_html(desc):
            desc = f'<p>{prepare_string_for_xml(desc)}</p>'
        elif not desc:
            desc = ''

        lines: list[str] = []
        primary_meta = (
            ('Source URL', first_non_empty(payload.get('source'))),
            ('Status', first_non_empty(payload.get('status'), raw_meta.get('status'))),
            ('Chapters', first_non_empty(payload.get('chapters'), raw_meta.get('chapters'))),
            ('Words', first_non_empty(payload.get('words'), raw_meta.get('words'))),
            ('Updated', first_non_empty(payload.get('updated'), raw_meta.get('updated'))),
        )

        for label, val in primary_meta:
            if val is None:
                continue
            sval = str(val).strip()
            if sval:
                lines.append(
                    f'<p><b>{prepare_string_for_xml(label)}:</b> {prepare_string_for_xml(as_unicode(val))}</p>'
                )

        stats = raw_meta.get('stats')
        if isinstance(stats, dict):
            stats_lines = helper.format_ao3_stats(cast(dict[str, Any], stats))
            if stats_lines:
                lines.append('<hr/>')
                lines.extend(stats_lines)

        extra = first_non_empty(payload.get('extraMeta'))
        if extra:
            lines.append(f'<p><em>{prepare_string_for_xml(as_unicode(extra))}</em></p>')

        return desc + ''.join(lines)


class ServiceFactory:
    """Factory for constructing service objects used by this module."""

    @staticmethod
    def create_url_extractor(log: Any, preferred_keys: tuple[str, ...]) -> UrlExtractor:
        """Create a configured URL extractor.

        The extractor uses a preferred-key strategy first, followed by a
        generic scan strategy.

        Args:
            log (Any): Logger-like object for diagnostics.
            preferred_keys (tuple[str, ...]): Ordered identifier keys to check
                before scanning all values.

        Returns:
            UrlExtractor: Configured URL extractor instance.
        """
        normalizer = UrlNormalizer(log)
        return UrlExtractor(
            strategies=[PreferredKeyUrlStrategy(preferred_keys), GenericScanUrlStrategy()],
            normalizer=normalizer,
        )

    @staticmethod
    def create_metadata_transformer(log: Any) -> MetadataTransformer:
        """Create a configured metadata transformer.

        Args:
            log (Any): Logger-like object for diagnostics.

        Returns:
            MetadataTransformer: Metadata transformer backed by `MetadataMapper`.
        """
        return MetadataMapper(domain_info=DomainInfoService(log), log=log)
