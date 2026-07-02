# ================= GEVENT =================
from gevent import monkey
monkey.patch_all()

# ================= STANDARD =================
import os
import math
import secrets
import uuid
import pandas as pd
from datetime import datetime, timedelta
import pytz 
import urllib.parse
# ================= FLASK =================
from flask import (
    Flask, render_template, send_from_directory,
    request, redirect, url_for, session, jsonify, flash
)
from dotenv import load_dotenv
import os

load_dotenv()
# ================= EXTENSIONS =================
from flask_socketio import SocketIO, emit, join_room
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from sqlalchemy import or_, case
from sqlalchemy.orm import joinedload
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, current_user


from flask import Flask, render_template, request, redirect, url_for, session, flash
from push import VAPID_PUBLIC_KEY, register_subscription, send_push, subscriptions
from functools import wraps
import firebase_admin
from firebase_admin import credentials


# ================= LOCAL IMPORTS =================
from push import send_push
from users.routes import users_bp 
from extensions import db
from models import (
    db, Restaurant, RestaurantUser, MenuItem, Order,
    OrderItem, DeliveryPerson, FoodItem, OTP,
    CouponUsage, RestaurantOffer, Customer ,UserFeedback, RestaurantDelivery,DeliverySettings,Item,CoinLedger,ShopSettings,RewardSetting,RewardBadge,Category, Offer ,Employee, EmployeeOTP, EmployeeSession
)
from reward_engine import add_coins, redeem_coins

# ================= APP =================
# ================= APP =================
app = Flask(__name__)

# 🔐 SECURITY & CSRF CONFIG
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "my-super-secret-key-123"),
    WTF_CSRF_ENABLED=True,
    WTF_CSRF_TIME_LIMIT=3600,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

if os.getenv("FLASK_ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True
from extensions import csrf 
# 🔐 INIT CSRF (AFTER config)
csrf.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "users.login"

# ================= DATABASE =================
import os
import sys
# after app = Flask(__name__) and db.init_app(app)


# Get DATABASE_URL from environment (for production)
db_url = os.getenv("DATABASE_URL")

if db_url:
    # Fix old postgres:// URLs for SQLAlchemy
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    print("✅ Using PRODUCTION PostgreSQL database")
else:
    # Local development: use local PostgreSQL instead of SQLite
    print("⚠️ Using LOCAL PostgreSQL database")
    LOCAL_DB_USER = "postgres"       # your local DB username
    LOCAL_DB_PASSWORD = "9676382650"   # your local DB password
    LOCAL_DB_HOST = "localhost"      # usually localhost
    LOCAL_DB_PORT = "5433"           # your PostgreSQL port
    LOCAL_DB_NAME = "testdb"         # your local database name

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"postgresql://{LOCAL_DB_USER}:{LOCAL_DB_PASSWORD}"
        f"@{LOCAL_DB_HOST}:{LOCAL_DB_PORT}/{LOCAL_DB_NAME}"
    )

# Disable track modifications for performance
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# CSRF temporarily disabled for development (enable safely later)
app.config["WTF_CSRF_ENABLED"] = False

# Detect if running Flask CLI commands (migrate, upgrade, etc.)
IS_FLASK_CLI = any(cmd in sys.argv for cmd in ["flask", "db", "migrate", "upgrade"])

# Optional: print DB URI for debug (remove in production)
print("DB URI:", app.config["SQLALCHEMY_DATABASE_URI"])

# ================= INIT EXTENSIONS =================
db.init_app(app)
csrf = CSRFProtect(app)
migrate = Migrate(app, db)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    ping_interval=25,
    ping_timeout=60,
    max_http_buffer_size=10_000_000
)

from werkzeug.middleware.proxy_fix import ProxyFix

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
# ================= BLUEPRINTS =================
app.register_blueprint(users_bp, url_prefix="/users")

from datetime import timedelta

app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    REMEMBER_COOKIE_DURATION=timedelta(days=30),
)
import razorpay


RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")
if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise Exception("Razorpay keys not found in environment variables")

razorpay_client = razorpay.Client(auth=(
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET
))
# ------------------ UTILS ------------------
def generate_otp():
    return str(secrets.randbelow(900000) + 100000)

def generate_order_id(order_db_id):
    unique_part = uuid.uuid4().hex[:6].upper()
    return f"ORD-{order_db_id}-{unique_part}"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2)**2 + \
        math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2

    c = 2 * math.asin(math.sqrt(a))
    return R * c 
import math

import math
import requests
import math



def calculate_distance_km(lat1, lng1, lat2, lng2):

    print("DISTANCE INPUT:", lat1, lng1, lat2, lng2)

    if None in (lat1, lng1, lat2, lng2):
        return 0

    lat1, lng1, lat2, lng2 = map(float, (lat1, lng1, lat2, lng2))

    url = f"https://router.project-osrm.org/route/v1/driving/{lng1},{lat1};{lng2},{lat2}?overview=false"

    try:
        r = requests.get(url, timeout=3)
        data = r.json()

        if "routes" not in data or len(data["routes"]) == 0:
            print("OSRM failed, using haversine fallback")

            km = haversine(lat1, lng1, lat2, lng2)
            km = km * 1.35
            km = math.ceil(km * 2) / 2
            return km

        meters = data["routes"][0]["distance"]

        km = meters / 1000
        km = km * 1.07
        km = math.ceil(km * 2) / 2

        return km

    except Exception as e:
        print("DISTANCE ERROR:", e)
        print("Using haversine fallback")

        km = haversine(lat1, lng1, lat2, lng2)
        km = km * 1.35
        km = math.ceil(km * 2) / 2

        return km 

def cancel_unpaid_orders():

    cutoff = datetime.utcnow() - timedelta(minutes=15)

    unpaid_orders = Order.query.filter(

        Order.payment_type == "Online",

        Order.status == "Pending Payment",

        Order.payment_status == "Pending",

        Order.created_at < cutoff

    ).all()

    for order in unpaid_orders:

        order.status = "Cancelled"

        order.cancel_reason = (
            "Payment not completed"
        )

    db.session.commit() 

@app.before_request
def cleanup_orders():

    cancel_unpaid_orders()
# ------------------ ADMIN CONFIG ------------------

# Admin credentials
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
# Use the hashed password instead of plain text
# Admin credentials
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")  # default username
ADMIN_PASSWORD_HASH ="scrypt:32768:8:1$KjIRJyvNzAIMkq3H$93b2da15188e769f503cc5c4285c7281bd8b42b774b320355f476652eafc983e994d285b434753ae852d8faabec936e50b8f63d43d8d0ffd8ab09b4614501661"

app.permanent_session_lifetime = timedelta(days=30)

from flask import request
from flask import request, session, render_template
 # make sure you have this function or library 
from flask import send_from_directory
from flask import request, redirect


@app.route('/googleb0a5e859452528b7.html')
def google_verify():
    return send_from_directory('static', 'googleb0a5e859452528b7.html')
from flask import Response, url_for
from datetime import datetime

@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    # Base URL
    base_url = 'https://www.ruchigo.in'

    # Static pages
    pages = [
        url_for('home', _external=True),
    ]

    # Add all restaurants dynamically
    restaurants = Restaurant.query.all()
    for r in restaurants:
        pages.append(url_for('menu', restaurant_id=r.id, _external=True))

    # Generate XML content
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for page in pages:
        xml += '  <url>\n'
        xml += f'    <loc>{page}</loc>\n'
        xml += f'    <lastmod>{datetime.today().date()}</lastmod>\n'
        xml += '    <changefreq>weekly</changefreq>\n'
        xml += '    <priority>0.8</priority>\n'
        xml += '  </url>\n'

    xml += '</urlset>'

    return Response(xml, mimetype='application/xml')
@login_manager.user_loader
def load_user(user_id):
    return None
from datetime import datetime, timedelta, timezone

def is_new_restaurant(restaurant):
    if not restaurant.created_at:
        return False

    now = datetime.now(timezone.utc)

    created = restaurant.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    return created >= now - timedelta(days=7)

app.jinja_env.globals["is_new_restaurant"] = is_new_restaurant

import urllib.parse
import re

def format_phone(phone):
    phone = re.sub(r"\D", "", phone)   # remove spaces, +, -, etc

    if phone.startswith("0"):
        phone = phone[1:]

    if len(phone) == 10:
        phone = "91" + phone     # India country code

    elif len(phone) == 12 and phone.startswith("91"):
        pass
    else:
        return None

    return phone

import os
import json
import firebase_admin
from firebase_admin import credentials

# Initialize Firebase ONLY ONCE
if not firebase_admin._apps:
    firebase_json = os.environ.get("FIREBASE_KEY")

    if firebase_json:
        cred = credentials.Certificate(json.loads(firebase_json))
        firebase_admin.initialize_app(cred)
        print("✅ Firebase initialized successfully")
    else:
        print("❌ FIREBASE_KEY not found in environment variables")

def make_whatsapp_link(order):

    restaurant = Restaurant.query.get(order.restaurant_id)
    rname = restaurant.name if restaurant else "Restaurant"

    phone = format_phone(order.phone)
    if not phone:
        return "#invalid-number"

    otp = order.otp or "----"

    msg = (
        "*RucHiGo*\n\n"

        f"Hi *{order.customer_name}* 👋\n\n"

        f"✅ Your order *#{order.order_id}* from *{rname}* has been *Accepted*.\n"
        f"💰 Amount: *₹{order.get_final_total()}*\n\n"

        f"🔐 Delivery OTP: ✨*{order.otp}*✨\n"
        "Please keep this OTP safe.\n"
        "Share it with the delivery partner only after receiving your order.\n\n"

        f"🍽️ *{rname}* is preparing your food.\n"
        "🚴 A delivery partner will be assigned shortly.\n\n"

        "📞 Support: 7207002650\n"
        "🌐 Track your order on *RucHiGo Website/App*\n\n"

        "Thank you for choosing *RucHiGo* 💙"
    )
    encoded = urllib.parse.quote_plus(msg)
    return f"https://wa.me/{phone}?text={encoded}"

from datetime import datetime 
from zoneinfo import ZoneInfo
from sqlalchemy.orm import joinedload
from datetime import datetime
import pytz
from flask import request, render_template, session
from reward_engine import update_customer_badge
from flask_login import current_user
from sqlalchemy import or_
# ===== ADD THESE CACHES AT TOP OF app.py (outside any function) =====
import time as time_module

_badge_cache = {"data": None, "time": 0}
_location_cache = {"data": None, "time": 0}

def get_badge_counts():
    now = time_module.time()
    if _badge_cache["data"] and now - _badge_cache["time"] < 300:
        return _badge_cache["data"]
    data = {
        "silver": Customer.query.join(RewardBadge).filter(RewardBadge.name == "Silver").count(),
        "gold": Customer.query.join(RewardBadge).filter(RewardBadge.name == "Gold").count(),
        "platinum": Customer.query.join(RewardBadge).filter(RewardBadge.name == "Platinum").count(),
    }
    _badge_cache["data"] = data
    _badge_cache["time"] = now
    return data

def get_all_locations():
    now = time_module.time()
    if _location_cache["data"] and now - _location_cache["time"] < 300:
        return _location_cache["data"]
    locs = [loc[0] for loc in db.session.query(Restaurant.location).distinct() if loc[0]]
    _location_cache["data"] = locs
    _location_cache["time"] = now
    return locs


# ===== FIXED HOME ROUTE =====
@app.route("/")
def home():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist).time()
    selected_location = request.args.get("location", "").strip()

    # ================= BADGE COUNTS (CACHED 5 mins) =================
    badge_counts = get_badge_counts()
    silver_count = badge_counts["silver"]
    gold_count = badge_counts["gold"]
    platinum_count = badge_counts["platinum"]

    # ================= CUSTOMER DATA =================
    coins = 0
    earned_coins = 0
    customer = None
    badge = "No Badge"
    next_badge = None
    coins_to_next_badge = 0
    progress_percent = 0

    if current_user.is_authenticated:
        customer = current_user
        coins = customer.coins or 0
        badge = customer.badge.name if customer.badge else "No Badge"

        # ⭐ ONE-TIME COINS FOR UI ANIMATION
        if customer.last_reward_coins and customer.last_reward_coins > 0:
            earned_coins = customer.last_reward_coins
            customer.last_reward_coins = 0
            db.session.commit()

        # ===== BADGE PROGRESS =====
        badges = RewardBadge.query.filter_by(active=True)\
            .order_by(RewardBadge.required_coins.asc()).all()

        for b in badges:
            if customer.coins < b.required_coins:
                next_badge = b
                break

        if next_badge:
            current_min = customer.badge.required_coins if customer.badge else 0
            span = next_badge.required_coins - current_min
            if span > 0:
                progress_percent = int(((customer.coins - current_min) / span) * 100)
            progress_percent = max(0, min(progress_percent, 100))
            coins_to_next_badge = max(0, next_badge.required_coins - customer.coins)
        else:
            progress_percent = 100
            coins_to_next_badge = 0

    # ================= FETCH RESTAURANTS (ONE QUERY) =================
    if selected_location:
        restaurants = Restaurant.query.filter(
            Restaurant.location == selected_location,
            Restaurant.category_type.in_(["restaurant", "bakery"])
        ).all()
    else:
        restaurants = Restaurant.query.filter(
            Restaurant.category_type.in_(["restaurant", "bakery"])
        ).all()

    categories = Category.query.all()

    # ================= LOCATION DROPDOWN (CACHED) =================
    all_locations = get_all_locations()

    # ================= TRENDING ITEMS =================
    if selected_location:
        trending_items = (
            db.session.query(FoodItem)
            .join(Restaurant)
            .filter(
                Restaurant.location == selected_location,
                FoodItem.order_count > 0
            )
            .order_by(FoodItem.order_count.desc())
            .limit(8)
            .all()
        )
    else:
        trending_items = []

    # ================= USER LOCATION =================
    user_lat = session.get("user_lat")
    user_lng = session.get("user_lng")
    user_location_set = user_lat is not None and user_lng is not None

    # ================= RESTAURANT STATUS =================
    limited_restaurants = []

    for r in restaurants:
        r.deliverable = True
        r.distance = None

        if (
            user_location_set
            and r.latitude is not None
            and r.longitude is not None
            and r.delivery_radius_km
        ):
            dist = haversine(
                float(user_lat),
                float(user_lng),
                float(r.latitude),
                float(r.longitude)
            )
            r.distance = round(dist, 1)
            r.deliverable = dist <= r.delivery_radius_km

        if r.opening_time and r.closing_time:
            if r.opening_time < r.closing_time:
                r.is_open = r.opening_time <= now <= r.closing_time
            else:
                r.is_open = now >= r.opening_time or now <= r.closing_time
        else:
            r.is_open = True

        if r.is_limited_drop and r.can_accept_orders:
            limited_restaurants.append(r)

    restaurants = get_sorted_restaurants(restaurants)

    # ================= SEO =================
    if selected_location:
        seo_title = f"Online Food Delivery in {selected_location} | RuchiGo"
        seo_description = f"Order food online from nearby restaurants and bakeries in {selected_location}. Fast local delivery."
        seo_keywords = f"{selected_location} food delivery, bakery, RuchiGo"
    else:
        seo_title = "Online Food Delivery | RuchiGo"
        seo_description = "Order food online from trusted local restaurants and bakeries. Fast delivery, fresh food."
        seo_keywords = "food delivery, bakery delivery, RuchiGo"

    # ================= AJAX =================
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template(
            "_restaurants.html",
            restaurants=restaurants,
            trending_items=trending_items,
            now=now
        )

    # ================= FULL PAGE =================
    return render_template(
        "index.html",
        restaurants=restaurants,
        limited_restaurants=limited_restaurants,
        all_locations=all_locations,
        selected_location=selected_location,
        trending_items=trending_items,
        user_location_set=user_location_set,
        now=now,
        seo_title=seo_title,
        seo_description=seo_description,
        seo_keywords=seo_keywords,
        coins=coins,
        customer=customer,
        badge=badge,
        earned_coins=earned_coins,
        next_badge=next_badge,
        coins_to_next_badge=coins_to_next_badge,
        silver_count=silver_count,
        gold_count=gold_count,
        platinum_count=platinum_count,
        progress_percent=progress_percent,
        categories=categories
    )



@app.route("/city/<city_slug>")
def city_page(city_slug):
    # Convert slug to readable name
    selected_location = city_slug.replace("-", " ").title()

    # 🔹 Restaurants in this city
    restaurants = Restaurant.query.filter_by(location=selected_location).all()

    # 🔹 All locations (for dropdown)
    all_locations = [
        loc[0]
        for loc in db.session.query(Restaurant.location).distinct()
        if loc[0]
    ]

    # 🔹 Trending items (city only)
    trending_items = (
        db.session.query(FoodItem)
        .join(Restaurant)
        .filter(
            Restaurant.location == selected_location,
            FoodItem.order_count > 0
        )
        .order_by(FoodItem.order_count.desc())
        .limit(8)
        .all()
    )

    # 🔹 User location
    user_lat = session.get("user_lat")
    user_lng = session.get("user_lng")
    user_location_set = user_lat is not None and user_lng is not None

   

    # 🔹 Delivery + open status
    for r in restaurants:
        r.deliverable = True
        r.distance = None

        if (
            user_location_set
            and r.latitude is not None
            and r.longitude is not None
            and r.delivery_radius_km
        ):
            dist = haversine(
                float(user_lat),
                float(user_lng),
                float(r.latitude),
                float(r.longitude)
            )
            r.distance = round(dist, 1)
            r.deliverable = dist <= r.delivery_radius_km

        if r.opening_time and r.closing_time:
            r.is_open = r.opening_time <= now <= r.closing_time
        else:
            r.is_open = False

    restaurants.sort(
        key=lambda r: (
            not r.deliverable,
            not r.is_open
        )
    )

    # 🔹 SEO (CITY PAGE)
    seo_title = f"Online Food Delivery in {selected_location} | RuchiGo"
    seo_description = (
        f"Order food online from nearby restaurants in {selected_location}. "
        "Fast delivery from trusted local kitchens."
    )
    seo_keywords = (
        f"{selected_location} food delivery, "
        f"online food {selected_location}, RuchiGo"
    )

    return render_template(
        "index.html",
        restaurants=restaurants,
        all_locations=all_locations,
        selected_location=selected_location,
        trending_items=trending_items,
        user_location_set=user_location_set,
        now=now,
        seo_title=seo_title,
        seo_description=seo_description,
        seo_keywords=seo_keywords
    )


@app.route('/admin/update-menus', endpoint='update_menus')
def update_menus():
    # Google Sheets API scopes
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    # Load credentials (make sure credentials.json is in your project root)
    try:
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    except FileNotFoundError:
        flash("Google credentials file not found. Please upload credentials.json.", "danger")
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        flash(f"Error loading Google credentials: {e}", "danger")
        return redirect(url_for('admin_dashboard'))

    # Authorize gspread client
    try:
        client = gspread.authorize(creds)
    except Exception as e:
        flash(f"Failed to authorize Google Sheets client: {e}", "danger")
        return redirect(url_for('admin_dashboard'))

    restaurants = Restaurant.query.all()
    updated_restaurants = 0

    for restaurant in restaurants:
        if not restaurant.sheet_id:
            continue  # skip restaurants without sheet

        try:
            sheet = client.open_by_key(restaurant.sheet_id).sheet1
            data = sheet.get_all_records()
        except Exception as e:
            print(f"[ERROR] Could not load sheet for {restaurant.name}: {e}")
            continue

        for row in data:
            name = row.get('Name')
            category = row.get('Category') or "Uncategorized"
            try:
                price = float(row.get('Price', 0) or 0)
            except ValueError:
                print(f"[WARNING] Invalid price for {name} in {restaurant.name}. Skipping.")
                continue

            if not name:
                continue  # skip rows without a name

            # Check if menu item already exists
            item = MenuItem.query.filter_by(name=name, restaurant_id=restaurant.id).first()
            if item:
                item.category = category
                item.price = price
            else:
                new_item = MenuItem(
                    restaurant_id=restaurant.id,
                    name=name,
                    category=category,
                    price=price
                )
                db.session.add(new_item)

        db.session.commit()
        updated_restaurants += 1

    flash(f"Menus updated for {updated_restaurants} restaurants from Google Sheets!", "success")
    return redirect(url_for('admin_dashboard'))

from geopy.geocoders import Nominatim

def get_coordinates(address):
    """
    Converts a full address string into latitude and longitude.
    Returns (lat, lng) or (None, None) if not found.
    """
    geolocator = Nominatim(user_agent="myapp")
    try:
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
    except Exception as e:
        print("Geocode error:", e)
    return None, None
from datetime import datetime
import pytz
import re
import pytz
from pytz import UTC

def normalize_phone(phone):
    if not phone:
        return None

    phone = re.sub(r'\D', '', phone)  # remove non-digits

    # Handle Indian numbers
    if phone.startswith("91") and len(phone) > 10:
        phone = phone[-10:]
    elif phone.startswith("0") and len(phone) == 11:
        phone = phone[1:]

    return phone[-10:]


@app.route("/myorders", methods=["GET", "POST"])
def myorders():
    phone = None
    restaurant_id = None

    ACTIVE = [
        "Pending",
        "Placed",
        "Accepted",
        "Preparing",
        "Ready",
        "Out for Delivery",
        "Started"
    ]

    HISTORY = [
        "Delivered",
        "Cancelled",
        "Customer Not Available"
    ]

    if request.method == "POST":
        phone = normalize_phone(request.form.get("phone"))
        session["order_phone"] = phone
    else:
        phone = normalize_phone(session.get("order_phone"))

    active_orders = []
    history_orders = []

    if phone:
        active_orders = Order.query.filter(
            func.right(
                func.regexp_replace(Order.phone, r'[^0-9]', '', 'g'),
                10
            ) == phone,
            Order.status.in_(ACTIVE)
        ).order_by(Order.created_at.desc()).all()

        history_orders = Order.query.filter(
            func.right(
                func.regexp_replace(Order.phone, r'[^0-9]', '', 'g'),
                10
            ) == phone,
            Order.status.in_(HISTORY)
        ).order_by(Order.created_at.desc()).all()

        # ===== Convert time to IST =====
        ist = pytz.timezone("Asia/Kolkata")

        for order in active_orders + history_orders:
            if order.created_at:
                if order.created_at.tzinfo is None:
                    order.created_at = UTC.localize(order.created_at)

                order.created_at_ist = order.created_at.astimezone(ist)
                order.created_at_str = order.created_at_ist.strftime("%d-%m-%Y %I:%M %p")

        # Restaurant ID
        if active_orders:
            restaurant_id = active_orders[0].restaurant.id
        elif history_orders:
            restaurant_id = history_orders[0].restaurant.id

    return render_template(
        "myorders.html",
        active_orders=active_orders,
        history_orders=history_orders,
        restaurant_id=restaurant_id,
        phone=phone
    )

from sqlalchemy import func

from sqlalchemy import func
from datetime import datetime
from models import Customer
from flask import session, render_template
from sqlalchemy import func
from datetime import datetime


@app.route("/cart/<int:restaurant_id>")
def cart_page(restaurant_id):
    # -------------------- RESTAURANT --------------------
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    cart_items = session.get("cart", [])

    # -------------------- ITEMS & TOTAL --------------------
    items = []
    items_total = 0
    for c in cart_items:
        item = FoodItem.query.get(c["id"])
        if item:
            total = item.price * c["quantity"]
            items_total += total
            items.append({
                "id": item.id,
                "name": item.name,
                "price": item.price,
                "quantity": c["quantity"],
                "total": total
            })

    # -------------------- DISTANCE --------------------
    user_lat = session.get("latitude")
    user_lon = session.get("longitude")
    distance_km = 0
    if user_lat and user_lon and restaurant.latitude and restaurant.longitude:
        distance_km = calculate_distance_km(
            user_lat,
            user_lon,
            restaurant.latitude,
            restaurant.longitude
        )

    # -------------------- DELIVERY CHARGE --------------------
    delivery_charge, delivery_msg = calculate_delivery_charge(
        distance_km,
        items_total,
        restaurant
    )

    # -------------------- CUSTOMER & REWARD --------------------
    customer_id = session.get("customer_id")
    customer = Customer.query.get(customer_id) if customer_id else None
    reward_setting = RewardSetting.query.first()

    # -------------------- FIRST TIME USER --------------------
    phone = session.get("phone")
    device_fingerprint = session.get("device_fingerprint")
    delivered_orders = Order.query.filter(
        ((Order.phone == phone) | (Order.device_fingerprint == device_fingerprint)) &
        (func.lower(Order.status) == "delivered")
    ).count()
    first_time_user = delivered_orders == 0

    # -------------------- ACTIVE OFFER --------------------
    active_offer = RestaurantOffer.query.filter_by(
        restaurant_id=restaurant.id,
        is_active=True
    ).first()
    offer_already_used = False
    if active_offer:
        offer_already_used = Order.query.filter(
            (Order.restaurant_id == restaurant.id) &
            ((Order.phone == phone) | (Order.device_fingerprint == device_fingerprint)) &
            (Order.restaurant_offer_id == active_offer.id) &
            (func.lower(Order.status) == "delivered")
        ).first() is not None
    order = None

    # -------------------- RENDER --------------------
    return render_template(
        "cart.html",
        restaurant=restaurant,
        items=items,
        items_total=items_total,
        delivery_charge=delivery_charge,
        delivery_msg=delivery_msg,
        first_time_user=first_time_user,
        active_offer=active_offer,
        offer_already_used=offer_already_used,
        customer=customer,
        reward_setting=reward_setting,
        order=order

    )


import random
from datetime import datetime

def generate_otp():
    return str(random.randint(100000, 999999))
from datetime import datetime




from flask import request, flash, redirect, url_for, session
from models import Order, OrderItem, RestaurantOffer
from sqlalchemy import func
from datetime import datetime
 # your existing function
import random
import string

def generate_order_code(order_db_id):
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{order_db_id}-{rand}"

from datetime import datetime, timedelta,date
from models import Order, OrderItem, RestaurantOffer, Restaurant
from utils import generate_otp, generate_order_code


from sqlalchemy import func
def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
def generate_map_link(lat, lng, house_no=None, landmark=None, city=None, state=None, pincode=None):
    if lat and lng:
        return f"https://www.google.com/maps?q={lat},{lng}"
    else:
        # fallback to full address
        parts = [house_no, landmark, city, state, pincode]
        address = ", ".join([p for p in parts if p])
        if address:
            return f"https://www.google.com/maps/search/?api=1&query={address}"
    return None
# Assume order_time is in UTC
from flask import request, flash, redirect, url_for, session
from datetime import datetime
import pytz
from sqlalchemy import func 
from reward_engine import add_coins
from datetime import datetime
import pytz

@app.route("/place_order", methods=["POST"])
def place_order():

    # ================= BASIC DETAILS =================
    name = request.form.get("name")
    phone = request.form.get("phone")
    email = request.form.get("email")
    alt_phone = request.form.get("alt_phone")
    payment_type = request.form.get("payment_type")
    address_type = request.form.get("address_type")
    house_no = request.form.get("house_no")
    landmark = request.form.get("landmark")
    city = request.form.get("city")
    state = request.form.get("state")
    pincode = request.form.get("pincode")
    delivery_note = request.form.get("delivery_note")
    restaurant_id = int(request.form.get("restaurant_id"))
    device_fingerprint = request.form.get("device_fingerprint")
    order_type = request.form.get("order_type")
    # ================= LOCATION =================
    customer_lat = safe_float(request.form.get("customer_lat") or request.form.get("lat"))
    customer_lng = safe_float(request.form.get("customer_lng") or request.form.get("lng"))

    # ================= ITEMS =================
    item_names = request.form.getlist("item_name[]")
    quantities = request.form.getlist("quantity[]")
    prices = request.form.getlist("price[]")

    if not item_names:
        flash("Cart is empty", "error")
        return redirect("/")

    restaurant = Restaurant.query.get_or_404(restaurant_id)

    # ================= RESTAURANT STATUS =================
    if not restaurant.can_accept_orders:
        flash(f"{restaurant.name} is closed now", "warning")
        return redirect(request.referrer or url_for("home"))

    # ================= ITEMS TOTAL =================
    items_total = sum(int(quantities[i]) * float(prices[i]) for i in range(len(item_names)))

    # ================= LOCATION VALIDATION =================
    if not customer_lat or not customer_lng:
        flash("Please select delivery location", "error")
        return redirect(request.referrer)

    # ================= DISTANCE =================
    distance_km = calculate_distance_km(
        restaurant.latitude,
        restaurant.longitude,
        customer_lat,
        customer_lng
    )

    # ================= DELIVERY CHARGE =================
    delivery_charge, delivery_msg = calculate_delivery_charge(
        distance_km, items_total, restaurant
    )

    # ================= FINAL TOTAL (INITIAL) =================
    final_total = round(items_total + delivery_charge, 2)

    # ================= MAP LINK =================
    map_link = generate_map_link(
        customer_lat, customer_lng, house_no, landmark, city, state, pincode
    )
    

    # ================= CREATE ORDER =================
    new_order = Order(
        restaurant_id=restaurant_id,
        customer_id=current_user.id if current_user.is_authenticated else None,  # <-- FIXED
        customer_name=name,
        phone=phone,
        email=email,
        alt_phone=alt_phone,
        house_no=house_no,
        landmark=landmark,
        city=city,
        state=state,
        pincode=pincode,
        address_type=address_type,
        delivery_note=delivery_note,
        payment_type=payment_type,
        payment_status="Pending" if payment_type == "Online" else "Pending",
        payment_verified=False, 
        status=(
            "Pending Payment"
            if payment_type == "Online"
            else "Pending"
        ),

        payment_source=(
            "Checkout"
            if payment_type == "Online"
            else "COD"
        ),
        
        device_fingerprint=device_fingerprint,
        order_type=order_type,
        items_total=items_total,
        delivery_charge=delivery_charge,
        final_total=final_total,
        latitude=customer_lat,
        longitude=customer_lng,
        distance_km=round(distance_km, 2),
        map_link=map_link,
        otp=generate_otp(),
        created_at=datetime.utcnow()
    )

    
    db.session.add(new_order)
    db.session.commit()   # ✅ IMPORTANT: new_order.id created here
    print("PAYMENT RECEIVED:", payment_type)
    print(request.form.to_dict(flat=False))
    # ================= COINS REDEMPTION =================
    coins_to_redeem = int(request.form.get("redeem_coins") or 0)

    if coins_to_redeem > 0 and session.get("customer_id"):
        success, msg, redeem_amount = redeem_coins(
            customer_id=session.get("customer_id"),
            coins_to_redeem=coins_to_redeem,
            order_id=new_order.id,
            order_total=new_order.items_total + new_order.delivery_charge
        )

        if success:
            new_order.final_total -= redeem_amount
            db.session.commit()
            flash(msg, "success")
        else:
            flash(msg, "warning")

    # ================= ORDER CODE =================
    new_order.order_id = generate_order_code(new_order.id)
    db.session.commit()

    # ================= ORDER ITEMS =================
    for i in range(len(item_names)):
        qty = int(quantities[i])
        if qty > 0:
            db.session.add(OrderItem(
                order_id=new_order.id,
                item_name=item_names[i],
                quantity=qty,
                price=float(prices[i])
            ))
    db.session.commit()

    # ================= FINAL =================
    if payment_type == "Online":
        return redirect(
            url_for(
                "payment_page",
                order_id=new_order.id
            )
        )

    flash(
        f"Order placed successfully! Order ID: {new_order.order_id}",
        "success"
    )

    return redirect(
        url_for(
            "order_placed",
            order_id=new_order.order_id
        )
    )

@app.route("/order-placed/<order_id>")
def order_placed(order_id):
    return render_template(
        "order_placed.html",
        order_id=order_id
    )


# ------------------ SUPER ADMIN ------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))

        flash("Invalid login", "warnig")

    return render_template("admin_login.html")


from datetime import datetime, timedelta
from flask import session, redirect, url_for, render_template, request
from models import Order, Restaurant, DeliveryPerson, db
from sqlalchemy import or_

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    query = request.args.get("query", "")
    status_filter = request.args.get("status", "")
    date_filter = request.args.get("date")  # Optional date filter (YYYY-MM-DD)
    page = request.args.get("page", 1, type=int)

    q = Order.query

    # ---------------- SEARCH FILTER ----------------
    if query:
        q = q.filter(
            or_(
                Order.order_id.contains(query),
                Order.customer_name.contains(query),
                Order.phone.contains(query),
                Order.email.contains(query)
            )
        )

    # ---------------- STATUS FILTER ----------------
    if status_filter:
        q = q.filter(Order.status == status_filter)

    # ---------------- DATE FILTER ----------------
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            q = q.filter(db.func.date(Order.created_at) == filter_date)
        except ValueError:
            pass  # ignore invalid date input

    q = q.order_by(Order.created_at.desc())
    pagination = q.paginate(page=page, per_page=100)
    orders = pagination.items

    # ---------------- DELIVERY PERSONS & RESTAURANTS ----------------
    delivery_persons = DeliveryPerson.query.order_by(DeliveryPerson.name).all()
    restaurants = Restaurant.query.all()

    # ---------------- ADMIN STATISTICS ----------------
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())

    from sqlalchemy import func

    today_orders_query = Order.query.filter(
        db.func.date(Order.created_at) == today
    )

    # ✅ Delivered orders (used for revenue + items)
    today_delivered_orders = today_orders_query.filter(
        Order.status == "Delivered"
    ).all()

    stats = {
        "total_orders": Order.query.count(),

        "pending": Order.query.filter_by(status="Pending").count(),
        "preparing": Order.query.filter_by(status="Preparing").count(),

        "assigned": Order.query.filter(
            Order.delivery_person_id.isnot(None),
            Order.status != "Delivered",
            Order.status != "Cancelled"
        ).count(),

        "delivered": Order.query.filter_by(status="Delivered").count(),
        "cancelled": Order.query.filter_by(status="Cancelled").count(),

        # ================= TODAY PERFORMANCE =================
        "today_orders": today_orders_query.count(),

        "today_delivered": len(today_delivered_orders),

        "today_cancelled": today_orders_query.filter(
            Order.status == "Cancelled"
        ).count(),

        "today_pending": today_orders_query.filter(
            Order.status == "Pending"
        ).count(),

        # 🔥 ACTIVE = Preparing + Assigned + Out for Delivery
        "today_active": today_orders_query.filter(
            Order.status.in_(["Preparing", "Assigned", "Out for Delivery"])
        ).count(),

        # 💰 Revenue (only delivered)
        "today_revenue": sum(
            o.get_final_total() for o in today_delivered_orders
        ),

        # 🚚 Delivery charges
        "today_delivery_charges": sum(
            o.delivery_charge for o in today_delivered_orders if o.delivery_charge
        ),

        # 📦 Items sold
        "today_items": sum(
            item.quantity
            for o in today_delivered_orders
            for item in o.items
        ) if today_delivered_orders else 0,

        # ================= WEEK =================
        "week_orders": Order.query.filter(
            Order.created_at >= week_start
        ).count(),

        "weekly_revenue": sum(
            o.get_final_total()
            for o in Order.query.filter(
                Order.created_at >= week_start,
                Order.status == "Delivered"
            ).all()
        ),

        # ================= TOTAL =================
        "total_revenue": sum(
            o.get_final_total()
            for o in Order.query.filter_by(status="Delivered").all()
        )
    }

    # ---------------- CLASSIFY ORDERS BY DAY ----------------
    for o in orders:
        if o.created_at.date() == today:
            o.day_category = "Today"
        elif o.created_at.date() == yesterday:
            o.day_category = "Yesterday"
        else:
            o.day_category = "Older"

    # ---------------- RESTAURANT PERFORMANCE ----------------
    restaurant_performance = []
    for r in restaurants:
        r_orders = Order.query.filter_by(restaurant_id=r.id).all()
        today_orders = [o for o in r_orders if o.created_at.date() == today and o.status=="Delivered"]
        weekly_orders = [o for o in r_orders if o.created_at.date() >= week_start and o.status=="Delivered"]
        restaurant_performance.append({
            "id": r.id,
            "name": r.name,
            "today_orders": len(today_orders),
            "today_earnings": sum(o.get_final_total() for o in today_orders),
            "weekly_orders": len(weekly_orders),
            "weekly_earnings": sum(o.get_final_total() for o in weekly_orders),
            "pending": len([o for o in r_orders if o.status == "Pending"]),
            "completed": len([o for o in r_orders if o.status == "Delivered"]),
                        # ✅ ADD THESE TWO
            "is_best_seller": r.is_best_seller,
            "is_fast_delivery": r.is_fast_delivery

        })

    return render_template(
        "admin_dashboard.html",
        orders=orders,
        delivery_persons=delivery_persons,
        pagination=pagination,
        query=query,
        status_filter=status_filter,
        date_filter=date_filter,
        restaurants=restaurants,
        stats=stats,
        restaurant_stats=restaurant_performance,
        make_whatsapp_link=make_whatsapp_link 
    )


# ---------------- ASSIGN DELIVERY PERSON ----------------
from flask_socketio import emit
@app.route("/restaurant/update_status/<int:order_id>", methods=["POST"])
def update_status(order_id):
    if not session.get("restaurant_logged_in"):
        return redirect(url_for("restaurant_login"))

    new_status = request.form.get("status")
    order = Order.query.get(order_id)

    if not order:
        flash("Order not found!", "error")
        return redirect(url_for("restaurant_dashboard"))

    # update DB
    order.status = new_status
    db.session.commit()

    # 🔥 REAL-TIME EMIT (FIXED)
    socketio.emit(
        "order_status_update",
        {
            "order_id": order.id,   # ✅ FIXED (DB ID ONLY)
            "status": order.status
        },
        room=f"order_{order.id}"   # ✅ FIXED
    )

    print("📤 Emitted:", order.id, order.status)

    flash("Order status updated!", "success")
    return redirect(url_for("restaurant_dashboard"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out successfully", "success")
    return redirect(url_for("admin_login"))
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("You must be logged in as admin to access this page", "error")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function
# ------------------ RESTAURANT OWNER ------------------
@app.route("/restaurant/login", methods=["GET", "POST"])
def restaurant_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = RestaurantUser.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["restaurant_logged_in"] = True
            session["restaurant_id"] = user.restaurant_id
            session["restaurant_name"] = user.username
            return redirect(url_for("restaurant_dashboard"))
        flash("Invalid login!", "error")
    return render_template("restaurant_login.html")






from datetime import datetime, timedelta
from flask import session, redirect, url_for, render_template
from models import Order, OrderItem, DeliveryPerson, db

from datetime import datetime, timedelta
@app.route("/restaurant/dashboard")
def restaurant_dashboard():
    restaurant_id = session.get("restaurant_id")
    if not restaurant_id:
        return redirect(url_for("restaurant_login"))

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    orders = Order.query.filter(

        Order.restaurant_id == restaurant_id,

        Order.status.in_(

            [

                "Pending",

                "Accepted",

                "Preparing",

                "Ready",

                "Out for Delivery",

                "Started",

                "Delivered",

                "Cancelled"

            ]

        )

    ).order_by(

        Order.created_at.desc()

    ).all()

    # Classify orders by day
    for o in orders:
        if o.created_at.date() == today:
            o.day_category = "Today"
        elif o.created_at.date() == yesterday:
            o.day_category = "Yesterday"
        else:
            o.day_category = "Older"

    today_orders = [o for o in orders if o.day_category == "Today"]
    delivered_today_orders = [o for o in today_orders if o.status == "Delivered"]

    stats = {
        "today_orders": len(today_orders),
        "delivered_today": len(delivered_today_orders),
        "pending_today": len([o for o in today_orders if o.status == "Pending"]),
        "cancelled_today": len([o for o in today_orders if o.status == "Cancelled"]),
        "active_orders": len([o for o in orders if o.status in ["Accepted", "Preparing","Ready", "Out for Delivery"]]),
        "today_earnings": sum(o.get_final_total() for o in delivered_today_orders),
        "today_cod_amount": sum(o.get_final_total() for o in delivered_today_orders if o.payment_type == "COD"),
        "today_online_amount": sum(o.get_final_total() for o in delivered_today_orders if o.payment_type == "Online"),
        "weekly_orders": len([o for o in orders if o.created_at.date() >= week_ago]),
        "weekly_earnings": sum(o.get_final_total() for o in orders if o.created_at.date() >= week_ago and o.status == "Delivered"),
        "weekly_delivered_orders": len([o for o in orders if o.created_at.date() >= week_ago and o.status == "Delivered"])
    }
     
    # ------------------ Delivery Boy Status ------------------
    # Mark inactive delivery boys offline
    threshold = datetime.utcnow() - timedelta(minutes=5)

    inactive_delivery_persons = DeliveryPerson.query.filter(
        DeliveryPerson.is_online == True,
        DeliveryPerson.last_seen < threshold
    ).all()

    for dp in inactive_delivery_persons:
        dp.is_online = False

    db.session.commit()



    # ✅ FIXED: Only this restaurant’s delivery boys
    delivery_persons = (
        DeliveryPerson.query
        .join(RestaurantDelivery)
        .filter(RestaurantDelivery.restaurant_id == restaurant_id)
        .order_by(DeliveryPerson.name)
        .all()
    )


    return render_template(
        "restaurant_dashboard.html",
        stats=stats,
        orders=orders,
        delivery_persons=delivery_persons
    )
@app.route("/restaurant/delivery-persons")
def restaurant_delivery_persons():
    restaurant_id = session.get("restaurant_id")
    if not restaurant_id:
        return redirect(url_for("restaurant_login"))

    # ✅ Assigned to THIS restaurant
    delivery_persons = (
        db.session.query(DeliveryPerson)
        .join(RestaurantDelivery)
        .filter(RestaurantDelivery.restaurant_id == restaurant_id)
        .order_by(DeliveryPerson.name)
        .all()
    )

    # ✅ NOT assigned to this restaurant
    other_delivery_persons = (
        db.session.query(DeliveryPerson)
        .filter(
            ~DeliveryPerson.id.in_(
                db.session.query(RestaurantDelivery.delivery_person_id)
                .filter(RestaurantDelivery.restaurant_id == restaurant_id)
            )
        )
        .order_by(DeliveryPerson.name)
        .all()
    )

    return render_template(
        "restaurant_delivery_persons.html",
        delivery_persons=delivery_persons,
        other_delivery_persons=other_delivery_persons
    )

@app.route("/restaurant/add_delivery_person/<int:delivery_id>", methods=["POST"])
def add_delivery_person_to_restaurant(delivery_id):
    restaurant_id = session.get("restaurant_id")
    if not restaurant_id:
        return redirect(url_for("restaurant_login"))

    exists = RestaurantDelivery.query.filter_by(
        restaurant_id=restaurant_id,
        delivery_person_id=delivery_id
    ).first()

    if exists:
        flash("Delivery person already assigned", "info")
        return redirect(url_for("restaurant_delivery_persons"))

    assignment = RestaurantDelivery(
        restaurant_id=restaurant_id,
        delivery_person_id=delivery_id
    )

    db.session.add(assignment)
    db.session.commit()

    flash("Delivery person assigned successfully", "success")
    return redirect(url_for("restaurant_delivery_persons"))


@app.route("/restaurant/update_status/<int:order_id>", methods=["POST"])
def restaurant_update_status(order_id):
    if not session.get("restaurant_logged_in"):
        return redirect(url_for("restaurant_login"))

    order = Order.query.get_or_404(order_id)
    new_status = request.form.get("status")

    # 🚫 Restaurant CANNOT touch delivery states
    protected_states = ["Started", "Delivered"]

    if order.status in protected_states:
        flash("Delivery is already in progress. Status cannot be changed.", "warning")
        return redirect(url_for("restaurant_dashboard"))

    # 🚫 Restaurant cannot force delivery states
    if new_status in protected_states:
        flash("Only delivery partner can update delivery status.", "danger")
        return redirect(url_for("restaurant_dashboard"))

    order.status = new_status
    db.session.commit()

    flash("Order status updated!", "success")
    return redirect(url_for("restaurant_dashboard"))

@app.route("/restaurant/logout")
def restaurant_logout():
    session.pop("restaurant_logged_in", None)
    session.pop("restaurant_id", None)
    session.pop("restaurant_name", None)
    return redirect(url_for("restaurant_login"))

from datetime import datetime

@app.route("/delivery/login", methods=["GET", "POST"])
def delivery_login():
    if request.method == "POST":
        phone = request.form.get("phone")
        password = request.form.get("password")

        dp = DeliveryPerson.query.filter_by(phone=phone).first()

        if dp and dp.check_password(password):
            # ✅ Clear session
            session.clear()
            session.permanent = True  # 6-hour login

            # ✅ Set session variables
            session["delivery_logged_in"] = True
            session["delivery_person_id"] = dp.id
            session["delivery_person_name"] = dp.name
            session["restaurant_id"] = dp.restaurant_id

            # 🔥 UPDATE ONLINE STATUS
            dp.is_online = True
            dp.last_seen = datetime.utcnow()
            db.session.commit()

            return redirect(url_for("delivery_dashboard"))

        else:
            flash("Invalid login!", "error")
            return render_template("delivery_login.html")

    return render_template("delivery_login.html")

@app.route("/delivery/dashboard", methods=["GET", "POST"])
def delivery_dashboard():

    # -------------------- AUTH --------------------
    if not session.get("delivery_logged_in"):
        return redirect(url_for("delivery_login"))

    dp_id = session.get("delivery_person_id")
    delivery_person = DeliveryPerson.query.get(dp_id)
    if not delivery_person:
        return redirect(url_for("delivery_login"))

    # -------------------- OTP SUBMIT --------------------
    if request.method == "POST":
        order_id = request.form.get("order_id")
        entered_otp = request.form.get("otp")
       

        order = Order.query.get(order_id)

        if not order or order.delivery_person_id != dp_id:
            flash("Invalid order", "error")
            return redirect(url_for("delivery_dashboard"))

        # ✅ Allow OTP ONLY if delivery already started
        if order.status != "Started":
            flash("Delivery not started yet", "error")
            return redirect(url_for("delivery_dashboard"))
        print("=== DEBUG COINS ===")
        print("Order ID:", order.id)
        print("Customer ID:", order.customer_id)
        print("Items Total:", order.items_total)
        setting = RewardSetting.query.first()
        print("RewardSetting:", setting.earn_per_rupees if setting else "None")
        # ✅ OTP CHECK

        if order.otp == entered_otp:

            
            # Prevent delivery if online payment not completed
            if (
                order.payment_type == "Online"
                and order.payment_status != "Paid"
            ):
                flash(
                    "Customer has not completed online payment yet.",
                    "error"
                )
                return redirect(
                    url_for("delivery_dashboard")
                )

            # Mark order delivered
            order.status = "Delivered"
            order.delivered_time = datetime.utcnow()

            coins_earned = add_coins(
                order.customer_id,
                order.items_total,
                order.id
            )

            db.session.commit()

            # Save earned coins in session
            session["earned_coins"] = coins_earned

            flash(
                f"Order {order.order_id} delivered successfully",
                "success"
            )
        

        else:
            flash(
            "❌ Invalid OTP. Try again.",
            "error"
            )


        return redirect(url_for("delivery_dashboard"))

    # -------------------- ACTIVE ORDERS --------------------
    orders = (
        Order.query
        .filter(
            Order.delivery_person_id == dp_id,
            Order.status.in_(["Out for Delivery", "Started"])
        )
        .order_by(
            case(
                (Order.status == "Out for Delivery", 0),
                (Order.status == "Started", 1),
                else_=2
            ),
            Order.created_at.desc()
        )
        .all()
    )

    # -------------------- STATS --------------------
    all_orders = Order.query.filter_by(delivery_person_id=dp_id).all()

    stats = {
        "total": len(all_orders),
        "active": len([o for o in all_orders if o.status in ["Out for Delivery", "Started"]]),
        "delivered": len([o for o in all_orders if o.status == "Delivered"]),
        "cod_total": sum(o.final_total or 0 for o in all_orders if o.payment_type == "COD"),
        "online_total": sum(o.final_total or 0 for o in all_orders if o.payment_type == "Online"),
    }

    return render_template(
        "delivery_dashboard.html",
        delivery_person=delivery_person,
        orders=orders,
        stats=stats,
        VAPID_PUBLIC_KEY=VAPID_PUBLIC_KEY
    )

@app.route("/admin/add_restaurant_user", methods=["GET", "POST"])
def add_restaurant_user():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    restaurants = Restaurant.query.all()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        restaurant_id = request.form.get("restaurant_id")

        if not username or not password or not restaurant_id:
            flash("All fields are required!", "error")
            return redirect(url_for("add_restaurant_user"))

        if RestaurantUser.query.filter_by(username=username).first():
            flash("Username already exists!", "danger")
            return redirect(url_for("add_restaurant_user"))

        new_user = RestaurantUser(username=username, restaurant_id=restaurant_id)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash("Restaurant user added successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_restaurant_user.html", restaurants=restaurants)

@app.route("/delivery/logout")
def delivery_logout():
    dp_id = session.get("delivery_person_id")
    if dp_id:
        dp = DeliveryPerson.query.get(dp_id)
        if dp:
            dp.is_online = False
            dp.last_seen = datetime.utcnow()
            db.session.commit()

    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("delivery_login"))
from datetime import datetime, timedelta

def update_delivery_status():
    threshold = datetime.utcnow() - timedelta(minutes=5)
    DeliveryPerson.query.filter(
        DeliveryPerson.is_online == True,
        DeliveryPerson.last_seen < threshold
    ).update({"is_online": False})
    db.session.commit()

@app.route("/admin/add_delivery_person", methods=["GET", "POST"])
def add_delivery_person():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")  # ✅ NEW
        phone = request.form.get("phone")
        password = request.form.get("password")
        restaurant_id = request.form.get("restaurant_id")

        if not all([name, username, phone, password, restaurant_id]):
            flash("All fields are required!", "danger")
            return redirect(url_for("add_delivery_person"))

        if DeliveryPerson.query.filter_by(phone=phone).first():
            flash("Phone already exists!", "danger")
            return redirect(url_for("add_delivery_person"))
        
        if DeliveryPerson.query.filter_by(username=username).first():
            flash("Username already exists!", "danger")
            return redirect(url_for("add_delivery_person"))

        dp = DeliveryPerson(
            name=name,
            username=username,  # ✅ SAVE USERNAME
            phone=phone,
            restaurant_id=restaurant_id
        )
        dp.set_password(password)

        db.session.add(dp)
        db.session.commit()

        flash("Delivery person added successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    # GET request
    restaurants = Restaurant.query.all()
    return render_template("add_delivery_person.html", restaurants=restaurants)
@app.route("/admin/add_restaurant", methods=["GET", "POST"])
def add_restaurant():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        try:
            # ---- GET FORM DATA ----
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            email = request.form.get("email", "").strip()
            address = request.form.get("address", "").strip()
            sheet_url = request.form.get("sheet_url", "").strip()
            location = request.form.get("location", "").strip()
            category_type = request.form.get("category_type", "").strip().lower()

            # ---- VALIDATION ----
            if not name or not phone or not email or not sheet_url:
                flash("Name, phone, email, and Google Sheet URL are required!", "danger")
                return redirect(url_for("add_restaurant"))

            if category_type not in ["restaurant", "bakery"]:
                flash("Please select a valid business type!", "danger")
                return redirect(url_for("add_restaurant"))

            if Restaurant.query.filter_by(name=name).first():
                flash("Restaurant already exists!", "danger")
                return redirect(url_for("add_restaurant"))

            # ---- CREATE NEW RESTAURANT ----
            restaurant = Restaurant(
                name=name,
                phone=phone,
                email=email,
                address=address,
                sheet_url=sheet_url,
                location=location,
                category_type=category_type  # ✅ ALWAYS SAVES CORRECTLY
            )

            db.session.add(restaurant)
            db.session.commit()

            # ---- OPTIONAL ADMIN USER ----
            admin_username = request.form.get("admin_username")
            admin_password = request.form.get("admin_password")

            if admin_username and admin_password:
                if RestaurantUser.query.filter_by(username=admin_username).first():
                    flash("Admin username already exists!", "danger")
                    return redirect(url_for("add_restaurant"))

                admin_user = RestaurantUser(
                    username=admin_username,
                    restaurant_id=restaurant.id
                )
                admin_user.set_password(admin_password)
                db.session.add(admin_user)
                db.session.commit()

            flash(
                f"{category_type.capitalize()} '{name}' added successfully!",
                "success"
            )
            return redirect(url_for("admin_dashboard"))

        except Exception as e:
            db.session.rollback()
            print("ERROR:", e)
            flash("Error while adding restaurant. Check server logs.", "danger")
            return redirect(url_for("add_restaurant"))

    # ---- GET REQUEST ----
    return render_template("add_restaurant.html")

from sqlalchemy import func
from flask_login import current_user
import re, unicodedata
from sqlalchemy import func
from datetime import datetime
import pytz
import pandas as pd


# ================= NORMALIZER =================
def normalize_name(name):
    name = unicodedata.normalize("NFKD", str(name))
    name = name.lower()
    name = re.sub(r"[^a-z0-9() ]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


# ================= MENU ROUTE =================
@app.route("/menu/<int:restaurant_id>")
def menu(restaurant_id):

    restaurant = Restaurant.query.get_or_404(restaurant_id)
    print("OPENING MENU FOR:", restaurant.name, restaurant.category_type)

    # ================= TIME CHECK =================
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist).time()

    if restaurant.opening_time and restaurant.closing_time:
        is_open = restaurant.opening_time <= now <= restaurant.closing_time
    else:
        is_open = True

    if not is_open or not restaurant.can_accept_orders:
        from flask import flash, redirect, url_for
        flash("Restaurant is currently not accepting orders", "warning")
        return redirect(url_for("home"))

    if not restaurant.sheet_url:
        return "Error: No Google Sheet URL set"

    # ================= LOAD SHEET =================
    df = pd.read_csv(restaurant.sheet_url)
    print("RAW SHEET DATA:\n", df.head())

    df = df.fillna("")

    # ================= REORDER DATA =================
    reorder_map = {}

    if current_user.is_authenticated:

        raw = (
            db.session.query(
                OrderItem.item_name,
                func.count(OrderItem.id)
            )
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.customer_id == current_user.id)
            .group_by(OrderItem.item_name)
            .all()
        )

        reorder_map = {
            normalize_name(name): count
            for name, count in raw
        }

    print("\n================ USER REORDER MAP =================")
    print(reorder_map)

    # ================= PROCESS ITEMS =================
    items = []

    for i, item in enumerate(df.to_dict(orient="records")):

        price_raw = str(item.get("price", "")).strip()
        weight_raw = str(item.get("weight_prices", "")).strip()

        print(f"ITEM {i}: name={item.get('name')}, price_raw='{price_raw}', weight_raw='{weight_raw}'")

        # PRICE
        try:
            item["price"] = float(price_raw) if price_raw else 0
        except Exception as e:
            print(f"⚠️ PRICE PARSE ERROR for {item.get('name')}: {e}")
            item["price"] = 0

        item["weight_prices"] = weight_raw

        # 🔥 NORMALIZED REORDER COUNT
        item_name = normalize_name(item.get("name", ""))
        item["reorder_count"] = reorder_map.get(item_name, 0)

        print(f"NORMALIZED NAME: {item_name}")
        print(f"REORDER COUNT: {item['reorder_count']}")

        items.append(item)

    # ================= GROUP BY CATEGORY =================
    menu_by_category = {}

    for item in items:
        category = item.get("category", "Other")
        menu_by_category.setdefault(category, []).append(item)

    print("✅ MENU BY CATEGORY:\n", menu_by_category)

    # ================= RENDER =================
    if restaurant.category_type == "bakery":
        print("👉 Loading BAKERY menu")
        return render_template(
            "bakery_menu.html",
            restaurant=restaurant,
            menu_by_category=menu_by_category
        )

    print("👉 Loading NORMAL restaurant menu")
    return render_template(
        "menu.html",
        restaurant=restaurant,
        menu_by_category=menu_by_category
    )

@app.route("/restaurant/assign_delivery/<int:order_id>", methods=["POST"])
def restaurant_assign_delivery(order_id):
    if not session.get("restaurant_logged_in"):
        return redirect(url_for("restaurant_login"))

    delivery_person_id = request.form.get("delivery_person_id")
    order = Order.query.get(order_id)

    if not order:
        flash("Order not found!", "danger")
        return redirect(url_for("restaurant_dashboard"))

    dp = DeliveryPerson.query.get(int(delivery_person_id))
    if not dp:
        flash("Delivery person not found!", "danger")
        return redirect(url_for("restaurant_dashboard"))

    # ✅ Assign delivery boy
    order.delivery_person_id = dp.id
    order.delivery_boy_name = dp.name
    order.delivery_boy_phone = dp.phone
    order.status = "Out for Delivery"

    db.session.commit()  # 🔴 MUST commit before emit

    # 🔔 SEND REAL-TIME NOTIFICATION TO DELIVERY PERSON (ADD HERE)
    socketio.emit(
        "new_order_assigned",
        {
            "order_id": order.id,
            "order_number": order.order_id,
            "restaurant": order.restaurant.name
        },
        room=f"delivery_{dp.id}"
    )
    socketio.emit(
        "delivery_assigned",
        {
            "order_id": order.id,
            "delivery_person_name": dp.name,
            "delivery_person_phone": dp.phone,
            "status": order.status
        },
        room=f"order_{order.id}"
    )
    flash(f"Delivery boy {dp.name} assigned to Order {order.order_id}", "success")
    return redirect(url_for("restaurant_dashboard"))

@app.route("/delivery/start/<int:order_id>", methods=["POST"])
def start_delivery(order_id):
    order = Order.query.get(order_id)

    print("BEFORE STATUS:", order.status)   # 👈 ADD
    order.status = "Started"
    db.session.commit()
    print("AFTER STATUS:", order.status)    # 👈 ADD

    return jsonify(success=True)

@app.route("/admin/restaurant/edit/<int:restaurant_id>", methods=["GET", "POST"])
def edit_restaurant(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    
    if request.method == "POST":
        restaurant.name = request.form["name"]
        restaurant.sheet_url = request.form.get("sheet_url")  # optional
        db.session.commit()
        flash("Restaurant updated successfully!", "success")
        return redirect(url_for("admin_dashboard"))
    
    return render_template("edit_restaurant.html", restaurant=restaurant)




@app.route("/delivery/history")
def delivery_history():
    delivery_person_id = session.get("delivery_person_id")
    if not delivery_person_id:
        return redirect(url_for("delivery_login"))

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    # ✅ ONLY completed orders
    history = Order.query.filter(
        Order.delivery_person_id == delivery_person_id,
        Order.status.in_(["Delivered", "Customer Not Available"])
    ).order_by(Order.updated_at.desc()).all()

    # ✅ Classify orders by day
    for o in history:
        if o.created_at.date() == today:
            o.day_category = "Today"
        elif o.created_at.date() == yesterday:
            o.day_category = "Yesterday"
        else:
            o.day_category = "Older"

    # ✅ Day-wise totals (Delivered only)
    totals = {}
    for day in ["Today", "Yesterday", "Older"]:
        day_orders = [
            o for o in history
            if o.day_category == day and o.status == "Delivered"
        ]

        cod_amount = sum(
            o.get_final_total() for o in day_orders if o.payment_type == "COD"
        )

        online_amount = sum(
            o.get_final_total() for o in day_orders if o.payment_type == "Online"
        )

        delivery_charge_total = sum(
            o.delivery_charge or 0 for o in day_orders
        )

        totals[day] = {
            "count": len(day_orders),
            "cod_amount": cod_amount,
            "online_amount": online_amount,
            "delivery_charge": delivery_charge_total,
            "grand_total": cod_amount + online_amount + delivery_charge_total
        }

    # ✅ ALL TOTALS (Today + Yesterday + Older)
    all_totals = {
        "count": sum(totals[d]["count"] for d in totals),
        "cod_amount": sum(totals[d]["cod_amount"] for d in totals),
        "online_amount": sum(totals[d]["online_amount"] for d in totals),
        "delivery_charge": sum(totals[d]["delivery_charge"] for d in totals),
    }

    all_totals["grand_total"] = (
        all_totals["cod_amount"]
        + all_totals["online_amount"]
        + all_totals["delivery_charge"]
    )

    return render_template(
        "delivery_history.html",
        history=history,
        totals=totals,
        all_totals=all_totals
    )


@app.route("/delivery/mark-delivered", methods=["POST"])
def delivery_mark_delivered():
    delivery_person_id = session.get("delivery_person_id")

    if not delivery_person_id:
        return redirect(url_for("delivery_login"))

    order_id = request.form.get("order_id")
    otp_entered = request.form.get("otp")

    order = Order.query.get(order_id)

    if not order:
        return "Order not found", 404

    # OTP CHECK
    if order.otp != otp_entered:
        return "Invalid OTP", 400

    # MARK AS DELIVERED
    order.status = "Delivered"
    order.delivered_time = datetime.utcnow()

    db.session.commit()

    return redirect(url_for("delivery_dashboard"))

def generate_otp():
    # using secrets is good
    return str(secrets.randbelow(900000) + 100000)

def generate_order_id(order_db_id):
    # call AFTER you saved order to DB (so order_db_id exists)
    unique_part = uuid.uuid4().hex[:6].upper()
    return f"ORD-{order_db_id}-{unique_part}"

from datetime import datetime

from flask import jsonify
from datetime import datetime

from flask import request, jsonify, flash, redirect, url_for

from models import Order  # ensure your Order model is imported
@app.route("/confirm_delivery/<int:order_id>", methods=["POST"])
def confirm_delivery(order_id):
    entered_otp = request.form.get("entered_otp")
    payment_type = request.form.get("payment_type")

    order = Order.query.get(order_id)

    if not order or order.otp != entered_otp:
        return jsonify({"success": False})

    order.status = "Delivered"
    order.payment_type = payment_type
    order.delivered_time = datetime.utcnow()
    order.otp = None  # 🔥 invalidate OTP
    db.session.commit()

    return jsonify({"success": True})

@app.route('/api/admin-orders')
def admin_orders_api():
    orders = Order.query.order_by(Order.id.desc()).all()

    return {
        "orders": [
            {
                "id": o.id,
                "order_id": o.order_id,
                "restaurant": o.restaurant.name,
                "customer": o.customer_name,
                "phone": o.phone,
                "items": [
                    {
                        "name": i.item_name,
                        "qty": i.quantity,
                        "price": i.price
                    } for i in o.items
                ],
                "total": o.get_final_total(),
                "status": o.status,
                "time": o.created_at.strftime("%d-%m-%Y %H:%M"),
            }
            for o in orders
        ]
    }
@app.route("/restaurant/orders_partial")
def restaurant_orders_partial():
    if not session.get("restaurant_logged_in"):
        return "Not logged in", 403

    restaurant_id = session.get("restaurant_id")
    orders = Order.query.filter_by(restaurant_id=restaurant_id).order_by(Order.created_at.desc()).all()

    return render_template("partials/orders_table.html", orders=orders)

# ------------------ API ------------------
@app.route("/api/order_status/<order_id>")
def get_status(order_id):
    order = Order.query.filter_by(order_id=order_id).first()
    if not order:
        return jsonify({"success": False}), 404
    return jsonify({
        "success": True,
        "order": {
            "order_id": order.order_id,
            "status": order.status,
            "otp": order.otp,
            "total_price": order.get_final_total()
        }
    })

from sqlalchemy.orm import joinedload


@app.route('/restaurants')
def restaurants_page():
    selected_location = request.args.get('location', '')

    query = Restaurant.query.options(joinedload(Restaurant.categories))

    if selected_location:
        query = query.filter_by(location=selected_location)

    restaurants = query.all()

    all_locations = [
        loc[0]
        for loc in db.session.query(Restaurant.location).distinct().all()
        if loc[0]
    ]
    print("Total restaurants in DB:", Restaurant.query.count())
    print("Restaurants sent to page:", len(restaurants))

    for r in restaurants:
        print(r.id, r.name)
    print("====== DEBUG RESTAURANTS ======")
    print("Selected Location:", selected_location)
    print("Total Restaurants In DB:", Restaurant.query.count())
    print("Restaurants After Filter:", len(restaurants))

    for r in restaurants:
        print("SHOWING:", r.id, r.name, r.location)
    print("================================")


    return render_template(
        'index.html',
        restaurants=restaurants,
        all_locations=all_locations,
        selected_location=selected_location
    )

@app.route("/restaurant/delivery_boys_cod_summary", methods=["GET"])
def delivery_boys_cod_summary():
    restaurant_id = session.get("restaurant_id")
    if not restaurant_id:
        return redirect(url_for("restaurant_login"))

    # Get date filter from query params
    date_str = request.args.get("date")
    if date_str:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        selected_date = datetime.utcnow().date()

    # Get all delivered orders for the selected date
    orders = Order.query.filter_by(restaurant_id=restaurant_id, status="Delivered").filter(
        db.func.date(Order.delivered_time) == selected_date
    ).all()

    # Create COD summary per delivery person
    cod_summary = {}
    for order in orders:
        dp = order.delivery_person.name if order.delivery_person else "Unassigned"
        if dp not in cod_summary:
            cod_summary[dp] = {"COD": 0, "Online": 0, "Total": 0, "Orders": 0}

        if order.payment_type == "COD":
            cod_summary[dp]["COD"] += order.get_final_total()
        elif order.payment_type == "Online":
            cod_summary[dp]["Online"] += order.get_final_total()

        cod_summary[dp]["Total"] += order.get_final_total()
        cod_summary[dp]["Orders"] += 1

    return render_template(
        "delivery_boys.html",
        cod_summary=cod_summary,
        date=selected_date
    )
from datetime import datetime
from sqlalchemy import func

from flask import session, redirect, url_for, request, render_template
from datetime import datetime
from sqlalchemy import func, case 
from flask import session, redirect, url_for, request, render_template
from datetime import datetime
from sqlalchemy import func
from app import db
from models import Order, OrderItem
from flask import render_template, request, session, redirect, url_for
from datetime import datetime
from models import Order, db

@app.route("/restaurant/reports", methods=["GET", "POST"])
def restaurant_reports():
    restaurant_id = session.get("restaurant_id")
    if not restaurant_id:
        return redirect(url_for("restaurant_login"))

    from_date = request.form.get("from_date")
    to_date = request.form.get("to_date")

    # Base query for the restaurant
    query = Order.query.filter_by(restaurant_id=restaurant_id)
    if from_date:
        query = query.filter(Order.created_at >= datetime.strptime(from_date, "%Y-%m-%d"))
    if to_date:
        query = query.filter(Order.created_at <= datetime.strptime(to_date, "%Y-%m-%d"))

    orders = query.all()

    # Initialize totals
    total_orders = len(orders)
    delivered_orders = 0
    cancelled_orders = 0
    total_items_total = 0
    total_delivery_total = 0
    total_coupon_discount = 0
    total_restaurant_offer_discount = 0
    total_earnings = 0
    cod_amount = 0
    online_amount = 0

    daywise = {}

    for o in orders:
        day = o.created_at.strftime("%d-%m-%Y")
        if day not in daywise:
            daywise[day] = {
                "orders": 0,
                "delivered": 0,
                "cancelled": 0,
                "items_total": 0,
                "delivery_total": 0,
                "coupon_discount": 0,
                "restaurant_offer_discount": 0,
                "grand_total": 0
            }

        daywise[day]["orders"] += 1

        if o.status == "Delivered":
            delivered_orders += 1

            # Compute totals
            items_total = sum(i.quantity * i.price for i in o.items)
            delivery_total = o.delivery_charge or 0
            restaurant_offer_discount = o.restaurant_offer_discount or 0
            coupon_discount = o.discount or 0  # <-- discount is now ONLY coupon

            # Update totals
            total_items_total += items_total
            total_delivery_total += delivery_total
            total_coupon_discount += coupon_discount
            total_restaurant_offer_discount += restaurant_offer_discount

            grand_total = items_total + delivery_total - coupon_discount - restaurant_offer_discount
            total_earnings += grand_total

            # COD / Online
            if o.payment_type == "COD":
                cod_amount += grand_total

            # Daywise aggregation
            daywise[day]["delivered"] += 1
            daywise[day]["items_total"] += items_total
            daywise[day]["delivery_total"] += delivery_total
            daywise[day]["coupon_discount"] += coupon_discount
            daywise[day]["restaurant_offer_discount"] += restaurant_offer_discount
            daywise[day]["grand_total"] += grand_total

        elif o.status == "Cancelled":
            cancelled_orders += 1
            daywise[day]["cancelled"] += 1

    online_amount = total_earnings - cod_amount

    return render_template(
        "restaurant_reports.html",
        total_orders=total_orders,
        delivered_orders=delivered_orders,
        cancelled_orders=cancelled_orders,
        total_items_total=total_items_total,
        total_delivery_total=total_delivery_total,
        total_coupon_discount=total_coupon_discount,
        total_restaurant_offer_discount=total_restaurant_offer_discount,
        total_earnings=total_earnings,
        cod_amount=cod_amount,
        online_amount=online_amount,
        daywise=daywise,
        from_date=from_date,
        to_date=to_date
    )



from sqlalchemy import case, func
from datetime import datetime

from flask import render_template, request
from sqlalchemy import func, case

from models import Restaurant, Order, OrderItem
from sqlalchemy import func, case
from models import Restaurant, Order, OrderItem
from sqlalchemy import func, case
@app.route("/admin/reports")
def admin_reports():
    restaurants = Restaurant.query.all()

    restaurant_id = request.args.get("restaurant_id")
    report_type = request.args.get("type", "day")   # day / week
    from_date = request.args.get("from")
    to_date = request.args.get("to")

    # =====================================================
    # CASE STATEMENTS
    # =====================================================
    delivered_case = case((Order.status == "Delivered", 1), else_=0)
    cancelled_case = case((Order.status == "Cancelled", 1), else_=0)

    items_case = case((Order.status == "Delivered", Order.items_total), else_=0)
    delivery_case = case((Order.status == "Delivered", Order.delivery_charge), else_=0)

    coupon_discount_case = case((Order.status == "Delivered", Order.discount), else_=0)
    restaurant_offer_case = case(
        (Order.status == "Delivered", Order.restaurant_offer_discount),
        else_=0
    )

    # =====================================================
    # MAIN REPORT (PER RESTAURANT / DAY / WEEK)
    # =====================================================
    query = (
        db.session.query(
            Restaurant.name.label("restaurant"),

            func.count(func.distinct(Order.id)).label("total_orders"),
            func.sum(delivered_case).label("delivered"),
            func.sum(cancelled_case).label("cancelled"),

            func.coalesce(func.sum(items_case), 0).label("items_total"),
            func.coalesce(func.sum(delivery_case), 0).label("delivery_total"),
            func.coalesce(func.sum(coupon_discount_case), 0).label("coupon_discount_total"),
            func.coalesce(func.sum(restaurant_offer_case), 0).label("restaurant_offer_total"),

            (
                func.coalesce(func.sum(items_case), 0)
                + func.coalesce(func.sum(delivery_case), 0)
                - func.coalesce(func.sum(coupon_discount_case), 0)
                - func.coalesce(func.sum(restaurant_offer_case), 0)
            ).label("total_earning")
        )
        .join(Order, Order.restaurant_id == Restaurant.id)
        .group_by(Restaurant.name)
    )

    # ---------- FILTERS ----------
    if restaurant_id:
        query = query.filter(Order.restaurant_id == restaurant_id)

    if from_date and to_date:
        query = query.filter(Order.created_at.between(from_date, to_date))

    # ---------- GROUPING ----------
    if report_type == "day":
        query = query.add_columns(
            func.date(Order.created_at).label("period")
        ).group_by(Restaurant.name, func.date(Order.created_at))
    else:
        query = query.add_columns(
            func.strftime('%Y-%W', Order.created_at).label("period")
        ).group_by(Restaurant.name, func.strftime('%Y-%W', Order.created_at))

    query = query.order_by(func.date(Order.created_at).desc())
    reports = query.all()

    # =====================================================
    # PER-RESTAURANT SUMMARY (NO DATE GROUPING)
    # =====================================================
    summary_query = (
        db.session.query(
            Restaurant.name.label("restaurant"),

            func.coalesce(func.sum(items_case), 0).label("items_total"),
            func.coalesce(func.sum(delivery_case), 0).label("delivery_total"),
            func.coalesce(func.sum(coupon_discount_case), 0).label("coupon_discount_total"),
            func.coalesce(func.sum(restaurant_offer_case), 0).label("restaurant_offer_total"),

            (
                func.coalesce(func.sum(items_case), 0)
                + func.coalesce(func.sum(delivery_case), 0)
                - func.coalesce(func.sum(coupon_discount_case), 0)
                - func.coalesce(func.sum(restaurant_offer_case), 0)
            ).label("total_earning")
        )
        .join(Order, Order.restaurant_id == Restaurant.id)
        .group_by(Restaurant.name)
    )

    if restaurant_id:
        summary_query = summary_query.filter(Order.restaurant_id == restaurant_id)

    if from_date and to_date:
        summary_query = summary_query.filter(Order.created_at.between(from_date, to_date))

    summary = summary_query.all()

    # =====================================================
    # 🌍 OVERALL PLATFORM SUMMARY (ALL RESTAURANTS)
    # =====================================================
    overall_query = db.session.query(
        func.count(Order.id).label("total_orders"),
        func.sum(delivered_case).label("delivered_orders"),
        func.sum(cancelled_case).label("cancelled_orders"),

        func.coalesce(func.sum(items_case), 0).label("items_total"),
        func.coalesce(func.sum(delivery_case), 0).label("delivery_total"),
        func.coalesce(func.sum(coupon_discount_case), 0).label("coupon_discount_total"),
        func.coalesce(func.sum(restaurant_offer_case), 0).label("restaurant_offer_total"),

        (
            func.coalesce(func.sum(items_case), 0)
            + func.coalesce(func.sum(delivery_case), 0)
            - func.coalesce(func.sum(coupon_discount_case), 0)
            - func.coalesce(func.sum(restaurant_offer_case), 0)
        ).label("grand_total")
    )

    if restaurant_id:
        overall_query = overall_query.filter(Order.restaurant_id == restaurant_id)

    if from_date and to_date:
        overall_query = overall_query.filter(Order.created_at.between(from_date, to_date))

    overall = overall_query.first()

    # =====================================================
    # RENDER
    # =====================================================
    return render_template(
        "admin_reports.html",
        restaurants=restaurants,
        reports=reports,
        summary=summary,
        overall=overall,
        report_type=report_type,
        selected_restaurant=restaurant_id,
        from_date=from_date,
        to_date=to_date
    )
@app.route("/delivery/not-delivered/<int:order_id>", methods=["POST"])
def mark_not_delivered(order_id):
    order = Order.query.get(order_id)

    if not order:
        return {"success": False, "message": "Order not found"}, 404

    data = request.get_json()
    reason = data.get("reason")

    order.status = "Customer Not Available"
    order.not_delivered_reason = reason
    order.not_delivered_time = datetime.utcnow()
    order.delivery_attempts = (order.delivery_attempts or 0) + 1

    db.session.commit()

    # 🔔 Notify restaurant (example)
    print(f"📢 Notify Restaurant {order.restaurant_id}: Order {order.order_id} failed")

    return {"success": True}
@app.route("/feedback/<int:order_id>", methods=['POST'])
def delivery_feedback(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.get_json()
    feedback = data.get('feedback', '')

    order.delivery_feedback = feedback
    order.status = "Delivery Failed"
    db.session.commit()

    return jsonify({"success": True})
@app.route("/delivery_feedback_notifications")
def delivery_feedback_notifications():
    feedbacks = Order.query.filter(Order.not_delivered_reason != None).order_by(Order.not_delivered_time.asc()).all()
    return jsonify([{"order_id": f.order_id, "message": f.not_delivered_reason} for f in feedbacks])



from datetime import datetime
from flask import request, jsonify

@app.route("/order-success")
def order_success():
    return render_template("order_success.html")
from flask import flash

@app.route("/add_to_cart/<int:restaurant_id>/<int:item_id>")
def add_to_cart(restaurant_id, item_id):

    cart = session.get("cart", [])
    cart_restaurant_id = session.get("cart_restaurant_id")

    # If cart has items from another restaurant
    if cart_restaurant_id and cart_restaurant_id != restaurant_id:
        flash("Your cart had items from another restaurant. Cart cleared.")
        cart = []

    # Get item from DB
    item = MenuItem.query.get_or_404(item_id)

    session["cart_restaurant_id"] = restaurant_id

    # Check if item already in cart
    for c in cart:
        if c["id"] == item.id:
            c["quantity"] += 1
            break
    else:
        cart.append({
            "id": item.id,
            "name": item.name,
            "price": float(item.price),
            "quantity": 1
        })

    session["cart"] = cart
    session["cart_count"] = sum(i["quantity"] for i in cart)

    return redirect(url_for("cart_page")) 
@login_manager.user_loader
def load_user(user_id):
    return Customer.query.get(int(user_id))
from flask_login import login_required, current_user

@app.route("/profile")
@login_required
def profile():
    print("USER:", current_user.is_authenticated)
    print("USER ID:", current_user.get_id())

    return render_template(
        "profile.html",
        logged_in=True,
        customer=current_user
    )


# Logout
from flask_login import logout_user

@app.route("/logout")
@login_required
def logout():

    logout_user()         # Flask-Login logout
    session.clear()       # Clear all session data

    response = redirect(url_for("users.login"))
    response.delete_cookie(app.config['SESSION_COOKIE_NAME'])

    flash("Logged out successfully", "success")

    return response
    return response
@app.route("/test-otp")
def test_otp():
    return render_template("test_otp.html")


@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    mobile = request.form.get("mobile")
    if not mobile:
        flash("Mobile number required")
        return redirect(url_for("login"))

    otp = str(random.randint(100000, 999999))
    otp_record = OTP(mobile=mobile, otp=otp, created_at=datetime.utcnow())
    db.session.add(otp_record)
    db.session.commit()
    
    session["mobile"] = mobile
    print(f"OTP for {mobile}: {otp}")
    flash("OTP resent successfully")
    return redirect(url_for("verify_otp"))
from flask import request, jsonify
from models import Order  # make sure you import your Order model
from sqlalchemy import func

@app.route("/apply_coupon", methods=["POST"])
def apply_coupon():
    data = request.get_json()

    phone = data.get("phone")
    device_fingerprint = data.get("device_fingerprint")
    coupon_code = data.get("coupon_code")
    items_total = float(data.get("items_total", 0))

    if not phone or not device_fingerprint:
        return jsonify({"success": False, "message": "Phone number is required."})

    # Only FIRST30 coupon supported for now
    if coupon_code != "FIRST20":
        return jsonify({"success": False, "message": "Invalid coupon code."})

    # Check if user has any delivered orders (first-time check)
    delivered_orders = Order.query.filter(
        ((Order.phone == phone) | (Order.device_fingerprint == device_fingerprint)) &
        (func.lower(Order.status) == "delivered")
    ).count()

    if delivered_orders > 0:
        return jsonify({"success": False, "message": "Coupon valid for first-time users only."})

    # Minimum items total to apply coupon
    if items_total < 599:
        return jsonify({"success": False, "message": "Order must be at least ₹599 to apply coupon."})

    # Apply discount: 20% off capped at 20
    discount = min(items_total * 0.20, 20)
    return jsonify({
        "success": True,
        "discount": discount,
        "message": f"Coupon applied! You saved ₹{discount}"
    }) 
 




# ---------------- MANAGE OFFERS ----------------
@app.route("/dashboard/<int:restaurant_id>/offers")
def manage_offers(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    offers = RestaurantOffer.query.filter_by(restaurant_id=restaurant_id).all()
    active_offer = RestaurantOffer.query.filter_by(
        restaurant_id=restaurant_id, is_active=True
    ).first()
    return render_template("dashboard/manage_offers.html",
                           restaurant=restaurant,
                           offers=offers,
                           active_offer=active_offer)


# ---------------- ADD OFFER ----------------
@app.route("/dashboard/offers/<int:restaurant_id>/add", methods=["GET", "POST"])
def add_offer(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        offer_type = request.form.get("offer_type")
        offer_value = float(request.form.get("offer_value") or 0)
        min_order_amount = float(request.form.get("min_order_amount") or 0)
        start_date = request.form.get("start_date")
        end_date = request.form.get("end_date")
        is_active = True if request.form.get("is_active") else False

        new_offer = RestaurantOffer(
            restaurant_id=restaurant_id,
            title=title,
            description=description,
            offer_type=offer_type,
            offer_value=offer_value,
            min_order_amount=min_order_amount,
            start_date=datetime.strptime(start_date, "%Y-%m-%d") if start_date else None,
            end_date=datetime.strptime(end_date, "%Y-%m-%d") if end_date else None,
            is_active=is_active
        )
        db.session.add(new_offer)
        db.session.commit()
        flash("Offer added successfully", "success")
        return redirect(url_for("manage_offers", restaurant_id=restaurant_id))

    return render_template("dashboard/add_offer.html", restaurant=restaurant)

# ---------------- EDIT OFFER ----------------
@app.route("/dashboard/offers/<int:offer_id>/edit", methods=["GET", "POST"])
def edit_offer(offer_id):
    offer = RestaurantOffer.query.get_or_404(offer_id)
    restaurant = Restaurant.query.get_or_404(offer.restaurant_id)

    if request.method == "POST":
        offer.title = request.form.get("title")
        offer.description = request.form.get("description")
        offer.offer_type = request.form.get("offer_type")
        offer.offer_value = float(request.form.get("offer_value") or 0)
        offer.min_order_amount = float(request.form.get("min_order_amount") or 0)
        offer.start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d") if request.form.get("start_date") else None
        offer.end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d") if request.form.get("end_date") else None
        offer.is_active = True if request.form.get("is_active") else False

        db.session.commit()
        flash("Offer updated successfully", "success")
        return redirect(url_for("manage_offers", restaurant_id=restaurant.id))

    return render_template("dashboard/edit_offer.html", offer=offer, restaurant=restaurant)

# ---------------- DELETE OFFER ----------------
@app.route("/dashboard/offers/<int:offer_id>/delete", methods=["POST"])
def delete_offer(offer_id):
    offer = RestaurantOffer.query.get_or_404(offer_id)
    restaurant_id = offer.restaurant_id
    db.session.delete(offer)
    db.session.commit()
    flash("Offer deleted successfully", "success")
    return redirect(url_for("manage_offers", restaurant_id=restaurant_id))
NEW_DAYS = 3

def is_new_restaurant(restaurant):
    if not restaurant.created_at:
        return False
    return restaurant.created_at >= datetime.utcnow() - timedelta(days=NEW_DAYS)
def is_open_now(restaurant):
    if not restaurant.opening_time or not restaurant.closing_time:
        return False

    tz = pytz.timezone(restaurant.timezone)
    now = datetime.now(tz).time()

    open_t = restaurant.opening_time
    close_t = restaurant.closing_time

    # Normal same-day timing
    if open_t <= close_t:
        return restaurant.is_accepting_orders and open_t <= now <= close_t

    # Overnight timing (e.g. 7 PM – 2 AM)
    return restaurant.is_accepting_orders and (now >= open_t or now <= close_t)
from datetime import date
import random

def get_sorted_restaurants(restaurants):
    random.seed(date.today().toordinal())

    def sort_key(r):
        new = is_new_restaurant(r)
        open_now = r.is_open
        accepting = r.can_accept_orders
        deliverable = r.deliverable

        available = open_now and accepting and deliverable

        # 1️⃣ NEW + AVAILABLE → TOP
        if new and available:
            return (0, -r.created_at.timestamp())

        # 2️⃣ AVAILABLE → MIDDLE (daily rotation)
        if available:
            return (1, random.random())

        # 3️⃣ NEW but NOT AVAILABLE
        if new and not available:
            return (2, -r.created_at.timestamp())

        # 4️⃣ EVERYTHING ELSE → BOTTOM
        return (3,)

    restaurants.sort(key=sort_key)
    return restaurants



from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

def ist_to_utc(dt_str):
    local_dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M")
    local_dt = IST.localize(local_dt)
    return local_dt.astimezone(pytz.utc)

from datetime import datetime
from flask import request, render_template, redirect, url_for, flash



@app.route("/dashboard/restaurant/<int:restaurant_id>/edit", methods=["GET", "POST"])
def edit_restaurant_card(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    categories = Category.query.all()
    if request.method == "POST":
        # 1️⃣ Get selected category IDs from form
        selected_ids = request.form.getlist("categories")
        print("Selected IDs:", selected_ids)

        # 2️⃣ Fetch Category objects from DB
        if selected_ids:
            selected_categories = Category.query.filter(
                Category.id.in_(selected_ids)
            ).all()
        else:
            selected_categories = []

        # 3️⃣ Assign categories to the restaurant
        restaurant.categories = selected_categories

        # 4️⃣ Commit changes
        db.session.commit()  # no need to flush separately here

        # 5️⃣ Debug: print categories
        print("AFTER COMMIT:", [(c.id, c.name) for c in restaurant.categories])



        # ================= BASIC INFO =================
        restaurant.name = request.form.get("name", "").strip()
        restaurant.address = request.form.get("address")
        restaurant.phone = request.form.get("phone")
        restaurant.email = request.form.get("email")

        # ================= CATEGORY TYPE =================
        category = request.form.get("category_type")
        restaurant.category_type = category if category in ["restaurant", "bakery"] else "restaurant"

        # ================= CARD DETAILS =================
        restaurant.is_veg = request.form.get("is_veg") == "yes"
        restaurant.rating = float(request.form.get("rating") or 4.0)
        restaurant.price_level = request.form.get("price_level")
        restaurant.delivery_time = request.form.get("delivery_time")
        restaurant.popular_items = request.form.get("popular_items")
        

        # ================= DELIVERY =================
        restaurant.delivery_charge = float(request.form.get("delivery_charge") or 30)
        restaurant.free_delivery_limit = float(request.form.get("free_delivery_limit") or 499)
        restaurant.latitude = request.form.get("latitude") or None
        restaurant.longitude = request.form.get("longitude") or None
        restaurant.delivery_radius_km = float(request.form.get("delivery_radius_km") or 5)
        restaurant.force_delivery_charge = request.form.get("force_delivery_charge") == "1"

        # ================= OPEN / CLOSE =================
        restaurant.opening_time = (
            datetime.strptime(request.form.get("opening_time"), "%H:%M").time()
            if request.form.get("opening_time") else None
        )

        restaurant.closing_time = (
            datetime.strptime(request.form.get("closing_time"), "%H:%M").time()
            if request.form.get("closing_time") else None
        )

        # ================= ACCEPT ORDERS =================
        restaurant.is_accepting_orders = request.form.get("is_accepting_orders") == "1"
        restaurant.accept_orders_until = (
            datetime.strptime(request.form.get("accept_orders_until"), "%H:%M").time()
            if request.form.get("accept_orders_until") else None
        )

        # ================= START DATE =================
        restaurant.start_date = (
            datetime.strptime(request.form.get("start_date"), "%Y-%m-%d").date()
            if request.form.get("start_date") else None
        )

        # ================= STATUS =================
        status = request.form.get("status")
        if status in ["active", "coming_soon", "suspended"]:
            restaurant.status = status

        if restaurant.status == "coming_soon" and not restaurant.start_date:
            flash("Start date is required for Coming Soon", "danger")
            return redirect(request.url)

        # ================= LIMITED DROP =================
        restaurant.is_limited_drop = request.form.get("is_limited_drop") == "1"
        restaurant.limited_item_name = request.form.get("limited_item_name") or None
        restaurant.limited_total_qty = int(request.form.get("limited_total_qty") or 0)
        restaurant.limited_remaining_qty = int(request.form.get("limited_remaining_qty") or 0)

        start_raw = request.form.get("limited_start_datetime")
        end_raw   = request.form.get("limited_end_datetime")
        
        # ---- Store as UTC (SINGLE SOURCE OF TRUTH) ----
        if restaurant.is_limited_drop:
            if start_raw and end_raw:
                restaurant.limited_start_datetime = ist_to_utc(start_raw)
                restaurant.limited_end_datetime   = ist_to_utc(end_raw)
            else:
                restaurant.limited_start_datetime = None
                restaurant.limited_end_datetime = None
        else:
            restaurant.limited_start_datetime = None
            restaurant.limited_end_datetime = None

        # ================= VALIDATION =================
        if restaurant.is_limited_drop:

            if not restaurant.limited_item_name:
                flash("Limited item name is required", "danger")
                return redirect(request.url)

            if restaurant.limited_total_qty <= 0:
                flash("Total quantity must be greater than 0", "danger")
                return redirect(request.url)

            if not restaurant.limited_start_datetime or not restaurant.limited_end_datetime:
                flash("Start and End time required", "danger")
                return redirect(request.url)

            if restaurant.limited_end_datetime <= restaurant.limited_start_datetime:
                flash("End time must be after start time", "danger")
                return redirect(request.url)

        # ================= DEBUG LOGS =================
        print("RAW FORM START:", start_raw)
        print("RAW FORM END:", end_raw)
        print("UTC START:", restaurant.limited_start_datetime)
        print("UTC END:", restaurant.limited_end_datetime)

        if restaurant.limited_start_datetime and restaurant.limited_end_datetime:
            hours = (
                restaurant.limited_end_datetime - restaurant.limited_start_datetime
            ).total_seconds() / 3600
        else:
            hours = 0

        print("HOURS:", hours)

        # ================= SAVE =================
        db.session.commit()
        flash("Restaurant updated successfully!", "success")
        return redirect(url_for("restaurant_dashboard", restaurant_id=restaurant.id))

    # ================= DISPLAY FORM =================
    restaurant.limited_start_local = restaurant.limited_start_datetime
    restaurant.limited_end_local = restaurant.limited_end_datetime

    return render_template(
        "dashboard/edit_restaurant_card.html",
        restaurant=restaurant,
        categories=categories
    )


@app.route('/toggle-offer/<int:offer_id>', methods=['POST'])
def toggle_offer_status(offer_id):
    offer = RestaurantOffer.query.get_or_404(offer_id)

    # Toggle status
    offer.is_active = not offer.is_active

    # Optional: ensure only ONE active offer per restaurant
    if offer.is_active:
        RestaurantOffer.query.filter(
            RestaurantOffer.restaurant_id == offer.restaurant_id,
            RestaurantOffer.id != offer.id
        ).update({RestaurantOffer.is_active: False})

    db.session.commit()
    flash("Offer status updated", "success")

    return redirect(request.referrer)

from datetime import datetime
def get_active_offer_for_restaurant(restaurant_id, device_fingerprint=None):
    now = datetime.utcnow()
    offer = RestaurantOffer.query.filter(
        RestaurantOffer.restaurant_id == restaurant_id,
        RestaurantOffer.is_active == True,
        RestaurantOffer.start_date <= now,
        RestaurantOffer.end_date >= now
    ).order_by(RestaurantOffer.id.desc()).first()

    already_used = False
    if offer and device_fingerprint:
        used_orders = Order.query.filter(
            Order.restaurant_offer_id == offer.id,
            Order.device_fingerprint == device_fingerprint
        ).count()
        if used_orders > 0:
            already_used = True

    return {
        "id": offer.id if offer else None,
        "title": offer.title if offer else "",
        "offer_value": offer.offer_value if offer else 0,
        "offer_type": offer.offer_type if offer else "",
        "min_order_amount": offer.min_order_amount if offer else 0,
        "already_used": already_used
    }
from flask import request, jsonify, session
from models import Order, RestaurantOffer
@app.route("/check_restaurant_offer", methods=["POST"])
def check_restaurant_offer():
    data = request.get_json()
    restaurant_id = data.get("restaurant_id")
    phone = data.get("phone")
    device_fingerprint = data.get("device_fingerprint")

    if not phone:
        return jsonify({
            "allowed": False,
            "message": "Enter your mobile number to unlock restaurant offers"
        })

    offer_data = get_active_offer_for_restaurant(
        restaurant_id,
        device_fingerprint
    )

    if not offer_data["id"]:
        return jsonify({
            "allowed": False,
            "message": "No active offer available for this restaurant"
        })

    if offer_data["already_used"]:
        return jsonify({
            "allowed": False,
            "message": "You have already used this restaurant offer"
        })

    return jsonify({
        "allowed": True,
        "offer_value": offer_data["offer_value"],
        "offer_type": offer_data["offer_type"],
        "min_order": offer_data["min_order_amount"],
        "title": offer_data["title"]
    })


import requests

FAST2SMS_API_KEY = "XM6Cc7mISMEJMng26lBEHgxUZjiwNIGRDFHKdbYXSsVjlXqeC2padqOTqeS2"

def send_otp_fast2sms(mobile, otp):
    url = "https://www.fast2sms.com/dev/bulkV2"
    payload = {
        "route": "otp",
        "variables_values": otp,
        "numbers": mobile
    }
    headers = {
        "authorization": FAST2SMS_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(url, data=payload, headers=headers)
    return response.json()


@app.route("/set_location", methods=["POST"])
def set_location():
    data = request.get_json()
    lat = data.get("lat")
    lng = data.get("lng")

    session["user_lat"] = lat
    session["user_lng"] = lng

    print("User location saved in session:", session.get("user_lat"), session.get("user_lng"))

    return jsonify({"success": True, "lat": lat, "lng": lng}) 

@app.route("/delivery/generate-otp/<int:order_id>", methods=["POST"])
def generate_delivery_otp(order_id):
    order = Order.query.get(order_id)

    if not order or order.status != "Out for Delivery":
        return jsonify({"success": False, "message": "Invalid order"})

    otp = generate_otp()
    order.otp = otp
    order.otp_generated_at = datetime.utcnow()
    db.session.commit()

    send_otp_fast2sms(order.phone, otp)

    return jsonify({"success": True, "message": "OTP sent to customer"})
from flask import session

def get_cart():
    if "cart" not in session:
        session["cart"] = {}
    return session["cart"]
# ------------------ chnageeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee-----------------
@app.route("/save_location", methods=["POST"])
def save_location():
    data = request.get_json()
    session["lat"] = data.get("lat")
    session["lng"] = data.get("lng")
    return jsonify({"status": "saved"})   
@app.route("/system_health")
def system_health():
    from datetime import datetime

    restaurants = Restaurant.query.all()
    health_data = []

    # Simulated cart
    test_items_total = 200 * 2 + 100 * 1  # = 500

    for r in restaurants:
        # 🔹 BACKEND CALCULATION (TRUTH)
        backend = calculate_totals(r, test_items_total)

        # 🔹 FRONTEND SIMULATION (what JS SHOULD do)
        frontend_delivery = r.delivery_charge or 0

        if r.free_delivery_limit and test_items_total >= r.free_delivery_limit:
            frontend_delivery = 0

        frontend_final = round(
            test_items_total
            + frontend_delivery
            - (backend["offer_discount"] + backend["coupon_discount"]),
            2
        )

        # 🔍 COMPARE
        if backend["final_total"] == frontend_final:
            health_data.append({
                "restaurant": r.name,
                "status": "green",
                "problem": ""
            })
        else:
            health_data.append({
                "restaurant": r.name,
                "status": "red",
                "problem": (
                    f"Frontend mismatch | "
                    f"Expected {backend['final_total']} "
                    f"but JS shows {frontend_final}"
                )
            })

    return render_template(
        "system_health.html",
        health_data=health_data,
        now=datetime.now()
    )

@app.route("/db-test")
def db_test():
    from sqlalchemy import text
    db.session.execute(text("SELECT 1"))
    return "PostgreSQL Connected ✅"


@app.errorhandler(404)
def page_not_found(e):
    # Fetch all active offers
    active_offers = RestaurantOffer.query.filter_by(is_active=True).all()
    
    return render_template("404.html", offers=active_offers), 404
# 🔹 Optional: handle other common errors
@app.errorhandler(500)
def server_error(e):
    return render_template("404.html"), 500 

@app.errorhandler(404)
def page_not_found(e):
    return redirect(url_for("promotions"))

@app.route("/promotions")
def promotions():
    return render_template("promotions.html")


from datetime import datetime


from flask_socketio import emit



@app.route("/track/<int:order_id>")
def track_order(order_id):
    order = Order.query.get_or_404(order_id)

    if not order.delivery_person:
        flash("Delivery boy not assigned yet", "warning")
        return redirect(url_for("myorders", restaurant_id=order.restaurant_id))
    print("📍 Customer lat/lng:", order.latitude, order.longitude)


    return render_template("track_order.html", order=order)


from flask_socketio import emit, join_room


# global or Redis (recommended)
last_locations = {}

@socketio.on("delivery_location_update")
def handle_location(data):
    order_id = data["order_id"]
    lat = data["lat"]
    lng = data["lng"]

    print(f"🚴 Delivery GPS → Order {order_id}: {lat}, {lng}")

    last_locations[order_id] = (lat, lng)

    emit(
        "delivery_location_update",
        {"lat": lat, "lng": lng},
        room=f"order_{order_id}",
    )

@socketio.on("join_order_room")
def join_order(data):
    order_id = data["order_id"]
    join_room(f"order_{order_id}")

    # 🔥 SEND LAST LOCATION INSTANTLY
    if order_id in last_locations:
        lat, lng = last_locations[order_id]
        emit(
            "delivery_location_update",
            {"lat": lat, "lng": lng},
        )
@socketio.on("join_delivery_room")
def join_delivery_room(data):
    join_room(f"delivery_{data['delivery_person_id']}")

# ------------------ track apge live ------------------
@app.route("/track")
def track_page():
    if session.get("tracking_order_id"):
        return redirect(url_for("live_track"))
    return render_template("track_search.html")
@app.route("/live-track")
def live_track():
    order_id = session.get("tracking_order_id")
    if not order_id:
        return redirect(url_for("track_page"))

    order = Order.query.get(order_id)
    return render_template("live_track.html", order=order)
@app.route("/order/status/<int:order_id>")
def order_status(order_id):
    order = Order.query.get(order_id)
    return jsonify({"status": order.status}) 
def send_push(order, message):
    print("🔔 PUSH:", message)

@app.route("/live/update_status/<int:order_id>", methods=["POST"])
def live_update_status(order_id):
    order = Order.query.get(order_id)
    order.status = request.form.get("status")
    db.session.commit()

    send_push(order, f"Order {order.order_id} is now {order.status}")

    return redirect(url_for("restaurant_dashboard"))
@app.route("/api/order_status/<order_id>")
def api_order_status(order_id):
    print("📡 API HIT FOR ORDER:", order_id)

    order = Order.query.filter_by(order_id=order_id).first()
    if not order:
        return jsonify({"error": "Order not found"}), 404

    return jsonify({"status": order.status})
from flask import Flask, request, jsonify


# Register subscription endpoint
@app.route("/subscribe", methods=["POST"])
def subscribe():
    subscription = request.get_json()
    register_subscription(subscription)
    return jsonify({"success": True}), 201

# Send push to all subscribers
@app.route("/notify_all", methods=["POST"])
def notify_all():
    data = request.get_json()

    title = data.get("title", "New Order")
    body = data.get("body", "Order assigned to you")
    url = data.get("url", "/delivery/dashboard")

    print("📢 Sending push to", len(subscriptions), "subscribers")

    for sub in subscriptions:
        send_push(sub, title=title, body=body, url=url)

    return jsonify({"success": True})
  


# =======================
# Feedback Form Route
# =======================
@app.route("/feedback", methods=["GET", "POST"])
def feedback_form():
    if request.method == "POST":
        try:
            data = request.get_json()
            if not data:
                return jsonify(success=False, message="No data received"), 400

            new_feedback = UserFeedback(
                user_name=data.get("name"),
                phone=data.get("phone"),
                order_id=data.get("order_id"),
                issue_type=data.get("issue_type"),
                description=data.get("description"),
                priority=data.get("priority", "Normal"),
                source="web"
            )

            db.session.add(new_feedback)
            db.session.commit()

            return jsonify({
                "success": True,
                "message": "Feedback submitted successfully!",
                "ticket_id": new_feedback.feedback_id  # 👈 IMPORTANT
            })

        except Exception as e:
            return jsonify(success=False, message=str(e)), 500

    return render_template("user/feedback.html")

# =======================
# Admin Feedback Dashboard
# =======================
@app.route("/admin/feedback")
def admin_feedback():
    feedbacks = UserFeedback.query.order_by(UserFeedback.created_at.desc()).all()
    return render_template("admin/feedback.html", feedbacks=feedbacks)


# =======================
# Update Feedback Status
# =======================

@app.route("/my-issues", methods=["GET", "POST"])
def my_issues():
    feedbacks = []

    if request.method == "POST":
        ticket_id = request.form.get("ticket_id")
        phone = request.form.get("phone")

        query = UserFeedback.query

        if ticket_id:
            query = query.filter(UserFeedback.feedback_id == ticket_id)
        elif phone:
            query = query.filter(UserFeedback.phone == phone)

        feedbacks = query.order_by(UserFeedback.created_at.desc()).all()

    return render_template("user/my_issues.html", feedbacks=feedbacks)
@app.route("/admin/feedback/<feedback_id>/status", methods=["POST"])
def update_feedback_status(feedback_id):
    feedback = UserFeedback.query.filter_by(feedback_id=feedback_id).first_or_404()

    new_status = request.form.get("status")
    feedback.status = new_status
    feedback.updated_at = datetime.utcnow()

    if new_status == "Resolved":
        feedback.resolved_at = datetime.utcnow()
    else:
        feedback.resolved_at = None

    db.session.commit()
    flash("Status updated successfully", "success")
    return redirect(url_for("admin_feedback"))  
def calculate_delivery_charge(distance_km, items_total, restaurant):
    s = DeliverySettings.query.first()

    if not s:
        return 30, "🚚 Delivery charge ₹30"

    # =========================
    # 1️⃣ RESTAURANT FREE DELIVERY (ONLY THIS)
    # =========================
    if (
        restaurant.free_delivery_limit
        and restaurant.free_delivery_limit > 0
        and items_total >= restaurant.free_delivery_limit
    ):
        return 0, "🎉 Free delivery (Restaurant)"

    # =========================
    # 2️⃣ DISTANCE SLAB
    # =========================
    if distance_km <= s.base_distance:
        charge = s.base_charge
    elif distance_km <= s.slab_1_upto:
        charge = s.slab_1_charge
    elif distance_km <= s.slab_2_upto:
        charge = s.slab_2_charge
    elif distance_km <= s.slab_3_upto:
        charge = s.slab_3_charge
    else:
        charge = s.max_charge

    # =========================
    # 3️⃣ NIGHT SURGE
    # =========================
    if s.is_night_surge_active:
        charge += s.night_surge
        msg = f"🌙 Night delivery charge ₹{charge}"
    else:
        msg = f"🚚 Delivery charge ₹{charge}"

    return charge, msg
@app.route("/calculate_delivery", methods=["POST"])
def calculate_delivery():
    data = request.get_json()

    restaurant_id = int(data["restaurant_id"])
    customer_lat = float(data["customer_lat"])
    customer_lng = float(data["customer_lng"])
    items_total = float(data["items_total"])

    restaurant = Restaurant.query.get_or_404(restaurant_id)

    distance_km = calculate_distance_km(
        restaurant.latitude,
        restaurant.longitude,
        customer_lat,
        customer_lng
    )

    delivery_charge, message =calculate_delivery_charge(distance_km, items_total, restaurant)

    

    return jsonify({
        "distance_km": round(distance_km, 2),
        "delivery_charge": delivery_charge,
        "message": message
    })

@app.route("/admin/delivery-settings", methods=["GET", "POST"])
def admin_delivery_settings():
    settings = DeliverySettings.query.first()

    if request.method == "POST":
        if not settings:
            settings = DeliverySettings()  # create new if not exists
            db.session.add(settings)

        # Safe update using helper functions
        settings.base_distance = safe_float(request.form.get("base_distance"), settings.base_distance)
        settings.base_charge = safe_int(request.form.get("base_charge"), settings.base_charge)

        settings.slab_1_upto = safe_float(request.form.get("slab_1_upto"), settings.slab_1_upto)
        settings.slab_1_charge = safe_int(request.form.get("slab_1_charge"), settings.slab_1_charge)

        settings.slab_2_upto = safe_float(request.form.get("slab_2_upto"), settings.slab_2_upto)
        settings.slab_2_charge = safe_int(request.form.get("slab_2_charge"), settings.slab_2_charge)

        settings.slab_3_upto = safe_float(request.form.get("slab_3_upto"), settings.slab_3_upto)
        settings.slab_3_charge = safe_int(request.form.get("slab_3_charge"), settings.slab_3_charge)

        settings.max_charge = safe_int(request.form.get("max_charge"), settings.max_charge)
        settings.free_delivery_min_order = safe_int(request.form.get("free_delivery_min_order"), settings.free_delivery_min_order)

        settings.night_surge = safe_int(request.form.get("night_surge"), settings.night_surge)
        settings.is_night_surge_active = request.form.get("is_night_surge_active") == "on"

        settings.updated_at = datetime.utcnow()

        db.session.commit()
        flash("Delivery settings updated successfully", "success")
        return redirect(url_for("admin_delivery_settings"))

    return render_template("admin_delivery_settings.html", settings=settings)
def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
from flask import Flask, render_template, request, redirect, url_for, flash, session



@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart_items = session.get('cart', [])  # list of dicts: [{'item_id':1, 'quantity':2}, ...]
    
    # Fetch items from DB
    items = [Item.query.get(ci['item_id']) for ci in cart_items]
    
    # Organize totals by shop
    shop_totals = {}
    for item, ci in zip(items, cart_items):
        total_price = item.price * ci['quantity']
        if item.shop_name in shop_totals:
            shop_totals[item.shop_name] += total_price
        else:
            shop_totals[item.shop_name] = total_price

    # Check minimum delivery per shop
    for shop_name, total in shop_totals.items():
        shop_setting = ShopSettings.query.filter_by(shop_name=shop_name).first()
        min_amount = shop_setting.min_delivery_amount if shop_setting else 0
        if total < min_amount:
            flash(f"Minimum order for {shop_name} delivery is ₹{min_amount}. Add ₹{min_amount - total} more.")
            return redirect(url_for('cart'))  # send back to cart
    
    # If all minimums met
    return render_template('checkout.html', items=items, shop_totals=shop_totals)


@app.route('/admin/min_delivery', methods=['GET', 'POST'])
def admin_min_delivery():
    shops = ShopSettings.query.all()

    if request.method == "POST":
        for shop in shops:
            new_amount = request.form.get(f'min_{shop.id}')
            if new_amount:
                shop.min_delivery_amount = float(new_amount)
        db.session.commit()
        flash("Updated successfully!")
        return redirect(url_for('admin_min_delivery'))

    return render_template('admin_min_delivery.html', shops=shops)


@app.route('/admin/add_shop', methods=['POST'])
def add_shop():
    if not session.get('is_admin'):
        flash("Access denied!")
        return redirect(url_for('login'))
    
    name = request.form.get('shop_name')
    min_amount = request.form.get('min_amount')
    
    if name and min_amount:
        shop = ShopSettings(shop_name=name, min_delivery_amount=float(min_amount))
        db.session.add(shop)
        db.session.commit()
        flash(f"{name} added successfully!")
    
    return redirect(url_for('admin_min_delivery'))
# routes.py
from flask import render_template, abort
import pandas as pd
from sqlalchemy import func
from models import OrderItem, Order, Restaurant

import re
import unicodedata


# ================= NORMALIZER =================
def normalize_name(name):
    name = unicodedata.normalize("NFKD", str(name))
    name = name.lower()
    name = re.sub(r"[^a-z0-9() ]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


# ================= ROUTE =================
@app.route("/bakery/<int:restaurant_id>")
def bakery_menu(restaurant_id):

    restaurant = Restaurant.query.get_or_404(restaurant_id)

    if restaurant.category_type != "bakery":
        abort(404)

    if not restaurant.sheet_url:
        return "No bakery menu sheet configured"

    df = pd.read_csv(restaurant.sheet_url)

    print("\n================ BAKERY SHEET RAW DATA ================")
    print(df)
    print("\nCOLUMN TYPES:")
    print(df.dtypes)

    # ✅ CLEAN NaN VALUES
    df = df.fillna("")

    print("\n================ AFTER fillna('') =====================")
    print(df)

    # ================= FETCH ORDERS =================
    raw = (
        db.session.query(
            OrderItem.item_name,
            func.count(OrderItem.id)
        )
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.restaurant_id == restaurant_id)
        .group_by(OrderItem.item_name)
        .all()
    )

    reorder_map = {
        normalize_name(name): count
        for name, count in raw
    }

    print("\n================ REORDER COUNT MAP ====================")
    print(reorder_map)

    # ================= PROCESS ITEMS =================
    items = []

    for i, item in enumerate(df.to_dict(orient="records")):

        print(f"\n--- ROW {i+1} BEFORE CLEAN ---")
        print(item)

        # PRICE CLEAN
        raw_price = str(item.get("price", "")).strip()
        item["price"] = float(raw_price) if raw_price else 0

        # WEIGHT CLEAN
        raw_weights = str(item.get("weight_prices", "")).strip()
        item["weight_prices"] = raw_weights

        # ✅ NORMALIZE CSV NAME
        item_name = normalize_name(item.get("name", ""))

        item["reorder_count"] = reorder_map.get(item_name, 0)

        print(f"PRICE PARSED: {item['price']}")
        print(f"WEIGHTS PARSED: '{item['weight_prices']}'")
        print(f"NORMALIZED NAME: {item_name}")
        print(f"REORDER COUNT: {item['reorder_count']}")

        items.append(item)

    print("\n================ FINAL ITEMS SENT TO TEMPLATE ==========")
    for item in items:
        print(item)

    # ================= GROUP BY CATEGORY =================
    menu_by_category = {}

    for item in items:
        category = item.get("category", "Other")
        menu_by_category.setdefault(category, []).append(item)

    print("\n================ CATEGORY GROUPING =====================")
    for k, v in menu_by_category.items():
        print(f"{k}: {len(v)} items")

    return render_template(
        "bakery_menu.html",
        restaurant=restaurant,
        menu_by_category=menu_by_category
    )


from sqlalchemy import event, inspect

@event.listens_for(Restaurant, "before_update")
def protect_bakery(mapper, connection, target):
    state = inspect(target)
    if state.attrs.category_type.history.has_changes():
        old = state.attrs.category_type.history.deleted
        if old and old[0] == "bakery":
            target.category_type = "bakery"
@app.route("/restaurant/<int:restaurant_id>/menu", methods=["GET", "POST"])
def manage_menu(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)

    if request.method == "POST":
        item = MenuItem(
            restaurant_id=restaurant.id,
            name=request.form["name"],
            category=request.form["category"],
            price=float(request.form["price"]),
            weight_prices=request.form.get("weight_prices"),
            availability="yes"
        )
        db.session.add(item)
        db.session.commit()

        flash("Item added successfully", "success")

    items = MenuItem.query.filter_by(restaurant_id=restaurant.id).all()
    return render_template("manage_menu.html", restaurant=restaurant, items=items)
from collections import defaultdict

def build_category_index(menu_items):
    category_index = defaultdict(set)

    for item in menu_items:
        if not item.category:
            continue

        # split multiple categories: "Cakes, Custom Cakes"
        categories = item.category.split(",")

        for cat in categories:
            clean_cat = cat.strip().lower()
            if clean_cat:
                category_index[clean_cat].add(item.restaurant_id)

    return {k: sorted(list(v)) for k, v in category_index.items()}
@app.route("/api/live-order-count")
def live_order_count():
    total_orders = db.session.query(Order).count()

    return {
        "count": total_orders,
        "timestamp": datetime.utcnow().isoformat()
    }
@app.route("/redeem_checkout", methods=["POST"])
def redeem_checkout():
    customer_id = session.get("customer_id")
    if not customer_id:
        flash("Please login to continue", "danger")
        return redirect(url_for("cart_page"))

    order_id = request.form.get("order_id")
    order_total = float(request.form.get("order_total", 0))
    coins_to_use = int(request.form.get("coins_to_use", 0))

    # Attempt to redeem coins
    success, msg, discount = redeem_coins(customer_id, coins_to_use, order_id, order_total)

    if success:
        final_total = round(order_total - discount, 2)
        flash(f"✅ {msg}. New total: ₹{final_total}", "success")
    else:
        final_total = order_total
        flash(f"⚠ {msg}", "warning")

    # Update order final total
    order = Order.query.get(order_id)
    if order:
        order.final_total = final_total
        db.session.commit()

    return redirect(url_for("order_summary", order_id=order_id))
@app.route("/apply_coins", methods=["POST"])
def apply_coins():
    customer_id = session.get("customer_id")
    order_id = request.form.get("order_id")
    coins_to_use = int(request.form.get("coins_to_use", 0))
    order_total = float(request.form.get("order_total"))

    success, msg, discount = redeem_coins(customer_id, coins_to_use, order_id, order_total)

    if success:
        flash(f"{msg}. Discount applied: ₹{discount}", "success")
    else:
        flash(msg, "warning")

    return redirect(url_for("cart_page", restaurant_id=request.form.get("restaurant_id")))
@app.route("/clear-earned-coins")
def clear_earned_coins():
    session.pop("earned_coins", None)
    return "", 204
@app.route("/admin/reward-badges", methods=["GET","POST"])
@admin_required
def manage_reward_badges():

    badges = RewardBadge.query.order_by(
        RewardBadge.required_coins.asc()
    ).all()

    if request.method == "POST":

        for badge in badges:
            value = request.form.get(f"coins_{badge.id}")

            if value:
                badge.required_coins = int(value)

        db.session.commit()
        flash("Badge coin values updated successfully")

        return redirect(url_for("manage_reward_badges"))

    return render_template(
        "admin/reward_badges.html",
        badges=badges
    )

from sqlalchemy import func

def get_reorder_items(customer_id):
    results = (
        db.session.query(
            OrderItem.item_name,
            func.count(OrderItem.id).label("order_count")
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.customer_id == customer_id)
        .group_by(OrderItem.item_name)
        .all()
    )

    return {r.item_name: r.order_count for r in results}
from werkzeug.utils import secure_filename
import os
from uuid import uuid4

@app.route("/admin/categories", methods=["GET", "POST"])
def manage_categories():

    if request.method == "POST":
        name = request.form.get("name")
        image = request.files.get("image")   # NEW

        if name:
            existing = Category.query.filter_by(name=name).first()
            if not existing:

                filename = secure_filename(image.filename)
                save_path = os.path.join("static/images/categories", filename)
                image.save(save_path)

                new_cat = Category(
                    name=name,
                    image="images/categories/" + filename
                )

                db.session.add(new_cat)
                db.session.commit()

    categories = Category.query.all()
    return render_template("admin_categories.html", categories=categories)

@app.route("/category/<int:category_id>")
def restaurants_by_category(category_id):
    category = Category.query.get_or_404(category_id)

    # Get restaurants in this category
    restaurants = category.restaurants

    # Pass current time for open/closed logic
    from datetime import datetime
    now = datetime.now().time()

    return render_template(
        "restaurants_by_category.html",
        category=category,
        restaurants=restaurants,
        now=now  # needed for open/closed checks in your template
    )

@app.route("/admin/category/<int:category_id>/edit", methods=["POST"])
def edit_category(category_id):
    cat = Category.query.get_or_404(category_id)
    new_name = request.form.get("name")
    image = request.files.get("image")

    if new_name:
        cat.name = new_name

    if image and image.filename != "":
        upload_folder = os.path.join("static", "images", "categories")
        os.makedirs(upload_folder, exist_ok=True)
        unique_name = f"{uuid4().hex}_{secure_filename(image.filename)}"
        save_path = os.path.join(upload_folder, unique_name)
        image.save(save_path)
        cat.image = f"images/categories/{unique_name}"

    db.session.commit()
    return redirect(url_for("manage_categories"))
@app.route("/admin/category/<int:category_id>/delete", methods=["POST"])
def delete_category(category_id):
    cat = Category.query.get_or_404(category_id)
    db.session.delete(cat)
    db.session.commit()
    return redirect(url_for("manage_categories"))
import qrcode
import io
import base64
from flask import send_file

import qrcode
import io
from flask import send_file
from urllib.parse import quote

@app.route('/generate_qr/<int:order_id>')
def generate_qr(order_id):
    order = Order.query.get_or_404(order_id)

    upi_id = "9618319849@ptyes"
    name = quote("RucHiGo")
    amount = f"{float(order.final_total):.2f}"
    note = quote(f"Order {order.id}")

    upi_link = (
        f"upi://pay?"
        f"pa={upi_id}"
        f"&pn={name}"
        f"&am={amount}"
        f"&cu=INR"
        f"&tn={note}"
    )

    qr = qrcode.make(upi_link)

    img_io = io.BytesIO()
    qr.save(img_io, "PNG")
    img_io.seek(0)

    return send_file(img_io, mimetype="image/png")
@app.route("/admin/update-tags/<int:id>", methods=["POST"])
def update_tags(id):

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    r = Restaurant.query.get_or_404(id)

    r.is_best_seller = "best" in request.form
    r.is_fast_delivery = "fast" in request.form

    db.session.commit()

    flash("Tags updated")
    return redirect(url_for("admin_dashboard"))
@app.route("/founder")
def founder():
    return render_template("founder.html")
from sqlalchemy import func, case
from datetime import datetime
from flask import request, render_template

from sqlalchemy import func, case

@app.route("/super/delivery_boys_summary", methods=["GET"])
def super_delivery_boys_summary():

    # 📅 Date filter
    date_str = request.args.get("date")
    if date_str:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        selected_date = datetime.utcnow().date()

    results = db.session.query(

        DeliveryPerson.id.label("delivery_person_id"),  # ✅ FIX
        DeliveryPerson.name.label("delivery_name"),

        # 💵 COD total
        func.sum(
            case(
                (Order.payment_type == "COD", Order.final_total),
                else_=0
            )
        ).label("cod_total"),

        # 💳 Online total
        func.sum(
            case(
                (Order.payment_type == "Online", Order.final_total),
                else_=0
            )
        ).label("online_total"),

        # 🚚 Delivery charges total
        func.coalesce(func.sum(Order.delivery_charge), 0).label("delivery_total"),

        # 💰 Grand total
        func.coalesce(func.sum(Order.final_total), 0).label("grand_total"),

        # 📦 Order count
        func.count(Order.id).label("order_count")

    ).join(DeliveryPerson, Order.delivery_person_id == DeliveryPerson.id) \
     .filter(
        Order.status == "Delivered",
        func.date(Order.delivered_time) == selected_date
     ) \
     .group_by(DeliveryPerson.id) \
     .all()

    return render_template(
        "super_delivery_boys.html",
        results=results,
        date=selected_date
    )

from flask import send_from_directory

@app.route('/firebase-messaging-sw.js')
def firebase_sw():
    return send_from_directory('static', 'firebase-messaging-sw.js')

from firebase_admin import messaging
def send_push_notification(title, body, target_type="topic", target_value="all_users"):

    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        )
    )

    if target_type == "topic":
        message.topic = target_value
    elif target_type == "token":
        message.token = target_value

    try:
        response = messaging.send(message)
        print("FCM Response:", response)
        return response
    except Exception as e:
        print("FCM ERROR:", e)
        return None

from flask import request, redirect, flash
from flask import request, redirect, flash
from firebase_admin import messaging
from models import FCMToken


@app.route("/admin/send-notification", methods=["POST"])
def admin_send_notification():
    title = request.form.get("title")
    body = request.form.get("body")

    print(f"Sending Notification -> Title: {title}, Body: {body}")

    tokens = list(set([t.token for t in FCMToken.query.all()]))  # remove duplicates
    print(f"Total UNIQUE tokens: {len(tokens)}")

    if not tokens:
        flash("No users to send notification.", "warning")
        return redirect("/admin/dashboard")

    try:
        message = messaging.MulticastMessage(
            data={   # ✅ DATA ONLY (better for PWA)
                "title": title,
                "body": body,
                "url": "/"
            },
            tokens=tokens
        )

        response = messaging.send_each_for_multicast(message)

        print(f"Success: {response.success_count}, Failure: {response.failure_count}")

        # 🔥 Remove invalid tokens automatically
        for idx, resp in enumerate(response.responses):
            if not resp.success:
                error = resp.exception
                token = tokens[idx]

                print(f"❌ Removing invalid token: {token} | Error: {error}")

                FCMToken.query.filter_by(token=token).delete()
        
        db.session.commit()

        flash(f"Notification sent to {response.success_count} users.", "success")

    except Exception as e:
        print("FCM ERROR:", e)
        flash(f"Error sending notification: {e}", "danger")

    return redirect("/admin/dashboard") 
from firebase_admin import messaging
from models import FCMToken


def send_multicast_notification(title, body):

    tokens = list(set([t.token for t in FCMToken.query.all()]))

    print(f"Total UNIQUE tokens: {len(tokens)}")

    if not tokens:
        print("No tokens found!")
        return
    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body
        ),
        data={
            "url": "/"
        },
        tokens=tokens
    )

    response = messaging.send_each_for_multicast(message)

    print(f"Success: {response.success_count}, Failure: {response.failure_count}")

    for idx, resp in enumerate(response.responses):
        if not resp.success:
            token = tokens[idx]
            print(f"❌ Removing invalid token: {token}")
            FCMToken.query.filter_by(token=token).delete()

    db.session.commit() 


@app.route("/admin/offers")
def admin_offers():
    offers = Offer.query.order_by(Offer.id.desc()).all() 
    return render_template("admin_offers.html", offers=offers)
from firebase_admin import messaging

def send_offer_notification(title, body, image=None, link="/"):

    tokens = list(set([t.token for t in FCMToken.query.all()]))

    if not tokens:
        print("No FCM tokens found.")
        return

    # ✅ FORCE EVERYTHING TO STRING
    data_payload = {
        "url": str(link or "/"),
        "offer_title": str(title or ""),
        "offer_body": str(body or ""),
        "image": str(image or "")
    }

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=str(title or ""),
            body=str(body or ""),
            image=str(image) if image else None
        ),
        data=data_payload,
        tokens=tokens
    )

    response = messaging.send_each_for_multicast(message)

    print("Success:", response.success_count)
    print("Failure:", response.failure_count)
@app.route("/admin/create-offer", methods=["POST"])
def create_offer():
    from datetime import datetime

    title = request.form.get("title")
    body = request.form.get("body")

    # 🔥 FIX 1: Never allow None for discount
    discount_str = request.form.get("discount")
    discount = int(discount_str) if discount_str else 0

    coupon = request.form.get("coupon") or None

    expiry_str = request.form.get("expiry")
    expiry = datetime.strptime(expiry_str, "%Y-%m-%dT%H:%M") if expiry_str else None

    image = request.form.get("image") or None
    link = request.form.get("link") or None

    new_offer = Offer(
        title=title,
        body=body,
        discount=discount,   # always integer
        coupon=coupon,
        expiry=expiry,
        image=image,
        link=link
    )

    db.session.add(new_offer)
    db.session.commit()

    # 🔥 Compose full notification message
    full_message = f"{body}"

    if discount > 0:
        full_message += f"\n🎁 {discount}% OFF"

    if coupon:
        full_message += f"\n🧾 Code: {coupon}"

    # 🔥 Send safe string-only data
    send_offer_notification(
        str(title),
        str(full_message),
        str(image or ""),
        str(link or "/")
    )

    flash("Offer created and notification sent!")
    return redirect("/admin/offers")
@app.route("/admin/delete-offer/<int:offer_id>", methods=["POST"])
def admin_delete_offer(offer_id):   # renamed function
    offer = Offer.query.get_or_404(offer_id)
    db.session.delete(offer)
    db.session.commit()
    flash("Offer deleted successfully!", "success")
    return redirect("/admin/offers") 
from sqlalchemy import func

from sqlalchemy import func
from sqlalchemy import func

@app.route("/top-customers")
def top_customers():

    # -------- Delivered Orders Count --------
    orders_sub = db.session.query(
        Order.customer_id,
        func.count(Order.id).label("orders")
    ).filter(
        Order.status == "Delivered",
        Order.customer_id != None
    ).group_by(
        Order.customer_id
    ).subquery()


    # -------- Coins Total --------
    coins_sub = db.session.query(
        CoinLedger.customer_id,
        func.sum(CoinLedger.coins).label("coins")
    ).group_by(
        CoinLedger.customer_id
    ).subquery()


    # -------- Main Query --------
    results = db.session.query(
        Customer.id,
        Customer.name,
        Customer.mobile,
        func.coalesce(orders_sub.c.orders, 0).label("orders"),
        func.coalesce(coins_sub.c.coins, 0).label("coins")
    ).outerjoin(
        orders_sub, orders_sub.c.customer_id == Customer.id
    ).outerjoin(
        coins_sub, coins_sub.c.customer_id == Customer.id
    ).order_by(
        func.coalesce(orders_sub.c.orders, 0).desc()
    ).limit(10).all()


    leaderboard = []

    for r in results:

        badge = RewardBadge.query.filter(
            RewardBadge.required_coins <= r.coins
        ).order_by(
            RewardBadge.required_coins.desc()
        ).first()

        leaderboard.append({
            "name": r.name if r.name else "Customer",
            "mobile": r.mobile,
            "orders": int(r.orders),
            "coins": int(r.coins),
            "badge": badge.name if badge else "No Badge"
        })

    return jsonify(leaderboard)  


from datetime import datetime, timedelta
from sqlalchemy import func

@app.route("/employee/dashboard")
def employee_dashboard():
    if not session.get("employee_id"):
        return redirect(url_for("employee_login"))

    emp = Employee.query.get(session.get("employee_id"))

    # 🔒 Force logout check
    if not emp or not emp.is_logged_in:
        session.clear()
        return redirect(url_for("employee_login"))

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    # ✅ FETCH ALL ORDERS (optimized)
    orders = (
        Order.query
        .filter(
            Order.status.in_([
                "Pending",
                "Accepted",
                "Preparing",
                "Ready",
                "Out for Delivery",
                "Started",
                "Delivered",
                "Cancelled"
            ])
        )
        .options(
            db.joinedload(Order.restaurant),
            db.joinedload(Order.items),
            db.joinedload(Order.delivery_person)
        )
        .order_by(Order.created_at.desc())
        .all()
    )

    # ================= DAY CLASSIFICATION =================
    for o in orders:
        if o.created_at.date() == today:
            o.day_category = "Today"
        elif o.created_at.date() == yesterday:
            o.day_category = "Yesterday"
        else:
            o.day_category = "Older"

    # ================= STATS =================
    # ================= STATS =================
    today_orders = [o for o in orders if o.created_at.date() == today]

    delivered_orders = [o for o in today_orders if o.status == "Delivered"]

    stats = {
        "today_orders": len(today_orders),

        "today_delivered": len(delivered_orders),

        "today_cancelled": len([o for o in today_orders if o.status == "Cancelled"]),

        "today_pending": len([o for o in today_orders if o.status == "Pending"]),

        "today_active": len([o for o in today_orders if o.status in ["Preparing", "Out for Delivery"]]),

        # ✅ ONLY delivered revenue
        "today_revenue": sum(o.final_total or 0 for o in delivered_orders),

        # ✅ ONLY delivered delivery charges (FIXED)
        "today_delivery_charges": sum(o.delivery_charge or 0 for o in delivered_orders),

        # ✅ ONLY delivered items (OPTIONAL BUT BETTER)
        "today_items": sum(
            sum(item.quantity for item in o.items)
            for o in delivered_orders
        )
    }

    # ================= TOTAL RESTAURANTS =================
    restaurants = Restaurant.query.all()

    # ================= DELIVERY PERSONS =================
    delivery_persons = DeliveryPerson.query.order_by(DeliveryPerson.name).all()

    return render_template(
        "employee_dashboard.html",
        orders=orders,
        delivery_persons=delivery_persons,
        stats=stats,
        restaurants=restaurants,
        employee=emp,   # ✅ ADD THIS LINE 
        timedelta=timedelta 

    )



import random
from datetime import datetime
import random
from datetime import datetime, timedelta

from flask import jsonify
@app.route("/employee/send-otp", methods=["POST"])
def employee_send_otp():
    phone = request.form.get("phone")

    emp = Employee.query.filter_by(phone=phone).first()

    if not emp:
        return jsonify({"success": False, "error": "Employee not found"})

    now = datetime.utcnow()

    # 🔍 Check existing active OTP
    existing_otp = (
        EmployeeOTP.query
        .filter_by(employee_id=emp.id, is_used=False)
        .order_by(EmployeeOTP.created_at.desc())
        .first()
    )

    # 🚫 If OTP still valid → block resend
    if existing_otp and existing_otp.expires_at > now:
        remaining_seconds = int((existing_otp.expires_at - now).total_seconds())

        return jsonify({
            "success": False,
            "error": f"OTP already sent. Try again in {remaining_seconds} sec",
            "retry_in": remaining_seconds
        })

    # ✅ Generate new OTP
    otp = str(random.randint(100000, 999999))
    print("🔥 OTP:", otp)

    new_otp = EmployeeOTP(
        employee_id=emp.id,
        otp=otp,
        expires_at=now + timedelta(minutes=5),
        is_used=False
    )

    db.session.add(new_otp)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "OTP sent",
        "expires_in": 300
    })
@app.route("/employee/login")
def employee_login():
    return render_template("employee_login.html") 



@app.route("/employee/logout")
def employee_logout():
    emp = Employee.query.get(session.get("employee_id"))

    if emp:
        emp.is_logged_in = False

    session.clear()
    return redirect("/employee/login") 

@app.route("/admin/otps")
def admin_otps():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    from datetime import datetime

    otps = (
        db.session.query(EmployeeOTP, Employee)
        .join(Employee, EmployeeOTP.employee_id == Employee.id)
        .order_by(EmployeeOTP.created_at.desc())
        .limit(50)
        .all()
    )

    return render_template("admin_otps.html", otps=otps, now=datetime.utcnow())
from flask import jsonify
@app.route("/employee/update-status/<int:order_id>", methods=["POST"])
def employee_update_status(order_id):
    if not session.get("employee_id"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    order = Order.query.get_or_404(order_id)

    # 🚫 LOCK FINAL STATUS
    if order.status in ["Delivered", "Cancelled"]:
        return jsonify({"success": False, "error": "Order locked"})

    new_status = request.form.get("status")

    if not new_status:
        return jsonify({"success": False, "error": "No status provided"})

    # ✅ Update status
    order.status = new_status
    db.session.commit()

    # 🔥 Real-time update to customer
    socketio.emit(
        "order_status_update",
        {
            "order_id": order.id,
            "status": order.status
        },
        room=f"order_{order.id}"
    )
    
    print(f"📤 Employee emitted: order_{order.id} -> {order.status}")

    return jsonify({
        "success": True,
        "new_status": order.status
    })
@app.route("/employee/assign-delivery/<int:order_id>", methods=["POST"])
def employee_assign_delivery(order_id):
    if not session.get("employee_id"):
        return jsonify({"success": False, "error": "Not logged in"}), 401

    order = Order.query.get_or_404(order_id)

    # 🚫 LOCK FINAL STATUS
    if order.status in ["Delivered", "Cancelled"]:
        return jsonify({"success": False, "error": "Order locked"})

    dp_id = request.form.get("delivery_person_id")

    if not dp_id:
        return jsonify({"success": False, "error": "No delivery person selected"})

    dp = DeliveryPerson.query.get(dp_id)

    if not dp:
        return jsonify({"success": False, "error": "Invalid delivery person"})

    # ✅ ASSIGN DELIVERY
    order.delivery_person_id = dp.id

    # 🔥 AUTO STATUS CHANGE
    order.status = "Out for Delivery"

    db.session.commit()
    socketio.emit(
        "delivery_assigned",
        {
            "order_id": order.id,
            "delivery_person_name": dp.name,
            "delivery_person_phone": dp.phone,
            "status": order.status
        },
        room=f"order_{order.id}"
    )
    return jsonify({
        "success": True,
        "delivery_person_name": dp.name,
        "new_status": order.status
    }) 


@app.route("/employee/verify-otp", methods=["POST"])
def employee_verify_otp():
    phone = request.form.get("phone")
    otp_input = request.form.get("otp")

    emp = Employee.query.filter_by(phone=phone).first()

    if not emp:
        return jsonify({"success": False, "error": "Invalid user"})

    now = datetime.utcnow()

    # ✅ GET LATEST OTP (IMPORTANT)
    latest_otp = (
        EmployeeOTP.query
        .filter_by(employee_id=emp.id, is_used=False)
        .order_by(EmployeeOTP.created_at.desc())
        .first()
    )

    if not latest_otp:
        return jsonify({"success": False, "error": "No OTP found"})

    # ❌ EXPIRED
    if latest_otp.expires_at < now:
        return jsonify({"success": False, "error": "OTP expired"})

    # ❌ WRONG OTP
    if latest_otp.otp != otp_input:
        return jsonify({"success": False, "error": "Invalid OTP"})

    # ✅ SUCCESS → MARK USED
    latest_otp.is_used = True

    emp.is_logged_in = True
    session["employee_id"] = emp.id

    db.session.commit()

    return jsonify({
        "success": True,
        "redirect": "/employee/dashboard"
    })
@app.route("/employee/orders-json")
def employee_orders_json():
    orders = (
        Order.query
        .order_by(Order.created_at.desc())
        .limit(20)
        .all()
    )

    data = []
    for o in orders:
        data.append({
            "id": o.id,
            "order_id": o.order_id,
            "customer": o.customer_name,
            "phone": o.phone,
            "status": o.status,
            "total": o.final_total,
            "created_at": o.created_at.strftime("%H:%M"),
        })

    return {"orders": data} 



@app.route("/admin/employees", methods=["GET", "POST"])
def admin_employees():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        role = request.form.get("role")

        # ❌ Prevent duplicate
        existing = Employee.query.filter_by(phone=phone).first()
        if existing:
            flash("Employee already exists", "error")
            return redirect(url_for("admin_employees"))

        emp = Employee(
            name=name,
            phone=phone,
            role=role,
            is_active=True
        )

        db.session.add(emp)
        db.session.commit()

        flash("✅ Employee added successfully", "success")
        return redirect(url_for("admin_employees"))

    # GET → show all employees
    employees = Employee.query.order_by(Employee.id.desc()).all()

    return render_template("admin_employees.html", employees=employees)


@app.route("/admin/delete-employee/<int:id>")
def delete_employee(id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    emp = Employee.query.get_or_404(id)

    db.session.delete(emp)
    db.session.commit()

    flash("❌ Employee deleted", "info")
    return redirect(url_for("admin_employees")) 


@app.route("/admin/logout-employee/<int:id>")
def logout_employee(id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    emp = Employee.query.get_or_404(id)

    emp.is_logged_in = False
    db.session.commit()

    flash("🚫 Employee logged out", "warning")
    return redirect(url_for("admin_employees")) 


@app.route("/employee/check-session")
def employee_check_session():
    if not session.get("employee_id"):
        return {"active": False}

    emp = Employee.query.get(session.get("employee_id"))

    if not emp or not emp.is_logged_in:
        return {"active": False}

    return {"active": True} 

@app.route("/admin/delivery-history/<int:delivery_id>")
def admin_delivery_history(delivery_id):

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    # ✅ SAME FILTER AS DELIVERY (IMPORTANT)
    history = Order.query.filter(
        Order.delivery_person_id == delivery_id,
        Order.status.in_(["Delivered", "Customer Not Available"])
    ).order_by(Order.updated_at.desc()).all()

    # ✅ CLASSIFY DAYS (same as yours)
    for o in history:
        if o.created_at.date() == today:
            o.day_category = "Today"
        elif o.created_at.date() == yesterday:
            o.day_category = "Yesterday"
        else:
            o.day_category = "Older"

    # ✅ TOTALS (same logic)
    totals = {}
    for day in ["Today", "Yesterday", "Older"]:
        day_orders = [
            o for o in history
            if o.day_category == day and o.status == "Delivered"
        ]

        cod_amount = sum(
            o.get_final_total() for o in day_orders if o.payment_type == "COD"
        )

        online_amount = sum(
            o.get_final_total() for o in day_orders if o.payment_type == "Online"
        )

        delivery_charge_total = sum(
            o.delivery_charge or 0 for o in day_orders
        )

        totals[day] = {
            "count": len(day_orders),
            "cod_amount": cod_amount,
            "online_amount": online_amount,
            "delivery_charge": delivery_charge_total,
            "grand_total": cod_amount + online_amount + delivery_charge_total
        }

    # ✅ ALL TOTAL
    all_totals = {
        "count": sum(totals[d]["count"] for d in totals),
        "cod_amount": sum(totals[d]["cod_amount"] for d in totals),
        "online_amount": sum(totals[d]["online_amount"] for d in totals),
        "delivery_charge": sum(totals[d]["delivery_charge"] for d in totals),
    }

    all_totals["grand_total"] = (
        all_totals["cod_amount"]
        + all_totals["online_amount"]
        + all_totals["delivery_charge"]
    )

    return render_template(
        "delivery_history.html",
        history=history,
        totals=totals,
        all_totals=all_totals,
        delivery_id=delivery_id   # ✅ IMPORTANT
    ) 

from flask_socketio import join_room

@socketio.on("join_order_room")
def join_order(data):
    order_id = data.get("order_id")

    if not order_id:
        print("❌ No order_id received")
        return

    room = f"order_{order_id}"
    join_room(room)

    print("🟢 Joined room:", room) 
@app.route("/payment/<int:order_id>")
def payment_page(order_id):

    order = Order.query.get_or_404(order_id)

    # ✅ Already paid
    if order.payment_status == "Paid":

        return redirect(
            url_for(
                "order_placed",
                order_id=order.order_id
            )
        )

    # ❌ Payment window expired
    if order.status == "Cancelled":

        flash(
            "Payment session expired. Please place your order again.",
            "warning"
        )
    
        return render_template(
            "payment_expired.html",
            order=order
        )
    expires_at = order.created_at + timedelta(minutes=15)
    # ⏳ Still waiting for payment
    return render_template(
        "payment.html",
        order=order,
        razorpay_key=RAZORPAY_KEY_ID,
        expires_at=expires_at
    )
@app.route("/create_payment/<int:order_id>")
def create_payment(order_id):

    order = Order.query.get_or_404(order_id)

    if order.payment_status == "Paid":
        return jsonify({
            "success": False,
            "message": "Order already paid"
        })

    payment = razorpay_client.order.create({
        "amount": int(order.final_total * 100),
        "currency": "INR",
        "receipt": f"order_{order.id}"
    })

    order.payment_order_id = payment["id"]

    db.session.commit()

    return jsonify({
        "success": True,
        "key": RAZORPAY_KEY_ID,
        "amount": payment["amount"],
        "order_id": payment["id"],
        "name": order.customer_name,
        "email": order.email or "",
        "contact": order.phone
    })   

from datetime import datetime
from flask import request, jsonify, url_for 

@app.route("/verify_payment", methods=["POST"])
def verify_payment():

    data = request.get_json()

    order = Order.query.get_or_404(
        data["order_id"]
    )

    # 🔒 Do not allow payment for cancelled orders until 
    if order.status == "Cancelled":

        return jsonify({

            "success": False,

            "redirect_url":

                url_for(

                    "payment_page",

                    order_id=order.id

                )

        })

    # 🔒 Already paid
    if order.payment_status == "Paid":

        return jsonify({

            "success": True,

            "redirect_url":
            url_for(
                "order_placed",
                order_id=order.order_id
            )

        })

    try:

        razorpay_client.utility.verify_payment_signature({

            "razorpay_order_id":
            data["razorpay_order_id"],

            "razorpay_payment_id":
            data["razorpay_payment_id"],

            "razorpay_signature":
            data["razorpay_signature"]

        })

        # ✅ Payment successful
        order.payment_status = "Paid"

        order.payment_type = "Online"

        order.payment_verified = True

        order.status = "Pending"

        order.payment_id = data["razorpay_payment_id"]

        order.payment_order_id = (
            data["razorpay_order_id"]
        )

        order.payment_signature = (
            data["razorpay_signature"]
        )

        order.payment_time = datetime.utcnow()

        order.payment_method_used = "UPI"

        order.payment_source = "Checkout"

        db.session.commit()

        return jsonify({

            "success": True,

            "redirect_url":
            url_for(
                "order_placed",
                order_id=order.order_id
            )

        })

    except Exception as e:

        print(
            "Payment verification error:",
            e
        )

        order.payment_status = "Failed"

        db.session.commit()

        return jsonify({

            "success": False,

            "message":
            "Payment verification failed"

        }), 400
@app.route(
    "/payment_failed/<int:order_id>",
    methods=["POST"]
)
def payment_failed(order_id):

    order = Order.query.get_or_404(
        order_id
    )

    if order.payment_status != "Paid":
        order.payment_status = "Failed"
        db.session.commit()

    return jsonify({
        "success": True
    }) 

from flask import redirect
import urllib.parse

@app.route("/delivery_payment_link/<int:order_id>")
def delivery_payment_link(order_id):

    order = Order.query.get_or_404(order_id)

    payment_link = razorpay_client.payment_link.create({

        "amount": int(order.final_total * 100),

        "currency": "INR",

        "description": f"Payment for {order.order_id}",

        "customer": {
            "name": order.customer_name,
            "email": order.email or "",
            "contact": order.phone
        },

        "notify": {
            "sms": False,
            "email": False
        }

    })

    order.payment_link_id = payment_link["id"]
    order.payment_link_url = payment_link["short_url"]

    db.session.commit()

    message = f"""
Hello {order.customer_name},

Please complete payment for your order.

Order ID: {order.order_id}

Amount: ₹{order.final_total}

Payment Link:
{payment_link['short_url']}

Thank you for choosing RucHiGo.
"""

    whatsapp_url = (
        f"https://wa.me/91{order.phone}"
        f"?text={urllib.parse.quote(message)}"
    )

    return redirect(whatsapp_url)

@app.route("/delivery_payment_qr/<int:order_id>")
def delivery_payment_qr(order_id):

    order = Order.query.get_or_404(order_id)

    # Create payment link only if it doesn't exist
    if not order.payment_link_url:

        payment_link = razorpay_client.payment_link.create({

            "amount": int(order.final_total * 100),

            "currency": "INR",

            "description": f"Payment for {order.order_id}",

            "customer": {
                "name": order.customer_name,
                "email": order.email or "",
                "contact": order.phone
            },

            "notify": {
                "sms": False,
                "email": False
            }

        })

        order.payment_link_id = payment_link["id"]
        order.payment_link_url = payment_link["short_url"]

        db.session.commit()

    # Generate QR from payment link
    qr = qrcode.make(order.payment_link_url)

    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")

    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return render_template(
        "payment_qr.html",
        order=order,
        qr_base64=qr_base64
    )
import hmac
import hashlib
import json
from flask import request, jsonify



@app.route("/razorpay_webhook", methods=["POST"])
def razorpay_webhook():

    webhook_signature = request.headers.get(
        "X-Razorpay-Signature"
    )

    body = request.data

    generated_signature = hmac.new(
        bytes(RAZORPAY_WEBHOOK_SECRET, "utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()

    if generated_signature != webhook_signature:
        return jsonify({
            "success": False,
            "message": "Invalid signature"
        }), 400

    payload = json.loads(body)

    event = payload.get("event")

    print("Webhook Event:", event)

    # Only process successful payment link payments
    if event == "payment_link.paid":

        payment_entity = payload["payload"][
            "payment_link"
        ]["entity"]

        payment_link_id = payment_entity["id"]

        order = Order.query.filter_by(
            payment_link_id=payment_link_id
        ).first()

        if order:

            order.payment_status = "Paid"
            order.payment_verified = True
            order.payment_type = "Online"
            order.payment_source = "DeliveryLink"

            order.payment_time = datetime.utcnow()

            # Store Razorpay Payment Link ID
            order.payment_order_id = payment_link_id

            try:
                payment_data = payload["payload"][
                    "payment"
                ]["entity"]

                order.payment_id = payment_data.get("id")

                order.payment_method_used = (
                    payment_data.get("method", "")
                    .upper()
                )

                order.transaction_reference = (
                    payment_data.get(
                        "acquirer_data",
                        {}
                    ).get(
                        "upi_transaction_id"
                    )
                )

            except Exception as e:
                print(
                    "Could not fetch payment details:",
                    e
                )

            db.session.commit()

            print(
                f"Payment received for {order.order_id}"
            )

        else:
            print(
                "Order not found for payment link:",
                payment_link_id
            )
    # ---------------- QR PAYMENT ----------------

    elif event == "qr_code.credited":

        qr_entity = payload["payload"]["qr_code"]["entity"]

        qr_id = qr_entity["id"]

        order = Order.query.filter_by(
            payment_qr_id=qr_id
        ).first()

        if order:

            order.payment_status = "Paid"
            order.payment_verified = True
            order.payment_type = "Online"
            order.payment_source = "DeliveryQR"

            order.payment_time = datetime.utcnow()

            try:

                payment_data = payload["payload"]["payment"]["entity"]

                order.payment_id = payment_data.get("id")

                order.payment_method_used = (
                    payment_data.get("method", "").upper()
                )

                order.transaction_reference = (
                    payment_data.get(
                        "acquirer_data", {}
                    ).get("upi_transaction_id")
                )

            except Exception as e:

                print("QR Payment Details Error:", e)

            db.session.commit()

            print(
                f"QR Payment received for {order.order_id}"
            )

        else:

            print(
                "Order not found for QR:",
                qr_id
            )
    return jsonify({
        "success": True
    })


from datetime import datetime

@app.route("/admin/payment-status")
def payment_status():

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    from_date = request.args.get("from")
    to_date = request.args.get("to")

    query = Order.query

    if from_date and to_date:

        start = datetime.strptime(from_date,"%Y-%m-%d").date()
        end = datetime.strptime(to_date,"%Y-%m-%d").date()

        query = query.filter(
            db.func.date(Order.created_at).between(start,end)
        )

    orders = query.order_by(
        Order.created_at.desc()
    ).all()

    # -----------------------------
    # Dashboard Counts
    # -----------------------------

    total_orders = len(orders)

    paid_count = sum(
        1 for o in orders
        if o.payment_status == "Paid"
    )

    pending_count = sum(
        1 for o in orders
        if o.payment_status == "Pending"
    )

    failed_count = sum(
        1 for o in orders
        if o.payment_status == "Failed"
    )

    # -----------------------------
    # Revenue
    # -----------------------------

    total_revenue = sum(
        o.final_total or 0
        for o in orders
        if o.payment_status == "Paid"
    )

    # -----------------------------
    # Refund
    # -----------------------------

    refund_total = sum(
        o.refund_amount or 0
        for o in orders
    )

    return render_template(
        "payment_status.html",

        orders=orders,

        total_orders=total_orders,

        paid_count=paid_count,
        pending_count=pending_count,
        failed_count=failed_count,

        total_revenue=total_revenue,
        refund_total=refund_total,

        from_date=from_date,
        to_date=to_date
    )

from flask import jsonify
@app.route("/delivery_generate_qr/<int:order_id>")
def delivery_generate_qr(order_id):
    print("QR ROUTE HIT:", order_id)
    try:

        order = Order.query.get_or_404(order_id)

        if not order.payment_qr_image_url:

            qr = razorpay_client.qrcode.create({

                "type": "upi_qr",

                "usage": "single_use",

                "fixed_amount": True,

                "payment_amount": int(order.final_total * 100),

                "name": f"Order {order.order_id}",

                "description": f"Payment for {order.order_id}"

            })

            print("QR CREATED SUCCESSFULLY")
            print(qr)

            order.payment_qr_id = qr.get("id")
            order.payment_qr_image_url = qr.get("image_url")
            order.payment_qr_status = qr.get("status")

            db.session.commit()

        return jsonify({
            "success": True,
            "image": order.payment_qr_image_url,
            "amount": order.final_total,
            "order": order.order_id
        })

    except Exception as e:

        print("========== QR ERROR ==========")
        print(str(e))
        print("==============================")

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
# ------------------ DB INIT ------------------

# ------------------ RUN ------------------
# Your routes here...

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)