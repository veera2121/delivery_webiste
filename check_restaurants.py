from app import app, db
from models import Restaurant
from datetime import datetime, date
import pytz

# IST timezone
ist = pytz.timezone("Asia/Kolkata")
now = datetime.now(ist).time()

with app.app_context():  # <-- ensures Flask app context is active
    restaurants = Restaurant.query.all()

    for r in restaurants:
        status = "Unknown"

        if not r.is_accepting_orders:
            status = "⛔ Temporarily paused by restaurant"
        elif r.status == "suspended":
            status = "🚫 Suspended"
        elif r.status == "coming_soon" and r.start_date and date.today() < r.start_date:
            status = f"⏳ Coming Soon (starts {r.start_date})"
        elif r.opening_time and now < r.opening_time:
            status = f"⏳ Accepting orders at {r.opening_time.strftime('%I:%M %p')}"
        elif r.opening_time and r.closing_time and not (r.opening_time <= now <= r.closing_time):
            status = "🌙 Closed for today"
        elif r.can_accept_orders:
            status = "✅ Accepting orders"

        print(f"{r.name} → {status}")
