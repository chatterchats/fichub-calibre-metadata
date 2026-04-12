#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
"""calibre entry point for the FicHub metadata plugin."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source
from polyglot.urllib import urlencode

from .http import ApiConfig, ExponentialBackoffRetryPolicy, FicHubApiOperation
from .metadata import (
    DomainInfoService,
    MetadataMapper,
    ServiceFactory,
)

__license__ = 'GPL v3'
__copyright__ = '2026, Chats + contributors'
__docformat__ = 'restructuredtext en'


class FicHub(Source):  # type: ignore[misc]
    """calibre metadata source plugin for FicHub.

    This class integrates with calibre's metadata source framework to identify
    books by URL-like identifiers and fetch metadata from the FicHub API.

    Attributes:
        name (str): Human-readable plugin name shown by calibre.
        version (tuple[int, int, int]): Plugin version number.
        minimum_calibre_version (tuple[int, int, int]): Minimum supported
            calibre version.
        description (str): Short description of the plugin.
        capabilities (frozenset[str]): Supported calibre source capabilities.
        touched_fields (frozenset[str]): Metadata fields that may be populated
            or updated by this plugin.
        supports_gzip_transfer_encoding (bool): Whether gzip-compressed HTTP
            responses are supported.
        has_html_comments (bool): Whether generated comments may contain HTML.
        IDENTIFIER_FICHUB_ID (str): Identifier key for FicHub IDs.
        IDENTIFIER_AO3 (str): Identifier key for Archive of Our Own IDs.
        IDENTIFIER_FFNET (str): Identifier key for FanFiction.net IDs.
        API_META (str): FicHub metadata API endpoint.
        PREFERRED_IDENTIFIER_KEYS (tuple[str, ...]): Identifier keys preferred
            when extracting a story URL.
        MAX_RETRIES (int): Maximum number of HTTP retry attempts.
        INITIAL_BACKOFF (int): Initial retry backoff interval in seconds.
        MAX_RETRY_AFTER (int): Maximum allowed retry-after interval in seconds.
    """

    name: str = 'FicHub'
    author: str = 'Chatterchats'
    version: tuple[int, int, int] = (0, 1, 2)
    minimum_calibre_version: tuple[int, int, int] = (2, 80, 0)
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

    IDENTIFIER_FICHUB_ID: str = 'fichub_id'
    IDENTIFIER_AO3: str = 'ao3'
    IDENTIFIER_FFNET: str = 'ffnet'

    API_META: str = 'https://fichub.net/api/v0/meta'
    PREFERRED_IDENTIFIER_KEYS: tuple[str, ...] = ('url', 'uri', 'fichub')
    MAX_RETRIES: int = 5
    INITIAL_BACKOFF: int = 60
    MAX_RETRY_AFTER: int = 300
    AO3_URL_RE: re.Pattern[str] = re.compile(r'^https?://(?:www\.)?archiveofourown\.org/works/(\d+)(?:[/?#].*)?$', re.I)
    FFNET_URL_RE: re.Pattern[str] = re.compile(
        r'^https?://(?:www\.)?fanfiction\.net/s/(\d+)(?:/\d+)?(?:[/?#].*)?$',
        re.I,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the FicHub metadata source plugin.

        This constructor initializes the base calibre :class:`Source` class,
        configures API access settings, and creates helper service instances
        used for URL extraction, domain analysis, and metadata mapping.

        Args:
            *args (Any): Positional arguments forwarded to the parent
                :class:`Source` constructor.
            **kwargs (Any): Keyword arguments forwarded to the parent
                :class:`Source` constructor.

        Returns:
            None: This method initializes the instance in place.
        """
        super().__init__(*args, **kwargs)

        self.log: Any = None
        self.timeout: int = 60

        self.config = ApiConfig(
            meta_endpoint=self.API_META,
            max_retries=self.MAX_RETRIES,
            initial_backoff=self.INITIAL_BACKOFF,
            max_retry_after=self.MAX_RETRY_AFTER,
        )

        self._url_extractor = ServiceFactory.create_url_extractor(None, self.PREFERRED_IDENTIFIER_KEYS)
        self._domain_info = DomainInfoService(None)
        self._metadata_mapper = MetadataMapper(domain_info=self._domain_info, log=None)

    def get_book_url(self, identifiers: dict[str, Any] | None) -> tuple[str, str, str] | None:
        """Extract a canonical book URL tuple from identifiers.

        This method attempts to locate a story URL in the provided identifier
        mapping. If successful, it returns a calibre-compatible URL tuple.

        Args:
            identifiers (dict[str, Any] | None): Mapping of identifier names to
                identifier values. May be ``None``.

        Returns:
            tuple[str, str, str] | None: A tuple in the form
            ``("url", story_url, story_url)`` when a URL is found; otherwise
            ``None``.
        """
        identifiers = identifiers or {}

        ao3_id = identifiers.get(self.IDENTIFIER_AO3)
        if ao3_id:
            ao3_id_str = str(ao3_id).strip()
            if ao3_id_str:
                return self.IDENTIFIER_AO3, ao3_id_str, f'https://archiveofourown.org/works/{ao3_id_str}'

        ffnet_id = identifiers.get(self.IDENTIFIER_FFNET)
        if ffnet_id:
            ffnet_id_str = str(ffnet_id).strip()
            if ffnet_id_str:
                return self.IDENTIFIER_FFNET, ffnet_id_str, f'https://www.fanfiction.net/s/{ffnet_id_str}/1'

        story_url = self._extract_story_url(identifiers)
        if story_url:
            parsed = self.id_from_url(story_url)
            if parsed is not None:
                id_type, id_value = parsed
                return id_type, id_value, story_url
            return 'url', story_url, story_url
        return None

    def get_book_url_name(self, idtype: str, idval: str, url: str) -> str:
        """Return a human-readable label for a book URL."""
        del idval, url
        if idtype == self.IDENTIFIER_AO3:
            return 'Archive of Our Own'
        if idtype == self.IDENTIFIER_FFNET:
            return 'FanFiction.net'
        return 'Story page'

    def id_from_url(self, url: str) -> tuple[str, str] | None:
        """Parse a supported source URL into a source identifier tuple."""
        ao3_match = self.AO3_URL_RE.match(url)
        if ao3_match:
            return self.IDENTIFIER_AO3, ao3_match.group(1)

        ffnet_match = self.FFNET_URL_RE.match(url)
        if ffnet_match:
            return self.IDENTIFIER_FFNET, ffnet_match.group(1)

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
    ) -> str | None:
        """Identify a story and enqueue its metadata result.

        This is the main calibre entry point for metadata lookup. The method
        extracts a story URL from identifiers, requests metadata from the
        FicHub API, transforms the response into a calibre
        :class:`Metadata` object, and places the result into the provided
        queue.

        Args:
            log (Any): Logger-like object used for diagnostic output.
            result_queue (Any): Queue-like object that receives the resulting
                :class:`Metadata` instance.
            abort (Any): Abort flag object expected to provide an ``is_set()``
                method.
            title (str | None): Optional title value supplied by calibre.
                Present for interface compatibility.
            authors (list[str] | None): Optional author list supplied by
                calibre. Present for interface compatibility.
            identifiers (dict[str, Any] | None): Mapping of identifiers used to
                locate the story URL.
            timeout (int): Request timeout in seconds.

        Returns:
            str | None: ``None`` on success, otherwise a user-displayable error
            string.
        """
        self.log = log
        self.timeout = timeout

        self._url_extractor.normalizer.log = log
        self._domain_info.log = log
        self._metadata_mapper.log = log

        if abort.is_set():
            return None

        identifiers = (identifiers or {}).copy()

        story_url = self._extract_story_url(identifiers)
        if not story_url:
            err = 'No supported story URL found in identifiers'
            if log and hasattr(log, 'error'):
                log.error('FicHub: %s', err)
            return err

        payload, err = self._fetch_metadata(log, story_url, timeout, abort)

        if err:
            if log and hasattr(log, 'error'):
                log.error('FicHub: metadata fetch failed: %s', err)
            return err

        if abort.is_set():
            return None

        if not isinstance(payload, dict):
            err = 'FicHub returned an unexpected response payload'
            if log and hasattr(log, 'error'):
                log.error('FicHub: %s', err)
            return err

        mi = self._to_metadata(payload, story_url, log)
        if mi is None:
            return 'FicHub returned incomplete metadata for this story'

        if abort.is_set():
            return None

        self.clean_downloaded_metadata(mi)
        mi.source_relevance = 0
        result_queue.put(mi)
        return None

    def _extract_story_url(self, identifiers: dict[str, Any] | None) -> str | None:
        """Extract a story URL from a set of identifiers.

        This method delegates URL extraction to the configured URL extractor
        service.

        Args:
            identifiers (dict[str, Any] | None): Mapping of identifier names to
                values. May be ``None``.

        Returns:
            str | None: The extracted story URL if one can be determined;
            otherwise ``None``.
        """
        return self._url_extractor.extract(identifiers)

    def _normalize_url_candidate(self, val: str) -> str | None:
        """Normalize a potential story URL.

        This method applies the configured URL normalizer to an input string to
        produce a canonical URL form when possible.

        Args:
            val (str): Candidate URL string to normalize.

        Returns:
            str | None: The normalized URL if the input is recognized as valid;
            otherwise ``None``.
        """
        self._url_extractor.normalizer.log = self.log
        return self._url_extractor.normalizer.normalize(val)

    def _fetch_metadata(
        self, log: Any, story_url: str, timeout: int | float, abort: Any = None
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Fetch metadata for a story URL from the FicHub API.

        This method builds the API request URL, configures an exponential
        backoff retry policy, performs the HTTP operation, and returns either
        the decoded payload or an error message.

        Args:
            log (Any): Logger-like object used for diagnostic output.
            story_url (str): Canonical story URL to query.
            timeout (int | float): Request timeout in seconds.
            abort (Any): Optional abort flag object expected to provide an
                ``is_set()`` method.

        Returns:
            tuple[dict[str, Any] | None, str | None]: A two-item tuple
            ``(payload, error_message)`` where ``payload`` is the API response
            dictionary on success and ``error_message`` is a descriptive error
            string on failure. One element is typically ``None``.
        """
        endpoint = f'{self.config.meta_endpoint}?{urlencode({"q": story_url})}'
        policy = ExponentialBackoffRetryPolicy(
            max_retries=self.config.max_retries,
            initial_backoff=self.config.initial_backoff,
            max_retry_after=self.config.max_retry_after,
        )
        operation = FicHubApiOperation(self.browser, endpoint, timeout, self.config.max_retry_after)
        return policy.execute(operation, log, abort=abort)

    def _to_metadata(self, payload: dict[str, Any], submitted_url: str, log: Any) -> Metadata | None:
        """Convert an API payload into a calibre Metadata object.

        This method delegates transformation of raw FicHub API data into a
        fully populated calibre :class:`Metadata` instance.

        Args:
            payload (dict[str, Any]): Raw metadata payload returned by the
                FicHub API.
            submitted_url (str): Story URL originally submitted for lookup.
            log (Any): Logger-like object used for diagnostic output.

        Returns:
            Metadata | None: A populated calibre metadata object on success;
            otherwise ``None``.
        """
        self._metadata_mapper.log = log
        self._domain_info.log = log
        return self._metadata_mapper.transform(payload, submitted_url, log)

    def _extract_series(
        self, payload: dict[str, Any], raw_meta: dict[str, Any]
    ) -> tuple[str | None, float | None, list[str]]:
        """Extract series information from metadata.

        This method delegates extraction of series name, series index, and
        supplemental series-related tags or markers from the payload.

        Args:
            payload (dict[str, Any]): Top-level API payload.
            raw_meta (dict[str, Any]): Raw nested metadata structure extracted
                from the payload.

        Returns:
            tuple[str | None, float | None, list[str]]: A tuple containing the
            series name, series index, and a list of related tag strings.
        """
        self._metadata_mapper.log = self.log
        self._domain_info.log = self.log
        return self._metadata_mapper.extract_series(payload, raw_meta)

    def _collect_tags(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> list[str]:
        """Collect metadata tags from the payload.

        This method delegates extraction and normalization of tag values from
        the API response.

        Args:
            payload (dict[str, Any]): Top-level API payload.
            raw_meta (dict[str, Any]): Raw nested metadata structure extracted
                from the payload.

        Returns:
            list[str]: A list of tag strings derived from the metadata.
        """
        self._metadata_mapper.log = self.log
        self._domain_info.log = self.log
        return self._metadata_mapper.collect_tags(payload, raw_meta)

    def _build_comments(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> str:
        """Build the comments field for calibre metadata.

        This method delegates generation of the comments or description text,
        which may contain HTML when supported by calibre.

        Args:
            payload (dict[str, Any]): Top-level API payload.
            raw_meta (dict[str, Any]): Raw nested metadata structure extracted
                from the payload.

        Returns:
            str: The rendered comments text for the metadata record.
        """
        self._metadata_mapper.log = self.log
        self._domain_info.log = self.log
        return self._metadata_mapper.comment_builder.build(payload, raw_meta)

    def _format_ao3_stats(self, stats: dict[str, Any]) -> list[str]:
        """Format AO3 statistics into displayable text fragments.

        This method delegates formatting of AO3-specific statistical fields,
        such as counts or other summary metrics.

        Args:
            stats (dict[str, Any]): Dictionary containing AO3 statistics.

        Returns:
            list[str]: A list of formatted strings representing the statistics.
        """
        self._metadata_mapper.log = self.log
        return self._metadata_mapper.format_ao3_stats(stats)

    def _parse_pubdate(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> datetime | None:
        """Parse the publication date from metadata.

        This method delegates extraction and conversion of publication date
        information into a :class:`datetime` object.

        Args:
            payload (dict[str, Any]): Top-level API payload.
            raw_meta (dict[str, Any]): Raw nested metadata structure extracted
                from the payload.

        Returns:
            datetime | None: Parsed publication datetime if available and valid;
            otherwise ``None``.
        """
        self._metadata_mapper.log = self.log
        return self._metadata_mapper.parse_pubdate(payload, raw_meta)

    def _source_identifier_key(self, canonical_url: str | None) -> str | None:
        """Determine the source-specific identifier key for a URL.

        This method uses domain information derived from a canonical URL to
        choose the appropriate source identifier key.

        Args:
            canonical_url (str | None): Canonical story URL, or ``None``.

        Returns:
            str | None: The source identifier key associated with the URL, or
            ``None`` if no mapping is available.
        """
        self._domain_info.log = self.log
        return self._domain_info.source_identifier_key(canonical_url)

    def _is_html(self, text: Any) -> bool:
        """Check whether a value appears to contain HTML content.

        This method delegates HTML detection logic to the metadata mapper.

        Args:
            text (Any): Value to inspect for HTML-like markup.

        Returns:
            bool: ``True`` if the value appears to contain HTML content;
            otherwise ``False``.
        """
        return self._metadata_mapper.is_html(text)

    def _publisher_name(self, canonical_url: str | None) -> str | None:
        """Resolve a publisher name from a canonical URL.

        This method maps the source domain of a canonical URL to a human-readable
        publisher or site name.

        Args:
            canonical_url (str | None): Canonical story URL, or ``None``.

        Returns:
            str | None: The resolved publisher name if available; otherwise
            ``None``.
        """
        self._domain_info.log = self.log
        return self._domain_info.publisher_name(canonical_url)

    def _extract_authors(self, payload: dict[str, Any], raw_meta: dict[str, Any]) -> list[str]:
        """Extract author names from metadata.

        This method delegates author extraction and normalization to the
        metadata mapper.

        Args:
            payload (dict[str, Any]): Top-level API payload.
            raw_meta (dict[str, Any]): Raw nested metadata structure extracted
                from the payload.

        Returns:
            list[str]: A list of author names.
        """
        self._metadata_mapper.log = self.log
        return self._metadata_mapper.extract_authors(payload, raw_meta)

    def _first_non_empty(self, *vals: Any) -> Any | None:
        """Return the first non-empty value from the provided arguments.

        This method delegates selection logic that finds the first value
        considered non-empty by the metadata mapper.

        Args:
            *vals (Any): Values to evaluate in order.

        Returns:
            Any | None: The first non-empty value, or ``None`` if all values are
            empty.
        """
        self._metadata_mapper.log = self.log
        return self._metadata_mapper.first_non_empty(*vals)

    def _extract_from_ao3_stats(self, raw_meta: dict[str, Any], field: str) -> Any | None:
        """Extract a specific field from AO3 statistics metadata.

        This method delegates retrieval of a named field from AO3 statistics
        embedded within the raw metadata structure.

        Args:
            raw_meta (dict[str, Any]): Raw nested metadata structure extracted
                from the payload.
            field (str): Name of the AO3 statistics field to retrieve.

        Returns:
            Any | None: The extracted field value if present; otherwise
            ``None``.
        """
        return self._metadata_mapper.extract_from_ao3_stats(raw_meta, field)
