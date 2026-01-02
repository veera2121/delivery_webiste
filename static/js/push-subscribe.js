if ('serviceWorker' in navigator && 'PushManager' in window) {
    navigator.serviceWorker.register('/static/js/sw.js')
        .then(reg => {
            console.log("Service Worker registered:", reg);

            return navigator.serviceWorker.ready; // 🔥 WAIT UNTIL ACTIVE
        })
        .then(reg => {
            return reg.pushManager.getSubscription()
                .then(sub => {
                    if (sub) return sub;

                    return reg.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
                    });
                });
        })
        .then(subscription => {
            console.log("✅ Push subscribed");

            return fetch("/subscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(subscription)
            });
        })
        .catch(err => {
            console.error("❌ Push subscription error:", err);
        });
}

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/-/g, '+')
        .replace(/_/g, '/');

    const rawData = atob(base64);
    return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
}
