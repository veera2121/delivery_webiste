// =========================================
// RucHiGo Production Service Worker
// Version: 1.0.0
// =========================================

importScripts("/static/js/version.js");

// =============================
// RucHiGo Service Worker
// =============================

const STATIC_FILES = [
    "/",
    "/manifest.json",

    "/static/css/style.css",

    "/static/images/logo4.png"
];
// ===============================
// INSTALL
// ===============================

self.addEventListener("install", event => {

    self.skipWaiting();

    event.waitUntil(

        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(STATIC_CACHE))

    );

});

// ===============================
// ACTIVATE
// ===============================

self.addEventListener("activate", event => {

    event.waitUntil(

        caches.keys().then(keys =>

            Promise.all(

                keys.map(key => {

                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }

                })

            )

        )

    );

    self.clients.claim();

});

// ===============================
// FETCH
// ===============================

self.addEventListener("fetch", event => {

    if (event.request.method !== "GET") return;

    const url = new URL(event.request.url);

    // Never cache APIs
    if (
        url.pathname.startsWith("/api") ||
        url.pathname.startsWith("/admin") ||
        url.pathname.startsWith("/login") ||
        url.pathname.startsWith("/logout")
    ) {
        return;
    }

    // Cache static files
    if (url.pathname.startsWith("/static/")) {

        event.respondWith(

            caches.match(event.request).then(async cached => {

                if (cached) {
                    return cached;
                }

                try {

                    const response = await fetch(event.request);

                    const cache = await caches.open(CACHE_NAME);

                    cache.put(event.request, response.clone());

                    return response;

                } catch (err) {

                    return cached;

                }

            })

        );

        return;

    }

    // Network first for HTML pages

    event.respondWith(

        fetch(event.request)

            .then(response => {

                return response;

            })

            .catch(() => {

                return caches.match(event.request);

            })

    );

});

// ===============================
// MESSAGE
// ===============================

self.addEventListener("message", event => {

    if (event.data && event.data.type === "SKIP_WAITING") {

        self.skipWaiting();

    }

});