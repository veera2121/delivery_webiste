const SW_VERSION = "v11";   // Increment version

self.addEventListener('install', event => {
    console.log('✅ Service Worker installed', SW_VERSION);
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    console.log('✅ Service Worker activated', SW_VERSION);
    self.clients.claim();
});

self.addEventListener('push', event => {

    const data = event.data ? event.data.json() : {};

    event.waitUntil(

        self.registration.showNotification(
            data.title || "🚴 New Delivery Assigned",
            {
                body: data.body || "You have a new order",
                icon: "/static/icons/icon-192.png",
                badge: "/static/icons/icon-192.png",
                vibrate: [300, 100, 300],
                requireInteraction: true,
                data: {
                    url: data.url || "/delivery/dashboard"
                }
            }
        )

    );

});

self.addEventListener("notificationclick", event => {

    event.notification.close();

    event.waitUntil(

        clients.matchAll({
            type: "window",
            includeUncontrolled: true
        }).then(clientList => {

            for (const client of clientList) {
                if ("focus" in client) {
                    client.navigate(event.notification.data.url);
                    return client.focus();
                }
            }

            if (clients.openWindow) {
                return clients.openWindow(event.notification.data.url);
            }

        })

    );

});