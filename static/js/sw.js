self.addEventListener('install', event => {
    console.log('✅ Service Worker installed');
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    console.log('✅ Service Worker activated');
    self.clients.claim();
});

self.addEventListener('push', event => {
    const data = event.data ? event.data.json() : {};

    event.waitUntil(
        self.registration.showNotification(data.title || 'New Order', {
            body: data.body || 'You have a delivery update',
            icon: '/static/icons/icon-192.png',
            badge: '/static/icons/icon-192.png',
        })
    );
});
