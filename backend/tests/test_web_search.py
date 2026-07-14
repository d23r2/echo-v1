"""app/web_search.py — SearXNG/Wikimedia/RSS/direct-page providers and the
gather_sources() router. No real network calls: httpx.get is monkeypatched
per test via tests/fake_http.py's fake httpx.Response objects.

Includes a regression test for a real bug found during live verification
(2026-07-14): Wikimedia's API rejects requests whose User-Agent doesn't look
like it has a URL in it (its robot policy), returning a 403 that must be
surfaced as a clean failure_reason, never an unhandled exception or a
fabricated result.
"""

from types import SimpleNamespace

import httpx
import pytest

from app import web_search
from app.search_intent import SearchIntent
from tests.fake_http import fake_response, make_fake_get


@pytest.fixture(autouse=True)
def _clear_caches():
    web_search.clear_search_caches()
    yield
    web_search.clear_search_caches()


def _settings(**overrides):
    base = dict(
        web_search_enabled=True,
        web_search_provider="searxng",
        searxng_base_url="http://localhost:8080",
        web_search_max_results=5,
        web_fetch_timeout_seconds=10,
        web_search_cache_minutes=10,
        wiki_search_enabled=True,
        wiki_provider="wikimedia",
        wiki_api_base_url="https://en.wikipedia.org/w/api.php",
        wiki_max_results=5,
        wiki_fetch_timeout_seconds=10,
        wiki_user_agent="EchoPersonalAI/1.0 (https://github.com/echo-project/echo; test) python-httpx",
        rss_search_enabled=True,
        rss_feed_urls="https://example.com/feed.xml",
        rss_max_items_per_feed=10,
        rss_fetch_timeout_seconds=10,
        rss_cache_minutes=10,
    )
    base.update(overrides)
    settings = SimpleNamespace(**base)
    settings.rss_feed_url_list = [u.strip() for u in settings.rss_feed_urls.split(",") if u.strip()]
    return settings


# ---- SearXNG ----


def test_searxng_search_returns_results_when_configured_and_reachable(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    resp = fake_response(
        "http://localhost:8080/search",
        json_data={"results": [{"title": "Result A", "url": "https://a.example/x", "content": "snippet a"}]},
    )
    monkeypatch.setattr(web_search.httpx, "get", make_fake_get({"localhost:8080": resp}))

    outcome = web_search.searxng_search("test query")
    assert outcome.failure_reason is None
    assert len(outcome.results) == 1
    assert outcome.results[0].source_type == "web_search"
    assert outcome.results[0].provider == "searxng"
    assert outcome.results[0].domain == "a.example"


def test_searxng_search_disabled_returns_clean_failure_reason(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings(web_search_enabled=False))
    outcome = web_search.searxng_search("test query")
    assert outcome.results == []
    assert "disabled" in outcome.failure_reason.lower()


def test_searxng_search_missing_base_url_returns_clean_failure_reason(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings(searxng_base_url=None))
    outcome = web_search.searxng_search("test query")
    assert outcome.results == []
    assert "not configured" in outcome.failure_reason.lower()


def test_searxng_search_timeout_returns_clean_failure_reason(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        web_search.httpx, "get", make_fake_get({}, raises={"localhost:8080": httpx.TimeoutException("timed out")})
    )
    outcome = web_search.searxng_search("test query")
    assert outcome.results == []
    assert "timed out" in outcome.failure_reason.lower()


def test_searxng_search_no_results_returns_failure_reason(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    resp = fake_response("http://localhost:8080/search", json_data={"results": []})
    monkeypatch.setattr(web_search.httpx, "get", make_fake_get({"localhost:8080": resp}))
    outcome = web_search.searxng_search("test query")
    assert outcome.results == []
    assert outcome.failure_reason == "No results found."


# ---- Wikimedia ----


def test_wiki_search_returns_results(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    resp = fake_response(
        "en.wikipedia.org/w/api.php",
        json_data={"query": {"search": [{"title": "Marie Curie", "snippet": "Polish-born <span>physicist</span>"}]}},
    )
    monkeypatch.setattr(web_search.httpx, "get", make_fake_get({"en.wikipedia.org": resp}))

    outcome = web_search.wiki_search("Marie Curie")
    assert outcome.failure_reason is None
    assert len(outcome.results) == 1
    result = outcome.results[0]
    assert result.source_type == "wiki"
    assert result.title == "Marie Curie"
    assert "<span>" not in result.snippet  # searchmatch markup stripped
    assert result.url == "https://en.wikipedia.org/wiki/Marie_Curie"


def test_wiki_search_disabled_returns_failure_reason(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings(wiki_search_enabled=False))
    outcome = web_search.wiki_search("Marie Curie")
    assert outcome.results == []
    assert outcome.failure_reason == "Wiki search is disabled."


def test_wiki_search_http_error_returns_clean_failure_reason_not_an_exception(monkeypatch):
    """Regression test: Wikimedia's real API 403s any request whose
    User-Agent doesn't contain a URL-shaped token (its bot policy) — this
    must surface as a clean failure_reason, never propagate as an unhandled
    exception that would 500 the chat endpoint."""
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    resp = fake_response("en.wikipedia.org/w/api.php", status_code=403, text="Please respect our robot policy")
    monkeypatch.setattr(web_search.httpx, "get", make_fake_get({"en.wikipedia.org": resp}))

    outcome = web_search.wiki_search("Marie Curie")
    assert outcome.results == []
    assert "failed" in outcome.failure_reason.lower()


def test_wiki_search_no_results_returns_failure_reason(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    resp = fake_response("en.wikipedia.org/w/api.php", json_data={"query": {"search": []}})
    monkeypatch.setattr(web_search.httpx, "get", make_fake_get({"en.wikipedia.org": resp}))
    outcome = web_search.wiki_search("asdkfjhaslkdjfh")
    assert outcome.results == []
    assert outcome.failure_reason == "No wiki results found."


def test_wiki_search_sends_configured_user_agent(monkeypatch):
    """WIKI_USER_AGENT (config.py's wiki_user_agent) must actually be sent as
    the request's User-Agent header — this is what makes Wikimedia's robot
    policy pass in the first place, not just a config value that's read and
    ignored."""
    custom_ua = "MyEchoInstance/1.0 (https://example.com; me@example.com)"
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings(wiki_user_agent=custom_ua))
    captured_headers = {}

    def _capturing_get(url, *args, **kwargs):
        captured_headers.update(kwargs.get("headers", {}))
        return fake_response(url, json_data={"query": {"search": []}})

    monkeypatch.setattr(web_search.httpx, "get", _capturing_get)
    web_search.wiki_search("anything")
    assert captured_headers.get("User-Agent") == custom_ua


# ---- RSS / Atom ----

_RSS2_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Example Feed</title>
<item>
  <title>Local team wins match</title>
  <link>https://example.com/article1</link>
  <description>A thrilling win for the local team.</description>
  <pubDate>Mon, 13 Jul 2026 10:00:00 GMT</pubDate>
</item>
</channel></rss>"""

_ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Example Atom Feed</title>
<entry>
  <title>Match update: local team wins</title>
  <link href="https://example.com/atom1"/>
  <summary>Summary of the win.</summary>
  <updated>2026-07-13T10:00:00Z</updated>
</entry>
</feed>"""


def test_rss_search_parses_rss2_feed(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    resp = fake_response("example.com/feed.xml", text=_RSS2_XML)
    monkeypatch.setattr(web_search.httpx, "get", make_fake_get({"example.com/feed.xml": resp}))

    outcome = web_search.rss_search("local team wins")
    assert outcome.failure_reason is None
    assert len(outcome.results) == 1
    result = outcome.results[0]
    assert result.source_type == "rss"
    assert result.feed_title == "Example Feed"
    assert result.title == "Local team wins match"


def test_rss_search_parses_atom_feed(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    resp = fake_response("example.com/feed.xml", text=_ATOM_XML)
    monkeypatch.setattr(web_search.httpx, "get", make_fake_get({"example.com/feed.xml": resp}))

    outcome = web_search.rss_search("match update")
    assert outcome.failure_reason is None
    assert len(outcome.results) == 1
    assert outcome.results[0].feed_title == "Example Atom Feed"
    assert outcome.results[0].title == "Match update: local team wins"


def test_rss_search_disabled_returns_failure_reason(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings(rss_search_enabled=False))
    outcome = web_search.rss_search("anything")
    assert outcome.results == []
    assert "disabled" in outcome.failure_reason.lower()


def test_rss_search_skips_failed_feed_and_uses_others(monkeypatch):
    monkeypatch.setattr(
        web_search,
        "get_settings",
        lambda: _settings(rss_feed_urls="https://bad.example/feed.xml,https://good.example/feed.xml"),
    )
    good_resp = fake_response("good.example/feed.xml", text=_RSS2_XML)
    monkeypatch.setattr(
        web_search.httpx,
        "get",
        make_fake_get(
            {"good.example/feed.xml": good_resp},
            raises={"bad.example/feed.xml": httpx.ConnectError("refused")},
        ),
    )
    outcome = web_search.rss_search("local team wins")
    assert outcome.failure_reason is None
    assert len(outcome.results) == 1


def test_rss_search_all_feeds_failing_returns_failure_reason(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        web_search.httpx, "get", make_fake_get({}, raises={"example.com/feed.xml": httpx.ConnectError("refused")})
    )
    outcome = web_search.rss_search("anything")
    assert outcome.results == []
    assert "failed to load" in outcome.failure_reason.lower()


# ---- Direct page fetch ----


def test_fetch_direct_page_extracts_title_and_text(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    html = "<html><head><title>Example Page</title></head><body><p>Hello world.</p></body></html>"
    resp = fake_response("example.com/page", text=html)
    monkeypatch.setattr(web_search.httpx, "get", make_fake_get({"example.com/page": resp}))

    result = web_search.fetch_direct_page("https://example.com/page")
    assert result is not None
    assert result.source_type == "direct_page"
    assert result.title == "Example Page"
    assert "Hello world." in result.snippet
    assert result.domain == "example.com"


def test_fetch_direct_page_returns_none_on_http_error(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        web_search.httpx, "get", make_fake_get({}, raises={"example.com": httpx.ConnectError("refused")})
    )
    result = web_search.fetch_direct_page("https://example.com/page")
    assert result is None


# ---- gather_sources() routing ----


def test_gather_sources_short_circuits_for_memory_lookup(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    intent = SearchIntent(False, "memory_lookup", 0.9, "test")
    result = web_search.gather_sources(intent, "do you remember what I said")
    assert result.sources == []
    assert result.search_query is None
    assert result.task_type == "memory_lookup"


def test_gather_sources_combines_wiki_and_current_when_also_needs_wiki(monkeypatch):
    monkeypatch.setattr(web_search, "get_settings", lambda: _settings())
    searxng_resp = fake_response(
        "localhost:8080/search",
        json_data={"results": [{"title": "Messi scores", "url": "https://a.example/x", "content": "..."}]},
    )
    wiki_resp = fake_response(
        "en.wikipedia.org/w/api.php", json_data={"query": {"search": [{"title": "Lionel Messi", "snippet": "..."}]}}
    )
    monkeypatch.setattr(
        web_search.httpx,
        "get",
        make_fake_get({"localhost:8080": searxng_resp, "en.wikipedia.org": wiki_resp}),
    )

    intent = SearchIntent(True, "web_search", 0.75, "test", also_needs_wiki=True)
    result = web_search.gather_sources(intent, "Who is Messi and did he score today?")
    assert result.web_search_used is True
    assert result.wiki_search_used is True
    source_types = {s.source_type for s in result.sources}
    assert source_types == {"web_search", "wiki"}
    assert result.task_type == "web_search"


def test_gather_sources_reports_failure_reason_when_nothing_configured(monkeypatch):
    monkeypatch.setattr(
        web_search,
        "get_settings",
        lambda: _settings(web_search_enabled=False, rss_search_enabled=False, wiki_search_enabled=False),
    )
    intent = SearchIntent(True, "web_search", 0.75, "test")
    result = web_search.gather_sources(intent, "what's the latest on this")
    assert result.sources == []
    assert result.search_failure_reason
    assert "no current-info source" in result.search_failure_reason.lower()
