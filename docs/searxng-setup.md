# No-billing search setup (SearXNG, Wikipedia, RSS)

Echo can ground answers in real search results without any paid API or billing account.
Three independent sources feed into this, all off-or-safe by default:

| Source | What it's for | Default | Needs |
|---|---|---|---|
| **SearXNG** | Current/live web search (news, prices, "did X happen") | off | a running SearXNG instance |
| **Wikipedia/Wikimedia** | Stable background/definitional/historical facts | **on** | nothing — public API |
| **RSS/Atom feeds** | News/sports headlines from feeds you choose | off | feed URLs |

Wiki search is enabled by default because Wikimedia's public search API needs no
configuration or key at all. SearXNG and RSS are off by default because they need you to
either run something (SearXNG) or pick sources (RSS feed URLs).

None of this ever requires an API key, a paid tier, or a billing account. If a source
isn't configured or isn't reachable, Echo says it couldn't verify the answer rather than
guessing — see `backend/app/persona.py`'s `SOURCE_USAGE_INSTRUCTION` and
`_search_unavailable_note`.

## Setting up local SearXNG

SearXNG is a self-hosted metasearch engine — it queries other search engines' public
results and returns them to you, with no tracking and no account. Running your own
instance (rather than pointing at someone else's public one) is the recommended setup:
public instances are frequently overloaded, rate-limited, or shut down without notice.

**One command, using the optional compose file in the repo root:**

```bash
docker compose -f docker-compose.searxng.yml up -d
```

This starts SearXNG on `http://localhost:8080` and persists its config in
`./searxng-config/` (created on first run). It's a separate file from the main
`docker-compose.yml` on purpose — running Echo doesn't require SearXNG, and running
SearXNG doesn't require Echo to be in Docker at all.

**Then in `backend/.env`:**

```bash
WEB_SEARCH_ENABLED=true
WEB_SEARCH_PROVIDER=searxng
SEARXNG_BASE_URL=http://localhost:8080
```

Restart the backend (`uvicorn` picks up `.env` at startup, not live) and you're done.

### Backend in Docker Compose

If the *backend* is also running inside `docker compose` (the main `docker-compose.yml`),
`http://localhost:8080` refers to the backend container itself, not the SearXNG
container, so it won't be reachable. Point at the SearXNG container by its Compose
service name instead:

```bash
SEARXNG_BASE_URL=http://searxng:8080
```

This only works if both compose files are run on the same Docker network — the simplest
way is to merge them into one `docker compose up` invocation:
`docker compose -f docker-compose.yml -f docker-compose.searxng.yml up --build`.

### Health check

Confirm SearXNG itself is up and returning JSON before troubleting Echo's side:

```bash
curl "http://localhost:8080/search?q=test&format=json"
```

A healthy instance returns a JSON body with a `results` array (possibly empty for an
obscure query, but present). If this fails, the problem is SearXNG's setup, not Echo's —
check `docker compose -f docker-compose.searxng.yml logs searxng`.

Some SearXNG images disable the JSON API by default for safety (JSON responses can be
used for scraping/abuse) — if the health check above returns an error about the `json`
format not being enabled, edit `searxng-config/settings.yml` and ensure
`search.formats` includes `json`, then restart the container.

## Wikipedia/Wikimedia (no setup needed)

On by default via the public `https://en.wikipedia.org/w/api.php` search endpoint — no
config required. To point at a different (e.g. self-hosted) MediaWiki instance:

```bash
WIKI_PROVIDER=custom
WIKI_API_BASE_URL=https://your-wiki.example/w/api.php
```

To turn wiki search off entirely: `WIKI_SEARCH_ENABLED=false`.

**`WIKI_USER_AGENT`** — sent as the HTTP `User-Agent` header on every Wiki/SearXNG/RSS/
direct-page request. Wikimedia's API specifically enforces its robot policy
(https://w.wiki/4wJS) and returns HTTP 403 for a User-Agent that doesn't look like
`ClientName/Version (URL; contact) extra` — a plain description with no URL-shaped token
gets rejected. A working default is already set (`config.py`'s `wiki_user_agent`), so you
don't need to set this yourself unless you want to identify your own instance
distinctly. This is a client-identification string, not a credential — nothing here is a
key or secret.

Wiki results are only ever used for stable background/definitional/historical framing —
Echo is instructed to never treat a wiki result as proof of a current/live fact (a score,
a price, today's news), even if the wiki article happens to mention something recent.
**Wikipedia is not a live/current-events source** — for "did X happen today" questions,
Echo needs SearXNG or RSS, not Wiki alone.

## RSS/Atom feeds

Off by default (no feeds configured). Point at whatever feeds you actually want Echo to
be able to cite for news/sports headlines — a comma-separated list:

```bash
RSS_SEARCH_ENABLED=true
RSS_FEED_URLS=https://feeds.bbci.co.uk/sport/rss.xml,https://example.com/news/feed.xml
```

Both RSS 2.0 and Atom feeds are supported. A feed that fails to fetch or parse is skipped
cleanly — the rest of the configured feeds are still tried, and Echo only reports a
failure if *every* configured feed failed.

## Troubleshooting

- **Public SearXNG instances are unreliable.** They get rate-limited, blocked by upstream
  engines, or shut down with no notice. Prefer a local instance for anything you depend
  on regularly.
- **Some search engines behind SearXNG bot-block aggressively.** A query might return
  fewer results than expected, or none, if the underlying engines are rate-limiting the
  SearXNG instance's IP. This isn't an Echo bug — check SearXNG's own logs.
- **Wikimedia enforces a robot policy on its User-Agent header** (returns HTTP 403 for
  requests that don't identify themselves properly) — Echo's requests already comply with
  this out of the box (`WIKI_USER_AGENT`, see above), but if you're testing the Wikimedia
  API directly with `curl`, add a descriptive `User-Agent` header or you'll see the same
  403.
- **Results are cached briefly** (`WEB_SEARCH_CACHE_MINUTES` / `RSS_CACHE_MINUTES`,
  10 minutes by default) to avoid hammering SearXNG or a feed on repeated near-identical
  questions in the same conversation. Lower this if you need fresher results for testing;
  raise it if you're worried about rate limits.
- **Don't hammer a public SearXNG instance or small news feeds** — if you're testing
  repeatedly, use a local SearXNG instance (see above) rather than a shared public one.

## Privacy notes

- **Ollama itself stays fully local** — no query, answer, or Atlas memory is sent
  anywhere when you're chatting with Ollama and search is off. That changes the moment
  Wiki/SearXNG/RSS actually runs a lookup: the *search query* (not your full
  conversation) leaves your machine to reach whichever endpoint is configured —
  Wikipedia's public API, your SearXNG instance (or a public one if you pointed at one
  instead of self-hosting), or the RSS feed's host. Self-hosting SearXNG keeps that hop
  under your own control instead of a third party's.
- SearXNG itself doesn't log or track queries by design; running your own instance means
  the *only* party that sees your search queries is whichever upstream engines SearXNG
  forwards them to (same as using any search engine directly, minus the profiling).
- No search query, result, or fetched page is ever sent to a third-party AI provider as
  part of billing/telemetry — it's injected directly into the same local prompt that goes
  to whichever model you've selected (Ollama, or a cloud provider if you've configured
  one), exactly like any other part of the conversation.
- Direct-page fetches (`app/web_search.py`'s `fetch_direct_page`) only happen when
  explicitly wired to a caller — nothing in the current build auto-fetches arbitrary URLs
  found in search results.

## A note on what Echo can and can't know

- **Ollama (or any model) alone cannot know anything current** — its training data has a
  cutoff, and it has no live connection to the internet on its own. Without a search
  source configured and reachable, Echo says so honestly rather than guessing at a score,
  price, or headline.
- **Wikipedia is background, not a live feed.** An article can be edited recently and
  still not reflect literally today's events — Echo is instructed to never cite Wiki as
  proof of something current, even if it's the only source that returned anything.

## Worked example

With `WEB_SEARCH_ENABLED=true` and a local SearXNG instance running:

> **You:** Did Liverpool win their match today?
>
> **Echo:** *(searches, finds a recent SearXNG result)* According to a search just now,
> Liverpool beat [opponent] 2-1 earlier today... *(cites the source naturally — never
> "Source: Web search — SearXNG", just plain language)*
>
> **via Ollama, SearXNG**

Without SearXNG configured, the same question gets an honest answer instead of a guess:

> **Echo:** I don't have a way to verify today's match results right now — web search
> isn't configured, so I can't check. You'd need to check a live sports source directly.
>
> **via Ollama**
