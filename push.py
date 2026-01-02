import json
from pywebpush import webpush, WebPushException

# 🔑 VAPID KEYS
VAPID_PUBLIC_KEY = "BCFRU-UgsXF_DLPMXsyAKtgu_kFa18N-2vemrwKqCOCh0fxH13-fPEkzLNWiaiLLRQf96AptZl1JlNGCuUbvMx4="
VAPID_PRIVATE_KEY = "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JR0hBZ0VBTUJNR0J5cUdTTTQ5QWdFR0NDcUdTTTQ5QXdFSEJHMHdhd0lCQVFRZ1RVYXgzMk9NeVM3b01zRGoKdVZXelVLelU0TEtRdUpReG9pdTZLRVhNL2xlaFJBTkNBQVFoVVZQbElMRnhmd3l6ekY3TWdDcllMdjVCV3RmRApmdHIzcHE4Q3FnamdvZEg4UjlkL256eEpNeXpWb21vaXkwVUgvZWdLYldaZFNaVFJncmxHN3pNZQotLS0tLUVORCBQUklWQVRFIEtFWS0tLS0tCg=="

VAPID_CLAIMS = {
    "sub": "mailto:admin@ruchigo.com"
}

# 🧠 TEMP storage (use DB later)
subscriptions = []


def register_subscription(subscription):
    if subscription not in subscriptions:
        subscriptions.append(subscription)
        print("✅ Subscription saved")


def send_push(subscription, title="New Order", body="You have a new order", url="/"):
    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url
    })

    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS
        )
        print("📨 Push sent")
    except WebPushException as e:
        print("❌ Push failed:", e)
