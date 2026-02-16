const SW_VERSION = "v10";   // 🔴 change this every update

self.addEventListener('install', event => {
    console.log('✅ Service Worker installed', SW_VERSION);
    self.skipWaiting();   // activate immediately
});

self.addEventListener('activate', event => {
    console.log('✅ Service Worker activated', SW_VERSION);
    self.clients.claim(); // take control immediately
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
