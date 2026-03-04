

    /* ================= FIREBASE IMPORTS ================= */
importScripts('https://www.gstatic.com/firebasejs/10.7.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.0/firebase-messaging-compat.js');

/* ================= FIREBASE INIT ================= */
firebase.initializeApp({
  apiKey: "AIzaSyClOOasdB7hnuKOdHDsK_j7yJE5kCxLs9g",
  authDomain: "ruchigo-20f31.firebaseapp.com",
  projectId: "ruchigo-20f31",
  storageBucket: "ruchigo-20f31.firebasestorage.app",
  messagingSenderId: "889647192427",
  appId: "1:889647192427:web:e10aa7e57070818cc1142e"
});

const messaging = firebase.messaging();

/* ================= BACKGROUND MESSAGE ================= */
messaging.onBackgroundMessage(function (payload) {

  console.log("✅ Received background message:", payload);

  // 🔥 Support BOTH notification + data
  const notificationTitle =
      payload.notification?.title ||
      payload.data?.title ||
      "Ruchigo";

  const notificationOptions = {
    body:
      payload.notification?.body ||
      payload.data?.body ||
      "You have a new update.",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-96x96.png",
    vibrate: [200, 100, 200],
    requireInteraction: true,
    data: {
      url: payload.data?.url || "/"
    }
  };

  self.registration.showNotification(notificationTitle, notificationOptions);
});

/* ================= NOTIFICATION CLICK ================= */
self.addEventListener('notificationclick', function (event) {

  event.notification.close();

  const targetUrl = event.notification.data?.url || "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true })
      .then(function (clientList) {

        for (const client of clientList) {
          if (client.url.includes(targetUrl) && 'focus' in client) {
            return client.focus();
          }
        }

        if (clients.openWindow) {
          return clients.openWindow(targetUrl);
        }
      })
  );
});
