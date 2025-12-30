const CACHE_NAME = "ruchigo-v2";

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll([
        "/static/css/style.css"
      ]);
    })
  );
});
self.addEventListener("fetch", event => {

  // ✅ VERY IMPORTANT: allow Flask routes
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request));
    return;
  }

  // ✅ Cache only static assets
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});

