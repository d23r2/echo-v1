// App-shell cache for the Echo frontend. Static assets only — API requests
// (/api/*) are never intercepted here, so chat/Atlas/etc. always hit the live
// backend instead of a stale cached response. This also lays groundwork for
// push notifications later (the SW registration + activation lifecycle),
// but no push logic lives here yet.

const CACHE_NAME = "echo-shell-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only ever cache same-origin GET requests.
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) {
    return;
  }

  // Never intercept API calls — always go to the network live.
  if (new URL(request.url).pathname.startsWith("/api/")) {
    return;
  }

  // Cache-first for the static app shell (JS/CSS/HTML/icons), with a
  // network fallback that refreshes the cache for next time.
  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(request);
      const networkFetch = fetch(request)
        .then((response) => {
          if (response.ok) cache.put(request, response.clone());
          return response;
        })
        .catch(() => cached);

      return cached || networkFetch;
    })
  );
});
