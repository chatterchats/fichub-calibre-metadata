import json

import pytest

from calibre_plugin.main import FicHub


class DummyBrowserResponse:
    def __init__(self, code=200, body=b'{}', headers=None):
        self.code = code
        self._body = body
        self.headers = headers or {}

    def read(self):
        return self._body


class DummyBrowser:
    def __init__(self, responses):
        # iterable or callable popping responses
        self._responses = iter(responses)

    def open_novisit(self, url, timeout=None):
        return next(self._responses)


@pytest.fixture
def plugin():
    return FicHub()


def test_extract_story_url_preferred(plugin):
    ids = {'url': 'https://example.com/1', 'uri': 'https://bad', 'foo': 'https://good'}
    assert plugin._extract_story_url(ids) == 'https://example.com/1'


def test_extract_story_url_generic(plugin):
    ids = {'bar': '   https://generic/ '}
    assert plugin._extract_story_url(ids) == 'https://generic/'


def test_extract_story_url_none(plugin):
    assert plugin._extract_story_url(None) is None
    assert plugin._extract_story_url({'nothing': 123}) is None


def test_normalize_url_candidate(plugin):
    assert plugin._normalize_url_candidate(' https://foo ') == 'https://foo'
    assert plugin._normalize_url_candidate('not a url') is None
    assert plugin._normalize_url_candidate(123) is None


def test_id_from_url(plugin):
    assert plugin.id_from_url('https://example.org') == ('fichub', 'https://example.org')
    assert plugin.id_from_url('foo') is None


def test_source_identifier_key(plugin):
    assert plugin._source_identifier_key('https://archiveofourown.org/works/1') == plugin.IDENTIFIER_AO3
    assert plugin._source_identifier_key('https://www.fanfiction.net/s/1/1') == plugin.IDENTIFIER_FFNET
    assert plugin._source_identifier_key('https://unknown.com') is None
    assert plugin._source_identifier_key(None) is None


def test_is_html(plugin):
    assert plugin._is_html('<p>hello</p>')
    assert not plugin._is_html('not html')
    assert not plugin._is_html(None)


def test_publisher_name(plugin):
    assert plugin._publisher_name('https://archiveofourown.org/works/1') == 'Archive of Our Own'
    # real implementation capitalises the site name
    assert plugin._publisher_name('https://www.fanfiction.net/s/1/1') == 'FanFiction.net'
    # unknown hosts currently return the raw domain
    assert plugin._publisher_name('https://foo.bar') == 'foo.bar'


def test_to_metadata_basic(plugin):
    payload = {
        'title': 'T',
        'rawExtendedMeta': {'language': 'EN', 'id': 123},
        'source': 'https://archiveofourown.org/works/1',
    }

    # provide a dummy logger with exception/error methods
    class DummyLog:
        def __call__(self, *a, **k):
            pass

        def exception(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

    log = DummyLog()
    mi = plugin._to_metadata(payload, 'https://archiveofourown.org/works/1', log=log)
    assert mi.title == 'T'
    assert mi.language == 'en'
    # payload id is in rawExtendedMeta so it becomes an ao3 identifier
    assert mi._identifiers.get('ao3') == '123'


def test_fetch_metadata_success(plugin):
    # simulate a successful JSON response
    body = json.dumps({'ret': 0, 'title': 'x'}).encode('utf-8')
    plugin.browser = DummyBrowser([DummyBrowserResponse(200, body)])
    payload, err = plugin._fetch_metadata(lambda *a, **k: None, 'https://foo', timeout=5)
    assert err is None
    assert payload['title'] == 'x'


def test_fetch_metadata_retry_and_rate_limit(plugin, monkeypatch):
    # avoid actual sleeps during retry loops
    monkeypatch.setattr('time.sleep', lambda s: None)

    # dummy logger that supports exception() and error()
    class DummyLog:
        def __call__(self, *a, **k):
            pass

        def exception(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

    log = DummyLog()

    # first simulate network error by raising
    class ErrorBrowser(DummyBrowser):
        def open_novisit(self, url, timeout=None):
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
    assert payload['title'] == 'y'
