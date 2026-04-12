# pyright: reportPrivateUsage=false
import json
from collections.abc import Iterable, Iterator
from typing import Any, NoReturn, cast

import pytest

from calibre_plugin.main import FicHub


class DummyBrowserResponse:
    def __init__(self, code: int = 200, body: bytes = b'{}', headers: dict[str, str] | None = None) -> None:
        self.code: int = code
        self._body: bytes = body
        self.headers: dict[str, str] = headers or {}

    def read(self) -> bytes:
        return self._body


class DummyBrowser:
    def __init__(self, responses: Iterable[DummyBrowserResponse]) -> None:
        # iterable or callable popping responses
        self._responses: Iterator[DummyBrowserResponse] = iter(responses)

    def open_novisit(self, url: str, timeout: int | float | None = None) -> DummyBrowserResponse:
        del url, timeout
        return next(self._responses)


class DummyAbort:
    def __init__(self, is_set_result: bool = False) -> None:
        self._is_set_result = is_set_result

    def is_set(self) -> bool:
        return self._is_set_result


@pytest.fixture
def plugin() -> FicHub:
    return FicHub()


def test_extract_story_url_preferred(plugin: FicHub) -> None:
    ids: dict[str, str] = {'url': 'https://example.com/1', 'uri': 'https://bad', 'foo': 'https://good'}
    assert plugin._extract_story_url(ids) == 'https://example.com/1'


def test_extract_story_url_generic(plugin: FicHub) -> None:
    ids: dict[str, str] = {'bar': '   https://generic/ '}
    assert plugin._extract_story_url(ids) == 'https://generic/'


def test_extract_story_url_none(plugin: FicHub) -> None:
    assert plugin._extract_story_url(None) is None
    assert plugin._extract_story_url({'nothing': 123}) is None


def test_normalize_url_candidate(plugin: FicHub) -> None:
    assert plugin._normalize_url_candidate(' https://foo ') == 'https://foo'
    assert plugin._normalize_url_candidate('not a url') is None
    assert plugin._normalize_url_candidate(cast(Any, 123)) is None


def test_source_identifier_key(plugin: FicHub) -> None:
    assert plugin._source_identifier_key('https://archiveofourown.org/works/1') == plugin.IDENTIFIER_AO3
    assert plugin._source_identifier_key('https://www.fanfiction.net/s/1/1') == plugin.IDENTIFIER_FFNET
    assert plugin._source_identifier_key('https://fanfiction.net.example/s/1/1') is None
    assert plugin._source_identifier_key('https://unknown.com') is None
    assert plugin._source_identifier_key(None) is None


def test_is_html(plugin: FicHub) -> None:
    assert plugin._is_html('<p>hello</p>')
    assert not plugin._is_html('not html')
    assert not plugin._is_html(None)


def test_publisher_name(plugin: FicHub) -> None:
    assert plugin._publisher_name('https://archiveofourown.org/works/1') == 'Archive of Our Own'
    # real implementation capitalises the site name
    assert plugin._publisher_name('https://www.fanfiction.net/s/1/1') == 'FanFiction.net'
    # unknown hosts currently return the raw domain
    assert plugin._publisher_name('https://foo.bar') == 'foo.bar'


def test_to_metadata_basic(plugin: FicHub) -> None:
    payload: dict[str, Any] = {
        'title': 'T',
        'rawExtendedMeta': {'language': 'EN', 'id': 123},
        'source': 'https://archiveofourown.org/works/1',
    }

    # provide a dummy logger with exception/error methods
    class DummyLog:
        def __call__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def exception(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def error(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

    log = DummyLog()
    mi = plugin._to_metadata(payload, 'https://archiveofourown.org/works/1', log=log)
    assert mi is not None
    assert mi.title == 'T'
    assert mi.language == 'en'
    assert mi.languages == ['en']
    # payload id is in rawExtendedMeta so it becomes an ao3 identifier
    assert mi._identifiers.get('ao3') == '123'


def test_to_metadata_non_dict_raw_meta(plugin: FicHub) -> None:
    payload: dict[str, Any] = {
        'title': 'T',
        'rawExtendedMeta': ['unexpected'],
        'source': 'https://archiveofourown.org/works/1',
    }
    mi = plugin._to_metadata(payload, 'https://archiveofourown.org/works/1', log=None)
    assert mi is not None
    assert mi.title == 'T'
    assert mi._identifiers == {}


def test_fetch_metadata_success(plugin: FicHub) -> None:
    # simulate a successful JSON response
    body = json.dumps({'ret': 0, 'title': 'x'}).encode('utf-8')
    plugin.browser = DummyBrowser([DummyBrowserResponse(200, body)])
    payload, err = plugin._fetch_metadata(lambda *args, **kwargs: None, 'https://foo', timeout=5)
    assert err is None
    assert payload is not None
    assert payload['title'] == 'x'


def test_fetch_metadata_retry_and_rate_limit(plugin: FicHub, monkeypatch: pytest.MonkeyPatch) -> None:
    # avoid actual sleeps during retry loops
    monkeypatch.setattr('time.sleep', lambda seconds: None)

    # dummy logger that supports exception() and error()
    class DummyLog:
        def __call__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def exception(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def error(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

    log = DummyLog()

    # first simulate network error by raising
    class ErrorBrowser(DummyBrowser):
        def open_novisit(self, url: str, timeout: int | float | None = None) -> NoReturn:
            del url, timeout
            raise Exception('network fail')

    plugin.browser = ErrorBrowser([])
    payload, err = plugin._fetch_metadata(log, 'https://foo', timeout=1)
    assert payload is None
    assert err is not None

    # now 429 handling
    resp1 = DummyBrowserResponse(code=429, body=json.dumps({'ret': 0}).encode('utf-8'), headers={'Retry-After': '1'})
    resp2 = DummyBrowserResponse(200, json.dumps({'ret': 0, 'title': 'y'}).encode('utf-8'))
    plugin.browser = DummyBrowser([resp1, resp2])
    payload, err = plugin._fetch_metadata(log, 'https://foo', timeout=1)
    assert err is None
    assert payload is not None
    assert payload['title'] == 'y'


def test_fetch_metadata_retries_server_errors(plugin: FicHub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('time.sleep', lambda seconds: None)
    plugin.browser = DummyBrowser(
        [
            DummyBrowserResponse(500, json.dumps({'ret': 0}).encode('utf-8')),
            DummyBrowserResponse(200, json.dumps({'ret': 0, 'title': 'z'}).encode('utf-8')),
        ]
    )
    payload, err = plugin._fetch_metadata(lambda *args, **kwargs: None, 'https://foo', timeout=1)
    assert err is None
    assert payload is not None
    assert payload['title'] == 'z'


def test_fetch_metadata_stops_when_aborted(plugin: FicHub, monkeypatch: pytest.MonkeyPatch) -> None:
    abort = DummyAbort(is_set_result=True)

    def fail_sleep(seconds: float) -> None:
        raise AssertionError(f'should not sleep when aborted, got {seconds}')

    monkeypatch.setattr('time.sleep', fail_sleep)

    plugin.browser = DummyBrowser([DummyBrowserResponse(500, json.dumps({'ret': 0}).encode('utf-8'))])
    payload, err = plugin._fetch_metadata(lambda *args, **kwargs: None, 'https://foo', timeout=1, abort=abort)
    assert payload is None
    assert err == 'Request aborted'
