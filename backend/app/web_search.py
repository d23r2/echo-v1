"""No-billing web/wiki/RSS search — see docs/searxng-setup.md and README's
web-search section for the full setup picture.

Every provider here is genuinely free and requires no API key or billing
account: SearXNG is meant to be self-hosted (or pointed at a public
instance), Wikimedia's search API is public with no key, RSS is just HTTP +
XML parsing. None of this calls a paid API. If a provider isn't
configured/reachable/returns nothing, it reports a clean SearchOutcome with
results=[] and a failure_reason — callers (app/persona.py) must use that to
say "I couldn't verify this" rather than ever guessing a current fact.

Direct page fetching (fetch_direct_page) exists as a standalone function but
is deliberately NOT auto-triggered by gather_sources() — actually opening
and fetching arbitrary URLs found in search results adds real latency and
failure surface for a v1 pass; SearXNG's own result snippets are the primary
signal for now. Wiring "fetch the top N result pages" is a reasonable
follow-up, not done here.
"""

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.search_intent import SearchIntent

# The User-Agent sent with every outbound request is configurable via
# WIKI_USER_AGENT (see config.py's wiki_user_agent) — Wikimedia's API
# enforces its robot policy (https://w.wiki/4wJS) by rejecting any
# User-Agent that doesn't look like ClientName/Version (URL; contact), so the
# default value is already policy-compliant. Also sent to SearXNG/RSS/
# direct-page requests for consistency, though only Wikimedia actually
# enforces this. Not a credential — just client identification.


@dataclass
class SourceResult:
    source_type: str  # web_search | wiki | rss | direct_page
    provider: str
    title: str | None = None
    url: str | None = None
    domain: str | None = None
    feed_title: str | None = None
    snippet: str | None = None
    retrieved_at: str | None = None
    published_at: str | None = None
    reliability_note: str | None = None


@dataclass
class SearchOutcome:
    results: list[SourceResult]
    query: str | None
    failure_reason: str | None = None


@dataclass
class GatherResult:
    sources: list[SourceResult] = field(default_factory=list)
    web_search_used: bool = False
    wiki_search_used: bool = False
    rss_search_used: bool = False
    direct_page_used: bool = False
    search_query: str | None = None
    search_failure_reason: str | None = None
    # The classified SearchIntent.task_type that produced this result — kept
    # here so every caller that persists search metadata has one object to
    # read from, including the memory_lookup/code_help/general_chat
    # short-circuit case below, where no provider was called but the
    # classification itself is still worth recording.
    task_type: str | None = None


# ---- tiny TTL cache, shared shape for SearXNG (per-query) and RSS (per-feed) ----

_TTLCacheEntry = tuple[float, list[SourceResult]]


def _cache_get(cache: dict[str, _TTLCacheEntry], key: str, ttl_minutes: int) -> list[SourceResult] | None:
    entry = cache.get(key)
    if entry is None:
        return None
    written_at, results = entry
    if time.time() - written_at > ttl_minutes * 60:
        del cache[key]
        return None
    return results


def _cache_set(cache: dict[str, _TTLCacheEntry], key: str, results: list[SourceResult]) -> None:
    cache[key] = (time.time(), results)


_searxng_cache: dict[str, _TTLCacheEntry] = {}
_rss_cache: dict[str, _TTLCacheEntry] = {}


def clear_search_caches() -> None:
    """Test-only escape hatch — production never needs to call this."""
    _searxng_cache.clear()
    _rss_cache.clear()


# ---- SearXNG ----


def searxng_search(query: str, max_results: int | None = None) -> SearchOutcome:
    settings = get_settings()
    if not settings.web_search_enabled or settings.web_search_provider != "searxng":
        return SearchOutcome(
            [], query, "Web search is disabled (set WEB_SEARCH_ENABLED=true and SEARXNG_BASE_URL to enable it)."
        )
    if not settings.searxng_base_url:
        return SearchOutcome([], query, "SEARXNG_BASE_URL is not configured.")

    max_results = max_results or settings.web_search_max_results
    cache_key = f"{query.strip().lower()}::{max_results}"
    cached = _cache_get(_searxng_cache, cache_key, settings.web_search_cache_minutes)
    if cached is not None:
        return SearchOutcome(cached, query, None if cached else "No results found.")

    try:
        resp = httpx.get(
            f"{settings.searxng_base_url.rstrip('/')}/search",
            params={"q": query, "format": "json"},
            timeout=settings.web_fetch_timeout_seconds,
            headers={"User-Agent": settings.wiki_user_agent},
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        return SearchOutcome([], query, "SearXNG request timed out.")
    except httpx.HTTPError as exc:
        return SearchOutcome([], query, f"SearXNG request failed ({type(exc).__name__}).")
    except ValueError:
        return SearchOutcome([], query, "SearXNG returned an unparseable response.")

    raw_results = data.get("results", [])[:max_results]
    now = datetime.now(UTC).isoformat()
    results = []
    for r in raw_results:
        url = r.get("url") or ""
        results.append(
            SourceResult(
                source_type="web_search",
                provider="searxng",
                title=r.get("title") or None,
                url=url or None,
                domain=(urlparse(url).netloc or None) if url else None,
                snippet=(r.get("content") or "")[:500] or None,
                retrieved_at=now,
                reliability_note="Web search result; verify with the source before treating as certain.",
            )
        )
    _cache_set(_searxng_cache, cache_key, results)
    if not results:
        return SearchOutcome([], query, "No results found.")
    return SearchOutcome(results, query, None)


# ---- Wikimedia / custom MediaWiki ----


def wiki_search(query: str, max_results: int | None = None) -> SearchOutcome:
    settings = get_settings()
    if not settings.wiki_search_enabled or settings.wiki_provider == "disabled":
        return SearchOutcome([], query, "Wiki search is disabled.")

    max_results = max_results or settings.wiki_max_results
    try:
        resp = httpx.get(
            settings.wiki_api_base_url,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": max_results,
            },
            timeout=settings.wiki_fetch_timeout_seconds,
            headers={"User-Agent": settings.wiki_user_agent},
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        return SearchOutcome([], query, "Wiki search request timed out.")
    except httpx.HTTPError as exc:
        return SearchOutcome([], query, f"Wiki search request failed ({type(exc).__name__}).")
    except ValueError:
        return SearchOutcome([], query, "Wiki search returned an unparseable response.")

    hits = data.get("query", {}).get("search", [])[:max_results]
    if not hits:
        return SearchOutcome([], query, "No wiki results found.")

    now = datetime.now(UTC).isoformat()
    provider_name = "wikimedia" if settings.wiki_provider == "wikimedia" else "custom_wiki"
    results = []
    for h in hits:
        title = h.get("title") or ""
        snippet = re.sub(r"<[^>]+>", "", h.get("snippet") or "")  # strip <span class="searchmatch">…
        # Article-URL construction only makes sense for the default
        # Wikipedia base URL — a custom MediaWiki endpoint's article path
        # convention can't be assumed, so url stays unset for those.
        url = (
            f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            if settings.wiki_provider == "wikimedia" and title
            else None
        )
        results.append(
            SourceResult(
                source_type="wiki",
                provider=provider_name,
                title=title or None,
                url=url,
                snippet=snippet or None,
                retrieved_at=now,
                reliability_note="Wiki source; good for background, not live updates.",
            )
        )
    return SearchOutcome(results, query, None)


# ---- RSS / Atom ----


def _parse_rss_or_atom(xml_text: str, feed_title_fallback: str) -> tuple[str, list[dict]]:
    root = ET.fromstring(xml_text)  # noqa: S314 — feed URLs are operator-configured, not user input

    channel = root.find("channel")
    if channel is not None:  # RSS 2.0
        feed_title = (channel.findtext("title") or feed_title_fallback).strip()
        items = [
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
                "pubDate": (item.findtext("pubDate") or "").strip(),
            }
            for item in channel.findall("item")
        ]
        return feed_title, items

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    if root.tag.endswith("feed"):  # Atom
        feed_title = (root.findtext("atom:title", namespaces=ns) or feed_title_fallback).strip()
        items = []
        for entry in root.findall("atom:entry", namespaces=ns):
            link_el = entry.find("atom:link", namespaces=ns)
            link = link_el.get("href", "") if link_el is not None else ""
            items.append(
                {
                    "title": (entry.findtext("atom:title", namespaces=ns) or "").strip(),
                    "link": link,
                    "description": (entry.findtext("atom:summary", namespaces=ns) or "").strip(),
                    "pubDate": (entry.findtext("atom:updated", namespaces=ns) or "").strip(),
                }
            )
        return feed_title, items

    return feed_title_fallback, []


def rss_search(query: str, max_results: int | None = None) -> SearchOutcome:
    settings = get_settings()
    if not settings.rss_search_enabled:
        return SearchOutcome(
            [], query, "RSS search is disabled (set RSS_SEARCH_ENABLED=true and RSS_FEED_URLS to enable it)."
        )
    feed_urls = settings.rss_feed_url_list
    if not feed_urls:
        return SearchOutcome([], query, "No RSS_FEED_URLS configured.")

    max_results = max_results or settings.web_search_max_results
    query_words = {w for w in re.findall(r"[a-z0-9']+", query.lower()) if len(w) > 2}

    now = datetime.now(UTC).isoformat()
    matches: list[SourceResult] = []
    any_feed_succeeded = False

    for feed_url in feed_urls:
        feed_items = _cache_get(_rss_cache, feed_url, settings.rss_cache_minutes)
        if feed_items is None:
            try:
                resp = httpx.get(feed_url, timeout=settings.rss_fetch_timeout_seconds, headers={"User-Agent": settings.wiki_user_agent})
                resp.raise_for_status()
                feed_title, raw_items = _parse_rss_or_atom(resp.text, feed_url)
            except (httpx.HTTPError, ET.ParseError):
                continue  # skip this one feed cleanly, still try the rest
            feed_items = [
                SourceResult(
                    source_type="rss",
                    provider="rss",
                    feed_title=feed_title,
                    title=it["title"] or None,
                    url=it["link"] or None,
                    published_at=it["pubDate"] or None,
                    snippet=it["description"][:400] or None,
                    retrieved_at=now,
                    reliability_note="RSS feed item.",
                )
                for it in raw_items[: settings.rss_max_items_per_feed]
            ]
            _cache_set(_rss_cache, feed_url, feed_items)
        any_feed_succeeded = True
        for item in feed_items:
            haystack = f"{item.title or ''} {item.snippet or ''}".lower()
            if not query_words or any(w in haystack for w in query_words):
                matches.append(item)

    if not any_feed_succeeded:
        return SearchOutcome([], query, "All configured RSS feeds failed to load.")
    if not matches:
        return SearchOutcome([], query, "No matching RSS items found.")
    return SearchOutcome(matches[:max_results], query, None)


# ---- Direct page fetch (standalone — not auto-wired into gather_sources) ----

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def fetch_direct_page(url: str) -> SourceResult | None:
    """Fetches one URL and extracts basic readable text — a minimal
    tag-stripping extractor, not a full readability parser. Returns None on
    any failure (timeout, non-2xx, connection error) rather than raising;
    callers should treat None as "skip this source", not an error to
    surface."""
    settings = get_settings()
    try:
        resp = httpx.get(
            url, timeout=settings.web_fetch_timeout_seconds, follow_redirects=True, headers={"User-Agent": settings.wiki_user_agent}
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return None

    html = resp.text
    title_match = _TITLE_RE.search(html)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else None

    body = _SCRIPT_STYLE_RE.sub(" ", html)
    text = re.sub(r"\s+", " ", _TAG_RE.sub(" ", body)).strip()[:1500]

    return SourceResult(
        source_type="direct_page",
        provider="direct_page",
        title=title,
        url=url,
        domain=urlparse(url).netloc or None,
        snippet=text or None,
        retrieved_at=datetime.now(UTC).isoformat(),
        reliability_note="Directly fetched page text; formatting/structure stripped.",
    )


# ---- Source routing ----

_CURRENT_TASK_TYPES = {"web_search", "sports_update", "news_lookup", "docs_lookup"}
_WIKI_TASK_TYPES = {"encyclopedia_lookup", "background_lookup", "definition_lookup", "historical_lookup"}


def gather_sources(intent: SearchIntent, query: str) -> GatherResult:
    """Given a classified SearchIntent, calls whichever providers make
    sense and returns everything found — possibly nothing, with a clean
    failure_reason set. Never raises, never fabricates a result that wasn't
    actually retrieved from a real provider call."""
    if intent.task_type in ("memory_lookup", "code_help", "general_chat"):
        return GatherResult(search_query=None, task_type=intent.task_type)

    settings = get_settings()
    sources: list[SourceResult] = []
    web_used = wiki_used = rss_used = False
    failure_reasons: list[str] = []

    wants_current = intent.task_type in _CURRENT_TASK_TYPES
    wants_wiki = intent.task_type in _WIKI_TASK_TYPES or intent.also_needs_wiki

    if wants_current:
        if settings.web_search_enabled:
            outcome = searxng_search(query)
            web_used = True
            if outcome.results:
                sources.extend(outcome.results)
            elif outcome.failure_reason:
                failure_reasons.append(outcome.failure_reason)
        # RSS as a candidate current-info source too, especially for
        # sports/news — tried regardless of whether web search already
        # found something, since a configured sports/news feed is often
        # more precise than a general web search for those task types.
        if settings.rss_search_enabled and intent.task_type in ("sports_update", "news_lookup"):
            rss_outcome = rss_search(query)
            rss_used = True
            if rss_outcome.results:
                sources.extend(rss_outcome.results)
            elif rss_outcome.failure_reason and not sources:
                failure_reasons.append(rss_outcome.failure_reason)
        if not settings.web_search_enabled and not (settings.rss_search_enabled and rss_used):
            failure_reasons.append(
                "No current-info source is configured (WEB_SEARCH_ENABLED/SEARXNG_BASE_URL or RSS_FEED_URLS)."
            )

    if wants_wiki:
        wiki_outcome = wiki_search(query)
        wiki_used = True
        if wiki_outcome.results:
            sources.extend(wiki_outcome.results)
        elif wiki_outcome.failure_reason and not sources:
            failure_reasons.append(wiki_outcome.failure_reason)

    failure_reason = "; ".join(dict.fromkeys(failure_reasons)) if not sources and failure_reasons else None
    return GatherResult(
        sources=sources,
        web_search_used=web_used,
        wiki_search_used=wiki_used,
        rss_search_used=rss_used,
        direct_page_used=False,
        search_query=query,
        search_failure_reason=failure_reason,
        task_type=intent.task_type,
    )
