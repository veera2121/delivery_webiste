const CACHE_NAME = "ruchigo-16";

const STATIC_FILES = [
  "/static/css/style.css",
  "/static/images/logo4.png"
];

self.addEventListener("install", event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_FILES))
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {

  // ✅ Cache only static files
  if (event.request.url.includes("/static/")) {
    event.respondWith(
      caches.match(event.request).then(res => res || fetch(event.request))
    );
  }

  // ❌ Never cache pages or APIs
});
