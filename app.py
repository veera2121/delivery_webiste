# ================= GEVENT =================
from gevent import monkey
monkey.patch_all()
import sys

if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if sys.stderr:
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
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
from flask import send_file
load_dotenv()
# ================= EXTENSIONS =================
from flask_socketio import SocketIO, emit, join_room
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from sqlalchemy import or_, case
from sqlalchemy.orm import joinedload
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, current_user
from time import perf_counter

from flask import Flask, render_template, request, redirect, url_for, session, flash
from push import VAPID_PUBLIC_KEY, register_subscription, send_push, subscriptions
from functools import wraps
import firebase_admin
from firebase_admin import credentials

from dispatch_service import haversine 
from dispatch_service import assign_delivery_to_order,assign_waiting_order_to_rider,find_nearest_rider_excluding
# ================= LOCAL IMPORTS =================
from push import send_push
from users.routes import users_bp 
from extensions import db
from models import (
    db,
    Restaurant,
    RestaurantUser,
    MenuItem,
    Order,
    OrderItem,
    DeliveryPerson,
    FoodItem,
    OTP,
    CouponUsage,
    RestaurantOffer,
    Customer,
    UserFeedback,
    RestaurantDelivery,
    DeliverySettings,
    Item,
    CoinLedger,
    ShopSettings,
    RewardSetting,
    RewardBadge,
    Category,
    Offer,
    Employee,
    EmployeeOTP,
    EmployeeSession,
    OrderEditHistory,
    RiderSettlement,
    RiderApplication,
    RiderAuthAccount,
    RiderPasswordResetRequest,    
    RestaurantPickupQR,
    OrderPickupVerification
)
import os
import secrets

from datetime import datetime, timedelta
from functools import wraps

from flask import (
    jsonify,
    request,
    send_file,
    session
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from werkzeug.utils import secure_filename
from reward_engine import add_coins, redeem_coins
from recommendation_engine import get_recommendations
from apscheduler.schedulers.background import BackgroundScheduler
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
ASSIGNMENT_TIMEOUT_SECONDS = 30

ASSIGNMENT_PENDING_STATUS = "Assignment Pending"
READY_STATUS = "Ready"

RIDER_PENDING_RESPONSE = "Pending"
RIDER_ACCEPTED_RESPONSE = "Accepted"
RIDER_REJECTED_RESPONSE = "Rejected"
RIDER_EXPIRED_RESPONSE = "Expired"
# ------------------ edit order imports ------------------
from admin_order_edit import (
    register_admin_order_edit
)

register_admin_order_edit(
    app=app,
    db=db,
    Order=Order,
    OrderItem=OrderItem,
    MenuItem=MenuItem,
    OrderEditHistory=OrderEditHistory
)

ALLOWED_DOC_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "pdf"
}

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024


def _normalize_phone(value):
    digits = "".join(
        ch for ch in (value or "")
        if ch.isdigit()
    )

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]

    return digits


def _safe_doc_root():

    root = os.path.join(
        app.instance_path,
        "private_rider_documents"
    )

    os.makedirs(
        root,
        exist_ok=True
    )

    return root


def _validate_upload(
    file_storage,
    field_name,
    required=True
):

    if (
        not file_storage
        or not file_storage.filename
    ):

        if required:
            raise ValueError(
                f"{field_name} is required."
            )

        return None

    filename = secure_filename(
        file_storage.filename
    )

    if "." not in filename:

        raise ValueError(
            f"Invalid {field_name} file."
        )

    ext = filename.rsplit(
        ".",
        1
    )[1].lower()

    if ext not in ALLOWED_DOC_EXTENSIONS:

        raise ValueError(
            f"{field_name} must be JPG, JPEG, PNG, WEBP or PDF."
        )

    stream = file_storage.stream

    try:

        current = stream.tell()

        stream.seek(
            0,
            os.SEEK_END
        )

        size = stream.tell()

        stream.seek(current)

        if size > MAX_DOCUMENT_BYTES:

            raise ValueError(
                f"{field_name} must be 8 MB or smaller."
            )

    except (
        OSError,
        AttributeError
    ):

        pass

    return ext


def _save_private_upload(
    file_storage,
    application_code,
    label,
    required=True
):

    ext = _validate_upload(
        file_storage,
        label,
        required
    )

    if ext is None:
        return None

    app_dir = os.path.join(
        _safe_doc_root(),
        application_code
    )

    os.makedirs(
        app_dir,
        exist_ok=True
    )

    random_name = (
        f"{label}_{secrets.token_hex(12)}.{ext}"
    )

    full_path = os.path.join(
        app_dir,
        random_name
    )

    file_storage.save(
        full_path
    )

    return full_path


def _generate_application_code():

    while True:

        code = (
            f"RG-RIDER-"
            f"{datetime.utcnow().strftime('%y%m%d')}-"
            f"{secrets.randbelow(9000) + 1000}"
        )

        exists = (
            RiderApplication.query
            .filter_by(
                application_code=code
            )
            .first()
        )

        if not exists:
            return code


def _parse_date(value):

    if not value:
        return None

    try:

        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()

    except ValueError:

        raise ValueError(
            "Date of birth must be YYYY-MM-DD."
        )


def _admin_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not session.get("admin_id"):

            return jsonify({
                "success": False,
                "message": "Admin login required."
            }), 401

        return fn(*args, **kwargs)

    return wrapper
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

    cutoff = (
        datetime.utcnow()
        - timedelta(minutes=15)
    )

    unpaid_orders = Order.query.filter(
        Order.payment_type == "Online",
        Order.status == "Pending Payment",
        Order.payment_status == "Pending",
        Order.created_at < cutoff,
    ).all()

    for order in unpaid_orders:

        # Optional but recommended:
        # reconcile_razorpay_payment(order)
        # before cancelling.

        if order.payment_status == "Paid":
            continue

        order.status = "Cancelled"
        order.payment_status = "Failed"

        order.cancel_reason = (
            "Payment not completed within 15 minutes"
        )

    db.session.commit()
@app.before_request
def cleanup_orders():

    cancel_unpaid_orders()


def send_new_order_notification(rider, order):

    # ========================================================
    # FCM TOKEN CHECK
    # ========================================================

    if not rider.fcm_token:
        print(
            f"❌ Rider {rider.name} has no FCM token."
        )
        return False

    # ========================================================
    # ASSIGNMENT TIME
    # ========================================================

    assigned_at = ""

    assignment_expires_at = ""

    if order.assigned_at:
        assigned_at = order.assigned_at.isoformat()

    if order.assignment_expires_at:
        assignment_expires_at = (
            order.assignment_expires_at.isoformat()
        )

    # ========================================================
    # DELIVERY CHARGE
    # ========================================================

    delivery_charge = getattr(
        order,
        "delivery_charge",
        0
    )

    if delivery_charge is None:
        delivery_charge = 0

    # ========================================================
    # RIDER EARNING
    # ========================================================

    rider_earning = getattr(
        order,
        "rider_earning",
        None
    )

    if rider_earning is None:
        rider_earning = ""

    # ========================================================
    # NOTIFICATION DATA
    # ========================================================

    data = {

        "type":
            "new_order",

        "order_id":
            str(order.id),

        "order_number":
            str(order.order_id),

        "customer_name":
            order.customer_name or "",

        "customer_phone":
            order.phone or "",

        "restaurant_name":
            (
                order.restaurant.name
                if order.restaurant
                else ""
            ),

        "total":
            str(
                order.final_total or 0
            ),

        "payment_type":
            order.payment_type or "",

        "address":
            order.address or "",

        "distance":
            str(
                order.distance_km or 0
            ),

        # ====================================================
        # IMPORTANT
        # DELIVERY CHARGE
        # ====================================================

        "delivery_charge":
            str(delivery_charge),

        # ====================================================
        # RIDER EARNING
        # ====================================================

        "rider_earning":
            str(rider_earning),

        # ====================================================
        # SERVER TIMER
        # ====================================================

        "assigned_at":
            assigned_at,

        "assignment_expires_at":
            assignment_expires_at
    }

    # ========================================================
    # DEBUG
    # ========================================================

    print(
        "========================================"
    )

    print(
        "🚚 SENDING NEW ORDER NOTIFICATION"
    )

    print(
        "ORDER:",
        order.order_id
    )

    print(
        "RIDER:",
        rider.id,
        rider.name
    )

    print(
        "DELIVERY CHARGE:",
        delivery_charge
    )

    print(
        "RIDER EARNING:",
        rider_earning
    )

    print(
        "ASSIGNED AT:",
        assigned_at
    )

    print(
        "EXPIRES AT:",
        assignment_expires_at
    )

    print(
        "========================================"
    )

    # ========================================================
    # SEND FCM
    # ========================================================

    try:

        response = send_push_notification(

            title=
                "🚚 New Delivery Order",

            body=(
                f"Order #{order.order_id} "
                f"is waiting for your acceptance."
            ),

            target_type=
                "token",

            target_value=
                rider.fcm_token,

            data=
                data
        )

        if response:

            print(
                f"✅ New order notification "
                f"sent to {rider.name}"
            )

            return True

        print(
            f"❌ Notification sending failed "
            f"for {rider.name}"
        )

        return False

    except Exception as e:

        print(
            "❌ NEW ORDER NOTIFICATION ERROR:",
            e
        )

        return False
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



from datetime import datetime, time as datetime_time, timezone
from zoneinfo import ZoneInfo
import pandas as pd

from datetime import datetime, time as datetime_time, timezone
from zoneinfo import ZoneInfo

def build_rider_daily_settlement(rider_id):

    print("\n====================================")
    print("💰 BUILD RIDER SETTLEMENT")
    print("RIDER:", rider_id)
    print("====================================")

    # =========================================================
    # INDIA DATE → UTC RANGE
    # =========================================================

    india_tz = ZoneInfo("Asia/Kolkata")
    now_india = datetime.now(india_tz)

    today_date = now_india.date()

    start_india = datetime.combine(
        today_date,
        datetime_time.min,
        tzinfo=india_tz
    )

    end_india = datetime.combine(
        today_date,
        datetime_time.max,
        tzinfo=india_tz
    )

    start_utc = (
        start_india
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )

    end_utc = (
        end_india
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )

    # =========================================================
    # FIND LAST FROZEN BATCH
    #
    # Frozen means:
    #   Submitted
    #   Verified
    #
    # Once Submitted:
    # Never recalculate that batch again.
    # =========================================================

    last_frozen = (
        RiderSettlement.query
        .filter(
            RiderSettlement.rider_id == rider_id,
            RiderSettlement.settlement_date == today_date,
            db.func.lower(
                RiderSettlement.status
            ).in_([
                "submitted",
                "verified"
            ])
        )
        .order_by(
            RiderSettlement.batch_no.desc(),
            RiderSettlement.id.desc()
        )
        .first()
    )

    # =========================================================
    # FIND CURRENT PENDING BATCH
    # =========================================================

    current_settlement = (
        RiderSettlement.query
        .filter(
            RiderSettlement.rider_id == rider_id,
            RiderSettlement.settlement_date == today_date,
            db.func.lower(
                RiderSettlement.status
            ) == "pending"
        )
        .order_by(
            RiderSettlement.batch_no.desc(),
            RiderSettlement.id.desc()
        )
        .first()
    )

    # =========================================================
    # DETERMINE CURRENT BATCH NUMBER
    # =========================================================

    if current_settlement:

        current_batch_no = int(
            current_settlement.batch_no or 1
        )

    elif last_frozen:

        current_batch_no = (
            int(
                last_frozen.batch_no or 1
            )
            + 1
        )

    else:

        current_batch_no = 1

    # =========================================================
    # DETERMINE ORDER CUTOFF
    #
    # Submitted:
    # use submitted_at.
    #
    # Verified:
    # preferably use submitted_at.
    #
    # This means:
    #
    # Batch #4 Submitted
    # ↓
    # Any delivery after submitted_at
    # belongs to Batch #5.
    #
    # Admin does NOT need to verify #4
    # before Batch #5 can start.
    # =========================================================

    cutoff_time = None

    if last_frozen:

        frozen_status = str(
            last_frozen.status or ""
        ).strip().lower()

        if frozen_status == "submitted":

            cutoff_time = (
                last_frozen.submitted_at
                or last_frozen.updated_at
            )

        elif frozen_status == "verified":

            cutoff_time = (
                last_frozen.submitted_at
                or last_frozen.verified_at
                or last_frozen.updated_at
            )

    # =========================================================
    # QUERY TODAY'S DELIVERED ORDERS
    # =========================================================

    order_query = (
        Order.query
        .filter(
            Order.delivery_person_id == rider_id,
            Order.status == "Delivered",
            Order.delivered_time.isnot(None),
            Order.delivered_time >= start_utc,
            Order.delivered_time <= end_utc
        )
    )

    # =========================================================
    # ONLY ORDERS AFTER PREVIOUS FROZEN BATCH
    # =========================================================

    if cutoff_time:

        order_query = (
            order_query
            .filter(
                Order.delivered_time
                > cutoff_time
            )
        )

    orders = (
        order_query
        .order_by(
            Order.delivered_time.asc()
        )
        .all()
    )

    # =========================================================
    # DEBUG
    # =========================================================

    print(
        "DATE:",
        today_date
    )

    print(
        "CURRENT BATCH:",
        current_batch_no
    )

    if last_frozen:

        print(
            "LAST FROZEN BATCH:",
            last_frozen.batch_no
        )

        print(
            "LAST FROZEN STATUS:",
            last_frozen.status
        )

        print(
            "CUTOFF:",
            cutoff_time
        )

    print(
        "NEW UNSETTLED ORDERS:",
        len(orders)
    )

    # =========================================================
    # NO NEW DELIVERIES
    #
    # VERY IMPORTANT:
    #
    # Never create an empty Pending settlement.
    #
    # CASE 1:
    # Previous batch exists today.
    # Return frozen batch.
    #
    # CASE 2:
    # Absolutely no settlement exists today.
    # Return None.
    # =========================================================

    if (
        not orders
        and not current_settlement
    ):

        print(
            "NO NEW DELIVERIES."
        )

        if last_frozen:

            print(
                "RETURNING LAST FROZEN BATCH:",
                last_frozen.batch_no
            )

            return last_frozen

        print(
            "NO SETTLEMENT CREATED."
        )

        return None

    # =========================================================
    # CALCULATIONS
    # =========================================================

    total_deliveries = 0

    cod_orders = 0

    online_orders = 0

    cash_collected = 0.0

    online_amount = 0.0

    total_order_value = 0.0

    rider_earnings = 0.0

    # =========================================================
    # PROCESS ORDERS
    # =========================================================

    for order in orders:

        total_deliveries += 1

        order_total = float(
            order.final_total or 0
        )

        delivery_charge = float(
            order.delivery_charge or 0
        )

        total_order_value += (
            order_total
        )

        # Rider earns delivery charge
        # on every delivered order.
        rider_earnings += (
            delivery_charge
        )

        payment_type = str(
            order.payment_type or ""
        ).strip().lower()

        payment_source = str(
            order.payment_source or ""
        ).strip().lower()

        payment_method = str(
            order.payment_method_used or ""
        ).strip().lower()

        is_cod = (

            payment_type in (
                "cod",
                "cash",
                "cash on delivery",
                "cash_on_delivery"
            )

            or

            payment_source in (
                "cod",
                "cash",
                "cash on delivery",
                "cash_on_delivery"
            )

            or

            payment_method in (
                "cod",
                "cash",
                "cash on delivery",
                "cash_on_delivery"
            )
        )

        if is_cod:

            cod_orders += 1

            cash_collected += (
                order_total
            )

        else:

            online_orders += 1

            online_amount += (
                order_total
            )

        print(
            "ORDER:",
            order.id,
            "| DELIVERED:",
            order.delivered_time,
            "| TOTAL:",
            order_total,
            "| DELIVERY:",
            delivery_charge,
            "| TYPE:",
            payment_type,
            "| SOURCE:",
            payment_source,
            "| METHOD:",
            payment_method
        )

    # =========================================================
    # NET SETTLEMENT
    #
    # COD cash held by rider
    # minus rider earnings.
    #
    # Positive:
    # Rider gives RucHiGo cash.
    #
    # Negative:
    # RucHiGo pays rider.
    # =========================================================

    net_amount = (
        cash_collected
        - rider_earnings
    )

    if net_amount > 0:

        cash_to_submit = (
            net_amount
        )

        platform_to_pay = 0.0

    elif net_amount < 0:

        cash_to_submit = 0.0

        platform_to_pay = abs(
            net_amount
        )

    else:

        cash_to_submit = 0.0

        platform_to_pay = 0.0

    # =========================================================
    # CREATE CURRENT BATCH ONLY WHEN ORDERS EXIST
    # =========================================================

    if not current_settlement:

        # Safety:
        # absolutely do not create
        # a zero-delivery settlement.
        if not orders:

            print(
                "NO ORDERS."
            )

            print(
                "SKIPPING SETTLEMENT CREATION."
            )

            return (
                last_frozen
                if last_frozen
                else None
            )

        current_settlement = (
            RiderSettlement(
                rider_id=rider_id,
                settlement_date=today_date,
                batch_no=current_batch_no,
                status="Pending"
            )
        )

        db.session.add(
            current_settlement
        )

    # =========================================================
    # UPDATE ONLY CURRENT PENDING BATCH
    #
    # Submitted/Verified batches
    # are NEVER modified here.
    # =========================================================

    current_status = str(
        current_settlement.status
        or ""
    ).strip().lower()

    if current_status != "pending":

        print(
            "SETTLEMENT IS NOT PENDING."
        )

        print(
            "RETURNING WITHOUT RECALCULATION:",
            current_settlement.id
        )

        return current_settlement

    current_settlement.total_deliveries = (
        total_deliveries
    )

    current_settlement.cod_orders = (
        cod_orders
    )

    current_settlement.online_orders = (
        online_orders
    )

    current_settlement.cash_collected = round(
        cash_collected,
        2
    )

    current_settlement.online_amount = round(
        online_amount,
        2
    )

    current_settlement.total_order_value = round(
        total_order_value,
        2
    )

    current_settlement.rider_earnings = round(
        rider_earnings,
        2
    )

    current_settlement.cash_to_submit = round(
        cash_to_submit,
        2
    )

    current_settlement.platform_to_pay = round(
        platform_to_pay,
        2
    )

    current_settlement.updated_at = (
        datetime.utcnow()
    )

    db.session.commit()

    # =========================================================
    # FINAL DEBUG
    # =========================================================

    print(
        "\n===================================="
    )

    print(
        "💰 SETTLEMENT BATCH RESULT"
    )

    print(
        "RIDER:",
        rider_id
    )

    print(
        "DATE:",
        today_date
    )

    print(
        "BATCH:",
        current_settlement.batch_no
    )

    print(
        "------------------------------------"
    )

    print(
        "DELIVERIES:",
        total_deliveries
    )

    print(
        "COD ORDERS:",
        cod_orders
    )

    print(
        "ONLINE ORDERS:",
        online_orders
    )

    print(
        "------------------------------------"
    )

    print(
        "COD CASH:",
        cash_collected
    )

    print(
        "ONLINE:",
        online_amount
    )

    print(
        "TOTAL VALUE:",
        total_order_value
    )

    print(
        "------------------------------------"
    )

    print(
        "RIDER EARNINGS:",
        rider_earnings
    )

    print(
        "CASH TO SUBMIT:",
        cash_to_submit
    )

    print(
        "PLATFORM TO PAY:",
        platform_to_pay
    )

    print(
        "STATUS:",
        current_settlement.status
    )

    print(
        "====================================\n"
    )

    return current_settlement


def sync_restaurant_menu(restaurant):

    if not restaurant.sheet_url:
        return

    try:

        df = pd.read_csv(

            restaurant.sheet_url,

            engine="python",

            on_bad_lines="skip"

        )

        df = df.fillna("")

        new_items = []

        for _, row in df.iterrows():

            raw_price = str(

                row.get("price", "")

            ).strip()

            try:

                price = float(raw_price)

            except:

                price = 0

            item = MenuItem(

                restaurant_id=restaurant.id,

                name=row.get("name", ""),

                description=row.get(

                    "description", ""

                ),

                category=row.get(

                    "category", ""

                ),

                price=price,

                image_url=row.get(

                    "image_url", ""

                ),

                availability=row.get(

                    "availability",

                    "yes"

                ),

                item_type=restaurant.category_type,

                extra_data=dict(row)

            )

            new_items.append(item)

        MenuItem.query.filter_by(

            restaurant_id=restaurant.id

        ).delete()

        for item in new_items:

            db.session.add(item)

        db.session.commit()
   
        print(

            restaurant.name,

            "synced"
        
        )
        
    except Exception as e:

        print(

            restaurant.name,

            e

        )
def sync_all_restaurants():

    restaurants = Restaurant.query.all()

    for restaurant in restaurants:

        sync_restaurant_menu(
            restaurant
        )
    
    print("Done") 

def scheduled_sync():

    with app.app_context():

        sync_all_restaurants()
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
        "📸 Instagram: https://instagram.com/ruchigo.in\n"
        "🎉 Follow us for exciting offers, new restaurants & updates!\n\n"

        "Thank you for choosing *RucHiGo* 💙"
    )
    encoded = urllib.parse.quote_plus(msg)
    return f"https://wa.me/{phone}?text={encoded}"

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


import time


def restaurant_open(restaurant):

    # ========================================================
    # MANUAL ACCEPT ORDERS CHECK
    # ========================================================

    if not restaurant.can_accept_orders:
        return False


    # ========================================================
    # NO OPENING / CLOSING TIME
    # ========================================================

    if (
        not restaurant.opening_time
        or not restaurant.closing_time
    ):
        return True


    # ========================================================
    # INDIA CURRENT TIME
    # ========================================================

    now = datetime.now(
        pytz.timezone(
            "Asia/Kolkata"
        )
    ).time()


    # ========================================================
    # NORMAL HOURS
    # Example: 10 AM → 11 PM
    # ========================================================

    if (
        restaurant.opening_time
        < restaurant.closing_time
    ):

        return (
            restaurant.opening_time
            <= now
            <= restaurant.closing_time
        )


    # ========================================================
    # OVERNIGHT HOURS
    # Example: 6 PM → 2 AM
    # ========================================================

    return (
        now >= restaurant.opening_time
        or now <= restaurant.closing_time
    )

# ============================================================
# PROCESS RESTAURANT / STORE STATUS
# ============================================================

def process_store(
    store,
    user_lat,
    user_lng,
    user_location_set,
    now
):

    # ========================================================
    # DEFAULT DELIVERY STATE
    # ========================================================

    store.deliverable = True
    store.distance = None


    # ========================================================
    # DELIVERY DISTANCE CHECK
    # ========================================================

    if (
        user_location_set
        and store.latitude is not None
        and store.longitude is not None
        and store.delivery_radius_km
    ):

        try:

            dist = haversine(

                float(user_lat),
                float(user_lng),

                float(store.latitude),
                float(store.longitude)

            )


            store.distance = round(
                dist,
                1
            )


            store.deliverable = (
                dist
                <= float(
                    store.delivery_radius_km
                )
            )


        except Exception as e:

            print(
                "STORE DISTANCE ERROR:",
                store.name,
                e
            )

            store.distance = None
            store.deliverable = True


    # ========================================================
    # OPEN / CLOSED STATUS
    # ========================================================

    if (
        store.opening_time
        and store.closing_time
    ):

        # ----------------------------------------------------
        # NORMAL HOURS
        # Example:
        # 10:00 AM → 11:00 PM
        # ----------------------------------------------------

        if (
            store.opening_time
            < store.closing_time
        ):

            store.is_open = (

                store.opening_time
                <= now
                <= store.closing_time

            )


        # ----------------------------------------------------
        # OVERNIGHT HOURS
        # Example:
        # 6:00 PM → 2:00 AM
        # ----------------------------------------------------

        else:

            store.is_open = (

                now
                >= store.opening_time

                or

                now
                <= store.closing_time

            )


    else:

        store.is_open = True


    # ========================================================
    # MANUAL ACCEPT ORDERS
    # ========================================================

    if not store.can_accept_orders:

        store.is_open = False


    return store
total = time.time()
from datetime import datetime 
from zoneinfo import ZoneInfo
from sqlalchemy.orm import joinedload
from datetime import datetime
import pytz
from flask import request, render_template, session
from reward_engine import update_customer_badge
from flask_login import current_user
from sqlalchemy import or_
# ============================================================
# HOME PAGE
# ============================================================
# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def home():

    start = time.time()

    # ========================================================
    # CURRENT INDIA TIME
    # ========================================================

    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist).time()


    # ========================================================
    # SELECTED LOCATION
    # ========================================================

    location_from_url = request.args.get(
        "location",
        "",
        type=str
    ).strip()


    # Save selected location in session
    if location_from_url:

        session["selected_location"] = (
            location_from_url
        )


    # Keep selected location when customer
    # returns from Search / Profile / etc.
    selected_location = session.get(
        "selected_location",
        ""
    )


    # ========================================================
    # BADGE COUNTS
    # CACHED VERSION
    # ========================================================

    badge_counts = get_badge_counts()

    silver_count = badge_counts["silver"]
    gold_count = badge_counts["gold"]
    platinum_count = badge_counts["platinum"]


    # ========================================================
    # CUSTOMER DATA
    # ========================================================

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


        # ----------------------------------------------------
        # KEEP BADGE UPDATED
        # ----------------------------------------------------

        update_customer_badge(
            customer
        )


        badge = (
            customer.badge.name
            if customer.badge
            else "No Badge"
        )


        # ----------------------------------------------------
        # ONE-TIME COINS ANIMATION
        # ----------------------------------------------------

        if (
            customer.last_reward_coins
            and customer.last_reward_coins > 0
        ):

            earned_coins = (
                customer.last_reward_coins
            )

            customer.last_reward_coins = 0


        # Commit badge/reward changes together
        db.session.commit()


        # ----------------------------------------------------
        # BADGE PROGRESS
        # ----------------------------------------------------

        badges = (
            RewardBadge.query
            .filter_by(active=True)
            .order_by(
                RewardBadge.required_coins.asc()
            )
            .all()
        )


        for b in badges:

            if (
                customer.coins
                < b.required_coins
            ):

                next_badge = b

                break


        if next_badge:

            current_min = (
                customer.badge.required_coins
                if customer.badge
                else 0
            )


            span = (
                next_badge.required_coins
                - current_min
            )


            if span > 0:

                progress_percent = int(
                    (
                        (
                            customer.coins
                            - current_min
                        )
                        / span
                    )
                    * 100
                )


            progress_percent = max(
                0,
                min(
                    progress_percent,
                    100
                )
            )


            coins_to_next_badge = max(
                0,
                (
                    next_badge.required_coins
                    - customer.coins
                )
            )


        else:

            progress_percent = 100

            coins_to_next_badge = 0


    # ========================================================
    # USER GPS LOCATION
    # ========================================================

    user_lat = session.get(
        "user_lat"
    )

    user_lng = session.get(
        "user_lng"
    )


    user_location_set = (
        user_lat is not None
        and user_lng is not None
    )


    # ========================================================
    # FETCH RESTAURANTS + BAKERIES
    # ========================================================

    restaurant_query = (
        Restaurant.query
        .options(
            joinedload(
                Restaurant.categories
            )
        )
        .filter(
            Restaurant.category_type.in_(
                [
                    "restaurant",
                    "bakery"
                ]
            )
        )
    )


    if selected_location:

        restaurant_query = (
            restaurant_query
            .filter(
                Restaurant.location
                == selected_location
            )
        )


    restaurants = (
        restaurant_query.all()
    )


    # ========================================================
    # FETCH GROCERY SHOPS
    # ========================================================

    grocery_shops = []


    # --------------------------------------------------------
    # LOCATION MANUALLY SELECTED
    # --------------------------------------------------------

    if selected_location:

        grocery_shops = (
            Restaurant.query
            .filter(
                Restaurant.location
                == selected_location,
                Restaurant.category_type
                == "grocery"
            )
            .all()
        )


    # --------------------------------------------------------
    # NO LOCATION FILTER
    # ONLY SHOW NEARBY GROCERY USING GPS
    # --------------------------------------------------------

    elif user_location_set:

        all_grocery = (
            Restaurant.query
            .filter(
                Restaurant.category_type
                == "grocery"
            )
            .all()
        )


        for g in all_grocery:

            if (
                g.latitude is None
                or g.longitude is None
                or not g.delivery_radius_km
            ):

                continue


            dist = haversine(
                float(user_lat),
                float(user_lng),
                float(g.latitude),
                float(g.longitude)
            )


            if (
                dist
                <= g.delivery_radius_km
            ):

                grocery_shops.append(
                    g
                )


    # ========================================================
    # CATEGORIES
    # ========================================================

    categories = (
        Category.query.all()
        )
        # ========================================================
    # GROCERY ITEM CATEGORIES
    # ========================================================

    grocery_category_query = (
        db.session.query(
            MenuItem.category
        )
        .join(
            Restaurant,
            Restaurant.id == MenuItem.restaurant_id
        )
        .filter(
            Restaurant.category_type == "grocery",
            MenuItem.item_type == "grocery",
            MenuItem.availability == "yes",
            MenuItem.category.isnot(None)
        )
    )

    # Same selected-location filtering as grocery shops
    if selected_location:
        grocery_category_query = (
            grocery_category_query
            .filter(
                Restaurant.location == selected_location
            )
        )

    # Only categories belonging to currently visible grocery stores
    if grocery_shops:

        grocery_shop_ids = [
            g.id
            for g in grocery_shops
        ]

        grocery_category_query = (
            grocery_category_query
            .filter(
                MenuItem.restaurant_id.in_(
                    grocery_shop_ids
                )
            )
        )

    else:

        grocery_shop_ids = []


    grocery_category_rows = (
        grocery_category_query
        .distinct()
        .order_by(
            MenuItem.category.asc()
        )
        .all()
    )


    grocery_categories = [
        row[0].strip()
        for row in grocery_category_rows
        if row[0] and row[0].strip()
    ]


    # ========================================================
    # WHICH CATEGORIES EACH GROCERY SHOP HAS
    # ========================================================

    grocery_store_categories = {}

    if grocery_shop_ids:

        store_category_rows = (
            db.session.query(
                MenuItem.restaurant_id,
                MenuItem.category
            )
            .filter(
                MenuItem.restaurant_id.in_(
                    grocery_shop_ids
                ),
                MenuItem.item_type == "grocery",
                MenuItem.availability == "yes",
                MenuItem.category.isnot(None)
            )
            .distinct()
            .all()
        )

        for store_id, category in store_category_rows:

            if not category:
                continue

            category = category.strip()

            grocery_store_categories.setdefault(
                store_id,
                []
            )

            grocery_store_categories[
                store_id
            ].append(
                category
            )

    # ========================================================
    # POPULAR ITEMS
    # ========================================================

    restaurant_lookup = {

        r.id: r

        for r in restaurants

    }


    popular_items_raw = (

        db.session.query(

            Restaurant.id.label(
                "restaurant_id"
            ),

            Restaurant.name.label(
                "restaurant_name"
            ),

            Restaurant.category_type.label(
                "source_type"
            ),

            OrderItem.item_name,

            func.sum(
                OrderItem.quantity
            ).label(
                "total_orders"
            ),

            func.max(
                MenuItem.price
            ).label(
                "current_price"
            ),

            func.max(
                MenuItem.image_url
            ).label(
                "item_image"
            )

        )

        .join(
            Order,
            Order.id
            == OrderItem.order_id
        )

        .join(
            Restaurant,
            Restaurant.id
            == Order.restaurant_id
        )

        .outerjoin(
            MenuItem,

            db.and_(

                MenuItem.restaurant_id
                == Restaurant.id,

                MenuItem.name
                == OrderItem.item_name

            )
        )

    )


    # Only restaurants currently shown
    if restaurant_lookup:

        popular_items_raw = (
            popular_items_raw
            .filter(
                Restaurant.id.in_(
                    list(
                        restaurant_lookup.keys()
                    )
                )
            )
        )


    popular_items_raw = (

        popular_items_raw

        .group_by(

            Restaurant.id,

            Restaurant.name,

            Restaurant.category_type,

            OrderItem.item_name

        )

        .order_by(

            func.sum(
                OrderItem.quantity
            ).desc()

        )

        .limit(30)

        .all()

    )


    popular_sorted = []


    for item in popular_items_raw:

        restaurant = (
            restaurant_lookup.get(
                item.restaurant_id
            )
        )


        if not restaurant:

            continue


        price = (
            item.current_price
            or 0
        )


        # ----------------------------------------------------
        # BAKERY WEIGHT PRICE FALLBACK
        # ----------------------------------------------------

        if (
            item.source_type == "bakery"
            and price == 0
        ):

            menu = (
                MenuItem.query
                .filter_by(
                    restaurant_id=
                        item.restaurant_id,
                    name=
                        item.item_name
                )
                .first()
            )


            if menu:

                extra = (
                    menu.extra_data
                    or {}
                )


                weight_prices = (
                    extra.get(
                        "weight_prices",
                        ""
                    )
                )


                if weight_prices:

                    try:

                        price = float(

                            weight_prices
                            .split(",")[0]
                            .split(":")[1]

                        )

                    except (
                        ValueError,
                        IndexError,
                        TypeError
                    ):

                        pass


        # Don't show tiny addon items
        if price < 30:

            continue


        popular_sorted.append({

            "restaurant_id":
                item.restaurant_id,

            "restaurant_name":
                item.restaurant_name,

            "source_type":
                item.source_type,

            "item_name":
                item.item_name,

            "total_orders":
                item.total_orders,

            "price":
                price,

            "item_image":
                item.item_image,

            "restaurant":
                restaurant,

            "can_order": False

        })


    # ========================================================
    # BUDGET ITEMS
    # ========================================================

    restaurant_ids = [

        r.id

        for r in restaurants

    ]


    if restaurant_ids:

        budget_items = (

            MenuItem.query

            .filter(

                MenuItem.restaurant_id.in_(
                    restaurant_ids
                ),

                MenuItem.availability
                == "yes",

                MenuItem.price.between(
                    69,
                    159
                )

            )

            .all()

        )

    else:

        budget_items = []


    # ========================================================
    # WEEKLY TOP RESTAURANTS
    # ========================================================

    one_week_ago = (
        datetime.utcnow()
        - timedelta(days=7)
    )


    top_query = (

        db.session.query(

            Restaurant,

            func.count(
                Order.id
            ).label(
                "orders_count"
            )

        )

        .join(
            Order,
            Restaurant.id
            == Order.restaurant_id
        )

        .filter(
            Order.created_at
            >= one_week_ago,
            Order.status
            == "Delivered"
        )

    )


    if selected_location:

        top_query = (
            top_query
            .filter(
                Restaurant.location
                == selected_location
            )
        )


    top_restaurants_raw = (

        top_query

        .group_by(
            Restaurant.id
        )

        .order_by(
            func.count(
                Order.id
            ).desc()
        )

        .limit(20)

        .all()

    )


    top_restaurants = []


    for restaurant, count in top_restaurants_raw:

        top_restaurants.append(
            (
                restaurant,
                count
            )
        )


    section_title = (
        "🔥 This Week's Most Ordered"
    )


    # ========================================================
    # FALLBACK TOP RESTAURANTS
    # ========================================================

    if not top_restaurants:

        fallback_query = (

            db.session.query(

                Restaurant,

                func.count(
                    Order.id
                ).label(
                    "orders_count"
                )

            )

            .join(
                Order,
                Restaurant.id
                == Order.restaurant_id
            )

            .filter(
                Order.status
                == "Delivered"
            )

        )


        if selected_location:

            fallback_query = (
                fallback_query
                .filter(
                    Restaurant.location
                    == selected_location
                )
            )


        fallback_restaurants = (

            fallback_query

            .group_by(
                Restaurant.id
            )

            .order_by(
                func.count(
                    Order.id
                ).desc()
            )

            .limit(20)

            .all()

        )


        top_restaurants = [

            (
                restaurant,
                count
            )

            for restaurant, count
            in fallback_restaurants

        ]


        section_title = (
            "🏆 Most Ordered Restaurants"
        )


    # ========================================================
    # LOCATION DROPDOWN
    # ========================================================

    all_locations = (
        get_all_locations()
    )

    
    # ==========================================
    # FIND PENDING ONLINE PAYMENT
    # ==========================================

    pending_payment_order = (
        Order.query
        .filter(
            Order.payment_type == "Online",
            Order.payment_status == "Pending",
            Order.status == "Pending Payment"
        )
        .order_by(Order.created_at.desc())
        .first()
    )


    # ==========================================
    # CHECK RAZORPAY BEFORE SHOWING BUTTON
    # ==========================================

    if pending_payment_order:

        print(
            "Checking pending payment:",
            pending_payment_order.order_id
        )

        if pending_payment_order.payment_order_id:

            paid = reconcile_razorpay_payment(
                pending_payment_order
            )

            if paid:

                print(
                    "✅ Pending payment was actually Paid"
                )

                # Don't show Complete Payment button
                pending_payment_order = None
    # ========================================================
    # TRENDING ITEMS
    # ========================================================

    if selected_location:

        trending_items = (

            db.session.query(
                FoodItem
            )

            .join(
                Restaurant
            )

            .filter(

                Restaurant.location
                == selected_location,

                FoodItem.order_count > 0

            )

            .order_by(
                FoodItem.order_count.desc()
            )

            .limit(8)

            .all()

        )

    else:

        trending_items = []


    # ========================================================
    # PROCESS RESTAURANTS
    # ========================================================

    limited_restaurants = []


    for r in restaurants:

        process_store(
            r,
            user_lat,
            user_lng,
            user_location_set,
            now
        )


        if (
            r.is_limited_drop
            and r.can_accept_orders
        ):

            limited_restaurants.append(
                r
            )


    # ========================================================
    # PROCESS GROCERY SHOPS
    # SAME STATUS / DELIVERY LOGIC
    # ========================================================

    for g in grocery_shops:

        process_store(
            g,
            user_lat,
            user_lng,
            user_location_set,
            now
        )


    # ========================================================
    # POPULAR ITEM AVAILABILITY
    # Now restaurant state has been processed
    # ========================================================

    for item in popular_sorted:

        restaurant = (
            item["restaurant"]
        )


        item["can_order"] = (

            restaurant.can_accept_orders

            and restaurant.is_open

            and restaurant.deliverable

        )


    popular_sorted.sort(

        key=lambda x: (

            not x["can_order"],

            -x["total_orders"]

        )

    )


    popular_items = (
        popular_sorted[:25]
    )


    # ========================================================
    # BUDGET ITEM AVAILABILITY
    # ========================================================

    for item in budget_items:

        restaurant = (
            restaurant_lookup.get(
                item.restaurant_id
            )
        )


        item.can_order = bool(

            restaurant

            and restaurant.can_accept_orders

            and restaurant.is_open

            and restaurant.deliverable

        )


    budget_items.sort(

        key=lambda x: (

            not x.can_order,

            x.price

        )

    )


    # Max 3 budget items per restaurant
    restaurant_items = {}


    for item in budget_items:

        restaurant_items.setdefault(
            item.restaurant_id,
            []
        ).append(
            item
        )


    final_budget_items = []


    for items in (
        restaurant_items.values()
    ):

        final_budget_items.extend(
            items[:3]
        )


    budget_items = (
        final_budget_items[:27]
    )


    # ========================================================
    # SORT RESTAURANTS
    # NEW + OPEN + DELIVERABLE FIRST
    # ========================================================

    restaurants.sort(

        key=lambda r: (

            0
            if (
                is_new_restaurant(r)
                and r.deliverable
                and r.is_open
                and r.can_accept_orders
            )

            else 1
            if (
                r.deliverable
                and r.is_open
                and r.can_accept_orders
            )

            else 2,

            -(
                r.created_at.timestamp()
                if r.created_at
                else 0
            )

        )

    )


    # ========================================================
    # SORT GROCERY
    # ========================================================

    grocery_shops.sort(

        key=lambda g: (

            0
            if (
                is_new_restaurant(g)
                and g.deliverable
                and g.is_open
                and g.can_accept_orders
            )

            else 1
            if (
                g.deliverable
                and g.is_open
                and g.can_accept_orders
            )

            else 2,

            -(
                g.created_at.timestamp()
                if g.created_at
                else 0
            )

        )

    )


    # ========================================================
    # SORT TOP RESTAURANTS
    # OPEN FIRST + HIGH ORDER COUNT
    # ========================================================

    processed_restaurants = {

        r.id: r

        for r in restaurants

    }


    cleaned_top_restaurants = []


    for restaurant, count in top_restaurants:

        processed = (
            processed_restaurants.get(
                restaurant.id
            )
        )


        if processed:

            restaurant = processed

        else:

            process_store(
                restaurant,
                user_lat,
                user_lng,
                user_location_set,
                now
            )


        restaurant.is_open_now = (

            restaurant.can_accept_orders

            and restaurant.is_open

            and restaurant.deliverable

        )


        cleaned_top_restaurants.append(
            (
                restaurant,
                count
            )
        )


    cleaned_top_restaurants.sort(

        key=lambda x: (

            not x[0].is_open_now,

            -x[1]

        )

    )


    top_restaurants = (
        cleaned_top_restaurants[:10]
    )


    # ========================================================
    # SEO
    # ========================================================

    if selected_location:

        seo_title = (
            f"Online Food Delivery in "
            f"{selected_location} | RuchiGo"
        )


        seo_description = (

            "Order food online from nearby "
            "restaurants and bakeries in "
            f"{selected_location}. "
            "Fast local delivery."

        )


        seo_keywords = (

            f"{selected_location} "
            "food delivery, bakery, RuchiGo"

        )

    else:

        seo_title = (
            "Online Food Delivery | RuchiGo"
        )


        seo_description = (

            "Order food online from trusted "
            "local restaurants and bakeries. "
            "Fast delivery, fresh food."

        )


        seo_keywords = (
            "food delivery, "
            "bakery delivery, RuchiGo"
        )


    # ========================================================
    # AJAX RESTAURANT REFRESH
    # ========================================================

    if (
        request.headers.get(
            "X-Requested-With"
        )
        == "XMLHttpRequest"
    ):

        return render_template(

            "_restaurants.html",

            restaurants=
                restaurants,

            trending_items=
                trending_items,

            now=
                now

        )


    # ========================================================
    # PERFORMANCE DEBUG
    # ========================================================

    print(
        "HOME LOAD:",
        round(
            time.time() - start,
            2
        ),
        "seconds"
    )


    # ========================================================
    # FULL PAGE
    # ========================================================

    return render_template(

        "index.html",


        # Stores
        restaurants=
            restaurants,

        grocery_shops=
            grocery_shops,

        limited_restaurants=
            limited_restaurants,
            
        # Grocery category system
        grocery_categories=grocery_categories,
        grocery_store_categories=grocery_store_categories,

        # Location
        all_locations=
            all_locations,

        selected_location=
            selected_location,

        user_location_set=
            user_location_set,


        # Discovery sections
        trending_items=
            trending_items,

        popular_items=
            popular_items,

        budget_items=
            budget_items,

        top_restaurants=
            top_restaurants,

        section_title=
            section_title,


        # Current time
        now=
            now,


        # SEO
        seo_title=
            seo_title,

        seo_description=
            seo_description,

        seo_keywords=
            seo_keywords,


        # Customer rewards
        coins=
            coins,

        customer=
            customer,

        badge=
            badge,

        earned_coins=
            earned_coins,

        next_badge=
            next_badge,

        coins_to_next_badge=
            coins_to_next_badge,

        silver_count=
            silver_count,

        gold_count=
            gold_count,

        platinum_count=
            platinum_count,

        progress_percent=
            progress_percent,

        pending_payment_order=pending_payment_order,


        # Categories
        categories=
            categories

    )
# ============================================================
# RUCHIGO FLUTTER - FULL HOME API
#
# Add this route to your existing Flask application.
# It mirrors the customer-facing data prepared by your existing
# @app.route("/") home() route, but returns JSON for Flutter.
#
# It intentionally REUSES your existing helpers:
#   get_badge_counts()
#   update_customer_badge()
#   get_all_locations()
#   process_store()
#   is_new_restaurant()
#   haversine()
#   reconcile_razorpay_payment()
#
# It also uses your existing models:
#   Restaurant, Category, MenuItem, Order, OrderItem,
#   RewardBadge, FoodItem
# ============================================================
@app.route("/api/app/home", methods=["GET"])
def api_app_home():
    """
    RucHiGo Native App Home API

    Optimizations:
    - No Razorpay reconciliation inside Home request.
    - Avoids duplicate grocery-category queries.
    - Avoids per-item MenuItem query for bakery popular items.
    - Avoids lazy-loading FoodItem.restaurant for trending items.
    - Keeps the same JSON fields expected by Flutter.
    - Adds lightweight timing logs so slow sections can be identified.
    """

    home_started = perf_counter()

    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist).time()

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    selected_location = (
        request.args.get("location", "")
        .strip()
    )

    if selected_location:
        session["selected_location"] = selected_location
    else:
        selected_location = (
            session.get("selected_location", "")
            or ""
        ).strip()

    lat_arg = request.args.get("lat")
    lng_arg = request.args.get("lng")

    user_lat = None
    user_lng = None

    try:
        if lat_arg is not None and lng_arg is not None:
            user_lat = float(lat_arg)
            user_lng = float(lng_arg)

            session["user_lat"] = user_lat
            session["user_lng"] = user_lng

        else:
            saved_lat = session.get("user_lat")
            saved_lng = session.get("user_lng")

            if saved_lat is not None and saved_lng is not None:
                user_lat = float(saved_lat)
                user_lng = float(saved_lng)

    except (TypeError, ValueError):
        user_lat = None
        user_lng = None

    user_location_set = (
        user_lat is not None
        and user_lng is not None
    )

    # --------------------------------------------------------
    # REWARDS
    # Keep reward functionality, but only commit when needed.
    # --------------------------------------------------------

    rewards = None

    if current_user.is_authenticated:
        rewards_started = perf_counter()

        customer = current_user

        old_badge_id = getattr(
            customer,
            "badge_id",
            None,
        )

        earned_coins = 0

        update_customer_badge(customer)

        badge = (
            customer.badge.name
            if customer.badge
            else "No Badge"
        )

        if (
            customer.last_reward_coins
            and customer.last_reward_coins > 0
        ):
            earned_coins = (
                customer.last_reward_coins
            )

            customer.last_reward_coins = 0

        badges = (
            RewardBadge.query
            .filter_by(active=True)
            .order_by(
                RewardBadge.required_coins.asc()
            )
            .all()
        )

        next_badge = None

        customer_coins = (
            customer.coins or 0
        )

        for b in badges:
            if customer_coins < b.required_coins:
                next_badge = b
                break

        progress_percent = 100
        coins_to_next_badge = 0

        if next_badge:
            current_min = (
                customer.badge.required_coins
                if customer.badge
                else 0
            )

            span = (
                next_badge.required_coins
                - current_min
            )

            if span > 0:
                progress_percent = int(
                    (
                        (
                            customer_coins
                            - current_min
                        )
                        / span
                    )
                    * 100
                )

            progress_percent = max(
                0,
                min(
                    progress_percent,
                    100,
                ),
            )

            coins_to_next_badge = max(
                0,
                next_badge.required_coins
                - customer_coins,
            )

        badge_changed = (
            getattr(
                customer,
                "badge_id",
                None,
            )
            != old_badge_id
        )

        if earned_coins > 0 or badge_changed:
            db.session.commit()

        badge_counts = get_badge_counts()

        rewards = {
            "coins": customer_coins,

            "badge": badge,

            "earned_coins": earned_coins,

            "next_badge": (
                next_badge.name
                if next_badge
                else None
            ),

            "coins_to_next_badge":
                coins_to_next_badge,

            "progress_percent":
                progress_percent,

            "badge_counts": {
                "silver":
                    badge_counts["silver"],

                "gold":
                    badge_counts["gold"],

                "platinum":
                    badge_counts["platinum"],
            },
        }

        print(
            "HOME rewards: "
            f"{(perf_counter() - rewards_started) * 1000:.0f} ms"
        )

    # --------------------------------------------------------
    # RESTAURANTS + BAKERIES
    # --------------------------------------------------------

    restaurants_started = perf_counter()

    restaurant_query = (
        Restaurant.query
        .options(
            joinedload(
                Restaurant.categories
            )
        )
        .filter(
            Restaurant.category_type.in_(
                [
                    "restaurant",
                    "bakery",
                ]
            )
        )
    )

    if selected_location:
        restaurant_query = (
            restaurant_query
            .filter(
                Restaurant.location
                == selected_location
            )
        )

    restaurants = (
        restaurant_query
        .all()
    )

    print(
        "HOME restaurants query: "
        f"{(perf_counter() - restaurants_started) * 1000:.0f} ms "
        f"({len(restaurants)} stores)"
    )

    # --------------------------------------------------------
    # GROCERY
    # --------------------------------------------------------

    grocery_started = perf_counter()

    grocery_shops = []

    if selected_location:
        grocery_shops = (
            Restaurant.query
            .filter(
                Restaurant.location
                == selected_location,

                Restaurant.category_type
                == "grocery",
            )
            .all()
        )

    elif user_location_set:

        all_grocery = (
            Restaurant.query
            .filter(
                Restaurant.category_type
                == "grocery"
            )
            .all()
        )

        for g in all_grocery:
            if (
                g.latitude is None
                or g.longitude is None
                or not g.delivery_radius_km
            ):
                continue

            dist = haversine(
                float(user_lat),
                float(user_lng),
                float(g.latitude),
                float(g.longitude),
            )

            if (
                dist
                <= float(g.delivery_radius_km)
            ):
                grocery_shops.append(g)

    print(
        "HOME grocery: "
        f"{(perf_counter() - grocery_started) * 1000:.0f} ms "
        f"({len(grocery_shops)} stores)"
    )

    # --------------------------------------------------------
    # PROCESS STORE STATE
    # --------------------------------------------------------

    process_started = perf_counter()

    limited_restaurants = []

    for r in restaurants:
        process_store(
            r,
            user_lat,
            user_lng,
            user_location_set,
            now,
        )

        if (
            r.is_limited_drop
            and r.can_accept_orders
        ):
            limited_restaurants.append(r)

    for g in grocery_shops:
        process_store(
            g,
            user_lat,
            user_lng,
            user_location_set,
            now,
        )

    print(
        "HOME process_store: "
        f"{(perf_counter() - process_started) * 1000:.0f} ms"
    )

    # --------------------------------------------------------
    # LOOKUPS
    # --------------------------------------------------------

    restaurant_lookup = {
        r.id: r
        for r in restaurants
    }

    grocery_shop_ids = [
        g.id
        for g in grocery_shops
    ]

    # --------------------------------------------------------
    # SERIALIZERS
    # --------------------------------------------------------

    def category_json(category):
        return {
            "id": category.id,

            "name": (
                getattr(
                    category,
                    "name",
                    None,
                )
                or getattr(
                    category,
                    "category_name",
                    None,
                )
                or str(category)
            ),
        }

    def restaurant_json(r):
        return {
            "id": r.id,

            "name":
                r.name or "",

            "location":
                r.location or "",

            "category_type":
                r.category_type
                or "restaurant",

            "delivery_charge":
                float(
                    r.delivery_charge
                    or 0
                ),

            "free_delivery_limit":
                float(
                    r.free_delivery_limit
                    or 0
                ),

            "is_open":
                bool(
                    getattr(
                        r,
                        "is_open",
                        False,
                    )
                ),

            "can_accept_orders":
                bool(
                    getattr(
                        r,
                        "can_accept_orders",
                        True,
                    )
                ),

            "deliverable":
                bool(
                    getattr(
                        r,
                        "deliverable",
                        True,
                    )
                ),

            "distance": (
                float(r.distance)
                if getattr(
                    r,
                    "distance",
                    None,
                ) is not None
                else None
            ),

            "image_url": (
                getattr(
                    r,
                    "image_url",
                    None,
                )
                or getattr(
                    r,
                    "image",
                    None,
                )
            ),

            "is_limited_drop":
                bool(
                    getattr(
                        r,
                        "is_limited_drop",
                        False,
                    )
                ),

            "is_new":
                bool(
                    is_new_restaurant(r)
                ),

            "categories": [
                category_json(c)
                for c in (
                    getattr(
                        r,
                        "categories",
                        [],
                    )
                    or []
                )
            ],
        }

    # --------------------------------------------------------
    # CATEGORIES
    # --------------------------------------------------------

    categories_started = perf_counter()

    categories = (
        Category.query
        .all()
    )

    # One combined query for grocery categories.
    grocery_category_query = (
        db.session.query(
            MenuItem.restaurant_id,
            MenuItem.category,
        )
        .join(
            Restaurant,
            Restaurant.id
            == MenuItem.restaurant_id,
        )
        .filter(
            Restaurant.category_type
            == "grocery",

            MenuItem.item_type
            == "grocery",

            MenuItem.availability
            == "yes",

            MenuItem.category.isnot(None),
        )
    )

    if selected_location:
        grocery_category_query = (
            grocery_category_query
            .filter(
                Restaurant.location
                == selected_location
            )
        )

    if grocery_shop_ids:
        grocery_category_query = (
            grocery_category_query
            .filter(
                MenuItem.restaurant_id.in_(
                    grocery_shop_ids
                )
            )
        )

    grocery_category_rows = (
        grocery_category_query
        .distinct()
        .all()
    )

    grocery_categories_set = set()

    grocery_store_categories = {}

    for store_id, category in (
        grocery_category_rows
    ):
        if not category:
            continue

        clean_category = (
            category.strip()
        )

        if not clean_category:
            continue

        grocery_categories_set.add(
            clean_category
        )

        if (
            not grocery_shop_ids
            or store_id in grocery_shop_ids
        ):
            grocery_store_categories.setdefault(
                str(store_id),
                [],
            )

            if clean_category not in (
                grocery_store_categories[
                    str(store_id)
                ]
            ):
                grocery_store_categories[
                    str(store_id)
                ].append(
                    clean_category
                )

    grocery_categories = sorted(
        grocery_categories_set,
        key=lambda x: x.lower(),
    )

    print(
        "HOME categories: "
        f"{(perf_counter() - categories_started) * 1000:.0f} ms"
    )

    # --------------------------------------------------------
    # POPULAR ITEMS
    # --------------------------------------------------------

    popular_started = perf_counter()

    popular_items_raw = (
        db.session.query(
            Restaurant.id.label(
                "restaurant_id"
            ),

            Restaurant.name.label(
                "restaurant_name"
            ),

            Restaurant.category_type.label(
                "source_type"
            ),

            OrderItem.item_name,

            func.sum(
                OrderItem.quantity
            ).label(
                "total_orders"
            ),

            func.max(
                MenuItem.price
            ).label(
                "current_price"
            ),

            func.max(
                MenuItem.image_url
            ).label(
                "item_image"
            ),
        )

        .join(
            Order,
            Order.id
            == OrderItem.order_id,
        )

        .join(
            Restaurant,
            Restaurant.id
            == Order.restaurant_id,
        )

        .outerjoin(
            MenuItem,
            db.and_(
                MenuItem.restaurant_id
                == Restaurant.id,

                MenuItem.name
                == OrderItem.item_name,
            ),
        )
    )

    if restaurant_lookup:
        popular_items_raw = (
            popular_items_raw
            .filter(
                Restaurant.id.in_(
                    list(
                        restaurant_lookup.keys()
                    )
                )
            )
        )

    popular_items_raw = (
        popular_items_raw
        .group_by(
            Restaurant.id,
            Restaurant.name,
            Restaurant.category_type,
            OrderItem.item_name,
        )
        .order_by(
            func.sum(
                OrderItem.quantity
            ).desc()
        )
        .limit(30)
        .all()
    )

    # --------------------------------------------------------
    # Preload bakery fallback menu items in ONE query.
    # Prevents N+1 MenuItem queries.
    # --------------------------------------------------------

    bakery_pairs = []

    for row in popular_items_raw:
        price = row.current_price or 0

        if (
            row.source_type == "bakery"
            and price == 0
        ):
            bakery_pairs.append(
                (
                    row.restaurant_id,
                    row.item_name,
                )
            )

    bakery_menu_lookup = {}

    if bakery_pairs:

        conditions = [
            db.and_(
                MenuItem.restaurant_id
                == restaurant_id,

                MenuItem.name
                == item_name,
            )

            for restaurant_id, item_name
            in bakery_pairs
        ]

        fallback_menus = (
            MenuItem.query
            .filter(
                db.or_(*conditions)
            )
            .all()
        )

        bakery_menu_lookup = {
            (
                menu.restaurant_id,
                menu.name,
            ): menu
            for menu in fallback_menus
        }

    popular_items = []

    for row in popular_items_raw:

        restaurant = restaurant_lookup.get(
            row.restaurant_id
        )

        if not restaurant:
            continue

        price = (
            row.current_price
            or 0
        )

        if (
            row.source_type == "bakery"
            and price == 0
        ):

            menu = bakery_menu_lookup.get(
                (
                    row.restaurant_id,
                    row.item_name,
                )
            )

            if menu:
                extra = (
                    menu.extra_data
                    or {}
                )

                weight_prices = (
                    extra.get(
                        "weight_prices",
                        "",
                    )
                    if isinstance(
                        extra,
                        dict,
                    )
                    else ""
                )

                if weight_prices:
                    try:
                        price = float(
                            weight_prices
                            .split(",")[0]
                            .split(":")[1]
                        )
                    except (
                        ValueError,
                        IndexError,
                        TypeError,
                    ):
                        pass

        if price < 30:
            continue

        can_order = bool(
            restaurant.can_accept_orders
            and restaurant.is_open
            and restaurant.deliverable
        )

        popular_items.append({
            "restaurant_id":
                row.restaurant_id,

            "restaurant_name":
                row.restaurant_name,

            "source_type":
                row.source_type,

            "item_name":
                row.item_name,

            "total_orders":
                int(
                    row.total_orders
                    or 0
                ),

            "price":
                float(price or 0),

            "item_image":
                row.item_image,

            "restaurant":
                restaurant_json(
                    restaurant
                ),

            "can_order":
                can_order,
        })

    popular_items.sort(
        key=lambda x: (
            not x["can_order"],
            -x["total_orders"],
        )
    )

    popular_items = (
        popular_items[:25]
    )

    print(
        "HOME popular items: "
        f"{(perf_counter() - popular_started) * 1000:.0f} ms"
    )

    # --------------------------------------------------------
    # BUDGET ITEMS
    # --------------------------------------------------------

    budget_started = perf_counter()

    restaurant_ids = [
        r.id
        for r in restaurants
    ]

    budget_items = []

    if restaurant_ids:

        budget_rows = (
            MenuItem.query
            .filter(
                MenuItem.restaurant_id.in_(
                    restaurant_ids
                ),

                MenuItem.availability
                == "yes",

                MenuItem.price.between(
                    69,
                    159,
                ),
            )
            .all()
        )

        grouped = {}

        for item in budget_rows:

            restaurant = restaurant_lookup.get(
                item.restaurant_id
            )

            if not restaurant:
                continue

            can_order = bool(
                restaurant.can_accept_orders
                and restaurant.is_open
                and restaurant.deliverable
            )

            grouped.setdefault(
                item.restaurant_id,
                [],
            )

            grouped[
                item.restaurant_id
            ].append({
                "id":
                    item.id,

                "name":
                    item.name,

                "restaurant_id":
                    item.restaurant_id,

                "restaurant_name":
                    restaurant.name,

                "price":
                    float(
                        item.price
                        or 0
                    ),

                "image_url":
                    item.image_url,

                "can_order":
                    can_order,

                "restaurant":
                    restaurant_json(
                        restaurant
                    ),
            })

        for rows in grouped.values():

            rows.sort(
                key=lambda x: (
                    not x["can_order"],
                    x["price"],
                )
            )

            budget_items.extend(
                rows[:3]
            )

        budget_items = (
            budget_items[:27]
        )

    print(
        "HOME budget items: "
        f"{(perf_counter() - budget_started) * 1000:.0f} ms"
    )

    # --------------------------------------------------------
    # WEEKLY / FALLBACK TOP RESTAURANTS
    # --------------------------------------------------------

    top_started = perf_counter()

    one_week_ago = (
        datetime.utcnow()
        - timedelta(days=7)
    )

    top_query = (
        db.session.query(
            Restaurant,

            func.count(
                Order.id
            ).label(
                "orders_count"
            ),
        )

        .join(
            Order,
            Restaurant.id
            == Order.restaurant_id,
        )

        .filter(
            Order.created_at
            >= one_week_ago,

            Order.status
            == "Delivered",
        )
    )

    if selected_location:
        top_query = (
            top_query
            .filter(
                Restaurant.location
                == selected_location
            )
        )

    top_rows = (
        top_query
        .group_by(Restaurant.id)
        .order_by(
            func.count(
                Order.id
            ).desc()
        )
        .limit(20)
        .all()
    )

    section_title = (
        "🔥 This Week's Most Ordered"
    )

    if not top_rows:

        fallback_query = (
            db.session.query(
                Restaurant,

                func.count(
                    Order.id
                ).label(
                    "orders_count"
                ),
            )

            .join(
                Order,
                Restaurant.id
                == Order.restaurant_id,
            )

            .filter(
                Order.status
                == "Delivered"
            )
        )

        if selected_location:
            fallback_query = (
                fallback_query
                .filter(
                    Restaurant.location
                    == selected_location
                )
            )

        top_rows = (
            fallback_query
            .group_by(Restaurant.id)
            .order_by(
                func.count(
                    Order.id
                ).desc()
            )
            .limit(20)
            .all()
        )

        section_title = (
            "🏆 Most Ordered Restaurants"
        )

    top_restaurants = []

    for restaurant, count in top_rows:

        processed = restaurant_lookup.get(
            restaurant.id
        )

        if processed:
            restaurant = processed

        else:
            process_store(
                restaurant,
                user_lat,
                user_lng,
                user_location_set,
                now,
            )

        top_restaurants.append({
            "restaurant":
                restaurant_json(
                    restaurant
                ),

            "orders_count":
                int(count or 0),
        })

    top_restaurants.sort(
        key=lambda x: (
            not (
                x["restaurant"][
                    "can_accept_orders"
                ]
                and x["restaurant"][
                    "is_open"
                ]
                and x["restaurant"][
                    "deliverable"
                ]
            ),

            -x["orders_count"],
        )
    )

    top_restaurants = (
        top_restaurants[:10]
    )

    print(
        "HOME top restaurants: "
        f"{(perf_counter() - top_started) * 1000:.0f} ms"
    )

    # --------------------------------------------------------
    # TRENDING ITEMS
    # --------------------------------------------------------

    trending_started = perf_counter()

    trending_items = []

    if selected_location:

        rows = (
            db.session.query(
                FoodItem
            )

            .join(
                Restaurant,
                Restaurant.id
                == FoodItem.restaurant_id,
            )

            .filter(
                Restaurant.location
                == selected_location,

                FoodItem.order_count
                > 0,
            )

            .order_by(
                FoodItem.order_count.desc()
            )

            .limit(8)

            .all()
        )

        for item in rows:

            restaurant = restaurant_lookup.get(
                getattr(
                    item,
                    "restaurant_id",
                    None,
                )
            )

            trending_items.append({
                "id":
                    item.id,

                "name":
                    item.name,

                "price":
                    float(
                        getattr(
                            item,
                            "price",
                            0,
                        )
                        or 0
                    ),

                "image_url":
                    getattr(
                        item,
                        "image_url",
                        None,
                    ),

                "order_count":
                    int(
                        item.order_count
                        or 0
                    ),

                "restaurant_id": (
                    restaurant.id
                    if restaurant
                    else getattr(
                        item,
                        "restaurant_id",
                        None,
                    )
                ),

                "restaurant_name": (
                    restaurant.name
                    if restaurant
                    else ""
                ),

                "restaurant": (
                    restaurant_json(
                        restaurant
                    )
                    if restaurant
                    else None
                ),

                "can_order": bool(
                    restaurant
                    and restaurant.can_accept_orders
                    and restaurant.is_open
                    and restaurant.deliverable
                ),
            })

    print(
        "HOME trending: "
        f"{(perf_counter() - trending_started) * 1000:.0f} ms"
    )

    # --------------------------------------------------------
    # PENDING ONLINE PAYMENT
    #
    # IMPORTANT:
    # Do NOT call Razorpay from Home.
    #
    # Flutter already performs payment recovery separately.
    # Home only performs the lightweight DB lookup.
    # --------------------------------------------------------

    pending_started = perf_counter()

    pending_payment_order = None

    if current_user.is_authenticated:

        mobile = (
            current_user.mobile
            or ""
        )

        mobile10 = (
            mobile[3:]
            if mobile.startswith("+91")
            else mobile
        )

        pending = (
            Order.query
            .filter(
                Order.payment_type
                == "Online",

                Order.payment_status
                == "Pending",

                Order.status
                == "Pending Payment",

                db.or_(
                    Order.customer_id
                    == current_user.id,

                    Order.phone
                    == mobile,

                    Order.phone
                    == mobile10,
                ),
            )
            .order_by(
                Order.created_at.desc()
            )
            .first()
        )

        if pending:

            pending_payment_order = {
                "id":
                    pending.id,

                "order_id":
                    pending.order_id,

                "final_total":
                    float(
                        pending.get_final_total()
                        if hasattr(
                            pending,
                            "get_final_total",
                        )
                        else (
                            pending.final_total
                            or 0
                        )
                    ),

                "payment_status":
                    pending.payment_status,
            }

    print(
        "HOME pending payment: "
        f"{(perf_counter() - pending_started) * 1000:.0f} ms"
    )

    # --------------------------------------------------------
    # SORT STORES
    # --------------------------------------------------------

    def store_sort_key(r):
        if (
            is_new_restaurant(r)
            and r.deliverable
            and r.is_open
            and r.can_accept_orders
        ):
            priority = 0

        elif (
            r.deliverable
            and r.is_open
            and r.can_accept_orders
        ):
            priority = 1

        else:
            priority = 2

        created_timestamp = (
            r.created_at.timestamp()
            if r.created_at
            else 0
        )

        return (
            priority,
            -created_timestamp,
        )

    restaurants.sort(
        key=store_sort_key
    )

    grocery_shops.sort(
        key=store_sort_key
    )

    # --------------------------------------------------------
    # BUILD RESPONSE DATA ONCE
    # --------------------------------------------------------

    response_started = perf_counter()

    response_data = {
        "success": True,

        "selected_location":
            selected_location,

        "user_location_set":
            user_location_set,

        "all_locations":
            get_all_locations(),

        "restaurants": [
            restaurant_json(r)
            for r in restaurants
        ],

        "grocery_shops": [
            restaurant_json(g)
            for g in grocery_shops
        ],

        "limited_restaurants": [
            restaurant_json(r)
            for r in limited_restaurants
        ],

        "categories": [
            category_json(c)
            for c in categories
        ],

        "grocery_categories":
            grocery_categories,

        "grocery_store_categories":
            grocery_store_categories,

        "popular_items":
            popular_items,

        "budget_items":
            budget_items,

        "top_restaurants":
            top_restaurants,

        "section_title":
            section_title,

        "trending_items":
            trending_items,

        "rewards":
            rewards,

        "pending_payment_order":
            pending_payment_order,
    }

    result = jsonify(
        response_data
    )

    print(
        "HOME response build: "
        f"{(perf_counter() - response_started) * 1000:.0f} ms"
    )

    print(
        "================================================"
    )

    print(
        "HOME TOTAL: "
        f"{(perf_counter() - home_started) * 1000:.0f} ms"
    )

    print(
        "HOME LOCATION:",
        selected_location or "(none)",
    )

    print(
        "HOME RESTAURANTS:",
        len(restaurants),
    )

    print(
        "HOME GROCERY:",
        len(grocery_shops),
    )

    print(
        "HOME POPULAR:",
        len(popular_items),
    )

    print(
        "HOME BUDGET:",
        len(budget_items),
    )

    print(
        "HOME TOP:",
        len(top_restaurants),
    )

    print(
        "HOME TRENDING:",
        len(trending_items),
    )

    print(
        "================================================"
    )

    return result, 200
from flask import jsonify, request
from datetime import datetime
@app.route("/api/city/<city_slug>")
def api_city(city_slug):

    # =========================================================
    # CITY
    # =========================================================
    selected_location = (
        city_slug
        .replace("-", " ")
        .title()
    )

    # =========================================================
    # RESTAURANTS
    # =========================================================
    restaurants = (
        Restaurant.query
        .filter_by(
            location=selected_location
        )
        .all()
    )

    # =========================================================
    # CUSTOMER GPS FROM FLUTTER
    # Example:
    # /api/city/malikipuram?lat=16.41&lng=81.80
    # =========================================================
    user_lat = request.args.get(
        "lat",
        type=float
    )

    user_lng = request.args.get(
        "lng",
        type=float
    )

    user_location_set = (
        user_lat is not None
        and user_lng is not None
    )

    # =========================================================
    # CURRENT INDIA TIME
    # SAME TIMEZONE AS MAIN WEBSITE
    # =========================================================
    ist = pytz.timezone(
        "Asia/Kolkata"
    )

    now = datetime.now(
        ist
    ).time()

    # =========================================================
    # BUILD API RESPONSE
    # =========================================================
    result = []

    for r in restaurants:

        # =====================================================
        # IMPORTANT:
        # USE SAME PROCESSING LOGIC AS MAIN WEBSITE
        # =====================================================
        process_store(
            r,
            user_lat,
            user_lng,
            user_location_set,
            now
        )

        # =====================================================
        # FINAL ORDER AVAILABILITY
        # =====================================================
        can_order = bool(
            r.can_accept_orders
            and r.is_open
            and r.deliverable
        )

        # =====================================================
        # RESPONSE
        # =====================================================
        result.append({

            "id": r.id,

            "name": r.name,

            "location": r.location,

            "category_type": getattr(
                r,
                "category_type",
                None
            ),

            "image_url": getattr(
                r,
                "image_url",
                None
            ),

            # -----------------------------------------
            # DELIVERY
            # -----------------------------------------
            "delivery_charge": (
                r.delivery_charge or 0
            ),

            "free_delivery_limit": (
                r.free_delivery_limit or 0
            ),

            "delivery_radius_km": (
                r.delivery_radius_km or 0
            ),

            # -----------------------------------------
            # RESTAURANT LOCATION
            # -----------------------------------------
            "latitude": r.latitude,

            "longitude": r.longitude,

            # -----------------------------------------
            # CUSTOMER DISTANCE
            # -----------------------------------------
            "distance": getattr(
                r,
                "distance",
                None
            ),

            # -----------------------------------------
            # STATUS
            # -----------------------------------------
            "deliverable": bool(
                getattr(
                    r,
                    "deliverable",
                    True
                )
            ),

            "is_open": bool(
                getattr(
                    r,
                    "is_open",
                    False
                )
            ),

            "can_accept_orders": bool(
                r.can_accept_orders
            ),

            # -----------------------------------------
            # FINAL FLUTTER STATUS
            # -----------------------------------------
            "can_order": can_order,
        })

    # =========================================================
    # SORT RESTAURANTS
    #
    # 1. Can order
    # 2. Open
    # 3. Deliverable
    # 4. Closed / unavailable
    # =========================================================
    result.sort(
        key=lambda r: (

            not r["can_order"],

            not r["is_open"],

            not r["deliverable"]
        )
    )

    # =========================================================
    # RETURN JSON
    # =========================================================
    return jsonify({

        "success": True,

        "city": selected_location,

        "restaurants": result
    })
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

    ACTIVE = ["Pending","Placed", "Accepted", "Preparing","Ready","Out for Delivery","Started",]
    HISTORY = ["Delivered", "Cancelled","Customer Not Available"]

    if request.method == "POST":
        phone = request.form.get("phone")
        session["order_phone"] = phone
    else:
        phone = session.get("order_phone")

    active_orders = []
    history_orders = []

    if phone:
        active_orders = Order.query.filter(
            Order.phone == phone,
            Order.status.in_(ACTIVE)
        ).order_by(Order.created_at.desc()).all()

        history_orders = Order.query.filter(
            Order.phone == phone,
            Order.status.in_(HISTORY)
        ).order_by(Order.created_at.desc()).all()

        # ===== CONVERT ORDER TIMES TO IST =====
        ist = pytz.timezone('Asia/Kolkata')
        for order in active_orders + history_orders:
            if order.created_at:
                # Make sure it's timezone-aware UTC
                if order.created_at.tzinfo is None:
                    from pytz import UTC
                    order.created_at = UTC.localize(order.created_at)
                
                # Convert to IST
                order.created_at_ist = order.created_at.astimezone(ist)
                # Formatted string
                order.created_at_str = order.created_at_ist.strftime('%d-%m-%Y %I:%M %p')

        # Determine restaurant_id
        if active_orders:
            restaurant_id = active_orders[0].restaurant.id
        elif history_orders:
            restaurant_id = history_orders[0].restaurant.id

    return render_template(
        "myorders.html",
        active_orders=active_orders,
        history_orders=history_orders,
        restaurant_id=restaurant_id
    )
from flask import request, jsonify
from datetime import datetime
import pytz


# ============================================================
# ORDER SERIALIZER FOR FLUTTER APP
# 
def serialize_customer_order(order):

    ist = pytz.timezone("Asia/Kolkata")

    # --------------------------------------------------------
    # CREATED TIME
    # --------------------------------------------------------

    created_at_str = ""
    created_at_iso = None

    if order.created_at:

        created_at = order.created_at

        if created_at.tzinfo is None:
            created_at = pytz.UTC.localize(
                created_at
            )

        created_at_ist = (
            created_at.astimezone(ist)
        )

        created_at_str = (
            created_at_ist.strftime(
                "%d-%m-%Y %I:%M %p"
            )
        )

        # IMPORTANT:
        # Flutter uses this raw timestamp
        # to calculate the 15-minute countdown.
        created_at_iso = (
            created_at.isoformat()
        )


    # --------------------------------------------------------
    # ORDER ITEMS
    # --------------------------------------------------------

    items = []

    for item in order.items:

        price = float(
            item.price or 0
        )

        quantity = int(
            item.quantity or 0
        )

        items.append({

            "id":
                item.id,

            "item_name":
                item.item_name or "",

            "quantity":
                quantity,

            "price":
                price,

            "item_total":
                round(
                    price * quantity,
                    2
                ),

            "weight":
                getattr(
                    item,
                    "weight",
                    ""
                ) or "",

            "category":
                getattr(
                    item,
                    "category",
                    ""
                ) or ""
        })


    # --------------------------------------------------------
    # DELIVERY PERSON
    # --------------------------------------------------------

    delivery_person = None

    if order.delivery_person:

        delivery_person = {

            "id":
                order.delivery_person.id,

            "name":
                order.delivery_person.name
                or "",

            "phone":
                order.delivery_person.phone
                or ""
        }


    # --------------------------------------------------------
    # ADDRESS
    # --------------------------------------------------------

    address = {

        "house_no":
            order.house_no or "",

        "landmark":
            order.landmark or "",

        "city":
            order.city or "",

        "state":
            order.state or "",

        "pincode":
            order.pincode or ""
    }


    # --------------------------------------------------------
    # RESTAURANT
    # --------------------------------------------------------

    restaurant_name = ""
    restaurant_id = None

    if order.restaurant:

        restaurant_id = (
            order.restaurant.id
        )

        restaurant_name = (
            order.restaurant.name
            or ""
        )


    # --------------------------------------------------------
    # PAYMENT
    # --------------------------------------------------------

    payment_type = (
        getattr(
            order,
            "payment_type",
            ""
        ) or ""
    )

    payment_status = (
        getattr(
            order,
            "payment_status",
            ""
        ) or ""
    )

    payment_method_used = (
        getattr(
            order,
            "payment_method_used",
            ""
        ) or ""
    )


    # --------------------------------------------------------
    # COMPLETE JSON
    # --------------------------------------------------------

    return {

        "id":
            order.id,

        "order_id":
            order.order_id or "",

        "status":
            order.status or "Pending",

        "customer_name":
            order.customer_name or "",

        "phone":
            order.phone or "",

        "email":
            order.email or "",

        "restaurant_id":
            restaurant_id,

        "restaurant_name":
            restaurant_name,

        # IMPORTANT FOR FLUTTER TIMER
        "created_at":
            created_at_iso,

        "created_at_str":
            created_at_str,

        "estimated_time":
            getattr(
                order,
                "estimated_time",
                None
            ),

        "address":
            address,

        "items":
            items,

        "items_total":
            float(
                order.items_total or 0
            ),

        "delivery_charge":
            float(
                order.delivery_charge or 0
            ),

        "restaurant_offer_discount":
            float(
                getattr(
                    order,
                    "restaurant_offer_discount",
                    0
                ) or 0
            ),

        "discount":
            float(
                getattr(
                    order,
                    "discount",
                    0
                ) or 0
            ),

        "final_total":
            float(
                order.final_total or 0
            ),

        # ====================================================
        # PAYMENT FIELDS
        # ====================================================

        "payment_type":
            payment_type,

        "payment_status":
            payment_status,

        "payment_method_used":
            payment_method_used,

        "payment_verified":
            bool(
                getattr(
                    order,
                    "payment_verified",
                    False
                )
            ),

        # ====================================================

        "delivery_person_id":
            order.delivery_person_id,

        "delivery_person":
            delivery_person,

        "otp":
            str(
                getattr(
                    order,
                    "otp",
                    ""
                ) or ""
            ),

        "cancel_reason":
            getattr(
                order,
                "cancel_reason",
                ""
            ) or ""
    }

# ============================================================
# FLUTTER - FIND ORDERS USING CUSTOMER MOBILE NUMBER
#
# GET:
# /api/app/myorders?phone=9876543210
# ============================================================

@app.route(
    "/api/app/myorders",
    methods=["GET"]
)
def api_app_myorders():

    phone = (
        request.args.get(
            "phone",
            ""
        )
        .strip()
    )

    # Keep numbers only
    digits = "".join(
        ch
        for ch in phone
        if ch.isdigit()
    )

    # Keep last 10 digits
    if len(digits) > 10:

        digits = digits[-10:]


    if len(digits) != 10:

        return jsonify({

            "success":
                False,

            "message":
                "Enter a valid 10-digit mobile number."

        }), 400


    # ========================================================
    # SUPPORT BOTH OLD + NEW PHONE STORAGE
    #
    # 9876543210
    # +919876543210
    # ========================================================

    normal_phone = digits

    india_phone = (
        "+91" + digits
    )


    ACTIVE = [
        "Pending Payment",
        "Pending",
        "Placed",
        "Confirmed",
        "Accepted",
        "Preparing",
        "Ready",
        "Assigned",
        "Picked Up",
        "Out for Delivery",
        "Started"
    ]


    HISTORY = [

        "Delivered",
        "Cancelled",
        "Customer Not Available"
    ]


    # ========================================================
    # ACTIVE ORDERS
    # ========================================================

    active_orders = (

        Order.query

        .filter(

            Order.phone.in_([
                normal_phone,
                india_phone
            ]),

            Order.status.in_(
                ACTIVE
            )
        )

        .order_by(
            Order.created_at.desc()
        )

        .all()
    )


    # ========================================================
    # HISTORY
    # ========================================================

    history_orders = (

        Order.query

        .filter(

            Order.phone.in_([
                normal_phone,
                india_phone
            ]),

            Order.status.in_(
                HISTORY
            )
        )

        .order_by(
            Order.created_at.desc()
        )

        .limit(50)

        .all()
    )


    return jsonify({

        "success":
            True,

        "phone":
            digits,

        "active_count":
            len(active_orders),

        "history_count":
            len(history_orders),

        "active_orders": [

            serialize_customer_order(
                order
            )

            for order
            in active_orders
        ],

        "history_orders": [

            serialize_customer_order(
                order
            )

            for order
            in history_orders
        ]
    })


# ============================================================
# FLUTTER - LIVE ONE ORDER TRACKING
#
# GET:
# /api/app/order/123/track
#
# Flutter automatically calls this every 8 seconds.
# ============================================================

@app.route(
    "/api/app/order/<int:order_id>/track",
    methods=["GET"]
)
def api_app_track_order(order_id):

    order = (
        Order.query
        .filter_by(
            id=order_id
        )
        .first()
    )


    if not order:

        return jsonify({

            "success":
                False,

            "message":
                "Order not found."

        }), 404


    return jsonify({

        "success":
            True,

        "order":
            serialize_customer_order(
                order
            )
    })
from sqlalchemy import func

from sqlalchemy import func
from datetime import datetime
from models import Customer
from flask import session, render_template
from sqlalchemy import func
from datetime import datetime

# ============================================================
# CART PAGE
# ============================================================

@app.route("/cart/<int:restaurant_id>")
def cart_page(restaurant_id):

    # ========================================================
    # RESTAURANT
    # ========================================================

    restaurant = Restaurant.query.get_or_404(
        restaurant_id
    )


    # ========================================================
    # CART FROM SESSION
    # ========================================================

    cart_items = session.get(
        "cart",
        []
    )


    print("========== CART PAGE OPENED ==========")
    print("Restaurant ID:", restaurant.id)

    print("========== SESSION CART ==========")

    for c in cart_items:
        print(c)


    # ========================================================
    # ITEMS + TOTAL
    # ========================================================

    items = []

    items_total = 0


    for c in cart_items:

        item = MenuItem.query.get(
            c["id"]
        )


        if not item:
            continue


        quantity = int(
            c.get(
                "quantity",
                1
            )
        )


        total = (
            float(item.price)
            * quantity
        )


        items_total += total


        # ====================================================
        # KEEP WEIGHT FROM CART
        # ====================================================

        weight = c.get(
            "weight",
            ""
        )


        items.append({

            "id":
                item.id,

            "name":
                item.name,

            "price":
                item.price,

            "quantity":
                quantity,

            "weight":
                weight,

            "total":
                total,

            "category":
                item.category or "",

            "image_url":
                item.image_url or "",

            "description":
                item.description or "",

            "extra_data":
                item.extra_data or {}

        })


    print("========== ORDER ITEMS ==========")

    for i in items:
        print(i)


    # ========================================================
    # DISTANCE
    # ========================================================

    user_lat = session.get(
        "latitude"
    )

    user_lon = session.get(
        "longitude"
    )


    distance_km = 0


    if (
        user_lat is not None
        and user_lon is not None
        and restaurant.latitude is not None
        and restaurant.longitude is not None
    ):

        distance_km = calculate_distance_km(

            user_lat,
            user_lon,

            restaurant.latitude,
            restaurant.longitude

        )


    # ========================================================
    # DELIVERY CHARGE
    # ========================================================

    delivery_charge, delivery_msg = (
        calculate_delivery_charge(

            distance_km,
            items_total,
            restaurant

        )
    )


    # ========================================================
    # CUSTOMER + REWARDS
    # ========================================================

    customer_id = session.get(
        "customer_id"
    )


    customer = (

        Customer.query.get(
            customer_id
        )

        if customer_id

        else None

    )


    reward_setting = (
        RewardSetting.query.first()
    )


    # ========================================================
    # CUSTOMER IDENTIFICATION
    # ========================================================

    phone = session.get(
        "phone"
    )

    device_fingerprint = session.get(
        "device_fingerprint"
    )


    # ========================================================
    # FIRST-TIME CUSTOMER
    # ========================================================

    delivered_orders = 0


    # Avoid matching NULL against NULL unnecessarily
    if phone or device_fingerprint:

        identity_filters = []


        if phone:

            identity_filters.append(
                Order.phone == phone
            )


        if device_fingerprint:

            identity_filters.append(
                Order.device_fingerprint
                == device_fingerprint
            )


        delivered_orders = (

            Order.query

            .filter(

                db.or_(
                    *identity_filters
                ),

                func.lower(
                    Order.status
                ) == "delivered"

            )

            .count()

        )


    first_time_user = (
        delivered_orders == 0
    )


    # ========================================================
    # ACTIVE RESTAURANT OFFER
    # ========================================================

    active_offer = (

        RestaurantOffer.query

        .filter_by(

            restaurant_id=
                restaurant.id,

            is_active=True

        )

        .first()

    )


    # ========================================================
    # CHECK WHETHER OFFER ALREADY USED
    # ========================================================

    offer_already_used = False


    if (
        active_offer
        and (
            phone
            or device_fingerprint
        )
    ):

        identity_filters = []


        if phone:

            identity_filters.append(
                Order.phone == phone
            )


        if device_fingerprint:

            identity_filters.append(
                Order.device_fingerprint
                == device_fingerprint
            )


        used_order = (

            Order.query

            .filter(

                Order.restaurant_id
                == restaurant.id,

                db.or_(
                    *identity_filters
                ),

                Order.restaurant_offer_id
                == active_offer.id,

                func.lower(
                    Order.status
                ) == "delivered"

            )

            .first()

        )


        offer_already_used = (
            used_order is not None
        )


    # ========================================================
    # RECOMMENDATIONS
    # ========================================================

    recommendations = []


    try:

        recommendations = (
            get_recommendations(

                cart_items,
                restaurant.id

            )
            or []
        )


    except Exception as e:

        print(
            "RECOMMENDATION ERROR:",
            e
        )


        recommendations = []


    print(
        "========== RECOMMENDATIONS =========="
    )

    for recommendation in recommendations:
        print(recommendation)


    # ========================================================
    # ORDER PLACEHOLDER
    # ========================================================

    order = None


    # ========================================================
    # RENDER CART
    # ========================================================

    return render_template(

        "cart.html",


        # Restaurant
        restaurant=
            restaurant,


        # Cart
        items=
            items,

        items_total=
            items_total,


        # Delivery
        distance_km=
            distance_km,

        delivery_charge=
            delivery_charge,

        delivery_msg=
            delivery_msg,


        # Recommendations
        recommendations=
            recommendations,


        # Customer
        first_time_user=
            first_time_user,

        customer=
            customer,


        # Offers
        active_offer=
            active_offer,

        offer_already_used=
            offer_already_used,


        # Rewards
        reward_setting=
            reward_setting,


        # Existing template compatibility
        order=
            order

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

    # ========================================================
    # BASIC DETAILS
    # ========================================================

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

    restaurant_id = int(
        request.form.get("restaurant_id")
    )

    device_fingerprint = request.form.get(
        "device_fingerprint"
    )

    order_type = request.form.get(
        "order_type"
    )


    # ========================================================
    # LOCATION
    # ========================================================

    customer_lat = safe_float(
        request.form.get("customer_lat")
        or request.form.get("lat")
    )

    customer_lng = safe_float(
        request.form.get("customer_lng")
        or request.form.get("lng")
    )


    # ========================================================
    # ITEMS
    # ========================================================

    item_names = request.form.getlist(
        "item_name[]"
    )

    quantities = request.form.getlist(
        "quantity[]"
    )

    prices = request.form.getlist(
        "price[]"
    )

    weights = request.form.getlist(
        "weight[]"
    )

    categories = request.form.getlist(
        "category[]"
    )


    if not item_names:

        flash(
            "Cart is empty",
            "danger"
        )

        return redirect("/")


    # ========================================================
    # RESTAURANT
    # ========================================================

    restaurant = Restaurant.query.get_or_404(
        restaurant_id
    )


    # ========================================================
    # RESTAURANT STATUS
    # ========================================================

    if not restaurant.can_accept_orders:

        flash(
            f"{restaurant.name} is closed now",
            "warning"
        )

        return redirect(
            request.referrer
            or url_for("home")
        )


    # ========================================================
    # ITEMS TOTAL
    # ========================================================

    items_total = 0


    for i in range(len(item_names)):

        qty = int(
            quantities[i]
        )

        price = float(
            prices[i]
        )

        items_total += (
            qty * price
        )


    # ========================================================
    # LOCATION VALIDATION
    # ========================================================

    if (
        customer_lat is None
        or customer_lng is None
    ):

        flash(
            "Please select delivery location",
            "danger"
        )

        return redirect(
            request.referrer
            or url_for("home")
        )


    # ========================================================
    # DISTANCE
    # ========================================================

    distance_km = calculate_distance_km(

        restaurant.latitude,
        restaurant.longitude,

        customer_lat,
        customer_lng

    )


    # ========================================================
    # DELIVERY CHARGE
    # ========================================================

    delivery_charge, delivery_msg = (
        calculate_delivery_charge(

            distance_km,
            items_total,
            restaurant

        )
    )


    # ========================================================
    # NORMALIZE PHONE
    # ========================================================

    if phone:

        phone = (
            phone
            .replace("+91", "")
            .replace(" ", "")
            .strip()
        )


    # ========================================================
    # COMBINED DELIVERY
    # ========================================================

    from datetime import timedelta


    combined_delivery = False


    if (
        phone
        and house_no
        and pincode
    ):

        print(
            "\n========== COMBINED DELIVERY DEBUG =========="
        )

        print(
            "Normalized Phone:",
            phone
        )

        print(
            "House No:",
            house_no
        )

        print(
            "Pincode:",
            pincode
        )

        print(
            "Restaurant ID:",
            restaurant_id
        )


        existing_order = (

            Order.query

            .filter(

                Order.phone.contains(
                    phone
                ),

                Order.house_no
                == house_no,

                Order.pincode
                == pincode,

                Order.restaurant_id
                != restaurant_id,

                Order.created_at
                >= (
                    datetime.utcnow()
                    - timedelta(
                        minutes=10
                    )
                )

            )

            .order_by(
                Order.created_at.desc()
            )

            .first()

        )


        print(
            "Existing Order:",
            existing_order
        )


        if existing_order:

            time_diff = (

                datetime.utcnow()
                - existing_order.created_at

            )


            existing_status = (
                existing_order.status
                or ""
            ).lower()


            if (
                time_diff.total_seconds()
                <= 600

                and existing_status
                not in [
                    "delivered",
                    "cancelled",
                    "refunded"
                ]
            ):

                print(
                    "✅ Combined delivery activated"
                )


                print(
                    "Old delivery charge:",
                    delivery_charge
                )


                delivery_charge = max(

                    10,

                    round(
                        delivery_charge
                        * 0.3
                    )

                )


                delivery_msg = (
                    "Combined delivery applied"
                )


                combined_delivery = True


                print(
                    "New delivery charge:",
                    delivery_charge
                )


    # ========================================================
    # FINAL TOTAL
    # ========================================================

    final_total = round(
        items_total
        + delivery_charge,
        2
    )


    # ========================================================
    # MAP LINK
    # ========================================================

    map_link = generate_map_link(

        customer_lat,
        customer_lng,

        house_no,
        landmark,
        city,
        state,
        pincode

    )


    # ========================================================
    # PAYMENT STATE
    # ========================================================

    if payment_type == "Online":

        order_status = (
            "Pending Payment"
        )

        payment_source = (
            "Checkout"
        )

    else:

        order_status = (
            "Pending"
        )

        payment_source = (
            "COD"
        )


    # ========================================================
    # CREATE ORDER
    # ========================================================

    new_order = Order(

        restaurant_id=
            restaurant_id,

        customer_id=(
            current_user.id
            if current_user.is_authenticated
            else None
        ),

        customer_name=
            name,

        phone=
            phone,

        email=
            email,

        alt_phone=
            alt_phone,

        house_no=
            house_no,

        landmark=
            landmark,

        city=
            city,

        state=
            state,

        pincode=
            pincode,

        address_type=
            address_type,

        delivery_note=
            delivery_note,

        payment_type=
            payment_type,


        # PAYMENT
        payment_status=
            "Pending",

        payment_verified=
            False,

        status=
            order_status,

        payment_source=
            payment_source,


        # OTHER
        device_fingerprint=
            device_fingerprint,

        order_type=
            order_type,

        items_total=
            items_total,

        delivery_charge=
            delivery_charge,

        final_total=
            final_total,

        latitude=
            customer_lat,

        longitude=
            customer_lng,

        distance_km=
            round(
                distance_km,
                2
            ),

        map_link=
            map_link,

        otp=
            generate_otp(),

        created_at=
            datetime.utcnow()

    )


    # ========================================================
    # SAVE ORDER FIRST
    # ========================================================

    db.session.add(
        new_order
    )

    db.session.commit()


    print(
        "PAYMENT RECEIVED:",
        payment_type
    )

    print(
        request.form.to_dict(
            flat=False
        )
    )


    # ========================================================
    # COINS REDEMPTION
    # ========================================================

    coins_to_redeem = int(

        request.form.get(
            "redeem_coins"
        )

        or 0

    )


    if (
        coins_to_redeem > 0
        and session.get(
            "customer_id"
        )
    ):

        success, msg, redeem_amount = (
            redeem_coins(

                customer_id=
                    session.get(
                        "customer_id"
                    ),

                coins_to_redeem=
                    coins_to_redeem,

                order_id=
                    new_order.id,

                order_total=(
                    new_order.items_total
                    + new_order.delivery_charge
                )

            )
        )


        if success:

            new_order.final_total -= (
                redeem_amount
            )

            db.session.commit()

            flash(
                msg,
                "success"
            )


        else:

            flash(
                msg,
                "warning"
            )


    # ========================================================
    # ORDER CODE
    # ========================================================

    new_order.order_id = (
        generate_order_code(
            new_order.id
        )
    )

    db.session.commit()


    # ========================================================
    # ORDER ITEMS
    # ========================================================

    for i in range(
        len(item_names)
    ):

        qty = int(
            quantities[i]
        )


        if qty <= 0:
            continue


        db.session.add(

            OrderItem(

                order_id=
                    new_order.id,

                item_name=
                    item_names[i],

                quantity=
                    qty,

                price=
                    float(
                        prices[i]
                    ),

                weight=(
                    weights[i]
                    if i < len(weights)
                    else ""
                ),

                category=(
                    categories[i]
                    if i < len(categories)
                    else ""
                )

            )

        )


    db.session.commit()


    # ========================================================
    # ONLINE PAYMENT
    # ========================================================

    if payment_type == "Online":

        return redirect(

            url_for(

                "payment_page",

                order_id=
                    new_order.id

            )

        )


    # ========================================================
    # COD
    # ========================================================

    flash(

        f"Order placed successfully! "
        f"Order ID: {new_order.order_id}",

        "success"

    )


    return redirect(

        url_for(

            "order_placed",

            order_id=
                new_order.order_id

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

        flash("Invalid login", "danger")

    return render_template("admin_login.html")


from datetime import datetime, timedelta
from flask import session, redirect, url_for, render_template, request
from models import Order, Restaurant, DeliveryPerson, db
from sqlalchemy import or_
@app.route("/admin/dashboard")
def admin_dashboard():

    # =========================================================
    # ADMIN LOGIN CHECK
    # =========================================================

    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))


    # =========================================================
    # FILTER VALUES
    # =========================================================

    query = request.args.get(
        "query",
        "",
        type=str
    ).strip()

    status_filter = request.args.get(
        "status",
        "",
        type=str
    ).strip()

    date_filter = request.args.get(
        "date",
        "",
        type=str
    ).strip()


    # =========================================================
    # SEPARATE PAGINATION
    # =========================================================

    today_page = request.args.get(
        "today_page",
        1,
        type=int
    )

    yesterday_page = request.args.get(
        "yesterday_page",
        1,
        type=int
    )

    older_page = request.args.get(
        "older_page",
        1,
        type=int
    )

    per_page = 10


    # =========================================================
    # DATES
    # =========================================================

    today = datetime.utcnow().date()

    yesterday = (
        today - timedelta(days=1)
    )

    week_start = (
        today
        - timedelta(days=today.weekday())
    )


    today_start = datetime.combine(
        today,
        datetime.min.time()
    )

    tomorrow_start = (
        today_start
        + timedelta(days=1)
    )

    yesterday_start = datetime.combine(
        yesterday,
        datetime.min.time()
    )

    week_start_datetime = datetime.combine(
        week_start,
        datetime.min.time()
    )


    # =========================================================
    # BASE FILTER QUERY
    # =========================================================

    base_query = Order.query


    # ---------------------------------------------------------
    # SEARCH
    # ---------------------------------------------------------

    if query:

        search_value = (
            f"%{query}%"
        )

        base_query = base_query.filter(
            or_(
                Order.order_id.ilike(search_value),
                Order.customer_name.ilike(search_value),
                Order.phone.ilike(search_value),
                Order.email.ilike(search_value)
            )
        )


    # ---------------------------------------------------------
    # STATUS
    # ---------------------------------------------------------

    if status_filter:

        base_query = base_query.filter(
            Order.status == status_filter
        )


    # ---------------------------------------------------------
    # SELECTED DATE
    # ---------------------------------------------------------

    if date_filter:

        try:

            selected_date = (
                datetime.strptime(
                    date_filter,
                    "%Y-%m-%d"
                ).date()
            )

            selected_start = datetime.combine(
                selected_date,
                datetime.min.time()
            )

            selected_end = (
                selected_start
                + timedelta(days=1)
            )

            base_query = (
                base_query.filter(
                    Order.created_at
                    >= selected_start,

                    Order.created_at
                    < selected_end
                )
            )

        except ValueError:

            date_filter = ""


    # =========================================================
    # TODAY ORDERS
    # =========================================================

    today_pagination = (

        base_query

        .filter(
            Order.created_at >= today_start,
            Order.created_at < tomorrow_start
        )

        .order_by(
            Order.created_at.desc()
        )

        .paginate(
            page=today_page,
            per_page=per_page,
            error_out=False
        )

    )


    today_orders = (
        today_pagination.items
    )


    # =========================================================
    # YESTERDAY ORDERS
    # =========================================================

    yesterday_pagination = (

        base_query

        .filter(
            Order.created_at >= yesterday_start,
            Order.created_at < today_start
        )

        .order_by(
            Order.created_at.desc()
        )

        .paginate(
            page=yesterday_page,
            per_page=per_page,
            error_out=False
        )

    )


    yesterday_orders = (
        yesterday_pagination.items
    )


    # =========================================================
    # OLDER ORDERS
    # =========================================================

    older_pagination = (

        base_query

        .filter(
            Order.created_at < yesterday_start
        )

        .order_by(
            Order.created_at.desc()
        )

        .paginate(
            page=older_page,
            per_page=per_page,
            error_out=False
        )

    )


    older_orders = (
        older_pagination.items
    )


    # =========================================================
    # DELIVERY PERSONS
    # =========================================================

    delivery_persons = (

        DeliveryPerson.query

        .order_by(
            DeliveryPerson.name.asc()
        )

        .all()

    )


    # =========================================================
    # RESTAURANTS
    # =========================================================

    restaurants = (
        Restaurant.query.all()
    )

    restaurant_count = (
        len(restaurants)
    )


    # =========================================================
    # ADMIN STATISTICS
    # =========================================================

    # All today's orders
    today_all_orders = (

        Order.query

        .filter(
            Order.created_at >= today_start,
            Order.created_at < tomorrow_start
        )

        .all()

    )


    # Delivered today
    today_delivered_orders = [

        o

        for o in today_all_orders

        if o.status == "Delivered"

    ]


    # =========================================================
    # WEEKLY DELIVERED
    # =========================================================

    weekly_delivered_orders = (

        Order.query

        .filter(
            Order.created_at
            >= week_start_datetime,

            Order.status
            == "Delivered"
        )

        .all()

    )


    # =========================================================
    # ALL DELIVERED
    # =========================================================

    all_delivered_orders = (

        Order.query

        .filter_by(
            status="Delivered"
        )

        .all()

    )


    # =========================================================
    # STATISTICS
    # =========================================================

    stats = {

        # -----------------------------------------------------
        # TOTAL
        # -----------------------------------------------------

        "total_orders":
            Order.query.count(),


        "pending":
            Order.query.filter_by(
                status="Pending"
            ).count(),


        "preparing":
            Order.query.filter_by(
                status="Preparing"
            ).count(),


        "assigned":

            Order.query.filter(

                Order.delivery_person_id
                .isnot(None),

                Order.status
                != "Delivered",

                Order.status
                != "Cancelled"

            ).count(),


        "delivered":

            Order.query.filter_by(
                status="Delivered"
            ).count(),


        "cancelled":

            Order.query.filter_by(
                status="Cancelled"
            ).count(),


        # -----------------------------------------------------
        # TODAY
        # -----------------------------------------------------

        "today_orders":
            len(
                today_all_orders
            ),


        "today_delivered":
            len(
                today_delivered_orders
            ),


        "today_cancelled":

            sum(
                1
                for o in today_all_orders
                if o.status
                == "Cancelled"
            ),


        "today_pending":

            sum(
                1
                for o in today_all_orders
                if o.status
                == "Pending"
            ),


        "today_active":

            sum(
                1
                for o in today_all_orders
                if o.status
                in [
                    "Preparing",
                    "Assigned",
                    "Out for Delivery"
                ]
            ),


        # -----------------------------------------------------
        # TODAY REVENUE
        # -----------------------------------------------------

        "today_revenue":

            sum(
                o.get_final_total()
                for o
                in today_delivered_orders
            ),


        # -----------------------------------------------------
        # TODAY DELIVERY CHARGES
        # -----------------------------------------------------

        "today_delivery_charges":

            sum(
                o.delivery_charge or 0
                for o
                in today_delivered_orders
            ),


        # -----------------------------------------------------
        # TODAY ITEMS
        # -----------------------------------------------------

        "today_items":

            sum(

                item.quantity

                for o
                in today_delivered_orders

                for item
                in o.items

            )
            if today_delivered_orders
            else 0,


        # -----------------------------------------------------
        # WEEK
        # -----------------------------------------------------

        "week_orders":

            Order.query.filter(
                Order.created_at
                >= week_start_datetime
            ).count(),


        "weekly_revenue":

            sum(
                o.get_final_total()
                for o
                in weekly_delivered_orders
            ),


        # -----------------------------------------------------
        # TOTAL REVENUE
        # -----------------------------------------------------

        "total_revenue":

            sum(
                o.get_final_total()
                for o
                in all_delivered_orders
            )

    }


    # =========================================================
    # DAY CATEGORY
    # =========================================================

    for o in today_orders:

        o.day_category = (
            "Today"
        )


    for o in yesterday_orders:

        o.day_category = (
            "Yesterday"
        )


    for o in older_orders:

        o.day_category = (
            "Older"
        )


    # =========================================================
    # RESTAURANT PERFORMANCE
    # =========================================================

    restaurant_performance = []


    for r in restaurants:

        r_orders = (

            Order.query

            .filter_by(
                restaurant_id=r.id
            )

            .all()

        )


        today_restaurant_orders = [

            o

            for o in r_orders

            if (
                o.created_at
                and
                today_start
                <= o.created_at
                < tomorrow_start
                and o.status
                == "Delivered"
            )

        ]


        weekly_restaurant_orders = [

            o

            for o in r_orders

            if (
                o.created_at
                and
                o.created_at
                >= week_start_datetime
                and o.status
                == "Delivered"
            )

        ]


        restaurant_performance.append({

            "id":
                r.id,

            "name":
                r.name,


            # TODAY
            "today_orders":

                len(
                    today_restaurant_orders
                ),


            "today_earnings":

                sum(
                    o.get_final_total()
                    for o
                    in today_restaurant_orders
                ),


            # WEEKLY
            "weekly_orders":

                len(
                    weekly_restaurant_orders
                ),


            "weekly_earnings":

                sum(
                    o.get_final_total()
                    for o
                    in weekly_restaurant_orders
                ),


            # STATUS COUNTS
            "pending":

                sum(
                    1
                    for o in r_orders
                    if o.status
                    == "Pending"
                ),


            "completed":

                sum(
                    1
                    for o in r_orders
                    if o.status
                    == "Delivered"
                ),


            # RESTAURANT FLAGS
            "is_best_seller":
                r.is_best_seller,

            "is_fast_delivery":
                r.is_fast_delivery

        })


    # =========================================================
    # RENDER
    # =========================================================

    return render_template(

        "admin_dashboard.html",


        # =====================================================
        # ORDERS
        # =====================================================

        today_orders=
            today_orders,

        yesterday_orders=
            yesterday_orders,

        older_orders=
            older_orders,


        # =====================================================
        # PAGINATION
        # =====================================================

        today_pagination=
            today_pagination,

        yesterday_pagination=
            yesterday_pagination,

        older_pagination=
            older_pagination,


        # =====================================================
        # OTHER DATA
        # =====================================================

        delivery_persons=
            delivery_persons,

        restaurants=
            restaurants,

        restaurant_count=
            restaurant_count,


        # =====================================================
        # STATS
        # =====================================================

        stats=
            stats,

        restaurant_stats=
            restaurant_performance,


        # =====================================================
        # FILTERS
        # =====================================================

        query=
            query,

        status_filter=
            status_filter,

        date_filter=
            date_filter,


        # =====================================================
        # HELPERS
        # =====================================================

        make_whatsapp_link=
            make_whatsapp_link

    )

# ---------------- ASSIGN DELIVERY PERSON ----------------
# ============================================================
def auto_assign_order(order):

    status = (
        order.status or ""
    ).lower().strip()

    if status in {
        "cancelled",
        "canceled",
        "rejected",
        "declined",
        "delivered",
        "completed",
    }:

        print(
            f"🚫 AUTO ASSIGN BLOCKED: "
            f"Order {order.order_id} "
            f"has status '{order.status}'"
        )

        return {
            "success": False,
            "message": "Order is not eligible for delivery assignment."
        }

    # your existing auto_assign_order code below...
# RESTAURANT UPDATE ORDER STATUS
# + CUSTOMER PUSH
# + SOCKET UPDATE
# + AUTO ASSIGN DELIVERY RIDER
# ============================================================

from flask_socketio import emit
@app.route(
    "/restaurant/update_status/<int:order_id>",
    methods=["POST"]
)
def update_status(order_id):

    # ========================================================
    # RESTAURANT LOGIN CHECK
    # ========================================================

    if not session.get("restaurant_logged_in"):
        return redirect(
            url_for("restaurant_login")
        )

    # ========================================================
    # GET ORDER
    # ========================================================

    order = db.session.get(
        Order,
        order_id
    )

    if not order:
        flash(
            "Order not found!",
            "danger"
        )

        return redirect(
            url_for("restaurant_dashboard")
        )

    # ========================================================
    # GET NEW STATUS
    # ========================================================

    new_status = (
        request.form.get("status") or ""
    ).strip()

    if not new_status:
        flash(
            "Invalid order status.",
            "danger"
        )

        return redirect(
            url_for("restaurant_dashboard")
        )

    old_status = (
        order.status or ""
    ).strip()

    # ========================================================
    # NORMALIZE STATUS
    # ========================================================

    status_key = (
        new_status
        .lower()
        .replace("_", " ")
        .strip()
    )

    old_status_key = (
        old_status
        .lower()
        .replace("_", " ")
        .strip()
    )

    # ========================================================
    # PREVENT DUPLICATE STATUS
    # ========================================================

    if old_status_key == status_key:
        flash(
            "Order already has this status.",
            "info"
        )

        return redirect(
            url_for("restaurant_dashboard")
        )

    # ========================================================
    # DELIVERY-ONLY STATES
    # ========================================================

    protected_states = {
        "started",
        "picked up",
        "out for delivery",
        "delivered",
    }

    # Restaurant cannot modify once delivery started

    if old_status_key in protected_states:

        flash(
            "Delivery is already in progress. "
            "Restaurant cannot change this status.",
            "warning"
        )

        return redirect(
            url_for("restaurant_dashboard")
        )

    # Restaurant cannot manually set delivery states

    if status_key in protected_states:

        flash(
            "Only the delivery partner can update "
            "delivery status.",
            "danger"
        )

        return redirect(
            url_for("restaurant_dashboard")
        )

    # ========================================================
    # CHECK IF THIS IS REJECTION / CANCELLATION
    # ========================================================

    is_cancelled = status_key in {
        "cancelled",
        "canceled",
        "rejected",
        "declined",
    }

    # ========================================================
    # STORE CURRENT RIDER
    # ========================================================

    previous_rider_id = getattr(
        order,
        "delivery_person_id",
        None
    )

    # ========================================================
    # UPDATE ORDER STATUS
    # ========================================================

    order.status = new_status

    # ========================================================
    # IMPORTANT:
    # RESTAURANT REJECTED/CANCELLED ORDER
    #
    # Remove rider assignment immediately.
    # ========================================================

    if is_cancelled:

        print(
            "========================================"
        )

        print(
            "🚫 ORDER CANCELLED / REJECTED"
        )

        print(
            "ORDER:",
            order.id,
            order.order_id
        )

        print(
            "PREVIOUS RIDER:",
            previous_rider_id
        )

        print(
            "STATUS:",
            new_status
        )

        print(
            "========================================"
        )

        # ----------------------------------------------------
        # Clear rider assignment
        # ----------------------------------------------------

        if hasattr(order, "delivery_person_id"):
            order.delivery_person_id = None

        # ----------------------------------------------------
        # Clear assignment timestamp if your model has it
        # ----------------------------------------------------

        if hasattr(order, "assigned_at"):
            order.assigned_at = None

        # ----------------------------------------------------
        # Clear delivery status if your model has it
        # ----------------------------------------------------

        if hasattr(order, "delivery_status"):
            order.delivery_status = "Cancelled"

        # ----------------------------------------------------
        # Release rider
        # ----------------------------------------------------

        if previous_rider_id:

            try:

                rider = db.session.get(
                    DeliveryPerson,
                    previous_rider_id
                )

                if rider:

                    if hasattr(
                        rider,
                        "is_available"
                    ):
                        rider.is_available = True

                    if hasattr(
                        rider,
                        "is_online"
                    ):
                        # Do NOT force offline.
                        # Keep rider online if already online.
                        pass

                    if hasattr(
                        rider,
                        "last_assignment"
                    ):
                        rider.last_assignment = None

                    print(
                        f"✅ Rider {rider.id} "
                        "released successfully."
                    )

            except Exception as rider_error:

                print(
                    "⚠️ Unable to release rider:",
                    rider_error
                )

    # ========================================================
    # SAVE STATUS / CANCELLATION
    # ========================================================

    try:

        db.session.commit()

        print(
            "✅ ORDER STATUS SAVED:",
            order.order_id,
            order.status
        )

    except Exception as e:

        db.session.rollback()

        print(
            "❌ ORDER STATUS UPDATE ERROR:",
            e
        )

        flash(
            "Unable to update order status.",
            "danger"
        )

        return redirect(
            url_for("restaurant_dashboard")
        )

    # ========================================================
    # SOCKET.IO LIVE STATUS UPDATE
    # ========================================================

    try:

        socketio.emit(
            "order_status_update",
            {
                "order_id": order.order_id,
                "status": order.status,
                "delivery_person_id": (
                    order.delivery_person_id
                    if hasattr(
                        order,
                        "delivery_person_id"
                    )
                    else None
                ),
            },
            room=f"order_{order.order_id}"
        )

        print(
            "📤 Emitted status update:",
            order.order_id,
            order.status
        )

    except Exception as e:

        print(
            "⚠️ Socket status update error:",
            e
        )

    # ========================================================
    # AUTO ASSIGN DELIVERY
    #
    # ONLY:
    #   Ready
    #   Ready for Pickup
    #
    # NEVER:
    #   Cancelled
    #   Rejected
    # ========================================================

    if status_key in {
        "ready",
        "ready for pickup",
    } and not is_cancelled:

        try:

            order_type = (
                getattr(
                    order,
                    "order_type",
                    "delivery"
                )
                or "delivery"
            ).lower()

            if order_type == "delivery":

                db.session.refresh(order)

                # ------------------------------------------------
                # EXTRA SAFETY CHECK
                # ------------------------------------------------

                if order.status.lower() not in {
                    "ready",
                    "ready for pickup",
                }:

                    print(
                        "⚠️ Order is no longer ready. "
                        "Skipping rider assignment."
                    )

                elif order.delivery_person_id is None:

                    from dispatch_service import auto_assign_order

                    print(
                        "========================================"
                    )

                    print(
                        "🚚 AUTO ASSIGN START"
                    )

                    print(
                        "ORDER:",
                        order.id,
                        order.order_id
                    )

                    print(
                        "STATUS:",
                        order.status
                    )

                    print(
                        "========================================"
                    )

                    result = auto_assign_order(
                        order
                    )

                    print(
                        "🚚 AUTO ASSIGN RESULT:",
                        result
                    )

                    print(
                        "========================================"
                    )

                else:

                    print(
                        f"ℹ️ Order {order.order_id} "
                        f"already has rider "
                        f"{order.delivery_person_id}"
                    )

            else:

                print(
                    f"ℹ️ Order {order.order_id} "
                    "is not delivery type. "
                    "Skipping rider assignment."
                )

        except Exception as e:

            print(
                "❌ AUTO ASSIGN ERROR:",
                e
            )

    # ========================================================
    # CUSTOMER PUSH NOTIFICATIONS
    # ========================================================

# ========================================================
# CUSTOMER PUSH NOTIFICATION
# ========================================================

    notification_messages = {
        "accepted": (
            "🍽️ Order Accepted!",
            f"Your order {order.order_id} has been accepted."
        ),

        "confirmed": (
            "✅ Order Confirmed!",
            f"Your RucHiGo order {order.order_id} is confirmed."
        ),

        "preparing": (
            "👨‍🍳 Order Being Prepared",
            f"Your order {order.order_id} is now being prepared."
        ),

        "ready": (
            "🥡 Order Ready!",
            f"Your order {order.order_id} is ready for the delivery partner."
        ),

        "ready for pickup": (
            "🥡 Order Ready!",
            f"Your order {order.order_id} is ready for the delivery partner."
        ),

        "cancelled": (
            "❌ Order Cancelled",
            f"Your order {order.order_id} has been cancelled."
        ),

        "canceled": (
            "❌ Order Cancelled",
            f"Your order {order.order_id} has been cancelled."
        ),

        "rejected": (
            "❌ Order Rejected",
            f"Your order {order.order_id} has been rejected by the restaurant."
        ),

        "declined": (
            "❌ Order Rejected",
            f"Your order {order.order_id} has been declined by the restaurant."
        ),
    }

    notification = notification_messages.get(status_key)

    if notification:
        title, body = notification

        print("========================================")
        print("🔔 RESTAURANT → CUSTOMER PUSH")
        print("Order DB ID:", order.id)
        print("Order ID:", order.order_id)
        print("Customer phone:", order.phone)
        print("New status:", order.status)
        print("Title:", title)
        print("========================================")

        try:
            sent = send_order_push_to_customer(
                order=order,
                title=title,
                body=body
            )

            print("✅ CUSTOMER PUSH RESULT:", sent)

        except Exception as e:
            print("❌ CUSTOMER PUSH ERROR:", e)

    else:
        print(
            "ℹ️ No restaurant customer notification template for:",
            status_key
        )

    # ========================================================
    # FINAL MESSAGE
    # ========================================================

    if is_cancelled and previous_rider_id:

        flash(
            "Order cancelled and delivery rider released.",
            "success"
        )

    else:

        flash(
            "Order status updated!",
            "success"
        )

    return redirect(
        url_for("restaurant_dashboard")
    )
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out successfully", "success")
    return redirect(url_for("admin_login"))
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("You must be logged in as admin to access this page", "danger")
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
        flash("Invalid login!", "danger")
    return render_template("restaurant_login.html")






from datetime import datetime, timedelta
from flask import session, redirect, url_for, render_template
from models import Order, OrderItem, DeliveryPerson, db

from datetime import datetime, timedelta
from datetime import datetime, timedelta

@app.route("/restaurant/dashboard")
def restaurant_dashboard():

    restaurant_id = session.get("restaurant_id")

    if not restaurant_id:
        return redirect(
            url_for("restaurant_login")
        )

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    # ========================================================
    # FETCH ORDERS FOR THIS RESTAURANT
    # ========================================================

    orders = (
        Order.query
        .filter_by(
            restaurant_id=restaurant_id
        )
        .order_by(
            Order.created_at.desc()
        )
        .all()
    )

    # ========================================================
    # CLASSIFY ORDERS
    # ========================================================

    for o in orders:

        if o.created_at.date() == today:
            o.day_category = "Today"

        elif o.created_at.date() == yesterday:
            o.day_category = "Yesterday"

        else:
            o.day_category = "Older"

    today_orders = [
        o
        for o in orders
        if o.day_category == "Today"
    ]

    delivered_today_orders = [
        o
        for o in today_orders
        if o.status == "Delivered"
    ]

    # ========================================================
    # DASHBOARD STATS
    # ========================================================

    stats = {

        "today_orders":
            len(today_orders),

        "delivered_today":
            len(delivered_today_orders),

        "pending_today":
            len([
                o
                for o in today_orders
                if o.status == "Pending"
            ]),

        "cancelled_today":
            len([
                o
                for o in today_orders
                if o.status == "Cancelled"
            ]),

        "active_orders":
            len([
                o
                for o in orders
                if o.status in [
                    "Accepted",
                    "Preparing",
                    "Ready",
                    "Assignment Pending",
                    "Out for Delivery",
                ]
            ]),

        "today_earnings":
            sum(
                o.get_final_total()
                for o in delivered_today_orders
            ),

        "today_cod_amount":
            sum(
                o.get_final_total()
                for o in delivered_today_orders
                if o.payment_type == "COD"
            ),

        "today_online_amount":
            sum(
                o.get_final_total()
                for o in delivered_today_orders
                if o.payment_type == "Online"
            ),

        "weekly_orders":
            len([
                o
                for o in orders
                if o.created_at.date() >= week_ago
            ]),

        "weekly_earnings":
            sum(
                o.get_final_total()
                for o in orders
                if (
                    o.created_at.date() >= week_ago
                    and o.status == "Delivered"
                )
            ),

        "weekly_delivered_orders":
            len([
                o
                for o in orders
                if (
                    o.created_at.date() >= week_ago
                    and o.status == "Delivered"
                )
            ]),
    }

    # ========================================================
    # RIDER ONLINE / OFFLINE CLEANUP
    #
    # A rider is marked offline only when:
    # - currently marked online
    # - last_seen exists
    # - no heartbeat/location update for 5+ minutes
    # ========================================================

    threshold = (
        datetime.utcnow()
        - timedelta(minutes=5)
    )

    inactive_delivery_persons = (
        DeliveryPerson.query
        .filter(
            DeliveryPerson.is_online.is_(True),

            DeliveryPerson.last_seen.isnot(None),

            DeliveryPerson.last_seen < threshold,
        )
        .all()
    )

    for dp in inactive_delivery_persons:

        print(
            "⚠️ RIDER OFFLINE TIMEOUT:",
            dp.id,
            dp.name,
            "last_seen:",
            dp.last_seen
        )

        dp.is_online = False

    if inactive_delivery_persons:
        db.session.commit()

    # ========================================================
    # DELIVERY PERSONS LINKED TO THIS RESTAURANT
    # ========================================================

    delivery_persons = (
        DeliveryPerson.query
        .join(RestaurantDelivery)
        .filter(
            RestaurantDelivery.restaurant_id
            == restaurant_id
        )
        .order_by(
            DeliveryPerson.name
        )
        .all()
    )

    # ========================================================
    # RENDER DASHBOARD
    # ========================================================

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


# ============================================================
# RESTAURANT ORDER STATUS UPDATE + AUTO DISPATCH
# ============================================================

@app.route(
    "/restaurant/update_status/<int:order_id>",
    methods=["POST"]
)
def restaurant_update_status(order_id):

    # ========================================================
    # AUTH
    # ========================================================

    if not session.get("restaurant_logged_in"):
        return redirect(
            url_for("restaurant_login")
        )

    # ========================================================
    # GET ORDER
    # ========================================================

    order = Order.query.get_or_404(
        order_id
    )

    new_status = request.form.get(
        "status"
    )

    if not new_status:
        flash(
            "Invalid order status.",
            "danger"
        )

        return redirect(
            url_for("restaurant_dashboard")
        )

    # ========================================================
    # DELIVERY STATES RESTAURANT MUST NOT CHANGE
    # ========================================================

    protected_states = [
        "Assignment Pending",
        "Out for Delivery",
        "Picked Up",
        "Started",
        "Delivered",
    ]

    # If delivery process already started,
    # restaurant cannot change status.
    if order.status in protected_states:

        flash(
            "Delivery is already in progress. "
            "Status cannot be changed.",
            "warning"
        )

        return redirect(
            url_for("restaurant_dashboard")
        )

    # Restaurant cannot manually force delivery states.
    if new_status in protected_states:

        flash(
            "Only delivery partner can update "
            "delivery status.",
            "danger"
        )

        return redirect(
            url_for("restaurant_dashboard")
        )

    # ========================================================
    # UPDATE STATUS
    # ========================================================

    order.status = new_status

    db.session.commit()

    print(
        f"📦 ORDER STATUS UPDATED: "
        f"{order.order_id} → {new_status}"
    )

    # ========================================================
    # AUTO DISPATCH WHEN RESTAURANT MARKS READY
    # ========================================================

    if new_status == "Ready":

        print(
            "========================================"
        )

        print(
            f"🚚 STARTING AUTO DISPATCH FOR "
            f"{order.order_id}"
        )

        print(
            "========================================"
        )

        try:

            from dispatch_service import (
                auto_assign_order
            )

            success = auto_assign_order(
                order
            )

            if success:

                print(
                    f"✅ AUTO DISPATCH SUCCESS: "
                    f"{order.order_id}"
                )

            else:

                print(
                    f"⚠️ AUTO DISPATCH FAILED: "
                    f"No eligible rider for "
                    f"{order.order_id}"
                )

        except Exception as e:

            print(
                "❌ AUTO DISPATCH ERROR:",
                e
            )

            current_app.logger.exception(
                "Auto dispatch failed for order %s",
                order.order_id
            )

    # ========================================================
    # REAL-TIME CUSTOMER UPDATE
    # ========================================================

    socketio.emit(
        "order_status_update",
        {
            "order_id": order.id,
            "status": order.status,
        },
        room=f"order_{order.id}"
    )

    print(
        "📤 Emitted:",
        order.id,
        order.status
    )

    # ========================================================
    # SUCCESS
    # ========================================================

    flash(
        "Order status updated!",
        "success"
    )

    return redirect(
        url_for("restaurant_dashboard")
    )
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
            flash("Invalid login!", "danger")
            return render_template("delivery_login.html")

    return render_template("delivery_login.html")

@app.route("/delivery/dashboard", methods=["GET", "POST"])
def delivery_dashboard():

    # ========================================================
    # AUTH
    # ========================================================

    if not session.get("delivery_logged_in"):

        return redirect(
            url_for("delivery_login")
        )


    dp_id = session.get(
        "delivery_person_id"
    )


    delivery_person = (
        DeliveryPerson.query.get(
            dp_id
        )
    )


    if not delivery_person:

        return redirect(
            url_for("delivery_login")
        )


    # ========================================================
    # OTP SUBMIT
    # ========================================================

    if request.method == "POST":

        order_id = request.form.get(
            "order_id"
        )

        entered_otp = request.form.get(
            "otp"
        )


        order = Order.query.get(
            order_id
        )


        # ====================================================
        # ORDER VALIDATION
        # ====================================================

        if (
            not order
            or order.delivery_person_id
            != dp_id
        ):

            flash(
                "Invalid order",
                "danger"
            )

            return redirect(
                url_for(
                    "delivery_dashboard"
                )
            )


        # ====================================================
        # DELIVERY MUST BE STARTED
        # ====================================================

        if order.status != "Started":

            flash(
                "Delivery not started yet",
                "danger"
            )

            return redirect(
                url_for(
                    "delivery_dashboard"
                )
            )


        # ====================================================
        # DEBUG COINS
        # ====================================================

        print(
            "=== DEBUG COINS ==="
        )

        print(
            "Order ID:",
            order.id
        )

        print(
            "Customer ID:",
            order.customer_id
        )

        print(
            "Items Total:",
            order.items_total
        )


        setting = (
            RewardSetting.query.first()
        )


        print(
            "RewardSetting:",
            setting.earn_per_rupees
            if setting
            else "None"
        )


        # ====================================================
        # OTP CHECK
        # ====================================================

        if order.otp == entered_otp:


            # =================================================
            # ONLINE PAYMENT SAFETY CHECK
            # =================================================

            if (
                order.payment_type
                == "Online"

                and order.payment_status
                != "Paid"
            ):

                flash(
                    "Customer has not completed online payment yet.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "delivery_dashboard"
                    )
                )


            # =================================================
            # MARK DELIVERED
            # =================================================

            order.status = (
                "Delivered"
            )

            order.delivered_time = (
                datetime.utcnow()
            )


            # =================================================
            # REWARD COINS
            # =================================================

            coins_earned = add_coins(

                order.customer_id,

                order.items_total,

                order.id

            )


            db.session.commit()


            # =================================================
            # SAVE COINS FOR UI
            # =================================================

            session["earned_coins"] = (
                coins_earned
            )


            flash(

                f"Order {order.order_id} "
                f"delivered successfully",

                "success"

            )


        else:

            flash(
                "❌ Invalid OTP. Try again.",
                "danger"
            )


        return redirect(
            url_for(
                "delivery_dashboard"
            )
        )


    # ========================================================
    # ACTIVE ORDERS
    # ========================================================

    orders = (

        Order.query

        .filter(

            Order.delivery_person_id
            == dp_id,

            Order.status.in_(
                [
                    "Out for Delivery",
                    "Started"
                ]
            )

        )

        .order_by(

            case(

                (
                    Order.status
                    == "Out for Delivery",
                    0
                ),

                (
                    Order.status
                    == "Started",
                    1
                ),

                else_=2

            ),

            Order.created_at.desc()

        )

        .all()

    )


    # ========================================================
    # STATS
    # ========================================================

    all_orders = (

        Order.query

        .filter_by(
            delivery_person_id=
                dp_id
        )

        .all()

    )


    stats = {

        "total":

            len(
                all_orders
            ),


        "active":

            len([

                o

                for o in all_orders

                if o.status in [
                    "Out for Delivery",
                    "Started"
                ]

            ]),


        "delivered":

            len([

                o

                for o in all_orders

                if o.status
                == "Delivered"

            ]),


        "cod_total":

            sum(

                o.final_total or 0

                for o in all_orders

                if o.payment_type
                == "COD"

            ),


        "online_total":

            sum(

                o.final_total or 0

                for o in all_orders

                if o.payment_type
                == "Online"

            )

    }


    # ========================================================
    # RENDER
    # ========================================================

    return render_template(

        "delivery_dashboard.html",

        delivery_person=
            delivery_person,

        orders=
            orders,

        stats=
            stats,

        VAPID_PUBLIC_KEY=
            os.environ.get(
                "VAPID_PUBLIC_KEY"
            )

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
            flash("All fields are required!", "danger")
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

    # ========================================================
    # ADMIN AUTH
    # ========================================================

    if not session.get("admin_logged_in"):
        return redirect(
            url_for("admin_login")
        )


    # ========================================================
    # POST
    # ========================================================

    if request.method == "POST":

        try:

            # =================================================
            # FORM DATA
            # =================================================

            name = request.form.get(
                "name",
                ""
            ).strip()

            phone = request.form.get(
                "phone",
                ""
            ).strip()

            email = request.form.get(
                "email",
                ""
            ).strip()

            address = request.form.get(
                "address",
                ""
            ).strip()

            sheet_url = request.form.get(
                "sheet_url",
                ""
            ).strip()

            location = request.form.get(
                "location",
                ""
            ).strip()

            category_type = request.form.get(
                "category_type",
                ""
            ).strip().lower()


            # Normalize values like:
            # "Food Court" -> "food_court"
            category_type = (
                category_type
                .replace(" ", "_")
            )


            # =================================================
            # DEBUG
            # =================================================

            print(
                "\n===== ADD RESTAURANT FORM ====="
            )

            print(
                "RAW FORM:",
                request.form
            )

            print(
                "CATEGORY TYPE:",
                category_type
            )


            # =================================================
            # REQUIRED FIELDS
            # =================================================

            if (
                not name
                or not phone
                or not email
                or not sheet_url
            ):

                flash(
                    "Name, phone, email, and Google Sheet URL are required!",
                    "danger"
                )

                return redirect(
                    url_for(
                        "add_restaurant"
                    )
                )


            # =================================================
            # BUSINESS TYPE
            # =================================================

            allowed_types = [
                "restaurant",
                "bakery",
                "grocery"
            ]


            if category_type not in allowed_types:

                flash(
                    "Please select a valid business type!",
                    "danger"
                )

                return redirect(
                    url_for(
                        "add_restaurant"
                    )
                )


            # =================================================
            # DUPLICATE RESTAURANT
            # =================================================

            if (
                Restaurant.query
                .filter_by(
                    name=name
                )
                .first()
            ):

                flash(
                    "Restaurant already exists!",
                    "danger"
                )

                return redirect(
                    url_for(
                        "add_restaurant"
                    )
                )


            # =================================================
            # CREATE RESTAURANT
            # =================================================

            restaurant = Restaurant(

                name=
                    name,

                phone=
                    phone,

                email=
                    email,

                address=
                    address,

                sheet_url=
                    sheet_url,

                location=
                    location,

                category_type=
                    category_type

            )


            db.session.add(
                restaurant
            )

            db.session.commit()


            # =================================================
            # OPTIONAL RESTAURANT ADMIN USER
            # =================================================

            admin_username = request.form.get(
                "admin_username",
                ""
            ).strip()

            admin_password = request.form.get(
                "admin_password",
                ""
            )


            if (
                admin_username
                and admin_password
            ):

                # ---------------------------------------------
                # CHECK USERNAME
                # ---------------------------------------------

                if (
                    RestaurantUser.query
                    .filter_by(
                        username=
                            admin_username
                    )
                    .first()
                ):

                    flash(
                        "Admin username already exists!",
                        "danger"
                    )

                    return redirect(
                        url_for(
                            "add_restaurant"
                        )
                    )


                # ---------------------------------------------
                # CREATE RESTAURANT USER
                # ---------------------------------------------

                admin_user = RestaurantUser(

                    username=
                        admin_username,

                    restaurant_id=
                        restaurant.id

                )


                admin_user.set_password(
                    admin_password
                )


                db.session.add(
                    admin_user
                )

                db.session.commit()


            # =================================================
            # SUCCESS
            # =================================================

            display_type = (
                category_type
                .replace("_", " ")
                .title()
            )


            flash(
                f"{display_type} '{name}' added successfully!",
                "success"
            )


            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )


        # =====================================================
        # ERROR
        # =====================================================

        except Exception as e:

            db.session.rollback()


            print(
                "ADD RESTAURANT ERROR:",
                e
            )


            flash(
                "Error while adding restaurant. Check server logs.",
                "danger"
            )


            return redirect(
                url_for(
                    "add_restaurant"
                )
            )


    # ========================================================
    # GET
    # ========================================================

    return render_template(
        "add_restaurant.html"
    )
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

# ============================================================
# MENU ROUTE
# ============================================================

@app.route("/menu/<int:restaurant_id>")
def menu(restaurant_id):

    # ========================================================
    # RESTAURANT
    # ========================================================

    restaurant = Restaurant.query.get_or_404(
        restaurant_id
    )

    print(
        "OPENING MENU FOR:",
        restaurant.name,
        "| TYPE:",
        restaurant.category_type
    )


    # ========================================================
    # OPEN / CLOSE CHECK
    # ========================================================

    ist = pytz.timezone(
        "Asia/Kolkata"
    )

    now = datetime.now(
        ist
    ).time()


    if (
        restaurant.opening_time
        and restaurant.closing_time
    ):

        # ----------------------------------------------------
        # NORMAL HOURS
        # Example: 10:00 AM → 11:00 PM
        # ----------------------------------------------------

        if (
            restaurant.opening_time
            < restaurant.closing_time
        ):

            is_open = (

                restaurant.opening_time
                <= now
                <= restaurant.closing_time

            )


        # ----------------------------------------------------
        # OVERNIGHT HOURS
        # Example: 6:00 PM → 2:00 AM
        # ----------------------------------------------------

        else:

            is_open = (

                now
                >= restaurant.opening_time

                or

                now
                <= restaurant.closing_time

            )


    else:

        is_open = True


    # ========================================================
    # RESTAURANT ACCEPTING ORDERS?
    # ========================================================

    if (
        not is_open
        or
        not restaurant.can_accept_orders
    ):

        flash(
            "Restaurant is currently not accepting orders",
            "warning"
        )

        return redirect(
            url_for("home")
        )


    # ========================================================
    # LOAD MENU FROM POSTGRES
    # ========================================================

    menu_items = (

        MenuItem.query

        .filter(
            MenuItem.restaurant_id
            == restaurant.id,

            MenuItem.availability
            == "yes"
        )

        .order_by(
            MenuItem.category,
            MenuItem.name
        )

        .all()

    )


    # ========================================================
    # REMOVE ADD-ON ONLY ITEMS FROM NORMAL MENU
    # ========================================================

    menu_items = [

        item

        for item in menu_items

        if str(
            (item.extra_data or {}).get(
                "is_addon",
                "No"
            )
        ).strip().lower()
        != "yes"

    ]


    print(
        "MENU ITEMS FOUND:",
        len(menu_items)
    )


    # ========================================================
    # CUSTOMER REORDER DATA
    # ========================================================

    reorder_map = {}


    if current_user.is_authenticated:

        raw = (

            db.session.query(

                OrderItem.item_name,

                func.count(
                    OrderItem.id
                )

            )

            .join(
                Order,
                Order.id
                == OrderItem.order_id
            )

            .filter(
                Order.customer_id
                == current_user.id
            )

            .group_by(
                OrderItem.item_name
            )

            .all()

        )


        reorder_map = {

            normalize_name(name):
                count

            for name, count
            in raw

        }


    print(
        "USER REORDER MAP:",
        reorder_map
    )


    # ========================================================
    # ACTIVE RESTAURANT OFFER
    # ========================================================

    active_offer = (

        RestaurantOffer.query

        .filter(
            RestaurantOffer.restaurant_id
            == restaurant.id,

            RestaurantOffer.is_active
            == True
        )

        .first()

    )


    # ========================================================
    # SELECTED OFFER ITEM IDS
    # ========================================================

    selected_offer_item_ids = set()


    if (
        active_offer
        and active_offer.offer_scope
        == "selected_items"
    ):

        selected_offer_item_ids = {

            selected_item.id

            for selected_item
            in active_offer.selected_items

        }


    # ========================================================
    # PROCESS MENU ITEMS
    # ========================================================

    items = []


    for item in menu_items:

        # Copy JSON data so SQLAlchemy JSON
        # object itself is not modified
        data = dict(
            item.extra_data
            or {}
        )


        # ====================================================
        # BASIC ITEM DATA
        # ====================================================

        data["id"] = (
            item.id
        )

        data["name"] = (
            item.name
        )

        data["description"] = (
            item.description
            or ""
        )

        data["price"] = (
            item.price
            or 0
        )

        data["category"] = (
            item.category
            or "Other"
        )

        data["image_url"] = (
            item.image_url
            or ""
        )

        data["availability"] = (
            item.availability
        )

        data["item_type"] = (
            item.item_type
            or ""
        )


        # ====================================================
        # REORDER COUNT
        # ====================================================

        data["reorder_count"] = (

            reorder_map.get(

                normalize_name(
                    item.name
                ),

                0

            )

        )


        # ====================================================
        # OFFER DEFAULTS
        # ====================================================

        data["offer_price"] = (
            None
        )

        data["offer_percent"] = (
            None
        )

        data["offer_flat"] = (
            None
        )

        data["has_offer"] = (
            False
        )


        # ====================================================
        # CHECK RESTAURANT OFFER
        # ====================================================

        if active_offer:

            item_eligible = False


            # ------------------------------------------------
            # OFFER FOR ALL ITEMS
            # ------------------------------------------------

            if (
                active_offer.offer_scope
                == "all_items"
            ):

                item_eligible = True


            # ------------------------------------------------
            # OFFER FOR SELECTED ITEMS
            # ------------------------------------------------

            elif (
                active_offer.offer_scope
                == "selected_items"
            ):

                item_eligible = (

                    item.id
                    in selected_offer_item_ids

                )


            # =================================================
            # CALCULATE OFFER PRICE
            # =================================================

            if item_eligible:


                # ---------------------------------------------
                # PERCENT OFFER
                # ---------------------------------------------

                if (
                    active_offer.offer_type
                    == "percent"
                ):

                    discount_amount = (

                        float(
                            item.price
                            or 0
                        )

                        *

                        float(
                            active_offer.offer_value
                            or 0
                        )

                        / 100

                    )


                    offer_price = max(

                        0,

                        float(
                            item.price
                            or 0
                        )
                        -
                        discount_amount

                    )


                    data["offer_price"] = round(
                        offer_price,
                        2
                    )

                    data["offer_percent"] = (
                        active_offer.offer_value
                    )

                    data["has_offer"] = (
                        True
                    )


                # ---------------------------------------------
                # FLAT OFFER
                # ---------------------------------------------

                elif (
                    active_offer.offer_type
                    == "flat"
                ):

                    offer_price = max(

                        0,

                        float(
                            item.price
                            or 0
                        )
                        -
                        float(
                            active_offer.offer_value
                            or 0
                        )

                    )


                    data["offer_price"] = round(
                        offer_price,
                        2
                    )

                    data["offer_flat"] = (
                        active_offer.offer_value
                    )

                    data["has_offer"] = (
                        True
                    )


        items.append(
            data
        )


    # ========================================================
    # GROUP ITEMS BY CATEGORY
    # ========================================================

    menu_by_category = {}


    for item in items:

        category = (

            item.get(
                "category"
            )
            or "Other"

        )


        menu_by_category.setdefault(
            category,
            []
        ).append(
            item
        )


    print(
        "MENU CATEGORIES:",
        list(
            menu_by_category.keys()
        )
    )


    # ========================================================
    # BAKERY MENU
    # ========================================================

    if (
        restaurant.category_type
        == "bakery"
    ):

        print(
            "👉 Loading BAKERY menu"
        )

        return render_template(

            "bakery_menu.html",

            restaurant=
                restaurant,

            menu_by_category=
                menu_by_category,

            active_offer=
                active_offer

        )


    # ========================================================
    # NORMAL RESTAURANT MENU
    # ========================================================

    print(
        "👉 Loading NORMAL menu"
    )


    return render_template(

        "menu.html",

        restaurant=
            restaurant,

        menu_by_category=
            menu_by_category,

        active_offer=
            active_offer

    )
@app.route(
    "/restaurant/assign_delivery/<int:order_id>",
    methods=["POST"]
)
def restaurant_assign_delivery(order_id):

    # ========================================================
    # AUTH
    # ========================================================

    if not session.get("restaurant_logged_in"):

        return redirect(
            url_for("restaurant_login")
        )


    # ========================================================
    # GET ORDER + DELIVERY PERSON
    # ========================================================

    delivery_person_id = request.form.get(
        "delivery_person_id"
    )


    order = Order.query.get(
        order_id
    )


    if not order:

        flash(
            "Order not found!",
            "danger"
        )

        return redirect(
            url_for(
                "restaurant_dashboard"
            )
        )


    # ========================================================
    # DELIVERY PERSON ID VALIDATION
    # ========================================================

    if not delivery_person_id:

        flash(
            "Please select a delivery person.",
            "danger"
        )

        return redirect(
            url_for(
                "restaurant_dashboard"
            )
        )


    try:

        delivery_person_id = int(
            delivery_person_id
        )

    except (
        TypeError,
        ValueError
    ):

        flash(
            "Invalid delivery person.",
            "danger"
        )

        return redirect(
            url_for(
                "restaurant_dashboard"
            )
        )


    dp = DeliveryPerson.query.get(
        delivery_person_id
    )


    if not dp:

        flash(
            "Delivery person not found!",
            "danger"
        )

        return redirect(
            url_for(
                "restaurant_dashboard"
            )
        )


    # ========================================================
    # ASSIGN DELIVERY PERSON
    # ========================================================

    order.delivery_person_id = (
        dp.id
    )

    order.delivery_boy_name = (
        dp.name
    )

    order.delivery_boy_phone = (
        dp.phone
    )

    order.status = (
        "Out for Delivery"
    )


    # ========================================================
    # SAVE BEFORE NOTIFICATIONS
    # ========================================================

    db.session.commit()


    # ========================================================
    # FIREBASE PUSH TO DELIVERY PERSON
    # ========================================================

    if dp.fcm_token:

        distance = (
            order.distance_km
            or 0
        )


        body = (

            f"🏪 {order.restaurant.name}\n"

            f"👤 {order.customer_name}\n"

            f"💰 ₹{order.final_total}\n"

            f"📏 {distance} km\n"

            f"💳 {order.payment_type}"

        )


        # Build readable address safely
        address_parts = [

            order.house_no,

            order.landmark,

            order.city,

            order.state,

            order.pincode

        ]


        delivery_address = ", ".join(

            str(part)

            for part in address_parts

            if part

        )


        try:

            send_push_notification(

                title=
                    "🚴 New Delivery Assigned",

                body=
                    body,

                target_type=
                    "token",

                target_value=
                    dp.fcm_token,

                data={

                    "type":
                        "new_order",

                    "order_id":
                        str(order.id),

                    "order_number":
                        order.order_id
                        or "",

                    "restaurant_name":
                        order.restaurant.name
                        or "",

                    "customer_name":
                        order.customer_name
                        or "",

                    "customer_phone":
                        order.phone
                        or "",

                    "address":
                        delivery_address,

                    "distance":
                        str(distance),

                    "total":
                        str(
                            order.final_total
                            or 0
                        ),

                    "payment_type":
                        order.payment_type
                        or "COD"

                }

            )


        except Exception as e:

            # Push failure should NOT undo assignment
            print(
                "DELIVERY PUSH ERROR:",
                e
            )


    # ========================================================
    # LIVE UPDATE TO DELIVERY PERSON DASHBOARD
    # ========================================================

    socketio.emit(

        "new_order_assigned",

        {

            "order_id":
                order.id,

            "order_number":
                order.order_id,

            "restaurant":
                order.restaurant.name,

            "customer":
                order.customer_name,

            "distance":
                order.distance_km or 0,

            "total":
                order.final_total or 0,

            "payment_type":
                order.payment_type or "COD"

        },

        room=f"delivery_{dp.id}"

    )


    # ========================================================
    # LIVE UPDATE TO CUSTOMER TRACKING PAGE
    # ========================================================

    socketio.emit(

        "delivery_assigned",

        {

            "order_id":
                order.id,

            "public_order_id":
                order.order_id,

            "delivery_person_name":
                dp.name,

            "delivery_person_phone":
                dp.phone,

            "status":
                order.status

        },

        room=f"order_{order.id}"

    )


    # ========================================================
    # SUCCESS
    # ========================================================

    flash(

        f"Delivery boy {dp.name} "
        f"assigned to Order {order.order_id}",

        "success"

    )


    return redirect(
        url_for(
            "restaurant_dashboard"
        )
    )

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

    delivery_person_id = session.get(
        "delivery_person_id"
    )

    if not delivery_person_id:
        return redirect(
            url_for("delivery_login")
        )

    order_id = request.form.get(
        "order_id"
    )

    otp_entered = request.form.get(
        "otp"
    )

    order = db.session.get(
        Order,
        order_id
    )

    if not order:
        return "Order not found", 404

    # ========================================================
    # SECURITY: ORDER MUST BELONG TO THIS RIDER
    # ========================================================

    if order.delivery_person_id != delivery_person_id:
        return "This order is not assigned to you", 403

    # ========================================================
    # PREVENT DOUBLE DELIVERY
    # ========================================================

    if order.status == "Delivered":
        return redirect(
            url_for("delivery_dashboard")
        )

    # ========================================================
    # OTP CHECK
    # ========================================================

    if not order.otp:
        return "Delivery OTP is missing", 400

    if str(order.otp).strip() != str(otp_entered or "").strip():
        return "Invalid OTP", 400

    # ========================================================
    # GET RIDER
    # ========================================================

    rider = db.session.get(
        DeliveryPerson,
        delivery_person_id
    )

    if not rider:
        return "Delivery partner not found", 404

    # ========================================================
    # MARK ORDER AS DELIVERED
    # ========================================================

    order.status = "Delivered"

    order.delivered_time = datetime.utcnow()

    order.rider_response = "Accepted"

    # ========================================================
    # RELEASE RIDER
    #
    # Important:
    # Keep delivery_person_id on the delivered order so
    # history and today's rider statistics still work.
    # ========================================================

    rider.is_available = True

    # ========================================================
    # SAVE
    # ========================================================

    db.session.commit()

    print("\n====================================")
    print("✅ ORDER DELIVERED")
    print("ORDER:", order.id, order.order_id)
    print("RIDER:", rider.id, rider.name)
    print("RIDER AVAILABLE:", rider.is_available)
    print("DELIVERED TIME:", order.delivered_time)
    print("====================================\n")

    return redirect(
        url_for("delivery_dashboard")
    )

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

    # ========================================================
    # CURRENT SESSION CART
    # ========================================================

    cart = session.get(
        "cart",
        []
    )

    cart_restaurant_id = session.get(
        "cart_restaurant_id"
    )


    # ========================================================
    # DIFFERENT RESTAURANT
    # CLEAR OLD CART
    # ========================================================

    if (
        cart_restaurant_id
        and cart_restaurant_id != restaurant_id
    ):

        flash(
            "Your cart had items from another restaurant. Cart cleared.",
            "warning"
        )

        cart = []


    # ========================================================
    # GET MENU ITEM
    # ========================================================

    item = MenuItem.query.get_or_404(
        item_id
    )


    # Safety: make sure this item actually
    # belongs to the restaurant in the URL
    if (
        item.restaurant_id
        != restaurant_id
    ):

        flash(
            "Invalid menu item.",
            "danger"
        )

        return redirect(
            url_for("home")
        )


    # ========================================================
    # SAVE RESTAURANT ID
    # ========================================================

    session["cart_restaurant_id"] = (
        restaurant_id
    )


    # ========================================================
    # ITEM ALREADY EXISTS
    # ========================================================

    item_found = False


    for c in cart:

        if c.get("id") == item.id:

            c["quantity"] = (
                int(
                    c.get(
                        "quantity",
                        0
                    )
                )
                + 1
            )


            # Keep latest item information
            c["name"] = (
                item.name
            )

            c["price"] = float(
                item.price
            )

            c["restaurant_id"] = (
                restaurant_id
            )

            c["category"] = (
                item.category or ""
            )

            c["item_type"] = (
                item.item_type or ""
            )

            c["description"] = (
                item.description or ""
            )

            c["extra_data"] = (
                item.extra_data or {}
            )


            item_found = True

            break


    # ========================================================
    # NEW ITEM
    # ========================================================

    if not item_found:

        cart.append({

            "id":
                item.id,

            "restaurant_id":
                restaurant_id,

            "name":
                item.name,

            "price":
                float(
                    item.price
                ),

            "quantity":
                1,


            # Recommendation engine
            "category":
                item.category or "",

            "item_type":
                item.item_type or "",


            # Useful for future recommendation / ML
            "description":
                item.description or "",


            # Sheet / additional metadata
            "extra_data":
                item.extra_data or {}

        })


    # ========================================================
    # DEBUG
    # ========================================================

    print(
        "========== CART BEFORE SAVE =========="
    )

    print(
        cart
    )


    # ========================================================
    # SAVE SESSION CART
    # ========================================================

    session["cart"] = (
        cart
    )


    session["cart_count"] = sum(

        int(
            i.get(
                "quantity",
                0
            )
        )

        for i in cart

    )


    session.modified = True


    print(
        "========== CART AFTER SAVE =========="
    )

    print(
        session.get("cart")
    )


    # ========================================================
    # REDIRECT TO THIS RESTAURANT CART
    # ========================================================

    return redirect(

        url_for(
            "cart_page",
            restaurant_id=restaurant_id
        )

    )
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
@app.route(
    "/dashboard/offers/<int:restaurant_id>/add",
    methods=["GET", "POST"]
)
def add_offer(restaurant_id):

    restaurant = Restaurant.query.get_or_404(
        restaurant_id
    )

    menu_items = (
        MenuItem.query
        .filter_by(
            restaurant_id=restaurant_id
        )
        .order_by(
            MenuItem.category,
            MenuItem.name
        )
        .all()
    )

    if request.method == "POST":

        title = request.form.get("title")
        description = request.form.get("description")
        offer_type = request.form.get("offer_type")

        offer_value = float(
            request.form.get("offer_value") or 0
        )

        min_order_amount = float(
            request.form.get("min_order_amount") or 0
        )

        start_date = request.form.get("start_date")
        end_date = request.form.get("end_date")

        is_active = (
            request.form.get("is_active") == "1"
        )

        offer_scope = request.form.get(
            "offer_scope",
            "all_items"
        )

        # Free delivery applies to order,
        # not individual menu items
        if offer_type == "free_delivery":
            offer_scope = "all_items"

        selected_item_ids = request.form.getlist(
            "selected_items"
        )

        new_offer = RestaurantOffer(

            restaurant_id=restaurant_id,

            title=title,

            description=description,

            offer_type=offer_type,

            offer_value=offer_value,

            min_order_amount=min_order_amount,

            start_date=(
                datetime.strptime(
                    start_date,
                    "%Y-%m-%d"
                )
                if start_date
                else None
            ),

            end_date=(
                datetime.strptime(
                    end_date,
                    "%Y-%m-%d"
                )
                if end_date
                else None
            ),

            is_active=is_active,

            offer_scope=offer_scope
        )

        # ============================================
        # SELECTED ITEMS
        # ============================================

        if offer_scope == "selected_items":

            if not selected_item_ids:

                flash(
                    "Please select at least one menu item.",
                    "warning"
                )

                return render_template(
                    "dashboard/add_offer.html",
                    restaurant=restaurant,
                    menu_items=menu_items
                )

            selected_items = (

                MenuItem.query

                .filter(
                    MenuItem.restaurant_id
                    == restaurant_id,

                    MenuItem.id.in_(
                        selected_item_ids
                    )
                )

                .all()
            )

            new_offer.selected_items = (
                selected_items
            )

        db.session.add(
            new_offer
        )

        db.session.commit()

        flash(
            "Offer added successfully",
            "success"
        )

        return redirect(
            url_for(
                "manage_offers",
                restaurant_id=restaurant_id
            )
        )

    return render_template(
        "dashboard/add_offer.html",
        restaurant=restaurant,
        menu_items=menu_items
    )
# ---------------- EDIT OFFER ----------------
@app.route(
    "/dashboard/offers/<int:offer_id>/edit",
    methods=["GET", "POST"]
)
def edit_offer(offer_id):

    # ========================================================
    # GET OFFER + RESTAURANT
    # ========================================================

    offer = RestaurantOffer.query.get_or_404(
        offer_id
    )

    restaurant = Restaurant.query.get_or_404(
        offer.restaurant_id
    )


    # ========================================================
    # MENU ITEMS FOR THIS RESTAURANT
    # ========================================================

    menu_items = (
        MenuItem.query
        .filter_by(
            restaurant_id=restaurant.id
        )
        .order_by(
            MenuItem.category,
            MenuItem.name
        )
        .all()
    )


    # ========================================================
    # POST
    # ========================================================

    if request.method == "POST":

        # ----------------------------------------------------
        # BASIC DETAILS
        # ----------------------------------------------------

        offer.title = request.form.get(
            "title"
        )

        offer.description = request.form.get(
            "description"
        )

        offer.offer_type = request.form.get(
            "offer_type"
        )

        offer.offer_value = float(
            request.form.get(
                "offer_value"
            ) or 0
        )

        offer.min_order_amount = float(
            request.form.get(
                "min_order_amount"
            ) or 0
        )


        # ----------------------------------------------------
        # ACTIVE / INACTIVE
        # ----------------------------------------------------

        offer.is_active = (
            request.form.get(
                "is_active"
            ) == "1"
        )


        # ----------------------------------------------------
        # DATES
        # ----------------------------------------------------

        start_date = request.form.get(
            "start_date"
        )

        end_date = request.form.get(
            "end_date"
        )


        offer.start_date = (
            datetime.strptime(
                start_date,
                "%Y-%m-%d"
            )
            if start_date
            else None
        )


        offer.end_date = (
            datetime.strptime(
                end_date,
                "%Y-%m-%d"
            )
            if end_date
            else None
        )


        # ----------------------------------------------------
        # OFFER SCOPE
        # ----------------------------------------------------

        offer.offer_scope = request.form.get(
            "offer_scope",
            "all_items"
        )


        # Free delivery is order-level,
        # so selected items do not apply.
        if offer.offer_type == "free_delivery":

            offer.offer_scope = (
                "all_items"
            )


        # ----------------------------------------------------
        # SELECTED ITEM IDS
        # ----------------------------------------------------

        selected_item_ids = request.form.getlist(
            "selected_items"
        )


        # ----------------------------------------------------
        # SELECTED ITEMS OFFER
        # ----------------------------------------------------

        if (
            offer.offer_scope
            == "selected_items"
        ):

            if not selected_item_ids:

                flash(
                    "Please select at least one menu item.",
                    "warning"
                )

                return render_template(
                    "dashboard/edit_offer.html",
                    offer=offer,
                    restaurant=restaurant,
                    menu_items=menu_items,
                    is_edit=True
                )


            selected_items = (
                MenuItem.query
                .filter(
                    MenuItem.restaurant_id
                    == restaurant.id,

                    MenuItem.id.in_(
                        selected_item_ids
                    )
                )
                .all()
            )


            offer.selected_items = (
                selected_items
            )


        # ----------------------------------------------------
        # ALL ITEMS OFFER
        # ----------------------------------------------------

        else:

            # Clear old selected-item links
            offer.selected_items = []


        # ====================================================
        # SAVE
        # ====================================================

        try:

            db.session.commit()

        except Exception as e:

            db.session.rollback()

            print(
                "EDIT OFFER ERROR:",
                e
            )

            flash(
                "Unable to update offer.",
                "danger"
            )

            return render_template(
                "dashboard/edit_offer.html",
                offer=offer,
                restaurant=restaurant,
                menu_items=menu_items,
                is_edit=True
            )


        flash(
            "Offer updated successfully",
            "success"
        )


        return redirect(
            url_for(
                "manage_offers",
                restaurant_id=
                    restaurant.id
            )
        )


    # ========================================================
    # GET
    # ========================================================

    return render_template(
        "dashboard/edit_offer.html",
        offer=offer,
        restaurant=restaurant,
        menu_items=menu_items,
        is_edit=True
    )
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

    # Same random order for the whole day
    random.seed(
        date.today().toordinal()
    )

    def created_timestamp(r):

        if r.created_at:
            return r.created_at.timestamp()

        return 0


    def sort_key(r):

        new = is_new_restaurant(r)

        open_now = bool(
            r.is_open
        )

        accepting = bool(
            r.can_accept_orders
        )

        deliverable = bool(
            r.deliverable
        )


        available = (
            open_now
            and accepting
            and deliverable
        )


        # ====================================================
        # 1️⃣ NEW + AVAILABLE
        # Newest first
        # ====================================================

        if new and available:

            return (
                0,
                -created_timestamp(r)
            )


        # ====================================================
        # 2️⃣ AVAILABLE NORMAL RESTAURANTS
        # Daily rotation
        # ====================================================

        if available:

            return (
                1,
                random.random()
            )


        # ====================================================
        # 3️⃣ NEW BUT CURRENTLY NOT AVAILABLE
        # ====================================================

        if new:

            return (
                2,
                -created_timestamp(r)
            )


        # ====================================================
        # 4️⃣ EVERYTHING ELSE
        # ====================================================

        return (
            3,
            0
        )


    restaurants.sort(
        key=sort_key
    )

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


@app.route(
    "/dashboard/restaurant/<int:restaurant_id>/edit",
    methods=["GET", "POST"]
)
def edit_restaurant_card(restaurant_id):

    restaurant = Restaurant.query.get_or_404(
        restaurant_id
    )

    categories = Category.query.all()


    if request.method == "POST":

        try:

            # =================================================
            # RESTAURANT CATEGORIES
            # =================================================

            selected_ids = request.form.getlist(
                "categories"
            )

            print(
                "Selected IDs:",
                selected_ids
            )


            if selected_ids:

                selected_categories = (
                    Category.query
                    .filter(
                        Category.id.in_(
                            selected_ids
                        )
                    )
                    .all()
                )

            else:

                selected_categories = []


            restaurant.categories = (
                selected_categories
            )


            # =================================================
            # BASIC INFO
            # =================================================

            restaurant.name = request.form.get(
                "name",
                ""
            ).strip()

            restaurant.address = request.form.get(
                "address"
            )

            restaurant.phone = request.form.get(
                "phone"
            )

            restaurant.email = request.form.get(
                "email"
            )


            # =================================================
            # CATEGORY TYPE
            # =================================================

            allowed = [
                "restaurant",
                "bakery",
                "grocery",
                "pharmacy",
                "meat"
            ]


            category = request.form.get(
                "category_type",
                ""
            ).strip().lower()


            # Only update when a category is supplied
            if category:

                if category not in allowed:

                    flash(
                        "Invalid category selected!",
                        "danger"
                    )

                    return redirect(
                        request.url
                    )


                restaurant.category_type = (
                    category
                )


            # =================================================
            # CARD DETAILS
            # =================================================

            restaurant.is_veg = (
                request.form.get(
                    "is_veg"
                ) == "yes"
            )


            restaurant.rating = float(
                request.form.get(
                    "rating"
                ) or 4.0
            )


            restaurant.price_level = (
                request.form.get(
                    "price_level"
                )
            )


            restaurant.delivery_time = (
                request.form.get(
                    "delivery_time"
                )
            )


            restaurant.popular_items = (
                request.form.get(
                    "popular_items"
                )
            )


            # =================================================
            # DELIVERY
            # =================================================

            restaurant.delivery_charge = float(
                request.form.get(
                    "delivery_charge"
                ) or 30
            )


            restaurant.free_delivery_limit = float(
                request.form.get(
                    "free_delivery_limit"
                ) or 0
            )


            restaurant.latitude = (
                request.form.get(
                    "latitude"
                )
                or None
            )


            restaurant.longitude = (
                request.form.get(
                    "longitude"
                )
                or None
            )


            restaurant.delivery_radius_km = float(
                request.form.get(
                    "delivery_radius_km"
                ) or 5
            )


            restaurant.force_delivery_charge = (
                request.form.get(
                    "force_delivery_charge"
                ) == "1"
            )


            # =================================================
            # OPEN / CLOSE
            # =================================================

            opening_time = request.form.get(
                "opening_time"
            )

            closing_time = request.form.get(
                "closing_time"
            )


            restaurant.opening_time = (
                datetime.strptime(
                    opening_time,
                    "%H:%M"
                ).time()
                if opening_time
                else None
            )


            restaurant.closing_time = (
                datetime.strptime(
                    closing_time,
                    "%H:%M"
                ).time()
                if closing_time
                else None
            )


            # =================================================
            # ACCEPT ORDERS
            # =================================================

            restaurant.is_accepting_orders = (
                request.form.get(
                    "is_accepting_orders"
                ) == "1"
            )


            accept_orders_until = (
                request.form.get(
                    "accept_orders_until"
                )
            )


            restaurant.accept_orders_until = (
                datetime.strptime(
                    accept_orders_until,
                    "%H:%M"
                ).time()
                if accept_orders_until
                else None
            )


            # =================================================
            # START DATE
            # =================================================

            start_date = request.form.get(
                "start_date"
            )


            restaurant.start_date = (
                datetime.strptime(
                    start_date,
                    "%Y-%m-%d"
                ).date()
                if start_date
                else None
            )


            # =================================================
            # STATUS
            # =================================================

            status = request.form.get(
                "status"
            )


            if status in [
                "active",
                "coming_soon",
                "suspended"
            ]:

                restaurant.status = (
                    status
                )


            if (
                restaurant.status
                == "coming_soon"
                and not restaurant.start_date
            ):

                flash(
                    "Start date is required for Coming Soon",
                    "danger"
                )

                return redirect(
                    request.url
                )


            # =================================================
            # LIMITED DROP
            # =================================================

            restaurant.is_limited_drop = (
                request.form.get(
                    "is_limited_drop"
                ) == "1"
            )


            restaurant.limited_item_name = (
                request.form.get(
                    "limited_item_name"
                )
                or None
            )


            restaurant.limited_total_qty = int(
                request.form.get(
                    "limited_total_qty"
                ) or 0
            )


            restaurant.limited_remaining_qty = int(
                request.form.get(
                    "limited_remaining_qty"
                ) or 0
            )


            start_raw = request.form.get(
                "limited_start_datetime"
            )

            end_raw = request.form.get(
                "limited_end_datetime"
            )


            # =================================================
            # LIMITED DROP TIME → UTC
            # =================================================

            if restaurant.is_limited_drop:

                if start_raw and end_raw:

                    restaurant.limited_start_datetime = (
                        ist_to_utc(
                            start_raw
                        )
                    )

                    restaurant.limited_end_datetime = (
                        ist_to_utc(
                            end_raw
                        )
                    )

                else:

                    restaurant.limited_start_datetime = None
                    restaurant.limited_end_datetime = None


            else:

                restaurant.limited_start_datetime = None
                restaurant.limited_end_datetime = None


            # =================================================
            # LIMITED DROP VALIDATION
            # =================================================

            if restaurant.is_limited_drop:

                if not restaurant.limited_item_name:

                    flash(
                        "Limited item name is required",
                        "danger"
                    )

                    return redirect(
                        request.url
                    )


                if (
                    restaurant.limited_total_qty
                    <= 0
                ):

                    flash(
                        "Total quantity must be greater than 0",
                        "danger"
                    )

                    return redirect(
                        request.url
                    )


                if (
                    not restaurant.limited_start_datetime
                    or
                    not restaurant.limited_end_datetime
                ):

                    flash(
                        "Start and End time required",
                        "danger"
                    )

                    return redirect(
                        request.url
                    )


                if (
                    restaurant.limited_end_datetime
                    <=
                    restaurant.limited_start_datetime
                ):

                    flash(
                        "End time must be after start time",
                        "danger"
                    )

                    return redirect(
                        request.url
                    )


            # =================================================
            # DEBUG
            # =================================================

            print(
                "RAW FORM START:",
                start_raw
            )

            print(
                "RAW FORM END:",
                end_raw
            )

            print(
                "UTC START:",
                restaurant.limited_start_datetime
            )

            print(
                "UTC END:",
                restaurant.limited_end_datetime
            )


            if (
                restaurant.limited_start_datetime
                and
                restaurant.limited_end_datetime
            ):

                hours = (

                    restaurant.limited_end_datetime
                    -
                    restaurant.limited_start_datetime

                ).total_seconds() / 3600


            else:

                hours = 0


            print(
                "HOURS:",
                hours
            )


            # =================================================
            # SAVE EVERYTHING ONCE
            # =================================================

            db.session.commit()


            print(
                "AFTER COMMIT:",
                [
                    (c.id, c.name)
                    for c
                    in restaurant.categories
                ]
            )


            flash(
                "Restaurant updated successfully!",
                "success"
            )


            return redirect(
                url_for(
                    "restaurant_dashboard",
                    restaurant_id=
                        restaurant.id
                )
            )


        except Exception as e:

            db.session.rollback()

            print(
                "EDIT RESTAURANT ERROR:",
                e
            )

            flash(
                "Unable to update restaurant. Check server logs.",
                "danger"
            )

            return redirect(
                request.url
            )


    # ========================================================
    # DISPLAY FORM
    # ========================================================

    restaurant.limited_start_local = (
        restaurant.limited_start_datetime
    )

    restaurant.limited_end_local = (
        restaurant.limited_end_datetime
    )


    return render_template(

        "dashboard/edit_restaurant_card.html",

        restaurant=
            restaurant,

        categories=
            categories

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
def calculate_delivery_charge(
    distance_km,
    items_total,
    restaurant
):

    s = DeliverySettings.query.first()

    # ========================================================
    # FALLBACK
    # ========================================================

    if not s:

        return (
            30,
            "🚚 Delivery charge ₹30"
        )


    # ========================================================
    # NORMAL RESTAURANT FREE DELIVERY
    # DISABLED
    # ========================================================

    # Restaurant free-delivery threshold is no longer used.
    # Free delivery should only come from an active offer.


    # ========================================================
    # DISTANCE SLAB
    # ========================================================

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


    # ========================================================
    # NIGHT SURGE
    # ========================================================

    if s.is_night_surge_active:

        charge += s.night_surge

        msg = (
            f"🌙 Night delivery charge ₹{charge}"
        )


    else:

        msg = (
            f"🚚 Delivery charge ₹{charge}"
        )


    return (
        charge,
        msg
    )
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

# ============================================================
# BAKERY MENU
# ============================================================

@app.route("/bakery/<int:restaurant_id>")
def bakery_menu(restaurant_id):

    # ========================================================
    # RESTAURANT
    # ========================================================

    restaurant = Restaurant.query.get_or_404(
        restaurant_id
    )


    if restaurant.category_type != "bakery":

        abort(404)


    # ========================================================
    # LOAD BAKERY ITEMS FROM POSTGRES
    # ========================================================

    menu_items = (

        MenuItem.query

        .filter(

            MenuItem.restaurant_id
            == restaurant.id,

            MenuItem.availability
            == "yes"

        )

        .order_by(

            MenuItem.category,

            MenuItem.name

        )

        .all()

    )


    # ========================================================
    # REMOVE ADDON-ONLY ITEMS
    # ========================================================

    menu_items = [

        item

        for item in menu_items

        if str(

            (item.extra_data or {}).get(
                "is_addon",
                "No"
            )

        ).strip().lower() != "yes"

    ]


    print(
        "BAKERY:",
        restaurant.name,
        "| ITEMS:",
        len(menu_items)
    )


    # ========================================================
    # CUSTOMER REORDER DATA
    # ========================================================

    reorder_map = {}


    if current_user.is_authenticated:

        raw = (

            db.session.query(

                OrderItem.item_name,

                func.count(
                    OrderItem.id
                )

            )

            .join(

                Order,

                Order.id
                == OrderItem.order_id

            )

            .filter(

                Order.customer_id
                == current_user.id,

                Order.restaurant_id
                == restaurant.id

            )

            .group_by(
                OrderItem.item_name
            )

            .all()

        )


        reorder_map = {

            normalize_name(name):
                count

            for name, count
            in raw

        }


    # ========================================================
    # PROCESS ITEMS
    # ========================================================

    items = []


    for item in menu_items:

        # IMPORTANT:
        # copy JSON instead of modifying DB JSON directly
        data = dict(
            item.extra_data
            or {}
        )


        # ====================================================
        # BASIC DATA
        # ====================================================

        data["id"] = (
            item.id
        )

        data["name"] = (
            item.name
        )

        data["description"] = (
            item.description
            or ""
        )

        data["price"] = (
            item.price
            or 0
        )

        data["category"] = (
            item.category
            or "Other"
        )

        data["image_url"] = (
            item.image_url
            or ""
        )

        data["availability"] = (
            item.availability
        )

        data["item_type"] = (
            item.item_type
            or ""
        )


        # ====================================================
        # WEIGHT PRICES
        # ====================================================

        data["weight_prices"] = (

            data.get(
                "weight_prices",
                ""
            )
            or ""

        )


        # ====================================================
        # REORDER COUNT
        # ====================================================

        data["reorder_count"] = (

            reorder_map.get(

                normalize_name(
                    item.name
                ),

                0

            )

        )


        items.append(
            data
        )


    # ========================================================
    # GROUP BY CATEGORY
    # ========================================================

    menu_by_category = {}


    for item in items:

        category = (

            item.get(
                "category"
            )
            or "Other"

        )


        menu_by_category.setdefault(
            category,
            []
        ).append(
            item
        )


    # ========================================================
    # DEBUG
    # ========================================================

    print(
        "BAKERY CATEGORIES:",
        list(
            menu_by_category.keys()
        )
    )


    # ========================================================
    # RENDER
    # ========================================================

    return render_template(

        "bakery_menu.html",

        restaurant=
            restaurant,

        menu_by_category=
            menu_by_category

    )

from sqlalchemy import event, inspect

@event.listens_for(Restaurant, "before_update")
def protect_bakery(mapper, connection, target):
    state = inspect(target)
    if state.attrs.category_type.history.has_changes():
        old = state.attrs.category_type.history.deleted
        if old and old[0] == "bakery":
            target.category_type = "bakery"

@app.route("/api/restaurants/<int:restaurant_id>/menu")
def api_restaurant_menu(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)

    items = MenuItem.query.filter_by(
        restaurant_id=restaurant.id
    ).all()

    return jsonify({
        "restaurant": {
            "id": restaurant.id,
            "name": restaurant.name,
            "location": restaurant.location,
            "delivery_charge": restaurant.delivery_charge,
            "free_delivery_limit": restaurant.free_delivery_limit,
        },

        "items": [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "price": item.price,

                "weight_prices": getattr(
                    item,
                    "weight_prices",
                    None
                ),

                "availability": item.availability,

                "description": getattr(
                    item,
                    "description",
                    None
                ),

                "image_url": getattr(
                    item,
                    "image_url",
                    None
                ),

                "item_type": getattr(
                    item,
                    "item_type",
                    None
                ),
            }
            for item in items
        ]
    })           
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

@app.route('/generate_qr/<int:order_id>')
def generate_qr(order_id):
    order = Order.query.get(order_id)

    upi_id = "96738250@ybl"
    name = "RucHiGo"
    amount = order.final_total

    note = f"Order #{order.id}"

    upi_link = f"upi://pay?pa={upi_id}&pn={name}&am={amount}&tn={note}&cu=INR"

    qr = qrcode.make(upi_link)

    img_io = io.BytesIO()
    qr.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')
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
def send_order_push_to_customer(order, title, body):

    try:

        # ====================================================
        # NORMALIZE CUSTOMER PHONE
        # ====================================================

        phone = "".join(
            ch
            for ch in str(order.phone or "")
            if ch.isdigit()
        )

        if len(phone) > 10:
            phone = phone[-10:]

        if len(phone) != 10:
            print(
                "⚠️ Invalid order phone:",
                order.phone
            )
            return False


        # ====================================================
        # FIND CUSTOMER
        # ====================================================

        customer = (
            Customer.query
            .filter(
                db.or_(
                    Customer.mobile == phone,
                    Customer.mobile == "+91" + phone
                )
            )
            .first()
        )


        if not customer:

            print(
                "⚠️ Customer not found for:",
                phone
            )

            return False


        print(
            "👤 Push customer:",
            customer.id,
            customer.mobile
        )


        # ====================================================
        # FIND CUSTOMER DEVICES
        # ====================================================

        devices = (
            FCMToken.query
            .filter_by(
                user_id=customer.id
            )
            .all()
        )


        if not devices:

            print(
                "⚠️ No FCM token for customer:",
                customer.id
            )

            return False


        # ====================================================
        # SEND NOTIFICATION
        # ====================================================

        sent = 0


        for device in devices:

            if not device.token:
                continue


            response = send_push_notification(

                title=title,

                body=body,

                target_type="token",

                target_value=device.token,

                data={
                    # Notification category
                    "type": "order_update",

                    # IMPORTANT:
                    # Flutter OrderDetailsScreen uses DB integer ID.
                    "order_db_id": str(order.id),

                    # Public order number shown to customer
                    "order_id": str(order.order_id),

                    # Current status
                    "status": str(
                        order.status or ""
                    ),

                    # Flutter navigation instruction
                    "route": "order_details",
                }
            )


            if response:

                sent += 1

            else:

                print(
                    "🗑️ Removing invalid FCM token:",
                    device.id
                )

                db.session.delete(
                    device
                )


        # ====================================================
        # SAVE INVALID TOKEN CLEANUP
        # ====================================================

        db.session.commit()


        print(
            f"🔔 Order push sent to "
            f"{sent}/{len(devices)} device(s) "
            f"for customer {customer.id}"
        )


        return sent > 0


    except Exception as e:

        print(
            "❌ Order notification error:",
            e
        )

        db.session.rollback()

        return False
from flask import send_from_directory

@app.route('/firebase-messaging-sw.js')
def firebase_sw():
    return send_from_directory('static', 'firebase-messaging-sw.js')

from firebase_admin import messaging 
from firebase_admin import messaging


def send_push_notification(
    title,
    body,
    target_type="topic",
    target_value="all_users",
    data=None
):

    # ========================================================
    # PREPARE DATA
    # ========================================================

    raw_data = data or {}

    # FCM data values MUST be strings
    safe_data = {
        str(key): str(value)
        for key, value in raw_data.items()
        if value is not None
    }


    # ========================================================
    # CHECK IF THIS IS DELIVERY NEW ORDER
    # ========================================================

    is_delivery_new_order = (

        target_type == "token"

        and safe_data.get("type")
        == "new_order"

    )


    # ========================================================
    # DELIVERY NEW ORDER
    # DATA-ONLY + HIGH PRIORITY
    # ========================================================

    if is_delivery_new_order:

        print(
            "========================================"
        )

        print(
            "🚚 SENDING DELIVERY DATA-ONLY PUSH"
        )

        print(
            "ORDER ID:",
            safe_data.get("order_id")
        )

        print(
            "TARGET TOKEN:",
            str(target_value)[:20] + "..."
            if target_value
            else "NONE"
        )

        print(
            "========================================"
        )


        message = messaging.Message(

            # IMPORTANT:
            # NO notification=messaging.Notification(...)
            #
            # Flutter delivery app will handle this itself.

            data=safe_data,

            android=messaging.AndroidConfig(

                # Important for urgent delivery assignment
                priority="high"

            ),

            token=target_value

        )


    # ========================================================
    # NORMAL RUCHIGO NOTIFICATIONS
    # ========================================================

    else:

        message_kwargs = {

            "notification":
                messaging.Notification(
                    title=title,
                    body=body
                ),

            "data":
                safe_data,

            "android":
                messaging.AndroidConfig(
                    priority="high"
                )

        }


        # ====================================================
        # TARGET
        # ====================================================

        if target_type == "topic":

            message_kwargs["topic"] = (
                target_value
            )


        elif target_type == "token":

            message_kwargs["token"] = (
                target_value
            )


        else:

            print(
                "FCM ERROR: Invalid target type:",
                target_type
            )

            return None


        message = messaging.Message(
            **message_kwargs
        )


    # ========================================================
    # VALIDATE DELIVERY TARGET
    # ========================================================

    if (
        is_delivery_new_order
        and not target_value
    ):

        print(
            "FCM ERROR: Delivery token missing"
        )

        return None


    # ========================================================
    # SEND
    # ========================================================

    try:

        response = messaging.send(
            message
        )


        if is_delivery_new_order:

            print(
                "✅ DELIVERY DATA PUSH SENT:",
                response
            )

        else:

            print(
                "FCM Response:",
                response
            )


        return response


    except Exception as e:

        print(
            "FCM ERROR:",
            e
        )

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

    # ========================================================
    # LOGIN CHECK
    # ========================================================

    if not session.get("employee_id"):

        return redirect(
            url_for("employee_login")
        )


    emp = Employee.query.get(
        session.get("employee_id")
    )


    # ========================================================
    # FORCE LOGOUT CHECK
    # ========================================================

    if (
        not emp
        or not emp.is_logged_in
    ):

        session.clear()

        return redirect(
            url_for("employee_login")
        )


    # ========================================================
    # DATES
    # ========================================================

    today = datetime.utcnow().date()

    yesterday = (
        today - timedelta(days=1)
    )


    # ========================================================
    # ALLOWED ORDER STATUSES
    # ========================================================

    allowed_statuses = [

        "Pending",
        "Accepted",
        "Preparing",
        "Ready",
        "Out for Delivery",
        "Started",
        "Delivered",
        "Cancelled"

    ]


    # ========================================================
    # FETCH ORDERS
    # ========================================================

    orders = (

        Order.query

        .filter(
            Order.status.in_(
                allowed_statuses
            )
        )

        .options(

            db.joinedload(
                Order.restaurant
            ),

            db.joinedload(
                Order.items
            ),

            db.joinedload(
                Order.delivery_person
            )

        )

        .order_by(
            Order.created_at.desc()
        )

        .all()

    )


    # ========================================================
    # DAY CLASSIFICATION
    # ========================================================

    for o in orders:

        if (
            o.created_at
            and o.created_at.date()
            == today
        ):

            o.day_category = (
                "Today"
            )


        elif (
            o.created_at
            and o.created_at.date()
            == yesterday
        ):

            o.day_category = (
                "Yesterday"
            )


        else:

            o.day_category = (
                "Older"
            )


    # ========================================================
    # TODAY ORDERS
    # ========================================================

    today_orders = [

        o

        for o in orders

        if (
            o.created_at
            and o.created_at.date()
            == today
        )

    ]


    delivered_orders = [

        o

        for o in today_orders

        if o.status
        == "Delivered"

    ]


    # ========================================================
    # ACTIVE STATUSES
    # ========================================================

    active_statuses = [

        "Accepted",
        "Preparing",
        "Ready",
        "Out for Delivery",
        "Started"

    ]


    # ========================================================
    # STATS
    # ========================================================

    stats = {

        "today_orders":

            len(
                today_orders
            ),


        "today_delivered":

            len(
                delivered_orders
            ),


        "today_cancelled":

            len([

                o

                for o in today_orders

                if o.status
                == "Cancelled"

            ]),


        "today_pending":

            len([

                o

                for o in today_orders

                if o.status
                == "Pending"

            ]),


        "today_active":

            len([

                o

                for o in today_orders

                if o.status
                in active_statuses

            ]),


        # Delivered revenue only
        "today_revenue":

            sum(

                o.final_total or 0

                for o
                in delivered_orders

            ),


        # Delivered delivery charges only
        "today_delivery_charges":

            sum(

                o.delivery_charge or 0

                for o
                in delivered_orders

            ),


        # Delivered items only
        "today_items":

            sum(

                sum(

                    item.quantity

                    for item
                    in o.items

                )

                for o
                in delivered_orders

            )

    }


    # ========================================================
    # RESTAURANTS
    # ========================================================

    restaurants = (
        Restaurant.query.all()
    )


    # ========================================================
    # DELIVERY PERSONS
    # ========================================================

    delivery_persons = (

        DeliveryPerson.query

        .order_by(
            DeliveryPerson.name
        )

        .all()

    )


    # ========================================================
    # RENDER
    # ========================================================

    return render_template(

        "employee_dashboard.html",

        orders=
            orders,

        delivery_persons=
            delivery_persons,

        stats=
            stats,

        restaurants=
            restaurants,

        employee=
            emp,

        timedelta=
            timedelta

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

# ============================================================
# EMPLOYEE UPDATE ORDER STATUS
# ============================================================

@app.route(
    "/employee/update-status/<int:order_id>",
    methods=["POST"]
)
def employee_update_status(order_id):

    # ========================================================
    # LOGIN CHECK
    # ========================================================

    if not session.get("employee_id"):

        return jsonify({
            "success": False,
            "error": "Not logged in"
        }), 401


    # ========================================================
    # GET ORDER
    # ========================================================

    order = Order.query.get_or_404(
        order_id
    )


    # ========================================================
    # LOCK FINAL STATUS
    # ========================================================

    if order.status in [
        "Delivered",
        "Cancelled"
    ]:

        return jsonify({
            "success": False,
            "error": "Order locked"
        })


    # ========================================================
    # NEW STATUS
    # ========================================================

    new_status = request.form.get(
        "status"
    )


    if not new_status:

        return jsonify({
            "success": False,
            "error": "No status provided"
        })


    # ========================================================
    # UPDATE
    # ========================================================

    order.status = (
        new_status
    )


    db.session.commit()


    # ========================================================
    # REAL-TIME UPDATE TO CUSTOMER
    # ========================================================

    socketio.emit(

        "order_status_update",

        {
            "order_id":
                order.id,

            "public_order_id":
                order.order_id,

            "status":
                order.status
        },

        room=f"order_{order.id}"

    )


    print(
        f"📤 Employee emitted: "
        f"order_{order.id} -> {order.status}"
    )


    # ========================================================
    # RESPONSE
    # ========================================================

    return jsonify({

        "success": True,

        "new_status":
            order.status

    }) 
# ============================================================
# EMPLOYEE ASSIGN DELIVERY PERSON
# ============================================================

@app.route(
    "/employee/assign-delivery/<int:order_id>",
    methods=["POST"]
)
def employee_assign_delivery(order_id):

    # ========================================================
    # LOGIN CHECK
    # ========================================================

    if not session.get("employee_id"):

        return jsonify({
            "success": False,
            "error": "Not logged in"
        }), 401


    # ========================================================
    # GET ORDER
    # ========================================================

    order = Order.query.get_or_404(
        order_id
    )


    # ========================================================
    # LOCK FINAL STATUS
    # ========================================================

    if order.status in [
        "Delivered",
        "Cancelled"
    ]:

        return jsonify({
            "success": False,
            "error": "Order locked"
        })


    # ========================================================
    # DELIVERY PERSON
    # ========================================================

    dp_id = request.form.get(
        "delivery_person_id"
    )


    if not dp_id:

        return jsonify({
            "success": False,
            "error": "No delivery person selected"
        })


    dp = DeliveryPerson.query.get(
        dp_id
    )


    if not dp:

        return jsonify({
            "success": False,
            "error": "Invalid delivery person"
        })


    # ========================================================
    # ASSIGN DELIVERY
    # ========================================================

    order.delivery_person_id = (
        dp.id
    )

    order.delivery_boy_name = (
        dp.name
    )

    order.delivery_boy_phone = (
        dp.phone
    )


    # ========================================================
    # AUTO STATUS CHANGE
    # ========================================================

    order.status = (
        "Out for Delivery"
    )


    # ========================================================
    # SAVE FIRST
    # ========================================================

    db.session.commit()


    # ========================================================
    # FIREBASE PUSH TO DELIVERY PERSON
    # ========================================================

    if dp.fcm_token:

        try:

            send_push_notification(

                title=
                    "🚴 New Delivery Assigned",

                body=(
                    f"Order #{order.order_id} "
                    f"from {order.restaurant.name}"
                ),

                target_type=
                    "token",

                target_value=
                    dp.fcm_token,

                data={

                    "type":
                        "new_order",

                    "order_id":
                        str(order.id),

                    "order_number":
                        order.order_id or "",

                    "restaurant":
                        order.restaurant.name or ""

                }

            )


        except Exception as e:

            print(
                "EMPLOYEE DELIVERY PUSH ERROR:",
                e
            )


    # ========================================================
    # LIVE UPDATE TO DELIVERY PERSON DASHBOARD
    # ========================================================

    socketio.emit(

        "new_order_assigned",

        {

            "order_id":
                order.id,

            "order_number":
                order.order_id,

            "restaurant":
                order.restaurant.name

        },

        room=f"delivery_{dp.id}"

    )


    # ========================================================
    # LIVE UPDATE TO CUSTOMER TRACKING PAGE
    # ========================================================

    socketio.emit(

        "delivery_assigned",

        {

            "order_id":
                order.id,

            "public_order_id":
                order.order_id,

            "delivery_person_name":
                dp.name,

            "delivery_person_phone":
                dp.phone,

            "status":
                order.status

        },

        room=f"order_{order.id}"

    )


    # ========================================================
    # RESPONSE
    # ========================================================

    return jsonify({

        "success": True,

        "delivery_person_name":
            dp.name,

        "new_status":
            order.status

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


@app.route("/employee/latest-orders")
def latest_orders():
    orders = Order.query.order_by(Order.id.desc()).limit(1).all()

    return jsonify({
        "orders": [{
            "id": o.id,
            "order_id": o.order_id,
            "customer_name": o.customer_name,
            "phone": o.phone,
            "restaurant": o.restaurant.name,
            "total": o.final_total,
            "delivery_charge": o.delivery_charge or 0,
            "status": o.status,
            "created_at": o.created_at.strftime('%d-%m-%Y %I:%M %p')
        } for o in orders]
    })
@app.route("/get-stores")
def get_stores():

    category = request.args.get("type", "").strip().lower()
    location = request.args.get("location", "").strip()

    print("API HIT → category:", category)
    print("API HIT → location:", location)

    # ✅ validate category
    allowed = ["restaurant", "bakery", "grocery", "pharmacy", "meat"]
    if category not in allowed:
        return jsonify([])

    query = Restaurant.query.filter(Restaurant.category_type == category)

    # ✅ FILTER LOCATION
    if location:
        query = query.filter(Restaurant.location == location)

    stores = query.all()

    print("RESULT COUNT:", len(stores))

    return jsonify([
        {
            "id": s.id,
            "name": s.name,
            "category": s.category_type,
            "location": s.location
        }
        for s in stores
    ])
import requests
import csv
from io import StringIO

def fetch_grocery_items(sheet_url):
    items = []

    try:
        res = requests.get(sheet_url)
        res.raise_for_status()

        csv_data = StringIO(res.text)
        reader = csv.DictReader(csv_data)

        for row in reader:
            # ✅ SAFE FLOAT PARSE
            def to_float(val):
                try:
                    return float(val)
                except:
                    return 0

            items.append({
                "name": row.get("name", "").strip(),
                "category": row.get("category", "Others").strip(),

                "price": to_float(row.get("price")),
                "mrp": to_float(row.get("mrp")),

                "unit": row.get("unit", "").strip(),
                "image": row.get("image", "").strip(),

                # ✅ IMPORTANT FOR YOUR UI
                "weight_options": row.get("weight_options", "").strip(),

                # ✅ STOCK FIX
                "in_stock": str(row.get("in_stock", "yes")).lower() in ["yes", "true", "1"]
            })

    except Exception as e:
        print("SHEET ERROR:", e)

    return items  
def import_grocery_sheet_to_db(store_id):

    store = Restaurant.query.get_or_404(store_id)

    if store.category_type != "grocery":
        return {
            "success": False,
            "message": "This is not a grocery store"
        }

    if not store.sheet_url:
        return {
            "success": False,
            "message": "No Google Sheet URL configured"
        }

    sheet_items = fetch_grocery_items(
        store.sheet_url
    )

    added = 0
    updated = 0
    skipped = 0
    disabled = 0

    try:

        # =================================================
        # ALL CURRENT DB GROCERY ITEMS
        # =================================================

        db_items = (
            MenuItem.query
            .filter_by(
                restaurant_id=store.id,
                item_type="grocery"
            )
            .all()
        )

        # Case-insensitive name map
        db_by_name = {
            (item.name or "").strip().lower(): item
            for item in db_items
            if (item.name or "").strip()
        }

        sheet_item_names = set()


        # =================================================
        # ADD / UPDATE SHEET ITEMS
        # =================================================

        for row in sheet_items:

            name = (
                row.get("name")
                or ""
            ).strip()

            if not name:
                skipped += 1
                continue

            normalized_name = name.lower()

            sheet_item_names.add(
                normalized_name
            )

            category = (
                row.get("category")
                or "Others"
            ).strip()

            item = db_by_name.get(
                normalized_name
            )

            extra_data = {
                "weight_options":
                    row.get(
                        "weight_options",
                        ""
                    )
            }


            # =============================================
            # UPDATE EXISTING
            # =============================================

            if item:

                item.name = name

                item.category = category

                item.price = (
                    row.get("price")
                    or 0
                )

                item.mrp = (
                    row.get("mrp")
                    or 0
                )

                item.unit = (
                    row.get("unit")
                    or ""
                )

                item.image_url = (
                    row.get("image")
                    or ""
                )

                item.availability = (
                    "yes"
                    if row.get("in_stock")
                    else "no"
                )

                item.extra_data = (
                    extra_data
                )

                updated += 1


            # =============================================
            # ADD NEW
            # =============================================

            else:

                item = MenuItem(

                    restaurant_id=
                        store.id,

                    name=
                        name,

                    description=
                        "",

                    category=
                        category,

                    price=(
                        row.get("price")
                        or 0
                    ),

                    mrp=(
                        row.get("mrp")
                        or 0
                    ),

                    unit=(
                        row.get("unit")
                        or ""
                    ),

                    image_url=(
                        row.get("image")
                        or ""
                    ),

                    availability=(
                        "yes"
                        if row.get("in_stock")
                        else "no"
                    ),

                    item_type=
                        "grocery",

                    extra_data=
                        extra_data
                )

                db.session.add(item)

                db_by_name[
                    normalized_name
                ] = item

                added += 1


        # =================================================
        # DISABLE ITEMS REMOVED FROM SHEET
        # =================================================

        for db_item in db_items:

            db_name = (
                db_item.name
                or ""
            ).strip().lower()

            if (
                db_name
                and
                db_name not in sheet_item_names
            ):

                if db_item.availability != "no":

                    db_item.availability = "no"

                    disabled += 1


        # =================================================
        # SAVE
        # =================================================

        db.session.commit()


        return {

            "success": True,

            "total_sheet_items":
                len(sheet_items),

            "added":
                added,

            "updated":
                updated,

            "disabled":
                disabled,

            "skipped":
                skipped
        }


    except Exception as e:

        db.session.rollback()

        print(
            "GROCERY IMPORT ERROR:",
            e
        )

        return {
            "success": False,
            "message": str(e)
        }
from collections import defaultdict
from collections import defaultdict

from collections import defaultdict

@app.route("/grocery/<int:store_id>")
def grocery_store(store_id):

    store = Restaurant.query.get_or_404(store_id)

    # =====================================================
    # CHECK GROCERY STORE
    # =====================================================

    if store.category_type != "grocery":
        return "Invalid store", 404


    # =====================================================
    # SELECTED CATEGORY
    # Example:
    # /grocery/41?category=Cooking Oils
    # =====================================================

    selected_category = (
        request.args.get("category", "")
        .strip()
    )


    # =====================================================
    # LOAD ONLY AVAILABLE GROCERY ITEMS
    # =====================================================

    items = (
        MenuItem.query
        .filter(
            MenuItem.restaurant_id == store.id,
            MenuItem.item_type == "grocery",
            MenuItem.availability == "yes"
        )
        .order_by(
            MenuItem.category.asc(),
            MenuItem.name.asc()
        )
        .all()
    )


    # =====================================================
    # GROUP ITEMS BY CATEGORY
    # =====================================================

    menu_by_category = defaultdict(list)


    for item in items:

        category = (
            item.category
            or "Others"
        ).strip()


        # Extra JSON data
        extra_data = dict(
            item.extra_data or {}
        )


        # =================================================
        # PREPARE ITEM FOR TEMPLATE
        # =================================================

        menu_by_category[category].append({

            "id":
                item.id,

            "name":
                item.name,

            "category":
                category,

            "price":
                float(
                    item.price or 0
                ),

            "mrp":
                float(
                    item.mrp or 0
                ),

            "unit":
                item.unit or "",

            "image":
                item.image_url or "",

            # IMPORTANT
            # Used by:
            # {% if item.availability == "yes" %}
            "availability":
                item.availability,

            # Also keep this for old template code
            "in_stock":
                item.availability == "yes",

            "weight_options":
                extra_data.get(
                    "weight_options",
                    ""
                )
        })


    # =====================================================
    # RENDER
    # =====================================================

    return render_template(
        "grocery_menu.html",

        restaurant=store,

        menu_by_category=
            menu_by_category,

        selected_category=
            selected_category
    )
from flask import request

@app.before_request
def skip_static_and_api():
    if request.path.startswith('/static/'):
        return  # ✅ allow images, css, js

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

def reconcile_razorpay_payment(order):

    if not order:
        return False

    if order.payment_status == "Paid":
        return True

    if not order.payment_order_id:
        return False

    try:

        payments = razorpay_client.order.payments(
            order.payment_order_id
        )

        for payment in payments.get("items", []):

            print(
                "RAZORPAY CHECK:",
                order.order_id,
                payment.get("id"),
                payment.get("status")
            )

            if payment.get("status") == "captured":

                order.payment_status = "Paid"
                order.payment_verified = True
                order.payment_type = "Online"

                order.payment_id = payment.get("id")

                order.payment_method_used = (
                    payment.get("method", "")
                    .upper()
                )

                order.payment_source = "RazorpayReconcile"

                order.payment_time = datetime.utcnow()

                acquirer_data = payment.get(
                    "acquirer_data",
                    {}
                )

                order.transaction_reference = (
                    acquirer_data.get("upi_transaction_id")
                    or acquirer_data.get("rrn")
                    or acquirer_data.get(
                        "bank_transaction_id"
                    )
                )

                # Payment succeeded.
                # Don't leave active order as Pending Payment.
                if order.status == "Pending Payment":
                    order.status = "Pending"

                db.session.commit()

                print(
                    "✅ PAYMENT RECOVERED:",
                    order.order_id,
                    payment.get("id")
                )

                return True

    except Exception as e:

        db.session.rollback()

        print(
            "❌ RAZORPAY RECONCILE ERROR:",
            repr(e)
        )

    return False
@app.route("/payment/<int:order_id>")
def payment_page(order_id):

    order = Order.query.get_or_404(order_id)

    # ==========================================
    # ALREADY PAID
    # ==========================================

    if order.payment_status == "Paid":

        return redirect(
            url_for(
                "order_placed",
                order_id=order.order_id
            )
        )


    # ==========================================
    # IMPORTANT:
    # DB says Pending → ask Razorpay directly
    # ==========================================

    if order.payment_order_id:

        payment_found = reconcile_razorpay_payment(
            order
        )

        if payment_found:

            return redirect(
                url_for(
                    "order_placed",
                    order_id=order.order_id
                )
            )


    # ==========================================
    # CANCELLED
    # ==========================================

    if order.status == "Cancelled":

        flash(
            "Payment session expired. Please place your order again.",
            "warning"
        )

        return render_template(
            "payment_expired.html",
            order=order
        )


    expires_at = (
        order.created_at
        + timedelta(minutes=15)
    )


    return render_template(
        "payment.html",
        order=order,
        razorpay_key=RAZORPAY_KEY_ID,
        expires_at=expires_at
    )
@app.route(
    "/sync_payment/<int:order_id>",
    methods=["POST"]
)
def sync_payment(order_id):

    order = Order.query.get_or_404(order_id)


    # ============================================================
    # ALREADY PAID
    # ============================================================

    if order.payment_status == "Paid":

        return jsonify({

            "paid": True,

            "redirect_url": url_for(
                "order_placed",
                order_id=order.order_id
            )

        })


    # ============================================================
    # NO RAZORPAY ORDER ID YET
    # ============================================================

    if not order.payment_order_id:

        return jsonify({

            "paid": False

        })


    try:

        # ========================================================
        # ASK RAZORPAY DIRECTLY
        # ========================================================

        payments = razorpay_client.order.payments(
            order.payment_order_id
        )


        print(
            "Razorpay payment sync:",
            order.order_id,
            order.payment_order_id
        )


        # ========================================================
        # CHECK ALL PAYMENTS UNDER THIS RAZORPAY ORDER
        # ========================================================

        for payment in payments.get("items", []):

            print(
                "Razorpay payment:",
                payment.get("id"),
                payment.get("status")
            )


            if payment.get("status") == "captured":

                # =================================================
                # PAYMENT CONFIRMED
                # =================================================

                order.payment_status = "Paid"

                order.payment_verified = True

                order.payment_type = "Online"

                order.payment_id = payment.get("id")

                order.payment_order_id = (
                    payment.get("order_id")
                    or order.payment_order_id
                )

                order.payment_method_used = (
                    payment.get(
                        "method",
                        ""
                    ).upper()
                )

                order.payment_source = (
                    "RazorpaySync"
                )

                order.payment_time = (
                    datetime.utcnow()
                )


                # =================================================
                # UPI / BANK TRANSACTION REFERENCE
                # =================================================

                acquirer_data = payment.get(
                    "acquirer_data",
                    {}
                )


                order.transaction_reference = (

                    acquirer_data.get(
                        "upi_transaction_id"
                    )

                    or

                    acquirer_data.get(
                        "rrn"
                    )

                    or

                    acquirer_data.get(
                        "bank_transaction_id"
                    )

                )


                db.session.commit()


                print(
                    "✅ PAYMENT RECOVERED:",
                    order.order_id,
                    payment.get("id")
                )


                return jsonify({

                    "paid": True,

                    "redirect_url": url_for(
                        "order_placed",
                        order_id=order.order_id
                    )

                })


        # ========================================================
        # NO CAPTURED PAYMENT FOUND
        # ========================================================

        return jsonify({

            "paid": False

        })


    except Exception as e:

        db.session.rollback()


        print(
            "❌ Razorpay sync error:",
            str(e)
        )


        return jsonify({

            "paid": False,

            "message":
                "Unable to verify payment right now"

        }), 500
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


def sync_razorpay_payment(order):

    # No Razorpay order created
    if not order.payment_order_id:
        return False

    try:
        payments = razorpay_client.order.payments(
            order.payment_order_id
        )

        for payment in payments.get("items", []):

            if payment.get("status") == "captured":

                order.payment_status = "Paid"
                order.payment_verified = True
                order.payment_type = "Online"

                order.payment_id = payment.get("id")

                order.payment_method_used = (
                    payment.get("method", "")
                    .upper()
                )

                order.payment_source = "RazorpaySync"

                order.payment_time = datetime.utcnow()

                acquirer_data = payment.get(
                    "acquirer_data",
                    {}
                )

                order.transaction_reference = (
                    acquirer_data.get("upi_transaction_id")
                    or acquirer_data.get("rrn")
                    or acquirer_data.get(
                        "bank_transaction_id"
                    )
                )

                db.session.commit()

                print(
                    "✅ Razorpay payment synced:",
                    order.order_id,
                    payment.get("id")
                )

                return True

    except Exception as e:

        db.session.rollback()

        print(
            "❌ Razorpay payment sync error:",
            e
        )

    return False
import hmac
import hashlib
import json
from flask import request, jsonify


@app.route("/razorpay_webhook", methods=["POST"])
def razorpay_webhook():

    print("\n")
    print("=" * 70)
    print("🔥🔥🔥 RAZORPAY WEBHOOK HIT 🔥🔥🔥")
    print("=" * 70)

    # ============================================================
    # STEP 1 — REQUEST INFORMATION
    # ============================================================

    print("STEP 1: Webhook request received")
    print("Method:", request.method)
    print("Content-Type:", request.content_type)

    webhook_signature = request.headers.get(
        "X-Razorpay-Signature"
    )

    print(
        "X-Razorpay-Signature:",
        webhook_signature
    )

    body = request.data

    print("Raw body length:", len(body))

    # Don't print full body forever in production.
    # Useful temporarily for debugging.
    print(
        "Raw body:",
        body.decode(
            "utf-8",
            errors="ignore"
        )
    )


    # ============================================================
    # STEP 2 — CHECK WEBHOOK SECRET
    # ============================================================

    print("\nSTEP 2: Checking webhook secret")

    print(
        "RAZORPAY_WEBHOOK_SECRET exists:",
        bool(RAZORPAY_WEBHOOK_SECRET)
    )

    if not RAZORPAY_WEBHOOK_SECRET:

        print(
            "❌ STOP: RAZORPAY_WEBHOOK_SECRET IS EMPTY/NONE"
        )

        return jsonify({
            "success": False,
            "error": "Webhook secret missing"
        }), 500


    # ============================================================
    # STEP 3 — VERIFY SIGNATURE
    # ============================================================

    print("\nSTEP 3: Verifying webhook signature")

    generated_signature = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()

    print(
        "Generated signature:",
        generated_signature
    )

    print(
        "Received signature:",
        webhook_signature
    )


    if not hmac.compare_digest(
        generated_signature,
        webhook_signature or ""
    ):

        print("❌❌❌ INVALID WEBHOOK SIGNATURE")
        print("=" * 70)

        return jsonify({
            "success": False,
            "error": "Invalid webhook signature"
        }), 400


    print("✅ WEBHOOK SIGNATURE VALID")


    # ============================================================
    # STEP 4 — PARSE JSON
    # ============================================================

    print("\nSTEP 4: Parsing webhook JSON")

    try:

        payload = json.loads(body)

        print("✅ JSON parsed successfully")

    except Exception as e:

        print("❌ JSON PARSE FAILED")
        print("Error:", repr(e))

        return jsonify({
            "success": False
        }), 400


    event = payload.get("event")

    print("\n🔥 WEBHOOK EVENT:", event)


    # ============================================================
    # STEP 5 — NORMAL CHECKOUT SUCCESS
    # ============================================================

    if event in [
        "payment.captured",
        "order.paid"
    ]:

        print("\n")
        print("=" * 70)
        print("💰 PAYMENT SUCCESS EVENT RECEIVED")
        print("=" * 70)

        print("Event:", event)


        payment_data = (
            payload
            .get("payload", {})
            .get("payment", {})
            .get("entity", {})
        )


        print(
            "Payment entity exists:",
            bool(payment_data)
        )

        print(
            "Payment entity:",
            payment_data
        )


        # ========================================================
        # STEP 6 — GET RAZORPAY IDS
        # ========================================================

        print("\nSTEP 6: Reading Razorpay IDs")


        razorpay_order_id = payment_data.get(
            "order_id"
        )

        razorpay_payment_id = payment_data.get(
            "id"
        )


        print(
            "Razorpay Order ID:",
            razorpay_order_id
        )

        print(
            "Razorpay Payment ID:",
            razorpay_payment_id
        )

        print(
            "Razorpay Payment Status:",
            payment_data.get("status")
        )

        print(
            "Captured:",
            payment_data.get("captured")
        )

        print(
            "Payment Method:",
            payment_data.get("method")
        )

        print(
            "Amount:",
            payment_data.get("amount")
        )


        if not razorpay_order_id:

            print("❌ RAZORPAY ORDER ID MISSING")

            print(
                "Full payment_data:",
                payment_data
            )

            return jsonify({
                "success": True
            }), 200


        # ========================================================
        # STEP 7 — SEARCH DATABASE
        # ========================================================

        print("\nSTEP 7: Searching RucHiGo database")

        print(
            "Searching payment_order_id:",
            razorpay_order_id
        )


        try:

            order = Order.query.filter_by(
                payment_order_id=razorpay_order_id
            ).first()

        except Exception as e:

            print("❌ DATABASE QUERY FAILED")
            print("Error:", repr(e))

            db.session.rollback()

            return jsonify({
                "success": False
            }), 500


        print(
            "Database search result:",
            order
        )


        if not order:

            print("")
            print("❌❌❌ ORDER NOT FOUND")
            print(
                "Razorpay Order:",
                razorpay_order_id
            )

            print(
                "Possible problem: webhook and payment "
                "are using different database/environment."
            )

            print("=" * 70)

            return jsonify({
                "success": True
            }), 200


        # ========================================================
        # STEP 8 — PRINT CURRENT DATABASE VALUES
        # ========================================================

        print("\nSTEP 8: Current RucHiGo order")

        print("DB ID:", order.id)
        print("RucHiGo Order:", order.order_id)
        print("Order Status:", order.status)

        print(
            "Current Payment Status:",
            order.payment_status
        )

        print(
            "Current Payment Verified:",
            order.payment_verified
        )

        print(
            "Current Payment ID:",
            order.payment_id
        )

        print(
            "Current Payment Source:",
            order.payment_source
        )

        print(
            "DB Razorpay Order ID:",
            order.payment_order_id
        )


        # ========================================================
        # STEP 9 — ALREADY PAID?
        # ========================================================

        if order.payment_status == "Paid":

            print("")
            print("ℹ️ ORDER ALREADY PAID")
            print(
                "No database update required."
            )

            print("=" * 70)

            return jsonify({
                "success": True
            }), 200


        # ========================================================
        # STEP 10 — UPDATE PAYMENT
        # ========================================================

        print("\nSTEP 10: Updating payment to PAID")

        order.payment_status = "Paid"

        order.payment_verified = True

        order.payment_type = "Online"

        order.payment_id = (
            razorpay_payment_id
        )

        order.payment_order_id = (
            razorpay_order_id
        )

        order.payment_method_used = (
            payment_data.get(
                "method",
                ""
            ).upper()
        )

        order.payment_source = (
            "RazorpayWebhook"
        )

        order.payment_time = (
            datetime.utcnow()
        )


        acquirer_data = payment_data.get(
            "acquirer_data",
            {}
        )


        print(
            "Acquirer Data:",
            acquirer_data
        )


        order.transaction_reference = (

            acquirer_data.get(
                "upi_transaction_id"
            )

            or

            acquirer_data.get(
                "rrn"
            )

            or

            acquirer_data.get(
                "bank_transaction_id"
            )

        )


        print(
            "Transaction Reference:",
            order.transaction_reference
        )


        # ========================================================
        # STEP 11 — DATABASE COMMIT
        # ========================================================

        print("\nSTEP 11: Committing database")


        try:

            db.session.commit()

            print("✅ DATABASE COMMIT SUCCESSFUL")

        except Exception as e:

            print("")
            print("❌❌❌ DATABASE COMMIT FAILED")
            print("Error type:", type(e).__name__)
            print("Error:", repr(e))

            db.session.rollback()

            print("=" * 70)

            return jsonify({
                "success": False,
                "error": "Database commit failed"
            }), 500


        # ========================================================
        # STEP 12 — VERIFY DATABASE AFTER COMMIT
        # ========================================================

        print(
            "\nSTEP 12: Verifying database after commit"
        )


        try:

            db.session.refresh(order)

            print(
                "After commit Payment Status:",
                order.payment_status
            )

            print(
                "After commit Payment Verified:",
                order.payment_verified
            )

            print(
                "After commit Payment ID:",
                order.payment_id
            )

            print(
                "After commit Payment Source:",
                order.payment_source
            )

            print(
                "After commit Payment Method:",
                order.payment_method_used
            )

            print(
                "After commit Payment Time:",
                order.payment_time
            )

        except Exception as e:

            print(
                "⚠️ Could not refresh order:",
                repr(e)
            )


        print("")
        print("🎉🎉🎉 PAYMENT UPDATED SUCCESSFULLY")
        print(
            "RucHiGo Order:",
            order.order_id
        )

        print(
            "Razorpay Payment:",
            razorpay_payment_id
        )

        print("=" * 70)


        return jsonify({
            "success": True
        }), 200


    # ============================================================
    # PAYMENT FAILED
    # ============================================================

    elif event == "payment.failed":

        print("\n")
        print("=" * 70)
        print("❌ PAYMENT.FAILED EVENT RECEIVED")
        print("=" * 70)


        payment_data = (
            payload
            .get("payload", {})
            .get("payment", {})
            .get("entity", {})
        )


        razorpay_order_id = (
            payment_data.get("order_id")
        )

        razorpay_payment_id = (
            payment_data.get("id")
        )


        print(
            "Razorpay Order:",
            razorpay_order_id
        )

        print(
            "Razorpay Payment:",
            razorpay_payment_id
        )

        print(
            "Error Code:",
            payment_data.get("error_code")
        )

        print(
            "Error Description:",
            payment_data.get(
                "error_description"
            )
        )


        if razorpay_order_id:

            order = Order.query.filter_by(
                payment_order_id=razorpay_order_id
            ).first()


            print(
                "Database order:",
                order
            )


            if order:

                print(
                    "Current Payment Status:",
                    order.payment_status
                )


                # NEVER turn Paid back into Failed
                if order.payment_status != "Paid":

                    print(
                        "Updating payment to Failed"
                    )

                    order.payment_status = "Failed"


                    try:

                        db.session.commit()

                        print(
                            "✅ Failed status saved"
                        )

                    except Exception as e:

                        db.session.rollback()

                        print(
                            "❌ Failed status commit error:",
                            repr(e)
                        )

                        return jsonify({
                            "success": False
                        }), 500

                else:

                    print(
                        "⚠️ Ignoring payment.failed "
                        "because order is already Paid"
                    )


        print("=" * 70)

        return jsonify({
            "success": True
        }), 200


    # ============================================================
    # UNKNOWN / UNUSED EVENT
    # ============================================================

    else:

        print("")
        print("ℹ️ WEBHOOK EVENT NOT PROCESSED:", event)
        print("=" * 70)

        return jsonify({
            "success": True
        }), 200
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
    
from flask import request, jsonify

@app.route("/api/recommendations", methods=["POST"])
def api_recommendations():

    data = request.get_json()

    restaurant_id = int(data.get("restaurant_id"))
    cart = data.get("cart", [])

    recommendations = get_recommendations(
        cart,
        restaurant_id
    )

    result = []

    for item in recommendations:

        result.append({
            "id": item.id,
            "name": item.name,
            "price": float(item.price),
            "category": item.category,
            "image_url": item.image_url,
            "description": item.description
        })

    return jsonify(result)

@app.route("/api/get_cart", methods=["POST"])
def get_cart():

    data = request.get_json()
    restaurant_id = data.get("restaurant_id")

    cart = session.get("cart", [])

    return jsonify({
        "cart": cart
    })


@app.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()

        # Validation
        if not name:
            flash("Name cannot be empty.", "danger")
            return redirect(url_for("edit_profile"))

        # Check if email already belongs to another customer
        if email:
            existing = Customer.query.filter(
                Customer.email == email,
                Customer.id != current_user.id
            ).first()

            if existing:
                flash("Email already exists.", "danger")
                return redirect(url_for("edit_profile"))

        current_user.name = name
        current_user.email = email

        db.session.commit()

        flash("Profile updated successfully!", "success")
        return redirect(url_for("profile"))

    return render_template("edit_profile.html")



@app.route("/wallet")
@login_required
def wallet():

    logs = (
        CoinLedger.query
        .filter_by(customer_id=current_user.id)
        .order_by(CoinLedger.created_at.desc())
        .all()
    )

    badges = (
        RewardBadge.query
        .filter_by(active=True)
        .order_by(RewardBadge.required_coins)
        .all()
    )

    current_badge = current_user.badge

    next_badge = None

    for badge in badges:
        if badge.required_coins > current_user.coins:
            next_badge = badge
            break

    return render_template(
        "wallet.html",
        logs=logs,
        current_badge=current_badge,
        next_badge=next_badge
    )



@app.route("/order-details/<int:order_id>")
@login_required
def order_details(order_id):

    order = Order.query.filter_by(
        id=order_id,
        customer_id=current_user.id
    ).first_or_404()

    return render_template(
        "order_details.html",
        order=order
    )
@app.route("/order-history")
@login_required
def order_history():

    orders = (
        Order.query
        .filter_by(customer_id=current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )

    return render_template(
        "order_history.html",
        orders=orders
    )


@app.route("/delivery/save-fcm-token", methods=["POST"])
def save_delivery_fcm_token():

    if not session.get("delivery_logged_in"):
        return {"success": False}, 401

    dp = DeliveryPerson.query.get(session["delivery_person_id"])

    data = request.get_json()

    dp.fcm_token = data["token"]

    db.session.commit()

    return {"success": True}
import json

@app.route("/delivery/subscribe", methods=["POST"])
def delivery_subscribe():

    if not session.get("delivery_logged_in"):
        return jsonify({"success": False}), 401

    dp = DeliveryPerson.query.get(session["delivery_person_id"])

    if not dp:
        return jsonify({"success": False}), 404

    subscription = request.get_json()

    dp.push_subscription = json.dumps(subscription)

    db.session.commit()

    print("✅ Delivery subscription saved")

    return jsonify({"success": True})


@app.route("/admin/dashboard/today-performance")
def admin_today_performance():

    if not session.get("admin_logged_in"):
        return (
            '<div class="ajax-error">'
            'Session expired. Please login again.'
            '</div>',
            401
        )

    today = datetime.utcnow().date()

    today_start = datetime.combine(
        today,
        datetime.min.time()
    )

    tomorrow_start = (
        today_start + timedelta(days=1)
    )

    today_orders_query = Order.query.filter(
        Order.created_at >= today_start,
        Order.created_at < tomorrow_start
    )

    today_delivered_orders = (
        today_orders_query
        .filter(
            Order.status == "Delivered"
        )
        .all()
    )

    stats = {
        "today_orders": (
            today_orders_query.count()
        ),

        "today_delivered": (
            len(today_delivered_orders)
        ),

        "today_cancelled": (
            today_orders_query
            .filter(
                Order.status == "Cancelled"
            )
            .count()
        ),

        "today_active": (
            today_orders_query
            .filter(
                Order.status.in_(
                    [
                        "Preparing",
                        "Accepted",
                        "Assigned",
                        "Out for Delivery"
                    ]
                )
            )
            .count()
        ),

        "today_pending": (
            today_orders_query
            .filter(
                Order.status == "Pending"
            )
            .count()
        ),

        "today_revenue": sum(
            order.get_final_total()
            for order in today_delivered_orders
        ),

        "today_delivery_charges": sum(
            order.delivery_charge or 0
            for order in today_delivered_orders
        ),

        "today_items": sum(
            item.quantity
            for order in today_delivered_orders
            for item in order.items
        ) if today_delivered_orders else 0
    }

    restaurant_count = Restaurant.query.count()

    return render_template(
        "partials/admin_today_performance.html",
        stats=stats,
        restaurant_count=restaurant_count
    ) 

@app.route("/admin/dashboard/restaurant-performance")
def admin_restaurant_performance():

    if not session.get("admin_logged_in"):
        return (
            '<div class="ajax-error">'
            'Session expired. Please login again.'
            '</div>',
            401
        )

    today = datetime.utcnow().date()

    week_start = (
        today - timedelta(days=today.weekday())
    )

    today_start = datetime.combine(
        today,
        datetime.min.time()
    )

    tomorrow_start = (
        today_start + timedelta(days=1)
    )

    week_start_datetime = datetime.combine(
        week_start,
        datetime.min.time()
    )

    restaurants = (
        Restaurant.query
        .order_by(Restaurant.name.asc())
        .all()
    )

    restaurant_performance = []

    for restaurant in restaurants:

        restaurant_orders = (
            Order.query
            .filter(
                Order.restaurant_id == restaurant.id
            )
            .all()
        )

        today_delivered = [
            order
            for order in restaurant_orders
            if (
                order.created_at >= today_start
                and order.created_at < tomorrow_start
                and order.status == "Delivered"
            )
        ]

        weekly_delivered = [
            order
            for order in restaurant_orders
            if (
                order.created_at >= week_start_datetime
                and order.status == "Delivered"
            )
        ]

        restaurant_performance.append({
            "id": restaurant.id,

            "name": restaurant.name,

            "today_orders": len(
                today_delivered
            ),

            "today_earnings": sum(
                order.get_final_total()
                for order in today_delivered
            ),

            "weekly_orders": len(
                weekly_delivered
            ),

            "weekly_earnings": sum(
                order.get_final_total()
                for order in weekly_delivered
            ),

            "pending": len([
                order
                for order in restaurant_orders
                if order.status == "Pending"
            ]),

            "completed": len([
                order
                for order in restaurant_orders
                if order.status == "Delivered"
            ]),

            "is_best_seller": (
                restaurant.is_best_seller
            ),

            "is_fast_delivery": (
                restaurant.is_fast_delivery
            )
        })

    return render_template(
        "partials/admin_restaurant_performance.html",
        restaurant_stats=restaurant_performance
    )

@app.route("/admin/dashboard/orders/<order_group>")
def admin_orders_ajax(order_group):

    if not session.get("admin_logged_in"):
        return (
            '<div class="ajax-error">Session expired. Please log in again.</div>',
            401
        )

    allowed_groups = {
        "today",
        "yesterday",
        "older"
    }

    if order_group not in allowed_groups:
        return (
            '<div class="ajax-error">Invalid order group.</div>',
            400
        )

    page = request.args.get(
        "page",
        1,
        type=int
    )

    query = request.args.get(
        "query",
        "",
        type=str
    ).strip()

    status_filter = request.args.get(
        "status",
        "",
        type=str
    ).strip()

    date_filter = request.args.get(
        "date",
        "",
        type=str
    ).strip()

    per_page = 10

    today = datetime.utcnow().date()

    yesterday = (
        today - timedelta(days=1)
    )

    today_start = datetime.combine(
        today,
        datetime.min.time()
    )

    tomorrow_start = (
        today_start + timedelta(days=1)
    )

    yesterday_start = datetime.combine(
        yesterday,
        datetime.min.time()
    )

    orders_query = Order.query

    # =====================================================
    # SEARCH
    # =====================================================

    if query:

        search_value = f"%{query}%"

        orders_query = orders_query.filter(
            or_(
                Order.order_id.ilike(search_value),
                Order.customer_name.ilike(search_value),
                Order.phone.ilike(search_value),
                Order.email.ilike(search_value)
            )
        )

    # =====================================================
    # STATUS FILTER
    # =====================================================

    if status_filter:

        orders_query = orders_query.filter(
            Order.status == status_filter
        )

    # =====================================================
    # OPTIONAL SELECTED DATE
    # =====================================================

    if date_filter:

        try:

            selected_date = datetime.strptime(
                date_filter,
                "%Y-%m-%d"
            ).date()

            selected_start = datetime.combine(
                selected_date,
                datetime.min.time()
            )

            selected_end = (
                selected_start + timedelta(days=1)
            )

            orders_query = orders_query.filter(
                Order.created_at >= selected_start,
                Order.created_at < selected_end
            )

        except ValueError:
            date_filter = ""

    # =====================================================
    # GROUP FILTER
    # =====================================================

    if order_group == "today":

        orders_query = orders_query.filter(
            Order.created_at >= today_start,
            Order.created_at < tomorrow_start
        )

        section_title = "📅 Today Orders"

    elif order_group == "yesterday":

        orders_query = orders_query.filter(
            Order.created_at >= yesterday_start,
            Order.created_at < today_start
        )

        section_title = "🕒 Yesterday Orders"

    else:

        orders_query = orders_query.filter(
            Order.created_at < yesterday_start
        )

        section_title = "📦 Older Orders"

    # =====================================================
    # PAGINATION
    # =====================================================

    pagination = (
        orders_query
        .order_by(Order.created_at.desc())
        .paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
    )

    delivery_persons = (
        DeliveryPerson.query
        .order_by(DeliveryPerson.name.asc())
        .all()
    )

    return render_template(
        "partials/admin_orders_ajax_table.html",

        orders=pagination.items,
        pagination=pagination,

        order_group=order_group,
        section_title=section_title,

        delivery_persons=delivery_persons,

        query=query,
        status_filter=status_filter,
        date_filter=date_filter,

        make_whatsapp_link=make_whatsapp_link
    )

@app.route("/search")
def global_search_page():

    return render_template(
        "global_search.html"
    )

from flask import request, jsonify, url_for
from sqlalchemy import or_, func, case
@app.route("/api/global-menu-search")
def global_menu_search():

    # =========================================================
    # SEARCH / LOCATION / MODE INPUT
    # =========================================================

    search_text = request.args.get(
        "q",
        "",
        type=str
    ).strip()

    selected_location = request.args.get(
        "location",
        "",
        type=str
    ).strip()

    search_mode = request.args.get(
        "mode",
        "food",
        type=str
    ).strip().lower()


    if search_mode not in (
        "food",
        "grocery"
    ):
        search_mode = "food"


    # Fallback to saved location
    if not selected_location:

        selected_location = session.get(
            "selected_location",
            ""
        )


    # =========================================================
    # SHORT SEARCH
    # =========================================================

    if len(search_text) < 2:

        return jsonify({

            "success": True,

            "mode":
                search_mode,

            "query":
                search_text,

            "location":
                selected_location,

            "count": 0,

            "items": [],

            "restaurant_count": 0,

            "restaurants": [],

            "comparison": None
        })


    normalized_query = search_text.lower()

    search_pattern = (
        f"%{normalized_query}%"
    )


    # =========================================================
    # POSTGRESQL TRIGRAM SIMILARITY
    # =========================================================

    item_name_similarity = func.similarity(

        func.lower(
            func.coalesce(
                MenuItem.name,
                ""
            )
        ),

        normalized_query
    )


    category_similarity = func.similarity(

        func.lower(
            func.coalesce(
                MenuItem.category,
                ""
            )
        ),

        normalized_query
    )


    description_similarity = func.similarity(

        func.lower(
            func.coalesce(
                MenuItem.description,
                ""
            )
        ),

        normalized_query
    )


    restaurant_name_similarity = func.similarity(

        func.lower(
            func.coalesce(
                Restaurant.name,
                ""
            )
        ),

        normalized_query
    )


    highest_similarity = func.greatest(

        item_name_similarity,

        category_similarity,

        description_similarity,

        restaurant_name_similarity
    )


    # =========================================================
    # SEARCH MATCH PRIORITY
    # =========================================================

    match_score = case(

        # Exact item-name
        (
            func.lower(
                func.coalesce(
                    MenuItem.name,
                    ""
                )
            )
            ==
            normalized_query,

            100
        ),

        # Item starts with query
        (
            func.lower(
                func.coalesce(
                    MenuItem.name,
                    ""
                )
            ).like(
                f"{normalized_query}%"
            ),

            80
        ),

        # Item contains query
        (
            func.lower(
                func.coalesce(
                    MenuItem.name,
                    ""
                )
            ).like(
                search_pattern
            ),

            60
        ),

        # Category contains query
        (
            func.lower(
                func.coalesce(
                    MenuItem.category,
                    ""
                )
            ).like(
                search_pattern
            ),

            45
        ),

        # Store / restaurant name
        (
            func.lower(
                func.coalesce(
                    Restaurant.name,
                    ""
                )
            ).like(
                search_pattern
            ),

            35
        ),

        # Description
        (
            func.lower(
                func.coalesce(
                    MenuItem.description,
                    ""
                )
            ).like(
                search_pattern
            ),

            25
        ),

        else_=0
    )


    # =========================================================
    # REAL ORDER COUNT SUBQUERY
    # =========================================================

    order_count_subquery = (

        db.session.query(

            Order.restaurant_id.label(
                "restaurant_id"
            ),

            func.lower(
                OrderItem.item_name
            ).label(
                "item_name"
            ),

            func.coalesce(
                func.sum(
                    OrderItem.quantity
                ),
                0
            ).label(
                "order_count"
            )

        )

        .join(
            Order,
            Order.id == OrderItem.order_id
        )

        .group_by(

            Order.restaurant_id,

            func.lower(
                OrderItem.item_name
            )
        )

        .subquery()
    )


    # =========================================================
    # MENU ITEM SEARCH QUERY
    # =========================================================

    results_query = (

        db.session.query(

            MenuItem,

            Restaurant,

            match_score.label(
                "match_score"
            ),

            highest_similarity.label(
                "similarity_score"
            ),

            func.coalesce(
                order_count_subquery.c.order_count,
                0
            ).label(
                "order_count"
            )
        )

        .join(
            Restaurant,
            MenuItem.restaurant_id
            ==
            Restaurant.id
        )

        .outerjoin(

            order_count_subquery,

            db.and_(

                order_count_subquery.c.restaurant_id
                ==
                MenuItem.restaurant_id,

                order_count_subquery.c.item_name
                ==
                func.lower(
                    MenuItem.name
                )
            )
        )

        .filter(

            func.lower(
                func.coalesce(
                    MenuItem.availability,
                    ""
                )
            )
            ==
            "yes"
        )

        .filter(

            or_(

                func.lower(
                    func.coalesce(
                        MenuItem.name,
                        ""
                    )
                ).like(
                    search_pattern
                ),

                func.lower(
                    func.coalesce(
                        MenuItem.category,
                        ""
                    )
                ).like(
                    search_pattern
                ),

                func.lower(
                    func.coalesce(
                        MenuItem.description,
                        ""
                    )
                ).like(
                    search_pattern
                ),

                func.lower(
                    func.coalesce(
                        Restaurant.name,
                        ""
                    )
                ).like(
                    search_pattern
                ),

                item_name_similarity >= 0.25,

                category_similarity >= 0.30,

                restaurant_name_similarity >= 0.30
            )
        )
    )


    # =========================================================
    # FOOD / GROCERY MODE FILTER
    # =========================================================

    if search_mode == "grocery":

        results_query = (
            results_query.filter(

                Restaurant.category_type
                ==
                "grocery",

                MenuItem.item_type
                ==
                "grocery"
            )
        )

    else:

        results_query = (
            results_query.filter(

                Restaurant.category_type.in_(
                    [
                        "restaurant",
                        "bakery"
                    ]
                ),

                MenuItem.item_type
                !=
                "grocery"
            )
        )


    # =========================================================
    # LOCATION FILTER
    # =========================================================

    if selected_location:

        results_query = (
            results_query.filter(

                func.lower(
                    func.coalesce(
                        Restaurant.location,
                        ""
                    )
                )
                ==
                selected_location.lower()
            )
        )


    # =========================================================
    # EXECUTE SEARCH
    # =========================================================

    results = (

        results_query

        .order_by(

            match_score.desc(),

            highest_similarity.desc(),

            MenuItem.name.asc()
        )

        .limit(60)

        .all()
    )


    # =========================================================
    # BUILD MENU RESULTS
    # =========================================================

    search_items = []

    restaurant_ids = set()

    open_restaurant_ids = set()

    lowest_price_item = None

    most_ordered_item = None


    for (
        item,
        restaurant,
        result_match_score,
        similarity_score,
        order_count
    ) in results:


        extra_data = dict(
            item.extra_data or {}
        )


        # =====================================================
        # REMOVE ADD-ONS
        # =====================================================

        is_addon = str(

            extra_data.get(
                "is_addon",
                "no"
            )

        ).strip().lower() in (

            "yes",
            "true",
            "1"
        )


        if is_addon:
            continue


        # =====================================================
        # IMAGE
        # =====================================================

        image_url = str(
            item.image_url or ""
        ).strip()


        if (
            image_url
            and
            not image_url.startswith(
                (
                    "http://",
                    "https://",
                    "/"
                )
            )
        ):

            image_url = url_for(

                "static",

                filename=(
                    f"images/menu/"
                    f"{image_url}"
                )
            )


        # =====================================================
        # MATCH TYPE
        # =====================================================

        numeric_match_score = int(
            result_match_score or 0
        )

        numeric_similarity = float(
            similarity_score or 0
        )


        if numeric_match_score >= 100:

            match_type = "exact"

        elif numeric_match_score > 0:

            match_type = "partial"

        else:

            match_type = "typo"


        # =====================================================
        # STORE OPEN
        # =====================================================

        is_restaurant_open = (

            bool(
                restaurant.can_accept_orders
            )

            and

            restaurant_open(
                restaurant
            )
        )


        # =====================================================
        # BASE PRICE
        # =====================================================

        item_price = float(
            item.price or 0
        )


        # =====================================================
        # WEIGHT OPTIONS
        #
        # FOOD old format:
        # weight_prices = 500g:349,1kg:599
        #
        # GROCERY:
        # weight_options = 500ml:30
        # weight_options = 250g:30:40
        #                weight:selling:mrp
        # =====================================================

        weight_prices_raw = str(

            extra_data.get(
                "weight_prices",
                ""
            )
            or
            extra_data.get(
                "weight_options",
                ""
            )
            or
            ""

        ).strip()


        weight_price_options = []


        if weight_prices_raw:

            for option in (
                weight_prices_raw.split(",")
            ):

                option = option.strip()

                if ":" not in option:
                    continue


                parts = [
                    part.strip()
                    for part
                    in option.split(":")
                ]


                if len(parts) < 2:
                    continue


                weight = parts[0]


                try:

                    numeric_price = float(

                        str(
                            parts[1]
                        )
                        .replace(
                            "₹",
                            ""
                        )
                        .strip()
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    continue


                if numeric_price <= 0:
                    continue


                numeric_mrp = 0


                if len(parts) >= 3:

                    try:

                        numeric_mrp = float(

                            str(
                                parts[2]
                            )
                            .replace(
                                "₹",
                                ""
                            )
                            .strip()
                        )

                    except (
                        TypeError,
                        ValueError
                    ):

                        numeric_mrp = 0


                weight_price_options.append({

                    "weight":
                        weight,

                    "price":
                        numeric_price,

                    "mrp":
                        numeric_mrp
                })


        # Lowest weight price becomes displayed starting price
        if weight_price_options:

            valid_prices = [

                option["price"]

                for option
                in weight_price_options

                if option["price"] > 0
            ]


            if valid_prices:

                item_price = min(
                    valid_prices
                )


        # =====================================================
        # ORDER COUNT
        # =====================================================

        item_order_count = int(
            order_count or 0
        )


        # =====================================================
        # RESULT URL
        # =====================================================

        if search_mode == "grocery":

            menu_url = url_for(
                "grocery_store",
                store_id=restaurant.id,
                category=(
                    item.category or ""
                )
            )

        else:

            menu_url = url_for(
                "menu",
                restaurant_id=restaurant.id
            )


        # =====================================================
        # ITEM DATA
        # =====================================================

        item_data = {

            "id":
                item.id,

            "name":
                item.name or "",

            "price":
                item_price,

            "mrp":
                float(
                    item.mrp or 0
                ),

            "unit":
                item.unit or "",

            "has_weight_prices":
                bool(
                    weight_price_options
                ),

            "weight_prices":
                weight_price_options,

            "category":
                item.category or "",

            "description":
                item.description or "",

            "image_url":
                image_url,

            "item_type":
                item.item_type or "",

            "restaurant_id":
                restaurant.id,

            "restaurant_name":
                restaurant.name,

            "restaurant_open":
                is_restaurant_open,

            "restaurant_location":
                restaurant.location or "",

            "menu_url":
                menu_url,

            "match_type":
                match_type,

            "similarity_score":
                round(
                    numeric_similarity,
                    3
                ),

            "order_count":
                item_order_count
        }


        search_items.append(
            item_data
        )


        # =====================================================
        # FOOD COMPARISON DATA
        # =====================================================

        if search_mode == "food":

            restaurant_ids.add(
                restaurant.id
            )


            if is_restaurant_open:

                open_restaurant_ids.add(
                    restaurant.id
                )


            if item_price > 0:

                if (
                    lowest_price_item is None
                    or
                    item_price
                    <
                    lowest_price_item[
                        "price"
                    ]
                ):

                    lowest_price_item = (
                        item_data
                    )


            if item_order_count > 0:

                if (
                    most_ordered_item is None
                    or
                    item_order_count
                    >
                    most_ordered_item[
                        "order_count"
                    ]
                ):

                    most_ordered_item = (
                        item_data
                    )


    # =========================================================
    # OPEN STORES FIRST
    # =========================================================

    search_items.sort(

        key=lambda item: (

            not item[
                "restaurant_open"
            ]
        )
    )


    # =========================================================
    # SMART FOOD COMPARISON
    # FOOD MODE ONLY
    # =========================================================

    comparison = None


    if (
        search_mode == "food"
        and
        search_items
    ):

        comparison = {

            "total_items":
                len(
                    search_items
                ),

            "restaurant_count":
                len(
                    restaurant_ids
                ),

            "open_restaurant_count":
                len(
                    open_restaurant_ids
                ),

            "lowest_price":
                None,

            "most_ordered":
                None
        }


        if lowest_price_item:

            comparison[
                "lowest_price"
            ] = {

                "item_id":
                    lowest_price_item[
                        "id"
                    ],

                "item_name":
                    lowest_price_item[
                        "name"
                    ],

                "price":
                    lowest_price_item[
                        "price"
                    ],

                "restaurant_id":
                    lowest_price_item[
                        "restaurant_id"
                    ],

                "restaurant_name":
                    lowest_price_item[
                        "restaurant_name"
                    ],

                "restaurant_open":
                    lowest_price_item[
                        "restaurant_open"
                    ],

                "menu_url":
                    lowest_price_item[
                        "menu_url"
                    ]
            }


        if most_ordered_item:

            comparison[
                "most_ordered"
            ] = {

                "item_id":
                    most_ordered_item[
                        "id"
                    ],

                "item_name":
                    most_ordered_item[
                        "name"
                    ],

                "order_count":
                    most_ordered_item[
                        "order_count"
                    ],

                "price":
                    most_ordered_item[
                        "price"
                    ],

                "restaurant_id":
                    most_ordered_item[
                        "restaurant_id"
                    ],

                "restaurant_name":
                    most_ordered_item[
                        "restaurant_name"
                    ],

                "restaurant_open":
                    most_ordered_item[
                        "restaurant_open"
                    ],

                "menu_url":
                    most_ordered_item[
                        "menu_url"
                    ]
            }


    # =========================================================
    # RESTAURANT SEARCH
    # FOOD MODE ONLY
    # =========================================================

    restaurant_search_items = []


    if search_mode == "food":

        restaurant_query = (

            Restaurant.query

            .filter(

                Restaurant.category_type.in_(
                    [
                        "restaurant",
                        "bakery"
                    ]
                )
            )

            .filter(

                or_(

                    func.lower(
                        func.coalesce(
                            Restaurant.name,
                            ""
                        )
                    ).like(
                        search_pattern
                    ),

                    func.similarity(

                        func.lower(
                            func.coalesce(
                                Restaurant.name,
                                ""
                            )
                        ),

                        normalized_query
                    )
                    >=
                    0.30
                )
            )
        )


        # Location filter
        if selected_location:

            restaurant_query = (

                restaurant_query.filter(

                    func.lower(
                        func.coalesce(
                            Restaurant.location,
                            ""
                        )
                    )
                    ==
                    selected_location.lower()
                )
            )


        restaurant_results = (

            restaurant_query

            .order_by(

                case(

                    (
                        func.lower(
                            func.coalesce(
                                Restaurant.name,
                                ""
                            )
                        )
                        ==
                        normalized_query,

                        0
                    ),

                    (
                        func.lower(
                            func.coalesce(
                                Restaurant.name,
                                ""
                            )
                        ).like(
                            f"{normalized_query}%"
                        ),

                        1
                    ),

                    else_=2
                ),

                Restaurant.name.asc()
            )

            .limit(10)

            .all()
        )


        # =====================================================
        # BUILD RESTAURANT RESULTS
        # =====================================================

        for restaurant in (
            restaurant_results
        ):

            is_open_and_accepting = (

                bool(
                    restaurant.can_accept_orders
                )

                and

                restaurant_open(
                    restaurant
                )
            )


            restaurant_image = url_for(

                "static",

                filename=(

                    f"images/restaurants/"
                    f"{restaurant.id}.jpg"
                )
            )


            restaurant_search_items.append({

                "id":
                    restaurant.id,

                "name":
                    restaurant.name,

                "location":
                    restaurant.location or "",

                "category_type":
                    (
                        restaurant.category_type
                        or
                        "restaurant"
                    ),

                "image_url":
                    restaurant_image,

                "is_open":
                    is_open_and_accepting,

                "menu_url":
                    url_for(
                        "menu",
                        restaurant_id=restaurant.id
                    )
            })


        restaurant_search_items.sort(

            key=lambda restaurant: (

                not restaurant[
                    "is_open"
                ],

                restaurant[
                    "name"
                ].lower()
            )
        )


    # =========================================================
    # API RESPONSE
    # =========================================================

    return jsonify({

        "success":
            True,

        "mode":
            search_mode,

        "query":
            search_text,

        "location":
            selected_location,

        "count":
            len(
                search_items
            ),

        "items":
            search_items,

        "restaurant_count":
            len(
                restaurant_search_items
            ),

        "restaurants":
            restaurant_search_items,

        "comparison":
            comparison
    })
@app.route('/map-test')
def map_test():
    return render_template('map_test.html')
@app.route("/admin/grocery-sync")
def grocery_sync_page():

    grocery_stores = (
        Restaurant.query
        .filter(
            Restaurant.category_type == "grocery"
        )
        .order_by(
            Restaurant.name.asc()
        )
        .all()
    )

    return render_template(
        "admin_grocery_sync.html",
        grocery_stores=grocery_stores
    )


@app.route(
    "/admin/grocery/<int:store_id>/sync",
    methods=["POST"]
)
def sync_grocery_store(store_id):

    try:

        result = import_grocery_sheet_to_db(
            store_id
        )

        if not result.get("success"):
            return jsonify(result), 400

        return jsonify({

            "success": True,

            "message":
                "Grocery items synced successfully",

            "added":
                result.get("added", 0),

            "updated":
                result.get("updated", 0),

            "disabled":
                result.get("disabled", 0),

            "skipped":
                result.get("skipped", 0),

            "total_sheet_items":
                result.get(
                    "total_sheet_items",
                    0
                )
        })

    except Exception as e:

        db.session.rollback()

        print(
            "GROCERY SYNC ERROR:",
            e
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500 



#========================================================
# FLASK BACKEND - CART / RESTAURANT REVALIDATION
# Add these imports near the top of app.py if not already present:
# ============================================================

from datetime import datetime
from zoneinfo import ZoneInfo
from flask import request, jsonify


# ============================================================
# API - VALIDATE CART BEFORE CHECKOUT / PLACE ORDER
#
# Checks:
# 1. Restaurant exists
# 2. Restaurant can accept orders
# 3. Restaurant is currently open
# 4. Every item belongs to this restaurant
# 5. Every item still exists
# 6. Every item is currently available
# 7. Flutter receives the latest SERVER price
#
# IMPORTANT:
# The server/database is authoritative.
# Never trust price sent from Flutter.
# ============================================================

# ============================================================
# FLASK BACKEND - CUSTOMER ORDER HISTORY API
# Add this route to your existing Flask app.
#
# It supports the Flutter Profile -> My Orders screen.
#
# Required existing models:
#   Order
#   OrderItem
#   Restaurant
# ============================================================

from flask import request, jsonify


@app.route("/api/customer/orders", methods=["GET"])
def api_customer_orders():

    phone = (
        request.args.get("phone", "")
        .strip()
        .replace(" ", "")
    )

    # Accept +91xxxxxxxxxx or plain 10-digit phone.
    if phone.startswith("+91"):
        phone = phone[3:]

    if len(phone) != 10 or not phone.isdigit():
        return jsonify({
            "success": False,
            "message": "Valid 10 digit phone number is required."
        }), 400

    orders = (
        Order.query
        .filter(Order.phone == phone)
        .order_by(Order.created_at.desc())
        .all()
    )

    result = []

    for order in orders:

        restaurant = None

        if order.restaurant_id:
            restaurant = db.session.get(
                Restaurant,
                order.restaurant_id
            )

        item_rows = []

        for item in (order.items or []):

            # These getattr calls keep the API tolerant of slightly
            # different OrderItem model field names.
            item_name = (
                getattr(item, "item_name", None)
                or getattr(item, "name", None)
                or getattr(item, "food_name", None)
                or "Item"
            )

            quantity = int(
                getattr(item, "quantity", 1) or 1
            )

            unit_price = float(
                getattr(item, "price", 0)
                or getattr(item, "unit_price", 0)
                or 0
            )

            total = float(
                getattr(item, "total_price", 0)
                or getattr(item, "total", 0)
                or (unit_price * quantity)
            )

            item_rows.append({
                "name": item_name,
                "quantity": quantity,
                "price": round(unit_price, 2),
                "total": round(total, 2),
            })

        full_address_parts = [
            order.house_no,
            order.landmark,
            order.city,
            order.state,
            order.pincode,
        ]

        full_address = ", ".join(
            str(part).strip()
            for part in full_address_parts
            if part
        )

        result.append({
            "id": order.id,
            "order_id": order.order_id or str(order.id),

            "restaurant_id": order.restaurant_id,
            "restaurant_name": (
                restaurant.name
                if restaurant
                else "Restaurant"
            ),

            "status": order.status or "Pending",

            "created_at": (
                order.created_at.strftime(
                    "%d %b %Y, %I:%M %p"
                )
                if order.created_at
                else ""
            ),

            "updated_at": (
                order.updated_at.isoformat()
                if order.updated_at
                else None
            ),

            "item_count": sum(
                int(
                    getattr(item, "quantity", 1)
                    or 1
                )
                for item in (order.items or [])
            ),

            "items": item_rows,

            "items_total": float(
                order.items_total or 0
            ),

            "discount": float(
                order.discount or 0
            ),

            "restaurant_offer_discount": float(
                order.restaurant_offer_discount or 0
            ),

            "delivery_charge": float(
                order.delivery_charge or 0
            ),

            "final_total": float(
                order.get_final_total()
                if hasattr(order, "get_final_total")
                else order.final_total or 0
            ),

            "payment_type": order.payment_type or "COD",
            "payment_status": order.payment_status or "Pending",

            "address": (
                order.address
                or full_address
            ),

            "address_type": order.address_type,
            "delivery_note": order.delivery_note,

            "latitude": order.latitude,
            "longitude": order.longitude,

            "delivery_person_id":
                order.delivery_person_id,

            "delivered_time": (
                order.delivered_time.isoformat()
                if order.delivered_time
                else None
            ),
        })

    return jsonify({
        "success": True,
        "phone": phone,
        "orders": result,
    }), 200

# ============================================================
# RUCHIGO FLUTTER CUSTOMER ACCOUNT API
#
# Uses your EXISTING Customer model + Flask-Login.
# No OTP. No password.
#
# Existing website behavior preserved:
# - Create account: name + mobile
# - Login: registered mobile
#
# Add this block to your existing Flask application after
# Customer / Order / Restaurant models and login_manager setup.
# ============================================================

from flask import request, jsonify
from flask_login import (
    current_user,
    login_user,
    logout_user,
    login_required,
)
from sqlalchemy import or_


# ============================================================
# HELPER - NORMALIZE MOBILE
# ============================================================

def _app_normalize_mobile(value):
    mobile = str(value or "").strip().replace(" ", "")

    if mobile.startswith("+91"):
        mobile = mobile[3:]

    if len(mobile) != 10 or not mobile.isdigit():
        return None

    return mobile


def _app_customer_json(customer):
    mobile = customer.mobile or ""

    return {
        "id": customer.id,
        "name": customer.name or "",
        "mobile": mobile,
    }


# ============================================================
# CREATE CUSTOMER ACCOUNT
# POST JSON:
# {
#   "name": "Manikanta",
#   "mobile": "9876543210"
# }
# ============================================================

@app.route(
    "/api/app/customer/signup",
    methods=["POST"],
)
@csrf.exempt
def api_app_customer_signup():

    data = request.get_json(silent=True) or {}

    name = str(
        data.get("name", "")
    ).strip()

    mobile = _app_normalize_mobile(
        data.get("mobile")
    )

    if not name:
        return jsonify({
            "success": False,
            "message": "Please enter your name."
        }), 400

    if not mobile:
        return jsonify({
            "success": False,
            "message": "Please enter a valid 10 digit mobile number."
        }), 400

    normalized = "+91" + mobile

    customer = Customer.query.filter(
        or_(
            Customer.mobile == normalized,
            Customer.mobile == mobile,
        )
    ).first()

    if customer:
        return jsonify({
            "success": False,
            "message": "Account already exists. Please login."
        }), 409

    customer = Customer(
        mobile=normalized,
        name=name,
    )

    db.session.add(customer)
    db.session.commit()

    login_user(
        customer,
        remember=False,
    )

    session.permanent = True

    return jsonify({
        "success": True,
        "message": "Account created successfully.",
        "customer": _app_customer_json(customer),
    }), 201


# ============================================================
# CUSTOMER LOGIN
# POST JSON:
# {
#   "mobile": "9876543210"
# }
# ============================================================

@app.route(
    "/api/app/customer/login",
    methods=["POST"],
)
@csrf.exempt
def api_app_customer_login():

    data = request.get_json(silent=True) or {}

    mobile = _app_normalize_mobile(
        data.get("mobile")
    )

    if not mobile:
        return jsonify({
            "success": False,
            "message": "Please enter a valid 10 digit mobile number."
        }), 400

    normalized = "+91" + mobile

    customer = Customer.query.filter(
        or_(
            Customer.mobile == normalized,
            Customer.mobile == mobile,
        )
    ).first()

    if not customer:
        return jsonify({
            "success": False,
            "message": "Account not found. Please create an account."
        }), 404

    login_user(
        customer,
        remember=False,
    )

    session.permanent = True

    return jsonify({
        "success": True,
        "message": "Login successful.",
        "customer": _app_customer_json(customer),
    }), 200


# ============================================================
# CURRENT CUSTOMER PROFILE
# ============================================================

@app.route(
    "/api/app/customer/profile",
    methods=["GET"],
)
def api_app_customer_profile():

    if not current_user.is_authenticated:
        return jsonify({
            "success": False,
            "message": "Please login."
        }), 401

    return jsonify({
        "success": True,
        "customer": _app_customer_json(
            current_user
        )
    }), 200


# ============================================================
# LOGOUT
# ============================================================

@app.route(
    "/api/app/customer/logout",
    methods=["POST"],
)
@csrf.exempt
def api_app_customer_logout():

    if current_user.is_authenticated:
        logout_user()

    return jsonify({
        "success": True,
        "message": "Logged out successfully."
    }), 200


# ============================================================
# ORDER SERIALIZER
# ============================================================

def _app_order_json(order):

    restaurant = None

    if order.restaurant_id:
        restaurant = db.session.get(
            Restaurant,
            order.restaurant_id,
        )

    item_rows = []

    for item in (order.items or []):

        item_name = (
            getattr(item, "item_name", None)
            or getattr(item, "name", None)
            or getattr(item, "food_name", None)
            or "Item"
        )

        quantity = int(
            getattr(item, "quantity", 1)
            or 1
        )

        price = float(
            getattr(item, "price", 0)
            or getattr(item, "unit_price", 0)
            or 0
        )

        total = float(
            getattr(item, "total_price", 0)
            or getattr(item, "total", 0)
            or price * quantity
        )

        item_rows.append({
            "name": item_name,
            "quantity": quantity,
            "price": round(price, 2),
            "total": round(total, 2),
        })

    address_parts = [
        order.house_no,
        order.landmark,
        order.city,
        order.state,
        order.pincode,
    ]

    full_address = ", ".join(
        str(x).strip()
        for x in address_parts
        if x
    )

    final_total = (
        order.get_final_total()
        if hasattr(order, "get_final_total")
        else order.final_total or 0
    )

    return {
        "id": order.id,
        "order_id": order.order_id or str(order.id),

        "restaurant_id": order.restaurant_id,
        "restaurant_name": (
            restaurant.name
            if restaurant
            else "Restaurant"
        ),

        "status": order.status or "Pending",

        "created_at": (
            order.created_at.strftime(
                "%d %b %Y, %I:%M %p"
            )
            if order.created_at
            else ""
        ),

        "item_count": sum(
            int(
                getattr(item, "quantity", 1)
                or 1
            )
            for item in (order.items or [])
        ),

        "items": item_rows,

        "items_total": float(
            order.items_total or 0
        ),

        "discount": float(
            order.discount or 0
        ),

        "restaurant_offer_discount": float(
            order.restaurant_offer_discount or 0
        ),

        "delivery_charge": float(
            order.delivery_charge or 0
        ),

        "final_total": float(
            final_total
        ),

        "payment_type": order.payment_type or "COD",
        "payment_status": order.payment_status or "Pending",

        "address": (
            order.address
            or full_address
        ),

        "address_type": order.address_type,
        "delivery_note": order.delivery_note,

        "latitude": order.latitude,
        "longitude": order.longitude,
    }


# ============================================================
# CURRENT CUSTOMER ORDERS
#
# IMPORTANT:
# This uses customer_id first.
#
# Older orders that were created before customer_id was saved
# are also included when their phone matches the logged-in
# customer's registered mobile.
# ============================================================

@app.route(
    "/api/app/customer/orders",
    methods=["GET"],
)
def api_app_customer_orders():

    if not current_user.is_authenticated:
        return jsonify({
            "success": False,
            "message": "Please login."
        }), 401

    raw_mobile = current_user.mobile or ""

    mobile10 = (
        raw_mobile[3:]
        if raw_mobile.startswith("+91")
        else raw_mobile
    )

    orders = (
        Order.query
        .filter(
            or_(
                Order.customer_id == current_user.id,
                Order.phone == raw_mobile,
                Order.phone == mobile10,
            )
        )
        .order_by(
            Order.created_at.desc()
        )
        .all()
    )

    return jsonify({
        "success": True,
        "orders": [
            _app_order_json(order)
            for order in orders
        ],
    }), 200


# ============================================================
# FIXED CUSTOMER ORDER TRACKING
#
# Accepts BOTH:
# - DB order.id
# - public order.order_id
#
# Also verifies this order belongs to logged-in customer.
# ============================================================

@app.route(
    "/api/app/customer/orders/<string:order_ref>/track",
    methods=["GET"],
)
def api_app_customer_order_track(order_ref):

    if not current_user.is_authenticated:
        return jsonify({
            "success": False,
            "message": "Please login."
        }), 401

    raw_mobile = current_user.mobile or ""

    mobile10 = (
        raw_mobile[3:]
        if raw_mobile.startswith("+91")
        else raw_mobile
    )

    filters = [
        Order.order_id == order_ref,
    ]

    if order_ref.isdigit():
        filters.append(
            Order.id == int(order_ref)
        )

    order = Order.query.filter(
        or_(*filters)
    ).first()

    if not order:
        return jsonify({
            "success": False,
            "message": "Order not found."
        }), 404

    belongs_to_customer = (
        order.customer_id == current_user.id
        or order.phone == raw_mobile
        or order.phone == mobile10
    )

    if not belongs_to_customer:
        return jsonify({
            "success": False,
            "message": "This order does not belong to your account."
        }), 403

    data = _app_order_json(order)

    # Delivery partner fields
    if order.delivery_person:
        data["delivery_person_name"] = (
            getattr(
                order.delivery_person,
                "name",
                None,
            )
            or ""
        )

        data["delivery_person_phone"] = (
            getattr(
                order.delivery_person,
                "phone",
                None,
            )
            or getattr(
                order.delivery_person,
                "mobile",
                None,
            )
            or ""
        )
    else:
        data["delivery_person_name"] = ""
        data["delivery_person_phone"] = ""

    return jsonify({
        "success": True,
        "order": data,
    }), 200

# ============================================================
# FLUTTER APP - GROCERY STORE MENU API
#
# Used by:
# lib/screens/grocery/grocery_store_screen.dart
#
# Website route remains:
# /grocery/<store_id>
#
# Flutter route:
# /api/app/grocery/<store_id>
# ============================================================

@app.route("/api/app/grocery/<int:store_id>")
def api_app_grocery_store(store_id):

    # ========================================================
    # LOAD STORE
    # ========================================================

    store = Restaurant.query.get_or_404(
        store_id
    )

    # ========================================================
    # VALIDATE GROCERY STORE
    # ========================================================

    if store.category_type != "grocery":
        return jsonify({
            "success": False,
            "message": "Invalid grocery store"
        }), 404

    # ========================================================
    # LOAD AVAILABLE GROCERY ITEMS
    # ========================================================

    items = (
        MenuItem.query
        .filter(
            MenuItem.restaurant_id == store.id,
            MenuItem.item_type == "grocery",
            MenuItem.availability == "yes"
        )
        .order_by(
            MenuItem.category.asc(),
            MenuItem.name.asc()
        )
        .all()
    )

    # ========================================================
    # PREPARE ITEMS
    # ========================================================

    all_items = []

    categories = []

    for item in items:

        category = (
            item.category
            or "Others"
        ).strip()

        if category not in categories:
            categories.append(
                category
            )

        extra_data = dict(
            item.extra_data or {}
        )

        all_items.append({

            "id":
                item.id,

            "name":
                item.name or "",

            "description":
                item.description or "",

            "category":
                category,

            "price":
                float(
                    item.price or 0
                ),

            "mrp":
                float(
                    item.mrp or 0
                ),

            "unit":
                item.unit or "",

            "image":
                item.image_url or "",

            "availability":
                item.availability,

            "in_stock":
                item.availability == "yes",

            "weight_options":
                extra_data.get(
                    "weight_options",
                    ""
                )
        })

    # ========================================================
    # STORE INFORMATION
    # ========================================================

    store_data = {

        "id":
            store.id,

        "name":
            store.name or "",

        "location":
            store.location or "",

        "category_type":
            store.category_type,

        "delivery_charge":
            float(
                store.delivery_charge
                or 0
            ),

        "free_delivery_limit":
            float(
                store.free_delivery_limit
                or 0
            ),

        "image_url":
            getattr(
                store,
                "image_url",
                ""
            ) or "",

        "is_open":
            True,

        "can_accept_orders":
            bool(
                getattr(
                    store,
                    "can_accept_orders",
                    True
                )
            )
    }

    # ========================================================
    # RETURN JSON TO FLUTTER
    # ========================================================

    return jsonify({

        "success":
            True,

        "store":
            store_data,

        "categories":
            categories,

        "items":
            all_items,

        "all_items":
            all_items

    }), 200



def _parse_grocery_weight_options(menu_item):
    raw = str(
        (menu_item.extra_data or {}).get(
            "weight_options",
            ""
        )
        or ""
    ).strip()

    options = {}

    if not raw:
        return options

    for piece in raw.split(","):
        parts = [
            part.strip()
            for part in piece.split(":")
        ]

        if len(parts) < 2:
            continue

        label = parts[0]

        try:
            price = float(parts[1])
        except (TypeError, ValueError):
            continue

        if not label or price <= 0:
            continue

        try:
            mrp = (
                float(parts[2])
                if len(parts) >= 3
                and parts[2]
                else price
            )
        except (TypeError, ValueError):
            mrp = price

        options[label] = {
            "price": price,
            "mrp": mrp if mrp > 0 else price,
        }

    return options


def _server_cart_variant(menu_item, requested_weight=None):
    item_type = (
        getattr(menu_item, "item_type", "")
        or ""
    ).strip().lower()

    weight = (
        str(requested_weight).strip()
        if requested_weight is not None
        else ""
    )

    # Grocery with configured weight variants:
    # selected weight MUST exist in backend config.
    if item_type == "grocery":
        options = _parse_grocery_weight_options(
            menu_item
        )

        if options:
            selected = options.get(weight)

            if selected is None:
                return None

            return {
                "price": float(
                    selected["price"]
                ),
                "mrp": float(
                    selected["mrp"]
                ),
                "weight": weight,
            }

    # Restaurant item OR grocery item with no variants.
    server_price = float(
        menu_item.price or 0
    )

    server_mrp = float(
        getattr(menu_item, "mrp", 0)
        or server_price
    )

    return {
        "price": server_price,
        "mrp": server_mrp,
        "weight": weight or None,
    }


@app.route(
    "/api/validate-cart",
    methods=["POST"],
)
def api_validate_cart():

    data = request.get_json(
        silent=True
    ) or {}

    restaurant_id = data.get(
        "restaurant_id"
    )

    client_items = (
        data.get("items")
        or []
    )

    try:
        restaurant_id = int(
            restaurant_id
        )
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Invalid restaurant."
        }), 400

    if (
        not isinstance(
            client_items,
            list
        )
        or not client_items
    ):
        return jsonify({
            "success": False,
            "message": "Your cart is empty."
        }), 400

    restaurant = db.session.get(
        Restaurant,
        restaurant_id
    )

    if not restaurant:
        return jsonify({
            "success": False,
            "message":
                "Restaurant/store is no longer available."
        }), 404

    if (
        getattr(
            restaurant,
            "can_accept_orders",
            True
        )
        is False
    ):
        return jsonify({
            "success": False,
            "message":
                "This restaurant/store is not accepting orders right now."
        }), 409

    # Keep your existing open/closed rules.
    now = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).time()

    opening_time = getattr(
        restaurant,
        "opening_time",
        None
    )

    closing_time = getattr(
        restaurant,
        "closing_time",
        None
    )

    # If opening/closing values exist, validate them.
    if opening_time and closing_time:
        if opening_time <= closing_time:
            is_open = (
                opening_time
                <= now
                <= closing_time
            )
        else:
            is_open = (
                now >= opening_time
                or now <= closing_time
            )

        if not is_open:
            return jsonify({
                "success": False,
                "message":
                    "This restaurant/store is currently closed."
            }), 409

    # --------------------------------------------------------
    # NORMALIZE CLIENT CART.
    # IMPORTANT: key = menu item id + selected weight
    # --------------------------------------------------------

    requested = []

    ids = set()

    for raw in client_items:
        if not isinstance(
            raw,
            dict
        ):
            continue

        try:
            item_id = int(
                raw.get("id")
            )

            quantity = int(
                raw.get(
                    "quantity",
                    1
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if quantity < 1:
            continue

        quantity = min(
            quantity,
            99
        )

        weight = (
            str(
                raw.get("weight")
                or ""
            )
            .strip()
        )

        cart_key = (
            f"{item_id}|{weight}"
        )

        requested.append({
            "id": item_id,
            "quantity": quantity,
            "weight": weight,
            "cart_key": cart_key,
            "client_price":
                raw.get(
                    "client_price"
                ),
        })

        ids.add(item_id)

    if not requested:
        return jsonify({
            "success": False,
            "message":
                "No valid items found in cart."
        }), 400

    menu_items = (
        MenuItem.query
        .filter(
            MenuItem.id.in_(ids),
            MenuItem.restaurant_id
            == restaurant_id
        )
        .all()
    )

    menu_by_id = {
        item.id: item
        for item in menu_items
    }

    validated_items = []
    unavailable_cart_keys = []
    unavailable_item_ids = []

    cart_changed = False
    server_subtotal = 0.0

    for request_item in requested:

        item_id = request_item["id"]

        item = menu_by_id.get(
            item_id
        )

        cart_key = request_item[
            "cart_key"
        ]

        if item is None:
            unavailable_cart_keys.append(
                cart_key
            )
            unavailable_item_ids.append(
                item_id
            )
            cart_changed = True
            continue

        availability = str(
            getattr(
                item,
                "availability",
                "yes"
            )
            or ""
        ).strip().lower()

        if availability not in (
            "yes",
            "true",
            "1",
        ):
            unavailable_cart_keys.append(
                cart_key
            )
            unavailable_item_ids.append(
                item_id
            )
            cart_changed = True
            continue

        variant = _server_cart_variant(
            item,
            request_item.get("weight")
        )

        if variant is None:
            unavailable_cart_keys.append(
                cart_key
            )
            cart_changed = True
            continue

        server_price = float(
            variant["price"]
        )

        server_mrp = float(
            variant["mrp"]
        )

        quantity = request_item[
            "quantity"
        ]

        client_price = request_item.get(
            "client_price"
        )

        try:
            client_price = float(
                client_price
            )
        except (
            TypeError,
            ValueError,
        ):
            client_price = None

        if (
            client_price is None
            or abs(
                client_price
                - server_price
            )
            > 0.009
        ):
            cart_changed = True

        line_total = (
            server_price
            * quantity
        )

        server_subtotal += (
            line_total
        )

        validated_items.append({
            "cart_key":
                cart_key,

            "id":
                item.id,

            "name":
                item.name,

            "price":
                server_price,

            "mrp":
                server_mrp,

            "quantity":
                quantity,

            "weight":
                variant["weight"],

            "unit":
                getattr(
                    item,
                    "unit",
                    ""
                )
                or "",

            "category":
                item.category
                or "Others",

            "item_type":
                getattr(
                    item,
                    "item_type",
                    ""
                )
                or "",

            "line_total":
                round(
                    line_total,
                    2
                ),
        })

    if not validated_items:
        return jsonify({
            "success": False,
            "message":
                "The items in your cart are no longer available.",
            "cart_changed": True,
            "items": [],
            "unavailable_cart_keys":
                unavailable_cart_keys,
            "unavailable_item_ids":
                list(
                    set(
                        unavailable_item_ids
                    )
                ),
            "server_subtotal": 0,
        }), 409

    return jsonify({
        "success": True,

        "message": (
            "Cart updated with latest prices and availability."
            if cart_changed
            else "Cart is valid."
        ),

        "restaurant_id":
            restaurant.id,

        "cart_changed":
            cart_changed,

        "items":
            validated_items,

        "unavailable_cart_keys":
            unavailable_cart_keys,

        # Kept for older Flutter builds.
        "unavailable_item_ids":
            list(
                set(
                    unavailable_item_ids
                )
            ),

        "server_subtotal":
            round(
                server_subtotal,
                2
            ),
    }), 200
# ============================================================
# RUCHIGO FLUTTER ORDER API
#
# Add this route to app.py.
#
# It is separate from your existing website /place_order route.
#
# Supports:
# - Restaurant items
# - Grocery base-price items
# - Grocery selected weight variants
# - Server-authoritative prices
# - COD / existing payment_type value
# - Existing Order / OrderItem models
#
# REQUIRES existing project helpers/models:
# Restaurant, MenuItem, Order, OrderItem, db
# calculate_distance_km
# calculate_delivery_charge
# generate_map_link
# generate_otp
# generate_order_code
# current_user
# datetime
#
# Also copy:
# _parse_grocery_weight_options
# _server_cart_variant
# from flask_validate_cart_grocery_variants.py
# above this route (or import them).
# ============================================================

@app.route(
    "/api/place-order",
    methods=["POST"],
)
def api_place_order():

    data = request.get_json(
        silent=True
    ) or {}

    # ========================================================
    # BASIC INPUT
    # ========================================================

    try:
        restaurant_id = int(
            data.get(
                "restaurant_id"
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return jsonify({
            "success": False,
            "message":
                "Invalid restaurant/store."
        }), 400

    name = (
        data.get("name")
        or ""
    ).strip()

    phone = (
        data.get("phone")
        or ""
    ).strip()

    email = (
        data.get("email")
        or ""
    ).strip()

    alt_phone = (
        data.get("alt_phone")
        or ""
    ).strip()

    house_no = (
        data.get("house_no")
        or ""
    ).strip()

    landmark = (
        data.get("landmark")
        or ""
    ).strip()

    city = (
        data.get("city")
        or ""
    ).strip()

    state = (
        data.get("state")
        or ""
    ).strip()

    pincode = (
        data.get("pincode")
        or ""
    ).strip()

    address_type = (
        data.get("address_type")
        or "Home"
    ).strip()

    delivery_note = (
        data.get("delivery_note")
        or ""
    ).strip()

    payment_type = (
        data.get("payment_type")
        or "COD"
    ).strip()

    order_type = (
        data.get("order_type")
        or "Delivery"
    ).strip()

    client_items = (
        data.get("items")
        or []
    )

    if not name:
        return jsonify({
            "success": False,
            "message":
                "Customer name is required."
        }), 400

    normalized_phone = (
        phone
        .replace("+91", "")
        .replace(" ", "")
        .strip()
    )

    if (
        not normalized_phone.isdigit()
        or len(normalized_phone)
        != 10
    ):
        return jsonify({
            "success": False,
            "message":
                "Enter a valid 10 digit phone number."
        }), 400

    if (
        not isinstance(
            client_items,
            list
        )
        or not client_items
    ):
        return jsonify({
            "success": False,
            "message":
                "Your cart is empty."
        }), 400

    # ========================================================
    # LOCATION
    # ========================================================

    try:
        customer_lat = float(
            data.get("latitude")
        )

        customer_lng = float(
            data.get("longitude")
        )
    except (
        TypeError,
        ValueError,
    ):
        return jsonify({
            "success": False,
            "message":
                "Please confirm delivery location."
        }), 400

    # ========================================================
    # STORE
    # ========================================================

    restaurant = db.session.get(
        Restaurant,
        restaurant_id
    )

    if not restaurant:
        return jsonify({
            "success": False,
            "message":
                "Restaurant/store not found."
        }), 404

    if (
        getattr(
            restaurant,
            "can_accept_orders",
            True
        )
        is False
    ):
        return jsonify({
            "success": False,
            "message":
                "This restaurant/store is not accepting orders."
        }), 409

    # ========================================================
    # LOAD + VERIFY ITEMS
    # ========================================================

    ids = set()

    normalized_items = []

    for raw in client_items:

        if not isinstance(
            raw,
            dict
        ):
            continue

        try:
            item_id = int(
                raw.get("id")
            )

            qty = int(
                raw.get(
                    "quantity",
                    1
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if qty <= 0:
            continue

        qty = min(
            qty,
            99
        )

        weight = (
            str(
                raw.get("weight")
                or ""
            )
            .strip()
        )

        normalized_items.append({
            "id":
                item_id,
            "quantity":
                qty,
            "weight":
                weight,
        })

        ids.add(
            item_id
        )

    if not normalized_items:
        return jsonify({
            "success": False,
            "message":
                "No valid items in cart."
        }), 400

    db_items = (
        MenuItem.query
        .filter(
            MenuItem.id.in_(ids),
            MenuItem.restaurant_id
            == restaurant_id
        )
        .all()
    )

    by_id = {
        item.id: item
        for item in db_items
    }

    verified_items = []

    items_total = 0.0

    for requested in normalized_items:

        menu_item = by_id.get(
            requested["id"]
        )

        if not menu_item:
            return jsonify({
                "success": False,
                "message":
                    "One of the cart items is no longer available."
            }), 409

        availability = str(
            getattr(
                menu_item,
                "availability",
                "yes"
            )
            or ""
        ).strip().lower()

        if availability not in (
            "yes",
            "true",
            "1",
        ):
            return jsonify({
                "success": False,
                "message":
                    f"{menu_item.name} is currently unavailable."
            }), 409

        variant = _server_cart_variant(
            menu_item,
            requested.get(
                "weight"
            )
        )

        if variant is None:
            return jsonify({
                "success": False,
                "message":
                    f"Selected pack for {menu_item.name} is no longer available."
            }), 409

        qty = requested[
            "quantity"
        ]

        price = float(
            variant["price"]
        )

        mrp = float(
            variant["mrp"]
        )

        line_total = (
            price * qty
        )

        items_total += (
            line_total
        )

        verified_items.append({
            "menu_item":
                menu_item,

            "quantity":
                qty,

            "price":
                price,

            "mrp":
                mrp,

            "weight":
                variant["weight"],

            "unit":
                getattr(
                    menu_item,
                    "unit",
                    ""
                )
                or "",

            "category":
                menu_item.category
                or "Others",

            "item_type":
                getattr(
                    menu_item,
                    "item_type",
                    ""
                )
                or "",
        })

    # ========================================================
    # DISTANCE + DELIVERY
    # ========================================================

    distance_km = (
        calculate_distance_km(
            restaurant.latitude,
            restaurant.longitude,
            customer_lat,
            customer_lng,
        )
    )

    (
        delivery_charge,
        delivery_msg,
    ) = calculate_delivery_charge(
        distance_km,
        items_total,
        restaurant,
    )

    items_total = round(
        items_total,
        2
    )

    delivery_charge = round(
        float(
            delivery_charge
            or 0
        ),
        2
    )

    final_total = round(
        items_total
        + delivery_charge,
        2
    )

    # ========================================================
    # MAP LINK
    # ========================================================

    map_link = generate_map_link(
        customer_lat,
        customer_lng,
        house_no,
        landmark,
        city,
        state,
        pincode,
    )

    # ========================================================
    # PAYMENT / ORDER STATUS
    # ========================================================

    if payment_type == "Online":
        order_status = (
            "Pending Payment"
        )

        payment_source = (
            "Checkout"
        )
    else:
        order_status = (
            "Pending"
        )

        payment_source = (
            "COD"
        )

    # ========================================================
    # CREATE ORDER + ITEMS
    # ========================================================

    try:
        new_order = Order(
            restaurant_id=
                restaurant_id,

            customer_id=(
                current_user.id
                if current_user.is_authenticated
                else None
            ),

            customer_name=
                name,

            phone=
                normalized_phone,

            email=
                email,

            alt_phone=
                alt_phone,

            house_no=
                house_no,

            landmark=
                landmark,

            city=
                city,

            state=
                state,

            pincode=
                pincode,

            address_type=
                address_type,

            delivery_note=
                delivery_note,

            payment_type=
                payment_type,

            payment_status=
                "Pending",

            payment_verified=
                False,

            status=
                order_status,

            payment_source=
                payment_source,

            order_type=
                order_type,

            items_total=
                items_total,

            delivery_charge=
                delivery_charge,

            final_total=
                final_total,

            latitude=
                customer_lat,

            longitude=
                customer_lng,

            distance_km=
                round(
                    distance_km,
                    2
                ),

            map_link=
                map_link,

            otp=
                generate_otp(),

            created_at=
                datetime.utcnow(),
        )

        db.session.add(
            new_order
        )

        # Flush gets numeric DB id before commit.
        db.session.flush()

        new_order.order_id = (
            generate_order_code(
                new_order.id
            )
        )

        for verified in verified_items:

            menu_item = verified[
                "menu_item"
            ]

            order_item = OrderItem(
                order_id=
                    new_order.id,

                item_name=
                    menu_item.name,

                quantity=
                    verified[
                        "quantity"
                    ],

                price=
                    verified[
                        "price"
                    ],

                weight=(
                    verified[
                        "weight"
                    ]
                    or verified[
                        "unit"
                    ]
                    or ""
                ),

                category=
                    verified[
                        "category"
                    ],
            )

            # These fields are saved automatically IF you later
            # add them to OrderItem model. The route remains
            # compatible with your current model without them.
            if hasattr(
                OrderItem,
                "mrp"
            ):
                order_item.mrp = (
                    verified[
                        "mrp"
                    ]
                )

            if hasattr(
                OrderItem,
                "unit"
            ):
                order_item.unit = (
                    verified[
                        "unit"
                    ]
                )

            if hasattr(
                OrderItem,
                "item_type"
            ):
                order_item.item_type = (
                    verified[
                        "item_type"
                    ]
                )

            db.session.add(
                order_item
            )

        db.session.commit()

    except Exception as e:
        db.session.rollback()

        print(
            "APP ORDER CREATE ERROR:",
            e
        )

        return jsonify({
            "success": False,
            "message":
                "Unable to create order."
        }), 500

    # ========================================================
    # RESPONSE
    # ========================================================

    return jsonify({
        "success": True,

        "message":
            "Order placed successfully.",

        "order_id":
            new_order.order_id,

        "db_order_id":
            new_order.id,

        "items_total":
            items_total,

        "delivery_charge":
            delivery_charge,

        "delivery_message":
            delivery_msg,

        "final_total":
            final_total,

        "category_type":
            getattr(
                restaurant,
                "category_type",
                ""
            )
            or "",
    }), 201
# ============================================================
# RUCHIGO APP - RAZORPAY API ADAPTERS
#
# Reuses your existing:
#   razorpay_client
#   RAZORPAY_KEY_ID
#   Order model
#   db
#
# Flutter sends the public RucHiGo order_id, not the DB integer ID.
# ============================================================

from datetime import datetime
from flask import request, jsonify


@app.route("/api/app/payment/create", methods=["POST"])
def app_create_payment():
    data = request.get_json(silent=True) or {}

    public_order_id = (
        data.get("order_id")
        or ""
    ).strip()

    if not public_order_id:
        return jsonify({
            "success": False,
            "message": "Order ID required"
        }), 400

    order = (
        Order.query
        .filter_by(order_id=public_order_id)
        .first()
    )

    if not order:
        return jsonify({
            "success": False,
            "message": "Order not found"
        }), 404

    if order.status == "Cancelled":
        return jsonify({
            "success": False,
            "message": "Cancelled order cannot be paid"
        }), 400

    if order.payment_status == "Paid":
        return jsonify({
            "success": False,
            "message": "Order already paid"
        }), 400

    try:
        # Create a fresh Razorpay order for every retry.
        # This avoids reusing a failed/expired payment session.
        payment = razorpay_client.order.create({
            "amount": int(round(float(order.final_total or 0) * 100)),
            "currency": "INR",
            "receipt": f"order_{order.id}"
        })

        order.payment_order_id = payment["id"]
        order.payment_type = "Online"

        # Keep order in a payment-waiting state until verified.
        if order.payment_status != "Paid":
            order.payment_status = "Pending"

        if order.status in (
            None,
            "",
            "Pending",
        ):
            order.status = "Pending Payment"

        db.session.commit()

        return jsonify({
            "success": True,
            "key": RAZORPAY_KEY_ID,
            "amount": payment["amount"],
            "currency": "INR",
            "razorpay_order_id": payment["id"],
            "order_id": order.order_id,
            "name": order.customer_name or "",
            "email": order.email or "",
            "contact": order.phone or ""
        }), 200

    except Exception as e:
        db.session.rollback()

        print(
            "APP CREATE PAYMENT ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "message": "Unable to create payment"
        }), 500


@app.route("/api/app/payment/verify", methods=["POST"])
def app_verify_payment():
    data = request.get_json(silent=True) or {}

    public_order_id = (
        data.get("order_id")
        or ""
    ).strip()

    razorpay_order_id = (
        data.get("razorpay_order_id")
        or ""
    ).strip()

    razorpay_payment_id = (
        data.get("razorpay_payment_id")
        or ""
    ).strip()

    razorpay_signature = (
        data.get("razorpay_signature")
        or ""
    ).strip()

    if not all([
        public_order_id,
        razorpay_order_id,
        razorpay_payment_id,
        razorpay_signature,
    ]):
        return jsonify({
            "success": False,
            "paid": False,
            "message": "Incomplete payment verification data"
        }), 400

    order = (
        Order.query
        .filter_by(order_id=public_order_id)
        .first()
    )

    if not order:
        return jsonify({
            "success": False,
            "paid": False,
            "message": "Order not found"
        }), 404

    if order.status == "Cancelled":
        return jsonify({
            "success": False,
            "paid": False,
            "message": "Order is cancelled"
        }), 400

    if order.payment_status == "Paid":
        return jsonify({
            "success": True,
            "paid": True,
            "order_id": order.order_id,
            "final_total": float(order.final_total or 0)
        }), 200

    # Important safety check:
    # verify that the callback belongs to the Razorpay order
    # currently stored against this RucHiGo order.
    if (
        order.payment_order_id
        and order.payment_order_id != razorpay_order_id
    ):
        return jsonify({
            "success": False,
            "paid": False,
            "message": "Payment order mismatch"
        }), 400

    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature
        })

        # Ask Razorpay for the real method instead of hard-coding UPI.
        payment = razorpay_client.payment.fetch(
            razorpay_payment_id
        )

        payment_method = (
            payment.get("method")
            or ""
        ).upper()

        acquirer_data = (
            payment.get("acquirer_data")
            or {}
        )

        order.payment_status = "Paid"
        order.payment_type = "Online"
        order.payment_verified = True

        order.payment_id = razorpay_payment_id
        order.payment_order_id = razorpay_order_id
        order.payment_signature = razorpay_signature
        order.payment_time = datetime.utcnow()

        order.payment_method_used = (
            payment_method
            or "ONLINE"
        )

        order.payment_source = "FlutterCheckout"

        order.transaction_reference = (
            acquirer_data.get("upi_transaction_id")
            or acquirer_data.get("rrn")
            or acquirer_data.get("bank_transaction_id")
        )

        if order.status == "Pending Payment":
            order.status = "Pending"

        db.session.commit()

        return jsonify({
            "success": True,
            "paid": True,
            "order_id": order.order_id,
            "final_total": float(order.final_total or 0),
            "payment_method": order.payment_method_used
        }), 200

    except Exception as e:
        db.session.rollback()

        print(
            "APP PAYMENT VERIFY ERROR:",
            repr(e)
        )

        # Do NOT immediately overwrite the database as Failed here.
        # A captured payment can still be recovered by sync/webhook.
        return jsonify({
            "success": False,
            "paid": False,
            "message": "Payment verification failed"
        }), 400


@app.route("/api/app/payment/sync", methods=["POST"])
def app_sync_payment():
    data = request.get_json(silent=True) or {}

    public_order_id = (
        data.get("order_id")
        or ""
    ).strip()

    order = (
        Order.query
        .filter_by(order_id=public_order_id)
        .first()
    )

    if not order:
        return jsonify({
            "success": False,
            "paid": False,
            "message": "Order not found"
        }), 404

    if order.payment_status == "Paid":
        return jsonify({
            "success": True,
            "paid": True,
            "order_id": order.order_id,
            "final_total": float(order.final_total or 0)
        }), 200

    if not order.payment_order_id:
        return jsonify({
            "success": True,
            "paid": False
        }), 200

    try:
        payments = razorpay_client.order.payments(
            order.payment_order_id
        )

        for payment in payments.get("items", []):
            if payment.get("status") != "captured":
                continue

            order.payment_status = "Paid"
            order.payment_verified = True
            order.payment_type = "Online"

            order.payment_id = payment.get("id")
            order.payment_method_used = (
                payment.get("method", "")
                .upper()
                or "ONLINE"
            )

            order.payment_source = "FlutterSync"
            order.payment_time = datetime.utcnow()

            acquirer_data = (
                payment.get("acquirer_data")
                or {}
            )

            order.transaction_reference = (
                acquirer_data.get("upi_transaction_id")
                or acquirer_data.get("rrn")
                or acquirer_data.get("bank_transaction_id")
            )

            if order.status == "Pending Payment":
                order.status = "Pending"

            db.session.commit()

            return jsonify({
                "success": True,
                "paid": True,
                "order_id": order.order_id,
                "final_total": float(order.final_total or 0),
                "payment_method": order.payment_method_used
            }), 200

        return jsonify({
            "success": True,
            "paid": False
        }), 200

    except Exception as e:
        db.session.rollback()

        print(
            "APP PAYMENT SYNC ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "paid": False,
            "message": "Unable to sync payment"
        }), 500

@app.route(
    "/api/app/payment/failed",
    methods=["POST"]
)
def app_payment_failed():

    data = request.get_json(
        silent=True
    ) or {}

    public_order_id = (
        data.get("order_id") or ""
    ).strip()

    order = (
        Order.query
        .filter_by(
            order_id=public_order_id
        )
        .first()
    )

    if not order:
        return jsonify({
            "success": False
        }), 404

    # Already successfully paid.
    if order.payment_status == "Paid":
        return jsonify({
            "success": True,
            "paid": True
        }), 200

    # IMPORTANT:
    # Closing/cancelling Razorpay does NOT cancel
    # the RucHiGo order.
    #
    # Keep it payable until the 15-minute deadline.
    order.status = "Pending Payment"
    order.payment_status = "Pending"

    db.session.commit()

    return jsonify({
        "success": True,
        "paid": False,
        "status": "Pending Payment"
    }), 200
@app.route(
    "/api/app/register-device",
    methods=["POST"]
)
@csrf.exempt
def api_app_register_device():

    data = request.get_json(
        silent=True
    ) or {}

    token = (
        data.get("token") or ""
    ).strip()

    phone = (
        data.get("phone") or ""
    ).strip()

    device = (
        data.get("device") or "android"
    ).strip().lower()

    city = (
        data.get("city") or ""
    ).strip()


    # ========================================================
    # TOKEN REQUIRED
    # ========================================================

    if not token:

        return jsonify({
            "success": False,
            "message": "FCM token is required."
        }), 400


    # ========================================================
    # NORMALIZE PHONE
    # ========================================================

    digits = "".join(
        ch
        for ch in phone
        if ch.isdigit()
    )

    if len(digits) > 10:
        digits = digits[-10:]


    # ========================================================
    # FIND CUSTOMER
    # ========================================================

    customer = None

    if len(digits) == 10:

        normal_phone = digits
        india_phone = "+91" + digits

        customer = (
            Customer.query
            .filter(
                db.or_(
                    Customer.mobile ==
                    normal_phone,

                    Customer.mobile ==
                    india_phone
                )
            )
            .first()
        )


    # ========================================================
    # FIND EXISTING DEVICE TOKEN
    # ========================================================

    fcm = (
        FCMToken.query
        .filter_by(
            token=token
        )
        .first()
    )


    # ========================================================
    # UPDATE EXISTING TOKEN
    # ========================================================

    if fcm:

        fcm.device = device

        fcm.last_active = (
            datetime.utcnow()
        )

        if city:
            fcm.city = city

        if customer:
            fcm.user_id = customer.id


    # ========================================================
    # CREATE NEW TOKEN
    # ========================================================

    else:

        fcm = FCMToken(

            user_id=(
                customer.id
                if customer
                else None
            ),

            token=token,

            device=device,

            city=(
                city
                if city
                else None
            ),

            last_active=
                datetime.utcnow()
        )

        db.session.add(
            fcm
        )


    db.session.commit()


    # ========================================================
    # RESPONSE
    # ========================================================

    return jsonify({

        "success": True,

        "message":
            "Device registered successfully.",

        "linked_customer":
            customer is not None,

        "customer_id":
            (
                customer.id
                if customer
                else None
            ),

        "device":
            device,

        "city":
            fcm.city

    }), 200

# ============================================================
# FLUTTER DELIVERY APP - DEVELOPMENT API
#
# TEMPORARY:
# rider_id is supplied by Flutter until the new rider login
# system is implemented.
#
# Later this will use authenticated rider session/token.
# ============================================================

from flask import request, jsonify
from datetime import datetime

def delivery_order_json(order):

    restaurant = getattr(
        order,
        "restaurant",
        None
    )

    # =========================================================
    # ADDRESS
    # =========================================================

    house_no = getattr(order, "house_no", None)
    landmark = getattr(order, "landmark", None)
    city = getattr(order, "city", None)
    state = getattr(order, "state", None)
    pincode = getattr(order, "pincode", None)

    address_parts = [
        house_no,
        landmark,
        city,
        state,
        pincode,
    ]

    address = ", ".join(
        str(value)
        for value in address_parts
        if value
    )

    # =========================================================
    # ORDER ITEMS
    # =========================================================

    items = []

    for item in getattr(order, "items", []):

        items.append({
            "id":
                getattr(item, "id", None),

            "name":
                getattr(
                    item,
                    "item_name",
                    ""
                ) or "",

            "quantity":
                getattr(
                    item,
                    "quantity",
                    0
                ) or 0,

            "price":
                float(
                    getattr(
                        item,
                        "price",
                        0
                    ) or 0
                ),
        })

    # =========================================================
    # RESTAURANT
    # =========================================================

    restaurant_data = {

        "id":
            restaurant.id
            if restaurant
            else None,

        "name":
            restaurant.name
            if restaurant
            else "",

        "latitude":
            getattr(
                restaurant,
                "latitude",
                None
            )
            if restaurant
            else None,

        "longitude":
            getattr(
                restaurant,
                "longitude",
                None
            )
            if restaurant
            else None,
    }

    # Add restaurant phone only if the model has it.
    if restaurant:

        restaurant_data["phone"] = (
            getattr(
                restaurant,
                "phone",
                None
            )
            or getattr(
                restaurant,
                "phone_number",
                None
            )
            or ""
        )

    else:

        restaurant_data["phone"] = ""

    # =========================================================
    # CUSTOMER
    # =========================================================

    customer_data = {

        "name":
            getattr(
                order,
                "customer_name",
                ""
            ) or "",

        "phone":
            getattr(
                order,
                "phone",
                ""
            ) or "",

        "alt_phone":
            getattr(
                order,
                "alt_phone",
                ""
            ) or "",

        "address":
            address,

        "house_no":
            house_no or "",

        "landmark":
            landmark or "",

        "city":
            city or "",

        "state":
            state or "",

        "pincode":
            pincode or "",

        "latitude":
            getattr(
                order,
                "latitude",
                None
            ),

        "longitude":
            getattr(
                order,
                "longitude",
                None
            ),
    }

    # =========================================================
    # COMPLETE ORDER JSON
    # =========================================================

    return {

        "id":
            order.id,

        "order_id":
            getattr(
                order,
                "order_id",
                ""
            ) or "",

        "status":
            getattr(
                order,
                "status",
                ""
            ) or "",

        "rider_response":
            getattr(
                order,
                "rider_response",
                None
            ),

        # -----------------------------------------------------
        # Restaurant / Customer
        # -----------------------------------------------------

        "restaurant":
            restaurant_data,

        "customer":
            customer_data,

        # -----------------------------------------------------
        # Items
        # -----------------------------------------------------

        "items":
            items,

        # -----------------------------------------------------
        # Order information
        # -----------------------------------------------------

        "order_type":
            getattr(
                order,
                "order_type",
                ""
            ) or "",

        "delivery_note":
            getattr(
                order,
                "delivery_note",
                ""
            ) or "",

        "distance_km":
            float(
                getattr(
                    order,
                    "distance_km",
                    0
                ) or 0
            ),

        # -----------------------------------------------------
        # Money
        # -----------------------------------------------------

        "final_total":
            float(
                getattr(
                    order,
                    "final_total",
                    0
                ) or 0
            ),

        "delivery_charge":
            float(
                getattr(
                    order,
                    "delivery_charge",
                    0
                ) or 0
            ),

        # -----------------------------------------------------
        # Payment
        # -----------------------------------------------------

        "payment_type":
            getattr(
                order,
                "payment_type",
                None
            ) or "COD",

        "payment_status":
            getattr(
                order,
                "payment_status",
                None
            ),

        # -----------------------------------------------------
        # Dates
        # -----------------------------------------------------

        "created_at":
            order.created_at.isoformat()
            if getattr(
                order,
                "created_at",
                None
            )
            else None,

        "assigned_at":
            order.assigned_at.isoformat()
            if getattr(
                order,
                "assigned_at",
                None
            )
            else None,

        "assignment_expires_at":
            order.assignment_expires_at.isoformat()
            if getattr(
                order,
                "assignment_expires_at",
                None
            )
            else None,

        "delivered_time":
            order.delivered_time.isoformat()
            if getattr(
                order,
                "delivered_time",
                None
            )
            else None,
    }

@app.route(
    "/api/delivery/rider/status",
    methods=["POST"]
)
@csrf.exempt
def api_delivery_rider_status():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    rider_id = data.get(
        "rider_id"
    )

    online = bool(
        data.get(
            "online",
            False
        )
    )

    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:

        return jsonify({
            "success": False,
            "message":
                "Delivery partner not found."
        }), 404


    if not rider.is_active:

        return jsonify({
            "success": False,
            "message":
                "Delivery partner account is inactive."
        }), 403


    rider.is_online = online

    rider.last_seen = (
        datetime.utcnow()
    )


    # ========================================================
    # CHECK ACTIVE ORDER
    # ========================================================

    active_order = (

        Order.query

        .filter(

            Order.delivery_person_id
            == rider.id,

            Order.status.in_([
                "Assignment Pending",
                "Out for Delivery",
                "Picked Up",
                "Started"
            ])

        )

        .first()

    )


    rider.is_available = (
        online
        and active_order is None
    )


    db.session.commit()


    # ========================================================
    # IF RIDER JUST CAME ONLINE,
    # CHECK WAITING READY ORDERS
    # ========================================================

    if (
        online
        and rider.is_available
    ):

        try:

            assign_waiting_order_to_rider(
                rider
            )

        except Exception as e:

            print(
                "WAITING ORDER ASSIGN ERROR:",
                e
            )


    return jsonify({

        "success": True,

        "rider": {
            "id":
                rider.id,

            "name":
                rider.name,

            "online":
                rider.is_online,

            "available":
                rider.is_available,
        }

    })


@app.route(
    "/api/delivery/rider/location",
    methods=["POST"]
)
@csrf.exempt
def api_delivery_rider_location():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    rider_id = data.get(
        "rider_id"
    )

    try:

        latitude = float(
            data.get(
                "latitude"
            )
        )

        longitude = float(
            data.get(
                "longitude"
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "success": False,
            "message":
                "Invalid location."
        }), 400


    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )


    if not rider:

        return jsonify({
            "success": False,
            "message":
                "Delivery partner not found."
        }), 404


    # ========================================================
    # UPDATE GPS + HEARTBEAT
    # ========================================================

    rider.latitude = latitude
    rider.longitude = longitude
    rider.last_seen = datetime.utcnow()

    db.session.commit()


    # ========================================================
    # CHECK WAITING READY ORDERS
    # ========================================================

    if rider.is_online and rider.is_available:

        try:

            from dispatch_service import (
                assign_waiting_order_to_rider
            )

            print(
                "========================================"
            )
            print(
                "🔎 LOCATION HEARTBEAT: "
                "CHECK WAITING ORDERS"
            )
            print(
                "RIDER:",
                rider.id,
                rider.name
            )
            print(
                "ONLINE:",
                rider.is_online,
                "AVAILABLE:",
                rider.is_available
            )
            print(
                "========================================"
            )

            assigned_order = (
                assign_waiting_order_to_rider(
                    rider
                )
            )

            if assigned_order:

                print(
                    f"✅ Waiting order "
                    f"{assigned_order.order_id} "
                    f"assigned to {rider.name}"
                )

            else:

                print(
                    f"ℹ️ No waiting Ready order "
                    f"for {rider.name}"
                )

        except Exception as e:

            print(
                "⚠️ Waiting order assignment error:",
                e
            )


    return jsonify({
        "success": True
    }), 200
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@app.route(
    "/api/delivery/dashboard",
    methods=["GET"]
)
def api_delivery_dashboard():

    rider_id = request.args.get(
        "rider_id",
        type=int
    )

    print("\n====================================")
    print("DELIVERY APP DASHBOARD API")
    print("RIDER ID:", rider_id)
    print("====================================")

    # ========================================================
    # VALIDATE RIDER
    # ========================================================

    if not rider_id:
        return jsonify({
            "success": False,
            "message": "Rider ID is required."
        }), 400

    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:

        print("❌ RIDER NOT FOUND")

        return jsonify({
            "success": False,
            "message": "Delivery partner not found."
        }), 404

    print(
        "RIDER:",
        rider.id,
        rider.name,
        "ONLINE:",
        rider.is_online,
        "AVAILABLE:",
        rider.is_available,
        "LAST SEEN:",
        rider.last_seen
    )

    # ========================================================
    # CURRENT UTC TIME
    # ========================================================

    now_utc = datetime.utcnow()

    # ========================================================
    # CLEAN EXPIRED ASSIGNMENTS
    # ========================================================

    expired_orders = (
        Order.query
        .filter(
            Order.delivery_person_id == rider.id,
            Order.status == "Assignment Pending",
            Order.rider_response == "Pending",
            Order.assignment_expires_at.isnot(None),
            Order.assignment_expires_at <= now_utc
        )
        .all()
    )

    if expired_orders:

        print(
            "\n⏰ EXPIRED ASSIGNMENTS:",
            len(expired_orders)
        )

        for order in expired_orders:

            print(
                "⏰ EXPIRED:",
                order.id,
                order.order_id,
                order.assignment_expires_at
            )

            order.rider_response = "Expired"
            order.delivery_person_id = None

        db.session.commit()

        print("✅ EXPIRED ASSIGNMENTS RELEASED")

    # ========================================================
    # ACTIVE ORDERS
    # ========================================================

    active_orders = (
        Order.query
        .filter(
            Order.delivery_person_id == rider.id,

            db.or_(

                # --------------------------------------------
                # Waiting for rider Accept / Reject
                # --------------------------------------------

                db.and_(
                    Order.status == "Assignment Pending",
                    Order.rider_response == "Pending",

                    db.or_(
                        Order.assignment_expires_at.is_(None),
                        Order.assignment_expires_at > now_utc
                    )
                ),

                # --------------------------------------------
                # Accepted / ongoing delivery
                # --------------------------------------------

                Order.status.in_([
                    "Out for Delivery",
                    "Picked Up",
                    "Started"
                ])
            )
        )
        .order_by(
            Order.created_at.desc()
        )
        .all()
    )

    print(
        "\nACTIVE ORDERS FOUND:",
        len(active_orders)
    )

    for order in active_orders:

        print(
            "✅ ACTIVE:",
            order.id,
            order.order_id,
            repr(order.status),
            "RESPONSE:",
            repr(order.rider_response)
        )

    # ========================================================
    # RIDER AVAILABILITY
    # ========================================================

    should_be_available = (
        len(active_orders) == 0
    )

    if rider.is_available != should_be_available:

        print(
            "🔄 RIDER AVAILABLE:",
            rider.is_available,
            "->",
            should_be_available
        )

        rider.is_available = should_be_available

        db.session.commit()

    # ========================================================
    # INDIA TODAY RANGE
    #
    # App day = Asia/Kolkata
    # Database datetime assumed naive UTC
    # ========================================================

    india_tz = ZoneInfo(
        "Asia/Kolkata"
    )

    utc_tz = ZoneInfo(
        "UTC"
    )

    now_india = datetime.now(
        india_tz
    )

    today_start_india = (
        now_india.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )
    )

    tomorrow_start_india = (
        today_start_india
        + timedelta(days=1)
    )

    today_start_utc = (
        today_start_india
        .astimezone(utc_tz)
        .replace(tzinfo=None)
    )

    tomorrow_start_utc = (
        tomorrow_start_india
        .astimezone(utc_tz)
        .replace(tzinfo=None)
    )

    print("\n====================================")
    print("INDIA TODAY RANGE")
    print("INDIA START:", today_start_india)
    print("INDIA END:", tomorrow_start_india)
    print("UTC START:", today_start_utc)
    print("UTC END:", tomorrow_start_utc)
    print("====================================")

    # ========================================================
    # TODAY DELIVERED ORDERS
    # ========================================================

    today_delivered_orders = (
        Order.query
        .filter(
            Order.delivery_person_id == rider.id,
            Order.status == "Delivered",
            Order.delivered_time.isnot(None),
            Order.delivered_time >= today_start_utc,
            Order.delivered_time < tomorrow_start_utc
        )
        .order_by(
            Order.delivered_time.desc()
        )
        .all()
    )

    # ========================================================
    # TODAY STATS
    # ========================================================

    today_deliveries = len(
        today_delivered_orders
    )

    today_cod_deliveries = 0
    today_online_deliveries = 0

    today_cash_collected = 0.0
    today_online_amount = 0.0

    today_total_order_amount = 0.0
    today_delivery_charges = 0.0

    # ========================================================
    # CALCULATE TODAY PAYMENT BREAKDOWN
    # ========================================================

    for order in today_delivered_orders:

        payment_type = str(
            order.payment_type or ""
        ).strip().lower()

        order_amount = float(
            order.final_total or 0
        )

        delivery_charge = float(
            order.delivery_charge or 0
        )

        # --------------------------------------------
        # Total delivered order value
        # --------------------------------------------

        today_total_order_amount += (
            order_amount
        )

        # --------------------------------------------
        # Total delivery charges
        # --------------------------------------------

        today_delivery_charges += (
            delivery_charge
        )

        print(
            "PAYMENT CHECK:",
            order.order_id,
            "TYPE:",
            repr(order.payment_type),
            "NORMALIZED:",
            payment_type,
            "TOTAL:",
            order_amount
        )

        # --------------------------------------------
        # COD / CASH ORDER
        # --------------------------------------------

        if payment_type in [
            "cod",
            "cash",
            "cash on delivery",
            "cash_on_delivery"
        ]:

            today_cod_deliveries += 1

            today_cash_collected += (
                order_amount
            )

        # --------------------------------------------
        # ONLINE ORDER
        # --------------------------------------------

        elif payment_type in [
            "online",
            "online payment",
            "online_payment",
            "upi",
            "razorpay",
            "prepaid",
            "paid online"
        ]:

            today_online_deliveries += 1

            today_online_amount += (
                order_amount
            )

        # --------------------------------------------
        # Unknown payment type
        # --------------------------------------------

        else:

            print(
                "⚠️ UNKNOWN PAYMENT TYPE:",
                order.id,
                order.order_id,
                repr(order.payment_type)
            )

    # ========================================================
    # TOTAL HANDLED
    #
    # This is customer order value handled today.
    #
    # Cash + Online
    # ========================================================

    today_total_handled = (
        today_cash_collected
        + today_online_amount
    )

    # ========================================================
    # RIDER EARNINGS
    #
    # Currently treating delivery charge as rider earning.
    # ========================================================

    today_earnings = (
        today_delivery_charges
    )

    # ========================================================
    # DEBUG TODAY STATS
    # ========================================================

    print("\n====================================")
    print("📊 TODAY RIDER OVERVIEW")
    print("RIDER:", rider.id, rider.name)

    print(
        "DELIVERED:",
        today_deliveries
    )

    print(
        "COD DELIVERIES:",
        today_cod_deliveries
    )

    print(
        "ONLINE DELIVERIES:",
        today_online_deliveries
    )

    print(
        "CASH COLLECTED:",
        round(
            today_cash_collected,
            2
        )
    )

    print(
        "ONLINE AMOUNT:",
        round(
            today_online_amount,
            2
        )
    )

    print(
        "TOTAL HANDLED:",
        round(
            today_total_handled,
            2
        )
    )

    print(
        "TOTAL ORDER AMOUNT:",
        round(
            today_total_order_amount,
            2
        )
    )

    print(
        "DELIVERY CHARGES:",
        round(
            today_delivery_charges,
            2
        )
    )

    print(
        "EARNINGS:",
        round(
            today_earnings,
            2
        )
    )

    print("====================================")

    # ========================================================
    # RESPONSE
    # ========================================================

    response_data = {

        "success": True,

        "rider": {

            "id":
                rider.id,

            "name":
                rider.name or "",

            "phone":
                rider.phone or "",

            "online":
                bool(
                    rider.is_online
                ),

            "available":
                bool(
                    rider.is_available
                ),

            "last_seen":
                rider.last_seen.isoformat()
                if rider.last_seen
                else None,
        },

        "stats": {

            # --------------------------------------------
            # Today deliveries
            # --------------------------------------------

            "today_deliveries":
                today_deliveries,

            # --------------------------------------------
            # COD information
            # --------------------------------------------

            "today_cod_deliveries":
                today_cod_deliveries,

            "today_cash_collected":
                round(
                    today_cash_collected,
                    2
                ),

            # --------------------------------------------
            # Online information
            # --------------------------------------------

            "today_online_deliveries":
                today_online_deliveries,

            "today_online_amount":
                round(
                    today_online_amount,
                    2
                ),

            # --------------------------------------------
            # Total handled value
            # --------------------------------------------

            "today_total_handled":
                round(
                    today_total_handled,
                    2
                ),

            # --------------------------------------------
            # Total final_total of today's delivered orders
            # --------------------------------------------

            "today_order_amount":
                round(
                    today_total_order_amount,
                    2
                ),

            # --------------------------------------------
            # Delivery charges
            # --------------------------------------------

            "today_delivery_charges":
                round(
                    today_delivery_charges,
                    2
                ),

            # --------------------------------------------
            # Rider earnings
            # --------------------------------------------

            "today_earnings":
                round(
                    today_earnings,
                    2
                ),

            # --------------------------------------------
            # Backward compatibility
            # --------------------------------------------

            "deliveries":
                today_deliveries,

            "earnings":
                round(
                    today_earnings,
                    2
                ),
        },

        "orders": [

            delivery_order_json(order)

            for order in active_orders
        ]
    }

    # ========================================================
    # FINAL DEBUG
    # ========================================================

    print("\n====================================")
    print("DELIVERY DASHBOARD RESPONSE")
    print(
        "ONLINE:",
        response_data["rider"]["online"]
    )
    print(
        "AVAILABLE:",
        response_data["rider"]["available"]
    )
    print(
        "ACTIVE ORDERS:",
        len(
            response_data["orders"]
        )
    )

    print(
        "TODAY DELIVERED:",
        response_data["stats"][
            "today_deliveries"
        ]
    )

    print(
        "COD ORDERS:",
        response_data["stats"][
            "today_cod_deliveries"
        ]
    )

    print(
        "CASH:",
        response_data["stats"][
            "today_cash_collected"
        ]
    )

    print(
        "ONLINE ORDERS:",
        response_data["stats"][
            "today_online_deliveries"
        ]
    )

    print(
        "ONLINE AMOUNT:",
        response_data["stats"][
            "today_online_amount"
        ]
    )

    print(
        "TOTAL HANDLED:",
        response_data["stats"][
            "today_total_handled"
        ]
    )

    print(
        "DELIVERY CHARGES:",
        response_data["stats"][
            "today_delivery_charges"
        ]
    )

    print(
        "EARNINGS:",
        response_data["stats"][
            "today_earnings"
        ]
    )

    print("====================================\n")

    return jsonify(
        response_data
    ), 200

@app.route(
    "/api/delivery/order/<int:order_id>/accept",
    methods=["POST"]
)
@csrf.exempt
def api_delivery_accept_order(order_id):

    # ========================================================
    # REQUEST
    # ========================================================

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    rider_id = data.get(
        "rider_id"
    )

    # ========================================================
    # RIDER ID
    # ========================================================

    try:

        rider_id = int(
            rider_id
        )

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message": "Invalid delivery partner."
        }), 400

    # ========================================================
    # GET RIDER
    # ========================================================

    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:

        return jsonify({
            "success": False,
            "message": "Delivery partner not found."
        }), 404

    if not rider.is_active:

        return jsonify({
            "success": False,
            "message": "Delivery partner account is inactive."
        }), 403

    # ========================================================
    # GET ORDER
    # ========================================================

    order = db.session.get(
        Order,
        order_id
    )

    if not order:

        return jsonify({
            "success": False,
            "message": "Order not found."
        }), 404

    # ========================================================
    # SECURITY
    # Only assigned rider can accept
    # ========================================================

    if order.delivery_person_id != rider.id:

        return jsonify({
            "success": False,
            "message": "This order is not assigned to you."
        }), 403

    # ========================================================
    # STATUS CHECK
    # ========================================================

    if order.status != "Assignment Pending":

        return jsonify({
            "success": False,
            "message": (
                "Order assignment is no longer pending."
            )
        }), 409

    # ========================================================
    # RESPONSE CHECK
    # ========================================================

    if getattr(
        order,
        "rider_response",
        None
    ) not in (
        None,
        "Pending"
    ):

        return jsonify({
            "success": False,
            "message": "This order has already been answered."
        }), 409

    # ========================================================
    # EXPIRY CHECK
    # ========================================================

    now = datetime.utcnow()

    if (
        order.assignment_expires_at
        and now > order.assignment_expires_at
    ):

        return jsonify({
            "success": False,
            "message": "Order assignment has expired."
        }), 409

    # ========================================================
    # ACCEPT
    # ========================================================

    order.status = "Out for Delivery"

    order.rider_response = "Accepted"

    order.accepted_at = now

    # Assignment timer is finished.
    order.assignment_expires_at = None

    # Rider remains unavailable because
    # they now have an active delivery.
    rider.is_available = False

    rider.last_seen = now

    # ========================================================
    # SAVE
    # ========================================================

    try:

        db.session.commit()

    except Exception as e:

        db.session.rollback()

        print(
            "❌ ACCEPT ORDER DB ERROR:",
            e
        )

        return jsonify({
            "success": False,
            "message": "Unable to accept order."
        }), 500

    # ========================================================
    # LOG
    # ========================================================

    print(
        "========================================"
    )

    print(
        "✅ DELIVERY ORDER ACCEPTED"
    )

    print(
        "ORDER:",
        order.id,
        order.order_id
    )

    print(
        "RIDER:",
        rider.id,
        rider.name
    )

    print(
        "STATUS:",
        order.status
    )

    print(
        "RIDER RESPONSE:",
        order.rider_response
    )

    print(
        "========================================"
    )

    # ========================================================
    # RESPONSE
    # ========================================================

    return jsonify({

        "success": True,

        "message": "Order accepted successfully.",

        "order": {

            "id":
                order.id,

            "order_id":
                order.order_id,

            "status":
                order.status,

            "rider_response":
                order.rider_response
        }

    }), 200

@app.route(
    "/api/delivery/order/<int:order_id>/reject",
    methods=["POST"]
)
@csrf.exempt
def api_delivery_reject_order(order_id):

    data = request.get_json(silent=True) or {}

    rider_id = data.get("rider_id")

    # --------------------------------------------------------
    # Flutter automatic timeout can send either name
    # --------------------------------------------------------

    auto_reject = bool(
        data.get("autoReject")
        or data.get("auto_reject")
    )

    reason = (
        data.get("reason")
        or "Rejected by rider"
    )

    # ========================================================
    # VALIDATE RIDER ID
    # ========================================================

    try:

        rider_id = int(rider_id)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message": "Invalid rider."
        }), 400

    try:

        # ====================================================
        # LOCK ORDER
        # ====================================================

        order = (
            Order.query
            .filter(
                Order.id == order_id
            )
            .with_for_update()
            .first()
        )

        if not order:

            db.session.rollback()

            return jsonify({
                "success": False,
                "message": "Order not found."
            }), 404

        # ====================================================
        # LOCK RIDER
        # ====================================================

        rider = (
            DeliveryPerson.query
            .filter(
                DeliveryPerson.id == rider_id
            )
            .with_for_update()
            .first()
        )

        if not rider:

            db.session.rollback()

            return jsonify({
                "success": False,
                "message": "Rider not found."
            }), 404

        # ====================================================
        # SECURITY
        # ====================================================

        if order.delivery_person_id != rider.id:

            db.session.rollback()

            return jsonify({
                "success": False,
                "message":
                    "This order is not assigned to you."
            }), 403

        # ====================================================
        # MUST BE ASSIGNMENT PENDING
        # ====================================================

        if order.status != "Assignment Pending":

            db.session.rollback()

            return jsonify({
                "success": False,
                "message":
                    "Order assignment is no longer pending."
            }), 409

        # ====================================================
        # MUST NOT ALREADY BE ANSWERED
        # ====================================================

        rider_response = (
            getattr(
                order,
                "rider_response",
                None
            )
            or ""
        ).strip().lower()

        if rider_response not in (
            "",
            "pending"
        ):

            db.session.rollback()

            return jsonify({
                "success": False,
                "message":
                    "This order has already been answered."
            }), 409

        # ====================================================
        # DETERMINE WHETHER THIS IS AN EXPIRY
        # ====================================================

        now = datetime.utcnow()

        assignment_expires_at = getattr(
            order,
            "assignment_expires_at",
            None
        )

        assignment_expired = (
            assignment_expires_at is not None
            and now >= assignment_expires_at
        )

        # Automatic timer OR backend expiry = Expired
        is_expired = (
            auto_reject
            or assignment_expired
        )

        # ====================================================
        # LOG
        # ====================================================

        if is_expired:

            print(
                f"⏰ ASSIGNMENT EXPIRED | "
                f"Rider {rider.id} "
                f"({rider.name}) | "
                f"Order {order.order_id}"
            )

        else:

            print(
                f"🚫 RIDER REJECTED | "
                f"Rider {rider.id} "
                f"({rider.name}) | "
                f"Order {order.order_id} | "
                f"Reason: {reason}"
            )

        # ====================================================
        # CHECK OTHER ACTIVE ORDERS
        # ====================================================
        #
        # Example:
        #
        # Order A = Out for Delivery
        # Order B = Assignment Pending
        #
        # Rider rejects/expires B
        #
        # Rider MUST remain unavailable because A
        # is still active.
        #
        # ====================================================

        other_active_orders = (
            Order.query
            .filter(
                Order.delivery_person_id == rider.id,
                Order.id != order.id,
                Order.status.in_([
                    "Assignment Pending",
                    "Out for Delivery",
                    "Picked Up",
                    "Started"
                ])
            )
            .count()
        )

        # ====================================================
        # RELEASE RIDER ONLY IF NO OTHER ACTIVE ORDER
        # ====================================================

        if other_active_orders == 0:

            rider.is_available = True

            print(
                f"✅ Rider {rider.id} "
                f"is now AVAILABLE."
            )

        else:

            rider.is_available = False

            print(
                f"🔒 Rider {rider.id} "
                f"remains UNAVAILABLE. "
                f"Other active orders: "
                f"{other_active_orders}"
            )

        rider.last_seen = now

        # ====================================================
        # RETURN ORDER TO READY
        # ====================================================

        order.delivery_person_id = None

        if hasattr(
            order,
            "delivery_boy_name"
        ):

            order.delivery_boy_name = None

        if hasattr(
            order,
            "delivery_boy_phone"
        ):

            order.delivery_boy_phone = None

        order.status = "Ready"

        # ====================================================
        # MANUAL REJECT vs EXPIRY
        # ====================================================

        if is_expired:

            # -----------------------------------------------
            # TIMER EXPIRED
            # -----------------------------------------------

            order.rider_response = "Expired"

            # Expired orders should NOT enter rejection cooldown
            if hasattr(
                order,
                "rejected_at"
            ):

                order.rejected_at = None

            if hasattr(
                order,
                "rejection_reason"
            ):

                order.rejection_reason = (
                    "Assignment expired"
                )

        else:

            # -----------------------------------------------
            # RIDER MANUALLY REJECTED
            # -----------------------------------------------

            order.rider_response = "Rejected"

            if hasattr(
                order,
                "rejected_at"
            ):

                order.rejected_at = now

            if hasattr(
                order,
                "rejection_reason"
            ):

                order.rejection_reason = reason

        # ====================================================
        # CLEAR ASSIGNMENT INFORMATION
        # ====================================================

        if hasattr(
            order,
            "assigned_at"
        ):

            order.assigned_at = None

        if hasattr(
            order,
            "assignment_expires_at"
        ):

            order.assignment_expires_at = None

        # ====================================================
        # SAVE
        # ====================================================

        db.session.commit()

        # ====================================================
        # LOG FINAL STATE
        # ====================================================

        print(
            "========================================"
        )

        if is_expired:

            print(
                "✅ ORDER EXPIRED"
            )

        else:

            print(
                "✅ ORDER REJECTED"
            )

        print(
            "ORDER:",
            order.order_id
        )

        print(
            "STATUS:",
            order.status
        )

        print(
            "RIDER RESPONSE:",
            order.rider_response
        )

        print(
            "RIDER:",
            order.delivery_person_id
        )

        print(
            "OTHER ACTIVE ORDERS:",
            other_active_orders
        )

        print(
            "RIDER AVAILABLE:",
            rider.is_available
        )

        print(
            "========================================"
        )

        # ====================================================
        # RESPONSE
        # ====================================================

        if is_expired:

            message = (
                "Order assignment expired "
                "and returned to Ready."
            )

        else:

            message = (
                "Order rejected "
                "and returned to Ready."
            )

        return jsonify({

            "success": True,

            "message":
                message,

            "order_id":
                order.id,

            "order_number":
                order.order_id,

            "status":
                order.status,

            "rider_response":
                order.rider_response,

            "reason":
                (
                    "Assignment expired"
                    if is_expired
                    else reason
                ),

            "expired":
                is_expired,

            "reassigned":
                False,

            "next_rider":
                None,

            "rider_available":
                rider.is_available,

            "other_active_orders":
                other_active_orders

        }), 200

    # ========================================================
    # DATABASE ERROR
    # ========================================================

    except SQLAlchemyError as error:

        db.session.rollback()

        app.logger.exception(
            "Database error rejecting "
            "order %s: %s",
            order_id,
            error
        )

        return jsonify({

            "success": False,

            "message":
                "Database error while rejecting order."
        }), 500

    # ========================================================
    # UNKNOWN ERROR
    # ========================================================

    except Exception as error:

        db.session.rollback()

        app.logger.exception(
            "Unexpected error rejecting "
            "order %s: %s",
            order_id,
            error
        )

        return jsonify({

            "success": False,

            "message":
                "Unable to reject the order."
        }), 500
@app.route(
    "/api/delivery/order/<int:order_id>/start",
    methods=["POST"]
)
@csrf.exempt
def api_delivery_start_order(order_id):

    data = request.get_json(silent=True) or {}

    rider_id = data.get("rider_id")

    if not rider_id:
        return jsonify({
            "success": False,
            "message": "Rider ID is required."
        }), 400

    order = db.session.get(
        Order,
        order_id
    )

    if not order:
        return jsonify({
            "success": False,
            "message": "Order not found."
        }), 404

    # =========================================================
    # RIDER SECURITY
    # =========================================================

    if order.delivery_person_id != rider_id:

        return jsonify({
            "success": False,
            "message": (
                "This order is not assigned "
                "to you."
            )
        }), 403

    # =========================================================
    # FINAL / INVALID STATES
    # =========================================================

    order_status = (
        str(order.status or "")
        .strip()
        .lower()
    )

    if order_status in {
        "delivered",
        "completed",
        "cancelled",
        "canceled"
    }:

        return jsonify({
            "success": False,
            "message": (
                "This order cannot be started."
            )
        }), 400

    # =========================================================
    # PICKUP MUST BE VERIFIED FIRST
    # =========================================================

    if order.pickup_status not in {
        "qr_verified",
        "restaurant_confirmed",
        "picked_up"
    }:

        return jsonify({
            "success": False,
            "message": (
                "Please verify pickup at "
                "the restaurant first."
            )
        }), 409

    # =========================================================
    # ALREADY STARTED
    # =========================================================

    if order_status == "started":

        return jsonify({
            "success": True,
            "message": (
                "Delivery has already been started."
            ),
            "already_started": True,
            "order": delivery_order_json(order)
        }), 200

    # =========================================================
    # START DELIVERY
    # =========================================================

    order.status = "Started"

    db.session.commit()

    # =========================================================
    # LIVE CUSTOMER / RESTAURANT UPDATE
    # =========================================================

    try:

        socketio.emit(
            "order_status_update",
            {
                "order_id": order.order_id,
                "status": order.status,
                "pickup_status": order.pickup_status,
                "delivery_person_id": (
                    order.delivery_person_id
                )
            },
            room=f"order_{order.order_id}"
        )

    except Exception as e:

        print(
            "⚠️ Start delivery Socket.IO error:",
            e
        )

    # =========================================================
    # RESPONSE
    # =========================================================

    return jsonify({

        "success": True,

        "message": (
            "Delivery started successfully."
        ),

        "status": order.status,

        "pickup_status": (
            order.pickup_status
        ),

        "order": delivery_order_json(order)

    }), 200
@app.route(
    "/api/delivery/order/<int:order_id>/complete",
    methods=["POST"]
)
@csrf.exempt
def api_complete_delivery(order_id):

    data = request.get_json(silent=True) or {}

    rider_id = data.get("rider_id")

    entered_otp = str(
        data.get("otp", "")
    ).strip()

    # ========================================================
    # VALIDATE RIDER
    # ========================================================

    try:

        rider_id = int(rider_id)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message": "Invalid delivery partner."
        }), 400

    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:

        return jsonify({
            "success": False,
            "message":
                "Delivery partner not found."
        }), 404

    # ========================================================
    # GET ORDER
    # ========================================================

    order = db.session.get(
        Order,
        order_id
    )

    if not order:

        return jsonify({
            "success": False,
            "message": "Order not found."
        }), 404

    # ========================================================
    # SECURITY
    # ========================================================

    if order.delivery_person_id != rider.id:

        return jsonify({
            "success": False,
            "message":
                "This order is not assigned to you."
        }), 403

    # ========================================================
    # DELIVERY MUST BE STARTED
    # ========================================================

    if order.status != "Started":

        return jsonify({
            "success": False,
            "message":
                "Start delivery before completing the order."
        }), 400

    # ========================================================
    # OTP CHECK
    # ========================================================

    if not order.otp:

        return jsonify({
            "success": False,
            "message":
                "Delivery OTP is not available."
        }), 400

    if str(order.otp).strip() != entered_otp:

        return jsonify({
            "success": False,
            "message":
                "Invalid OTP. Please try again."
        }), 400

    # ========================================================
    # ONLINE PAYMENT SAFETY
    # ========================================================

    if (
        order.payment_type == "Online"
        and order.payment_status != "Paid"
    ):

        return jsonify({
            "success": False,
            "message":
                "Customer online payment is not completed."
        }), 400

    # ========================================================
    # COMPLETE DELIVERY
    # ========================================================

    now = datetime.utcnow()

    order.status = "Delivered"

    order.delivered_time = now

    # OTP cannot be reused
    order.otp = None

    # ========================================================
    # CLEAR ASSIGNMENT STATE
    # ========================================================

    order.rider_response = "Accepted"

    order.assignment_expires_at = None

    # ========================================================
    # RELEASE RIDER
    # ========================================================

    rider.last_seen = now

    # Rider is now ready for another delivery.
    rider.is_available = True

    # ========================================================
    # REWARD COINS
    # ========================================================

    coins_earned = 0

    try:

        coins_earned = add_coins(
            order.customer_id,
            order.items_total,
            order.id
        ) or 0

    except Exception as e:

        print(
            "REWARD COINS ERROR:",
            e
        )

    # ========================================================
    # SAVE DELIVERY
    #
    # IMPORTANT:
    # We DO NOT assign the next order here.
    # ========================================================

    try:

        db.session.commit()

    except Exception as e:

        db.session.rollback()

        print(
            "❌ DELIVERY COMPLETE DB ERROR:",
            e
        )

        return jsonify({
            "success": False,
            "message":
                "Unable to complete delivery."
        }), 500

    # ========================================================
    # LOG
    # ========================================================

    print(
        "========================================"
    )

    print(
        "✅ DELIVERY COMPLETED"
    )

    print(
        "ORDER:",
        order.order_id
    )

    print(
        "RIDER:",
        rider.id,
        rider.name
    )

    print(
        "STATUS:",
        order.status
    )

    print(
        "RIDER AVAILABLE:",
        rider.is_available
    )

    print(
        "NEXT ORDER:",
        "NOT ASSIGNED IN COMPLETE ROUTE"
    )

    print(
        "========================================"
    )

    # ========================================================
    # RESPONSE
    # ========================================================

    return jsonify({

        "success": True,

        "message":
            "Order delivered successfully.",

        "order": {

            "id":
                order.id,

            "order_id":
                order.order_id,

            "status":
                order.status
        },

        "coins_earned":
            coins_earned,

        "next_order_assigned":
            False,

        "next_order":
            None,

        "rider": {

            "id":
                rider.id,

            "is_available":
                rider.is_available,

            "is_online":
                rider.is_online
        }
    }), 200


@app.route(
    "/api/delivery/history",
    methods=["GET"]
)
def api_delivery_history():

    # ========================================================
    # RIDER
    # ========================================================

    rider_id = request.args.get(
        "rider_id",
        type=int
    )

    if not rider_id:
        return jsonify({
            "success": False,
            "message": "Rider ID required."
        }), 400


    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:
        return jsonify({
            "success": False,
            "message": "Delivery partner not found."
        }), 404


    # ========================================================
    # INDIA DATE
    # ========================================================

    india_tz = ZoneInfo("Asia/Kolkata")
    utc_tz = ZoneInfo("UTC")

    now_india = datetime.now(
        india_tz
    )

    today = now_india.date()

    yesterday = (
        today - timedelta(days=1)
    )


    # ========================================================
    # COMPLETED / HISTORY ORDERS
    # ========================================================

    history = (

        Order.query

        .filter(

            Order.delivery_person_id == rider.id,

            Order.status.in_([
                "Delivered",
                "Customer Not Available"
            ])

        )

        .order_by(
            Order.updated_at.desc()
        )

        .all()

    )


    # ========================================================
    # SERIALIZE ORDERS
    # ========================================================

    orders_data = []


    for order in history:

        restaurant = getattr(
            order,
            "restaurant",
            None
        )


        # ====================================================
        # ORDER TIME
        # ====================================================

        raw_order_time = (

            order.delivered_time
            or order.updated_at
            or order.created_at

        )


        order_time_india = None
        order_date = None


        if raw_order_time:

            try:

                # DB timestamps assumed naive UTC
                utc_time = raw_order_time.replace(
                    tzinfo=utc_tz
                )

                order_time_india = (
                    utc_time.astimezone(
                        india_tz
                    )
                )

                order_date = (
                    order_time_india.date()
                )

            except Exception as error:

                print(
                    "⚠️ HISTORY DATE ERROR:",
                    order.id,
                    error
                )


        # ====================================================
        # DAY CATEGORY
        # ====================================================

        if order_date == today:

            day_category = "Today"

        elif order_date == yesterday:

            day_category = "Yesterday"

        else:

            day_category = "Older"


        # ====================================================
        # CUSTOMER ADDRESS
        # ====================================================

        address_parts = [

            getattr(
                order,
                "house_no",
                None
            ),

            getattr(
                order,
                "landmark",
                None
            ),

            getattr(
                order,
                "city",
                None
            ),

            getattr(
                order,
                "state",
                None
            ),

            getattr(
                order,
                "pincode",
                None
            ),

        ]


        address = ", ".join(

            str(part).strip()

            for part in address_parts

            if part
            and str(part).strip()

        )


        # ====================================================
        # ITEMS
        # ====================================================

        items_data = []


        try:

            for item in order.items:

                items_data.append({

                    "id":
                        getattr(
                            item,
                            "id",
                            None
                        ),

                    "name":
                        getattr(
                            item,
                            "name",
                            ""
                        ),

                    "quantity":
                        int(
                            getattr(
                                item,
                                "quantity",
                                0
                            )
                            or 0
                        ),

                    "price":
                        float(
                            getattr(
                                item,
                                "price",
                                0
                            )
                            or 0
                        ),

                })

        except Exception as error:

            print(
                "⚠️ HISTORY ITEMS ERROR:",
                order.id,
                error
            )

            items_data = []


        # ====================================================
        # PAYMENT TYPE
        # ====================================================

        payment_type_raw = str(
            order.payment_type or ""
        ).strip()

        payment_type = (
            payment_type_raw.lower()
        )


        if payment_type in [
            "cod",
            "cash",
            "cash on delivery",
            "cash_on_delivery"
        ]:

            payment_category = "COD"

        elif payment_type in [
            "online",
            "online payment",
            "online_payment",
            "upi",
            "razorpay",
            "prepaid",
            "paid online"
        ]:

            payment_category = "Online"

        else:

            payment_category = (
                payment_type_raw
                if payment_type_raw
                else "Unknown"
            )


        # ====================================================
        # ORDER DATA
        # ====================================================

        orders_data.append({

            "id":
                order.id,

            "order_id":
                order.order_id or "",

            "status":
                order.status or "",

            "day_category":
                day_category,


            # --------------------------------------------
            # Restaurant
            # --------------------------------------------

            "restaurant": {

                "id":
                    restaurant.id
                    if restaurant
                    else None,

                "name":
                    restaurant.name
                    if restaurant
                    else "",

                "phone":
                    getattr(
                        restaurant,
                        "phone",
                        ""
                    )
                    if restaurant
                    else "",

            },


            # --------------------------------------------
            # Customer
            # --------------------------------------------

            "customer": {

                "name":
                    order.customer_name or "",

                "phone":
                    order.phone or "",

                "address":
                    address,

            },


            # --------------------------------------------
            # Delivery
            # --------------------------------------------

            "distance_km":
                float(
                    order.distance_km
                    or 0
                ),

            "delivery_charge":
                float(
                    order.delivery_charge
                    or 0
                ),


            # --------------------------------------------
            # Payment
            # --------------------------------------------

            "final_total":
                float(
                    order.final_total
                    or 0
                ),

            "payment_type":
                payment_category,

            "payment_type_raw":
                payment_type_raw,

            "payment_status":
                getattr(
                    order,
                    "payment_status",
                    None
                ),


            # --------------------------------------------
            # Items
            # --------------------------------------------

            "items":
                items_data,


            # --------------------------------------------
            # Times
            # --------------------------------------------

            "created_at":
                order.created_at.isoformat()
                if order.created_at
                else None,

            "delivered_time":
                order.delivered_time.isoformat()
                if order.delivered_time
                else None,

            "display_time":
                (
                    order_time_india
                    .isoformat()
                    if order_time_india
                    else None
                ),

        })


    # ========================================================
    # DELIVERED ORDERS ONLY
    # ========================================================

    delivered_orders = [

        order

        for order in history

        if order.status == "Delivered"

    ]


    # ========================================================
    # TOTAL STATS
    # ========================================================

    total_deliveries = len(
        delivered_orders
    )


    total_earnings = 0.0
    total_order_value = 0.0

    cod_orders_count = 0
    online_orders_count = 0

    cash_collected = 0.0
    online_amount = 0.0


    # ========================================================
    # CALCULATE TOTALS
    # ========================================================

    for order in delivered_orders:

        payment_type = str(
            order.payment_type or ""
        ).strip().lower()


        final_total = float(
            order.final_total or 0
        )


        delivery_charge = float(
            order.delivery_charge or 0
        )


        total_order_value += (
            final_total
        )


        total_earnings += (
            delivery_charge
        )


        # ----------------------------------------------------
        # COD
        # ----------------------------------------------------

        if payment_type in [
            "cod",
            "cash",
            "cash on delivery",
            "cash_on_delivery"
        ]:

            cod_orders_count += 1

            cash_collected += (
                final_total
            )


        # ----------------------------------------------------
        # ONLINE
        # ----------------------------------------------------

        elif payment_type in [
            "online",
            "online payment",
            "online_payment",
            "upi",
            "razorpay",
            "prepaid",
            "paid online"
        ]:

            online_orders_count += 1

            online_amount += (
                final_total
            )


        else:

            print(
                "⚠️ HISTORY UNKNOWN PAYMENT TYPE:",
                order.id,
                order.order_id,
                repr(order.payment_type)
            )


    # ========================================================
    # TODAY STATS
    # ========================================================

    today_delivered_orders = []


    for order in delivered_orders:

        if not order.delivered_time:
            continue


        try:

            delivered_utc = (
                order.delivered_time.replace(
                    tzinfo=utc_tz
                )
            )

            delivered_india = (
                delivered_utc.astimezone(
                    india_tz
                )
            )


            if delivered_india.date() == today:

                today_delivered_orders.append(
                    order
                )

        except Exception as error:

            print(
                "⚠️ TODAY HISTORY ERROR:",
                order.id,
                error
            )


    today_deliveries = len(
        today_delivered_orders
    )


    today_earnings = sum(

        float(
            order.delivery_charge
            or 0
        )

        for order in today_delivered_orders

    )


    # ========================================================
    # CUSTOMER NOT AVAILABLE COUNT
    # ========================================================

    failed_deliveries = len([

        order

        for order in history

        if order.status
        == "Customer Not Available"

    ])


    # ========================================================
    # DEBUG
    # ========================================================

    print("\n====================================")
    print("📜 DELIVERY HISTORY")
    print("RIDER:", rider.id, rider.name)
    print("TOTAL DELIVERED:", total_deliveries)
    print("TODAY DELIVERED:", today_deliveries)
    print("TOTAL EARNINGS:", total_earnings)
    print("TOTAL ORDER VALUE:", total_order_value)
    print("COD ORDERS:", cod_orders_count)
    print("ONLINE ORDERS:", online_orders_count)
    print("CASH COLLECTED:", cash_collected)
    print("ONLINE AMOUNT:", online_amount)
    print("FAILED:", failed_deliveries)
    print("====================================\n")


    # ========================================================
    # RESPONSE
    # ========================================================

    return jsonify({

        "success": True,


        # ====================================================
        # RIDER
        # ====================================================

        "rider": {

            "id":
                rider.id,

            "name":
                rider.name or "",

        },


        # ====================================================
        # TOTAL STATS
        # ====================================================

        "stats": {

            "total_deliveries":
                total_deliveries,

            "today_deliveries":
                today_deliveries,

            "total_earnings":
                round(
                    total_earnings,
                    2
                ),

            "today_earnings":
                round(
                    today_earnings,
                    2
                ),

            "total_order_value":
                round(
                    total_order_value,
                    2
                ),

            "cod_orders":
                cod_orders_count,

            "online_orders":
                online_orders_count,

            "cash_collected":
                round(
                    cash_collected,
                    2
                ),

            "online_amount":
                round(
                    online_amount,
                    2
                ),

            "failed_deliveries":
                failed_deliveries,

        },


        # ====================================================
        # ORDERS
        # ====================================================

        "count":
            len(
                orders_data
            ),

        "orders":
            orders_data,

    }), 200



@app.route(
    "/api/delivery/rider/fcm-token",
    methods=["POST"]
)
def api_delivery_save_fcm_token():

    data = request.get_json(silent=True) or {}

    rider_id = data.get("rider_id")
    token = str(
        data.get("fcm_token", "")
    ).strip()

    try:
        rider_id = int(rider_id)
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Invalid rider."
        }), 400

    if not token:
        return jsonify({
            "success": False,
            "message": "FCM token required."
        }), 400

    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:
        return jsonify({
            "success": False,
            "message": "Delivery partner not found."
        }), 404

    rider.fcm_token = token

    db.session.commit()

    print(
        "✅ DELIVERY FCM TOKEN SAVED:",
        rider.id,
        rider.name
    )

    return jsonify({
        "success": True,
        "message": "FCM token saved."
    })


# ============================================================
# DELIVERY RIDER ONLINE / OFFLINE STATUS
# + CHECK WAITING READY ORDERS
# ============================================================

@app.route(
    "/api/delivery/status",
    methods=["POST"]
)
@csrf.exempt
def api_delivery_status():

    data = request.get_json(silent=True) or {}

    # ========================================================
    # REQUEST DATA
    # ========================================================

    rider_id = data.get("rider_id")
    is_online = data.get("is_online")

    # ========================================================
    # VALIDATE RIDER ID
    # ========================================================

    try:
        rider_id = int(rider_id)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message": "Invalid rider."
        }), 400

    # ========================================================
    # NORMALIZE ONLINE VALUE
    # ========================================================

    if isinstance(is_online, str):

        is_online = (
            is_online
            .strip()
            .lower()
            in {
                "true",
                "1",
                "yes",
                "on",
            }
        )

    else:

        is_online = bool(is_online)

    # ========================================================
    # GET RIDER
    # ========================================================

    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:

        return jsonify({
            "success": False,
            "message": "Rider not found."
        }), 404

    try:

        # ====================================================
        # UPDATE ONLINE STATUS
        # ====================================================

        rider.is_online = is_online

        # IMPORTANT:
        # Every status request means rider is alive.
        rider.last_seen = datetime.utcnow()

        # ====================================================
        # IF OFFLINE
        # ====================================================

        if not is_online:

            # Offline rider should not receive new orders.
            rider.is_available = False

            db.session.commit()

            print(
                "🔴 RIDER OFFLINE:",
                rider.id,
                rider.name
            )

            return jsonify({
                "success": True,

                "rider": {
                    "id": rider.id,
                    "name": rider.name,
                    "online": rider.is_online,
                    "available": rider.is_available,
                }
            }), 200

        # ====================================================
        # RIDER IS ONLINE
        # ====================================================

        # Check whether rider already has an active order.
        active_order = (
            Order.query
            .filter(
                Order.delivery_person_id == rider.id,

                Order.status.in_([
                    "Assignment Pending",
                    "Started",
                    "Picked Up",
                    "Out for Delivery",
                ])
            )
            .first()
        )

        # ====================================================
        # ACTIVE ORDER EXISTS
        # ====================================================

        if active_order:

            rider.is_available = False

            db.session.commit()

            print(
                f"🟡 Rider {rider.id} "
                f"{rider.name} online but busy with "
                f"{active_order.order_id}"
            )

            return jsonify({
                "success": True,

                "rider": {
                    "id": rider.id,
                    "name": rider.name,
                    "online": True,
                    "available": False,
                },

                "active_order": {
                    "id": active_order.id,
                    "order_id": active_order.order_id,
                    "status": active_order.status,
                }

            }), 200

        # ====================================================
        # NO ACTIVE ORDER
        # ====================================================

        rider.is_available = True

        db.session.commit()

        print(
            "🟢 RIDER ONLINE + AVAILABLE:",
            rider.id,
            rider.name
        )

        # ====================================================
        # CHECK WAITING READY ORDERS
        # ====================================================

        assigned_order = None

        try:

            from dispatch_service import (
                assign_waiting_order_to_rider
            )

            print(
                "========================================"
            )

            print(
                "🔎 CHECKING WAITING ORDERS FOR:",
                rider.id,
                rider.name
            )

            print(
                "========================================"
            )

            assigned_order = (
                assign_waiting_order_to_rider(
                    rider
                )
            )

        except Exception as error:

            app.logger.exception(
                "Waiting order assignment error "
                "for rider %s: %s",
                rider.id,
                error
            )

        # ====================================================
        # REFRESH RIDER
        # ====================================================

        db.session.expire_all()

        rider = db.session.get(
            DeliveryPerson,
            rider_id
        )

        # ====================================================
        # RESPONSE
        # ====================================================

        return jsonify({

            "success": True,

            "rider": {
                "id": rider.id,
                "name": rider.name,
                "online": rider.is_online,
                "available": rider.is_available,
            },

            "assigned_order": (
                {
                    "id": assigned_order.id,
                    "order_id":
                        assigned_order.order_id,
                    "status":
                        assigned_order.status,
                }
                if assigned_order
                else None
            )

        }), 200

    except Exception as error:

        db.session.rollback()

        app.logger.exception(
            "Rider status update failed "
            "for rider %s: %s",
            rider_id,
            error
        )

        return jsonify({
            "success": False,
            "message":
                "Unable to update rider status."
        }), 500

@app.route(
    "/api/delivery/settlement",
    methods=["GET"]
)
def api_delivery_settlement():

    rider_id = request.args.get(
        "rider_id",
        type=int
    )

    if not rider_id:
        return jsonify({
            "success": False,
            "message": "Rider ID is required."
        }), 400

    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:
        return jsonify({
            "success": False,
            "message": "Rider not found."
        }), 404

    india_tz = ZoneInfo(
        "Asia/Kolkata"
    )

    today_date = (
        datetime
        .now(india_tz)
        .date()
    )

    # ==========================================================
    # FIRST:
    # CHECK OLD PENDING BATCHES
    #
    # Example:
    # 28 Aug Batch #5 Pending
    # User opens app on 29 Aug
    #
    # We must still return 28 Aug Batch #5.
    # ==========================================================

    old_pending = (
        RiderSettlement.query
        .filter(
            RiderSettlement.rider_id
            == rider.id,

            db.func.lower(
                RiderSettlement.status
            ) == "pending",

            RiderSettlement.total_deliveries
            > 0,

            RiderSettlement.settlement_date
            < today_date
        )
        .order_by(
            RiderSettlement.settlement_date.asc(),
            RiderSettlement.batch_no.asc(),
            RiderSettlement.id.asc()
        )
        .first()
    )

    if old_pending:

        settlement = old_pending

        print(
            "⚠️ RETURNING PREVIOUS-DAY "
            "PENDING SETTLEMENT"
        )

        print(
            "RIDER:",
            rider.id
        )

        print(
            "DATE:",
            settlement.settlement_date
        )

        print(
            "BATCH:",
            settlement.batch_no
        )

    else:

        settlement = (
            build_rider_daily_settlement(
                rider.id
            )
        )

    # ==========================================================
    # NO SETTLEMENT / NO DELIVERIES
    # ==========================================================

    if settlement is None:

        return jsonify({

            "success": True,

            "rider": {
                "id": rider.id,
                "name": rider.name or "",
            },

            "settlement": {

                "id": 0,

                "batch_no": 0,

                "date":
                    today_date.isoformat(),

                "status":
                    "No Deliveries",

                "total_deliveries": 0,

                "cod_orders": 0,

                "online_orders": 0,

                "cash_collected": 0.0,

                "online_amount": 0.0,

                "total_order_value": 0.0,

                "rider_earnings": 0.0,

                "cash_to_submit": 0.0,

                "platform_to_pay": 0.0,

                "submitted_at": None,

                "verified_at": None,
            }

        }), 200

    # ==========================================================
    # NORMAL SETTLEMENT RESPONSE
    # ==========================================================

    return jsonify({

        "success": True,

        "rider": {
            "id": rider.id,
            "name": rider.name or "",
        },

        "settlement": {

            "id": settlement.id,

            "batch_no": int(
                settlement.batch_no or 1
            ),

            "date": (
                settlement
                .settlement_date
                .isoformat()
                if settlement.settlement_date
                else None
            ),

            "status": (
                settlement.status
                or "Pending"
            ),

            "total_deliveries": int(
                settlement.total_deliveries
                or 0
            ),

            "cod_orders": int(
                settlement.cod_orders
                or 0
            ),

            "online_orders": int(
                settlement.online_orders
                or 0
            ),

            "cash_collected": round(
                float(
                    settlement.cash_collected
                    or 0
                ),
                2
            ),

            "online_amount": round(
                float(
                    settlement.online_amount
                    or 0
                ),
                2
            ),

            "total_order_value": round(
                float(
                    settlement.total_order_value
                    or 0
                ),
                2
            ),

            "rider_earnings": round(
                float(
                    settlement.rider_earnings
                    or 0
                ),
                2
            ),

            "cash_to_submit": round(
                float(
                    settlement.cash_to_submit
                    or 0
                ),
                2
            ),

            "platform_to_pay": round(
                float(
                    settlement.platform_to_pay
                    or 0
                ),
                2
            ),

            "submitted_at": (
                settlement
                .submitted_at
                .isoformat()
                if settlement.submitted_at
                else None
            ),

            "verified_at": (
                settlement
                .verified_at
                .isoformat()
                if settlement.verified_at
                else None
            ),
        }

    }), 200

@app.route(
    "/api/delivery/settlement/submit",
    methods=["POST"]
)
def submit_delivery_settlement():

    data = request.get_json(silent=True) or {}

    rider_id = data.get("rider_id")
    settlement_id = data.get("settlement_id")

    if not rider_id:
        return jsonify({
            "success": False,
            "message": "Rider ID is required."
        }), 400

    if not settlement_id:
        return jsonify({
            "success": False,
            "message": "Settlement ID is required."
        }), 400

    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:
        return jsonify({
            "success": False,
            "message": "Rider not found."
        }), 404

    # IMPORTANT:
    # Load the exact batch shown to the rider.
    # Do NOT rebuild today's settlement here.
    settlement = db.session.get(
        RiderSettlement,
        settlement_id
    )

    if not settlement:
        return jsonify({
            "success": False,
            "message": "Settlement not found."
        }), 404

    # Security: settlement must belong to this rider
    if settlement.rider_id != rider.id:
        return jsonify({
            "success": False,
            "message": "This settlement does not belong to this rider."
        }), 403

    current_status = str(
        settlement.status or ""
    ).strip().lower()

    if current_status == "submitted":
        return jsonify({
            "success": True,
            "message": (
                f"Batch #{settlement.batch_no} "
                f"is already submitted."
            ),
            "settlement": {
                "id": settlement.id,
                "batch_no": int(
                    settlement.batch_no or 1
                ),
                "status": settlement.status
            }
        }), 200

    if current_status == "verified":
        return jsonify({
            "success": False,
            "message": (
                f"Batch #{settlement.batch_no} "
                f"is already verified."
            )
        }), 400

    if current_status != "pending":
        return jsonify({
            "success": False,
            "message": (
                "Only a Pending settlement "
                "can be submitted."
            )
        }), 400

    if int(
        settlement.total_deliveries or 0
    ) <= 0:
        return jsonify({
            "success": False,
            "message": (
                "No deliveries available "
                "to submit."
            )
        }), 400

    now_utc = datetime.utcnow()

    # ==========================================
    # FREEZE EXACT BATCH
    # ==========================================

    settlement.status = "Submitted"
    settlement.submitted_at = now_utc
    settlement.updated_at = now_utc

    db.session.commit()

    print("\n====================================")
    print("✅ RIDER SETTLEMENT SUBMITTED")
    print("RIDER:", rider.id)
    print("SETTLEMENT ID:", settlement.id)
    print("DATE:", settlement.settlement_date)
    print("BATCH:", settlement.batch_no)
    print(
        "DELIVERIES:",
        settlement.total_deliveries
    )
    print(
        "CASH TO SUBMIT:",
        settlement.cash_to_submit
    )
    print(
        "PLATFORM TO PAY:",
        settlement.platform_to_pay
    )
    print(
        "SUBMITTED AT:",
        settlement.submitted_at
    )
    print("====================================\n")

    return jsonify({
        "success": True,
        "message": (
            f"Batch #{settlement.batch_no} "
            f"submitted successfully."
        ),
        "settlement": {
            "id": settlement.id,
            "batch_no": int(
                settlement.batch_no or 1
            ),
            "date": (
                settlement.settlement_date.isoformat()
                if settlement.settlement_date
                else None
            ),
            "status": settlement.status,
            "total_deliveries": int(
                settlement.total_deliveries or 0
            ),
            "cash_to_submit": round(
                float(
                    settlement.cash_to_submit or 0
                ),
                2
            ),
            "platform_to_pay": round(
                float(
                    settlement.platform_to_pay or 0
                ),
                2
            ),
            "submitted_at": (
                settlement.submitted_at.isoformat()
                if settlement.submitted_at
                else None
            )
        }
    }), 200
from datetime import datetime
from zoneinfo import ZoneInfo

@app.route("/admin/rider-settlements")
def admin_rider_settlements():

    india_tz = ZoneInfo("Asia/Kolkata")

    today_date = (
        datetime
        .now(india_tz)
        .date()
    )

    riders = (
        DeliveryPerson.query
        .order_by(
            DeliveryPerson.name.asc()
        )
        .all()
    )

    rider_data = []

    total_cash_collected = 0.0
    total_online_amount = 0.0
    total_rider_earnings = 0.0
    total_cash_to_collect = 0.0
    total_platform_to_pay = 0.0
    total_deliveries = 0

    for rider in riders:

        # Build/update current rider settlement first.
        build_rider_daily_settlement(
            rider.id
        )

        # Show:
        # - every Submitted batch from any date
        # - today's non-empty Pending / Submitted / Verified batches
        settlements = (
            RiderSettlement.query
            .filter(
                RiderSettlement.rider_id == rider.id,
                db.or_(
                    db.func.lower(
                        RiderSettlement.status
                    ) == "submitted",
                    db.and_(
                        RiderSettlement.settlement_date == today_date,
                        RiderSettlement.total_deliveries > 0
                    )
                )
            )
            .order_by(
                RiderSettlement.settlement_date.asc(),
                RiderSettlement.batch_no.asc(),
                RiderSettlement.id.asc()
            )
            .all()
        )

        batch_data = []

        for settlement in settlements:

            cash_collected = float(
                settlement.cash_collected or 0
            )

            online_amount = float(
                settlement.online_amount or 0
            )

            rider_earnings = float(
                settlement.rider_earnings or 0
            )

            cash_to_submit = float(
                settlement.cash_to_submit or 0
            )

            platform_to_pay = float(
                settlement.platform_to_pay or 0
            )

            deliveries = int(
                settlement.total_deliveries or 0
            )

            status = str(
                settlement.status or "Pending"
            ).strip().lower()

            total_cash_collected += cash_collected
            total_online_amount += online_amount
            total_rider_earnings += rider_earnings
            total_deliveries += deliveries

            if status == "submitted":
                total_cash_to_collect += cash_to_submit
                total_platform_to_pay += platform_to_pay

            batch_data.append({
                "settlement": settlement,
                "cash_collected": round(
                    cash_collected,
                    2
                ),
                "online_amount": round(
                    online_amount,
                    2
                ),
                "rider_earnings": round(
                    rider_earnings,
                    2
                ),
                "cash_to_submit": round(
                    cash_to_submit,
                    2
                ),
                "platform_to_pay": round(
                    platform_to_pay,
                    2
                ),
                "deliveries": deliveries,
                "status": status,
            })

        # Keep one rider card, containing all its settlement batches.
        # Skip riders with no visible settlement batches.
        if batch_data:
            rider_data.append({
                "rider": rider,
                "batches": batch_data,
            })

    summary = {
        "total_deliveries": total_deliveries,
        "cash_collected": round(
            total_cash_collected,
            2
        ),
        "online_amount": round(
            total_online_amount,
            2
        ),
        "rider_earnings": round(
            total_rider_earnings,
            2
        ),
        "cash_to_collect": round(
            total_cash_to_collect,
            2
        ),
        "platform_to_pay": round(
            total_platform_to_pay,
            2
        ),
    }

    return render_template(
        "admin_rider_settlements.html",
        rider_data=rider_data,
        summary=summary,
        today_date=today_date
    )


@app.route(
    "/api/admin/rider-settlement/<int:settlement_id>/verify",
    methods=["POST"]
)
def verify_rider_settlement(
    settlement_id
):

    settlement = db.session.get(
        RiderSettlement,
        settlement_id
    )

    if not settlement:
        return jsonify({
            "success": False,
            "message": "Settlement not found."
        }), 404

    current_status = str(
        settlement.status or ""
    ).strip().lower()

    if current_status == "verified":
        return jsonify({
            "success": True,
            "message": "Settlement already verified."
        }), 200

    # Only rider-submitted/frozen batches can be verified.
    if current_status != "submitted":
        return jsonify({
            "success": False,
            "message": (
                f"Batch #{settlement.batch_no} "
                "has not been submitted by the rider yet."
            )
        }), 400

    # Force oldest Submitted batch first.
    older_submitted_batch = (
        RiderSettlement.query
        .filter(
            RiderSettlement.rider_id
            == settlement.rider_id,

            db.func.lower(
                RiderSettlement.status
            ) == "submitted",

            db.or_(
                RiderSettlement.settlement_date
                < settlement.settlement_date,

                db.and_(
                    RiderSettlement.settlement_date
                    == settlement.settlement_date,

                    RiderSettlement.batch_no
                    < settlement.batch_no
                )
            )
        )
        .order_by(
            RiderSettlement.settlement_date.asc(),
            RiderSettlement.batch_no.asc(),
            RiderSettlement.id.asc()
        )
        .first()
    )

    if older_submitted_batch:
        return jsonify({
            "success": False,
            "message": (
                f"Verify "
                f"{older_submitted_batch.settlement_date.strftime('%d %b %Y')} "
                f"Batch #{older_submitted_batch.batch_no} "
                f"before Batch #{settlement.batch_no}."
            )
        }), 400

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    action = str(
        data.get(
            "action",
            ""
        )
    ).strip().lower()

    cash_to_submit = float(
        settlement.cash_to_submit or 0
    )

    platform_to_pay = float(
        settlement.platform_to_pay or 0
    )

    if cash_to_submit > 0:
        if action != "collect":
            return jsonify({
                "success": False,
                "message": "Cash must be collected from rider."
            }), 400

    elif platform_to_pay > 0:
        if action != "pay":
            return jsonify({
                "success": False,
                "message": "Rider payout must be completed."
            }), 400

    else:
        if action != "clear":
            return jsonify({
                "success": False,
                "message": "Invalid settlement action."
            }), 400

    now_utc = datetime.utcnow()

    settlement.status = "Verified"
    settlement.submitted_at = (
        settlement.submitted_at
        or now_utc
    )
    settlement.verified_at = now_utc
    settlement.updated_at = now_utc

    db.session.commit()

    if action == "collect":
        message = (
            f"₹{cash_to_submit:.2f} received. "
            f"Batch {settlement.batch_no} verified."
        )

    elif action == "pay":
        message = (
            f"₹{platform_to_pay:.2f} paid to rider. "
            f"Batch {settlement.batch_no} verified."
        )

    else:
        message = (
            f"Batch {settlement.batch_no} "
            f"verified successfully."
        )

    return jsonify({
        "success": True,
        "message": message,
        "settlement": {
            "id": settlement.id,
            "batch_no": int(
                settlement.batch_no or 1
            ),
            "rider_id": settlement.rider_id,
            "status": settlement.status,
            "cash_to_submit": cash_to_submit,
            "platform_to_pay": platform_to_pay,
            "verified_at": (
                settlement.verified_at.isoformat()
                if settlement.verified_at
                else None
            )
        }
    }), 200

# ==========================================================
# RIDER SETTLEMENT HISTORY
# Add this route in samebackup.py near your other settlement APIs.
# This does NOT change build_rider_daily_settlement().
# ==========================================================

@app.route(
    "/api/delivery/settlement/history",
    methods=["GET"]
)
def api_delivery_settlement_history():

    rider_id = request.args.get(
        "rider_id",
        type=int
    )

    if not rider_id:
        return jsonify({
            "success": False,
            "message": "Rider ID is required."
        }), 400

    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:
        return jsonify({
            "success": False,
            "message": "Rider not found."
        }), 404

    # History contains only frozen/finished batches.
    # Pending batch stays in /api/delivery/settlement.
    settlements = (
        RiderSettlement.query
        .filter(
            RiderSettlement.rider_id == rider.id,
            RiderSettlement.total_deliveries > 0,
            db.func.lower(
                RiderSettlement.status
            ).in_([
                "submitted",
                "verified"
            ])
        )
        .order_by(
            RiderSettlement.settlement_date.desc(),
            RiderSettlement.batch_no.desc(),
            RiderSettlement.id.desc()
        )
        .limit(50)
        .all()
    )

    history = []

    for settlement in settlements:
        history.append({
            "id": settlement.id,
            "batch_no": int(
                settlement.batch_no or 1
            ),
            "date": (
                settlement.settlement_date.isoformat()
                if settlement.settlement_date
                else None
            ),
            "status": settlement.status or "Pending",
            "total_deliveries": int(
                settlement.total_deliveries or 0
            ),
            "cod_orders": int(
                settlement.cod_orders or 0
            ),
            "online_orders": int(
                settlement.online_orders or 0
            ),
            "cash_collected": round(
                float(settlement.cash_collected or 0),
                2
            ),
            "online_amount": round(
                float(settlement.online_amount or 0),
                2
            ),
            "total_order_value": round(
                float(settlement.total_order_value or 0),
                2
            ),
            "rider_earnings": round(
                float(settlement.rider_earnings or 0),
                2
            ),
            "cash_to_submit": round(
                float(settlement.cash_to_submit or 0),
                2
            ),
            "platform_to_pay": round(
                float(settlement.platform_to_pay or 0),
                2
            ),
            "submitted_at": (
                settlement.submitted_at.isoformat()
                if settlement.submitted_at
                else None
            ),
            "verified_at": (
                settlement.verified_at.isoformat()
                if settlement.verified_at
                else None
            ),
        })

    return jsonify({
        "success": True,
        "rider": {
            "id": rider.id,
            "name": rider.name or "",
        },
        "history": history,
        "count": len(history)
    }), 200
# ==========================================================
# ADMIN - GET RIDER APPLICATIONS
# ==========================================================

@app.route(
    "/api/admin/rider-applications",
    methods=["GET"]
)
def get_rider_applications():

    try:

        status = request.args.get(
            "status",
            ""
        ).strip()

        query = RiderApplication.query.order_by(
            RiderApplication.submitted_at.desc()
        )

        if status:
            query = query.filter(
                RiderApplication.status == status
            )

        applications = query.all()

        result = []

        for a in applications:

            result.append({

                "id":
                    a.id,

                "application_code":
                    a.application_code,

                "full_name":
                    a.full_name,

                "phone":
                    a.phone,

                "dob":
                    a.dob.isoformat()
                    if a.dob
                    else None,

                "address":
                    a.address,

                "city":
                    a.city,

                "pincode":
                    a.pincode,

                "vehicle_type":
                    a.vehicle_type,

                "vehicle_number":
                    a.vehicle_number,

                "status":
                    a.status,

                "rejection_reason":
                    a.rejection_reason,

                "review_note":
                    a.review_note,

                "submitted_at":
                    (
                        a.submitted_at.isoformat()
                        if a.submitted_at
                        else None
                    ),

                # ==================================================
                # PRIVATE DOCUMENT URLs
                # ==================================================

                "document_urls": {

                    "aadhaar_front":
                        url_for(
                            "admin_view_rider_application_document",
                            application_id=a.id,
                            document_type="aadhaar_front"
                        )
                        if a.aadhaar_front_path
                        else None,

                    "aadhaar_back":
                        url_for(
                            "admin_view_rider_application_document",
                            application_id=a.id,
                            document_type="aadhaar_back"
                        )
                        if a.aadhaar_back_path
                        else None,

                    "pan_photo":
                        url_for(
                            "admin_view_rider_application_document",
                            application_id=a.id,
                            document_type="pan"
                        )
                        if a.pan_photo_path
                        else None,

                    "selfie_photo":
                        url_for(
                            "admin_view_rider_application_document",
                            application_id=a.id,
                            document_type="selfie"
                        )
                        if a.selfie_photo_path
                        else None,

                    "driving_license":
                        url_for(
                            "admin_view_rider_application_document",
                            application_id=a.id,
                            document_type="driving_license"
                        )
                        if a.driving_license_path
                        else None
                }
            })

        return jsonify({
            "success": True,
            "applications": result
        }), 200

    except Exception as e:

        app.logger.exception(
            "Failed to load rider applications"
        )

        return jsonify({

            "success": False,

            "message":
                "Unable to load rider applications.",

            "error":
                str(e)

        }), 500
@app.route(
    "/api/delivery/application",
    methods=["POST"]
)
def submit_rider_application():

    saved_paths = []

    try:

        phone = _normalize_phone(
            request.form.get("phone")
        )

        full_name = (
            request.form.get("full_name")
            or ""
        ).strip()

        address = (
            request.form.get("address")
            or ""
        ).strip()

        city = (
            request.form.get("city")
            or ""
        ).strip()

        pincode = (
            request.form.get("pincode")
            or ""
        ).strip()

        vehicle_type = (
            request.form.get("vehicle_type")
            or ""
        ).strip()

        vehicle_number = (
            request.form.get("vehicle_number")
            or ""
        ).strip().upper()

        dob = _parse_date(
            request.form.get("dob")
        )

        if not full_name:
            raise ValueError(
                "Full name is required."
            )

        if len(phone) != 10:
            raise ValueError(
                "Enter a valid 10-digit mobile number."
            )

        if not address:
            raise ValueError(
                "Address is required."
            )

        if not city:
            raise ValueError(
                "City / village is required."
            )

        if (
            not pincode
            or len(pincode) != 6
            or not pincode.isdigit()
        ):
            raise ValueError(
                "Enter a valid 6-digit pincode."
            )

        existing_auth = (
            RiderAuthAccount.query
            .filter_by(phone=phone)
            .first()
        )

        if existing_auth:

            return jsonify({
                "success": False,
                "message":
                    "A delivery partner account already exists for this mobile number."
            }), 409

        application_code = (
            _generate_application_code()
        )

        aadhaar_front = _save_private_upload(
            request.files.get(
                "aadhaar_front"
            ),
            application_code,
            "aadhaar_front"
        )

        saved_paths.append(
            aadhaar_front
        )

        aadhaar_back = _save_private_upload(
            request.files.get(
                "aadhaar_back"
            ),
            application_code,
            "aadhaar_back"
        )

        saved_paths.append(
            aadhaar_back
        )

        pan_photo = _save_private_upload(
            request.files.get(
                "pan_photo"
            ),
            application_code,
            "pan_photo"
        )

        saved_paths.append(
            pan_photo
        )

        selfie_photo = _save_private_upload(
            request.files.get(
                "selfie_photo"
            ),
            application_code,
            "selfie_photo"
        )

        saved_paths.append(
            selfie_photo
        )

        driving_license = _save_private_upload(
            request.files.get(
                "driving_license"
            ),
            application_code,
            "driving_license",
            required=False
        )

        if driving_license:
            saved_paths.append(
                driving_license
            )

        application = RiderApplication(

            application_code=
                application_code,

            full_name=
                full_name,

            phone=
                phone,

            dob=
                dob,

            address=
                address,

            city=
                city,

            pincode=
                pincode,

            vehicle_type=
                vehicle_type or None,

            vehicle_number=
                vehicle_number or None,

            aadhaar_front_path=
                aadhaar_front,

            aadhaar_back_path=
                aadhaar_back,

            pan_photo_path=
                pan_photo,

            selfie_photo_path=
                selfie_photo,

            driving_license_path=
                driving_license,

            status=
                "Pending"
        )

        db.session.add(
            application
        )

        db.session.commit()

        return jsonify({

            "success": True,

            "message":
                "Application submitted successfully.",

            "application": {

                "id":
                    application.id,

                "application_code":
                    application.application_code,

                "status":
                    application.status,

                "submitted_at":
                    application.submitted_at.isoformat()
            }

        }), 201

    except ValueError as exc:

        db.session.rollback()

        for path in saved_paths:

            if (
                path
                and os.path.exists(path)
            ):

                try:
                    os.remove(path)
                except OSError:
                    pass

        return jsonify({
            "success": False,
            "message": str(exc)
        }), 400

    except Exception:

        db.session.rollback()

        app.logger.exception(
            "Rider application failed"
        )

        return jsonify({
            "success": False,
            "message":
                "Unable to submit application right now."
        }), 500
from werkzeug.security import check_password_hash

@app.route(
    "/api/delivery/auth/login",
    methods=["POST"]
)
def api_delivery_login():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        phone = _normalize_phone(
            data.get("phone")
        )

        password = (
            data.get("password")
            or ""
        ).strip()

        # ======================================================
        # VALIDATION
        # ======================================================

        if len(phone) != 10:

            return jsonify({
                "success": False,
                "message":
                    "Enter a valid 10-digit mobile number."
            }), 400

        if not password:

            return jsonify({
                "success": False,
                "message":
                    "Password is required."
            }), 400

        # ======================================================
        # FIND AUTH ACCOUNT
        # ======================================================

        account = (
            RiderAuthAccount.query
            .filter_by(
                phone=phone
            )
            .first()
        )

        if not account:

            return jsonify({
                "success": False,
                "message":
                    "Invalid mobile number or password."
            }), 401

        # ======================================================
        # ACCOUNT NOT ACTIVATED
        # ======================================================

        if not account.is_active:

            return jsonify({
                "success": False,
                "message":
                    "Your delivery partner account is not active."
            }), 403

        # ======================================================
        # PASSWORD NOT SET
        # ======================================================

        if not account.password_is_set:

            return jsonify({
                "success": False,
                "message":
                    "Your login account has not been activated yet."
            }), 403

        if not account.password_hash:

            return jsonify({
                "success": False,
                "message":
                    "Login credentials are not configured."
            }), 403

        # ======================================================
        # CHECK PASSWORD
        # ======================================================

        if not check_password_hash(
            account.password_hash,
            password
        ):

            return jsonify({
                "success": False,
                "message":
                    "Invalid mobile number or password."
            }), 401

        # ======================================================
        # FIND RIDER
        # ======================================================

        rider = db.session.get(
            DeliveryPerson,
            account.rider_id
        )

        if not rider:

            return jsonify({
                "success": False,
                "message":
                    "Delivery partner profile not found."
            }), 404

        # ======================================================
        # UPDATE LAST LOGIN
        # ======================================================

        account.last_login_at = datetime.utcnow()

        db.session.commit()

        # ======================================================
        # SUCCESS
        # ======================================================

        return jsonify({

            "success": True,

            "message":
                "Login successful.",

            "rider": {

                "id":
                    rider.id,

                "name":
                    rider.name or "",

                "phone":
                    account.phone or ""

            }

        }), 200

    except Exception as e:

        db.session.rollback()

        app.logger.exception(
            "Rider login failed"
        )

        return jsonify({

            "success": False,

            "message":
                "Unable to login right now.",

            "error":
                str(e)

        }), 500

@app.route("/admin/rider-applications")
def admin_rider_applications():
    return render_template("admin/rider_applications.html")
# ==========================================================
# APPROVE RIDER APPLICATION
# ==========================================================
# ==========================================================
# VIEW RIDER APPLICATION DOCUMENT
# ==========================================================

@app.route(
    "/api/admin/rider-applications/<int:application_id>/document/<document_type>",
    methods=["GET"]
)
def admin_view_rider_application_document(
    application_id,
    document_type
):
    try:

        application = RiderApplication.query.get(
            application_id
        )

        if not application:
            return jsonify({
                "success": False,
                "message": "Rider application not found."
            }), 404

        document_map = {
            "aadhaar_front":
                application.aadhaar_front_path,

            "aadhaar_back":
                application.aadhaar_back_path,

            "pan":
                application.pan_photo_path,

            "pan_photo":
                application.pan_photo_path,

            "selfie":
                application.selfie_photo_path,

            "selfie_photo":
                application.selfie_photo_path,

            "driving_license":
                application.driving_license_path,
        }

        if document_type not in document_map:
            return jsonify({
                "success": False,
                "message": "Invalid document type."
            }), 400

        file_path = document_map[document_type]

        if not file_path:
            return jsonify({
                "success": False,
                "message": "Document was not uploaded."
            }), 404

        # Handle relative paths saved by _save_private_upload()
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)

        if not os.path.isfile(file_path):
            return jsonify({
                "success": False,
                "message": "Document file not found."
            }), 404

        return send_file(
            file_path,
            as_attachment=False
        )

    except Exception as e:

        app.logger.exception(
            "Rider application document view failed"
        )

        return jsonify({
            "success": False,
            "message": "Unable to open document.",
            "error": str(e)
        }), 500
# ==========================================================
# REJECT RIDER APPLICATION
# ==========================================================

@app.route(
    "/api/admin/rider-applications/<int:application_id>/reject",
    methods=["POST"]
)
def reject_rider_application(application_id):

    try:

        # ======================================================
        # FIND APPLICATION
        # ======================================================

        application = (
            RiderApplication.query
            .get(application_id)
        )

        if not application:

            return jsonify({
                "success": False,
                "message":
                    "Rider application not found."
            }), 404

        # ======================================================
        # CHECK CURRENT STATUS
        # ======================================================

        if application.status == "Rejected":

            return jsonify({
                "success": False,
                "message":
                    "This rider application is already rejected."
            }), 400

        if application.status == "Approved":

            return jsonify({
                "success": False,
                "message":
                    "An approved rider application cannot be rejected."
            }), 400

        # ======================================================
        # GET REQUEST DATA
        # ======================================================

        data = request.get_json(
            silent=True
        ) or {}

        rejection_reason = (
            data.get("rejection_reason")
            or data.get("rejectionReason")
            or data.get("reason")
            or ""
        ).strip()

        # ======================================================
        # DEFAULT REASON
        # ======================================================

        if not rejection_reason:

            rejection_reason = (
                "Application rejected by admin."
            )

        # ======================================================
        # UPDATE APPLICATION
        # ======================================================

        application.status = "Rejected"

        application.rejection_reason = (
            rejection_reason
        )

        application.reviewed_at = (
            datetime.utcnow()
        )

        # ======================================================
        # IF RIDER WAS ALREADY CREATED
        # ======================================================

        if application.rider_id:

            rider = db.session.get(
                DeliveryPerson,
                application.rider_id
            )

            if rider:

                rider.is_active = False
                rider.is_online = False
                rider.is_available = False

            # ----------------------------------------------
            # DISABLE AUTH ACCOUNT
            # ----------------------------------------------

            auth_account = (
                RiderAuthAccount.query
                .filter_by(
                    rider_id=application.rider_id
                )
                .first()
            )

            if auth_account:

                auth_account.is_active = False

        # ======================================================
        # SAVE
        # ======================================================

        db.session.commit()

        # ======================================================
        # LOG
        # ======================================================

        print("")
        print("==============================================")
        print("❌ RIDER APPLICATION REJECTED")
        print("==============================================")
        print(
            "Application ID:",
            application.id
        )
        print(
            "Application Code:",
            application.application_code
        )
        print(
            "Name:",
            application.full_name
        )
        print(
            "Phone:",
            application.phone
        )
        print(
            "Reason:",
            rejection_reason
        )
        print("==============================================")
        print("")

        # ======================================================
        # JSON RESPONSE
        # ======================================================

        return jsonify({

            "success": True,

            "message":
                "Rider application rejected successfully.",

            "application_id":
                application.id,

            "application_code":
                application.application_code,

            "status":
                application.status,

            "rejection_reason":
                application.rejection_reason

        }), 200

    except Exception as e:

        db.session.rollback()

        app.logger.exception(
            "Rider application rejection failed"
        )

        return jsonify({

            "success": False,

            "message":
                "Unable to reject rider application.",

            "error":
                str(e)

        }), 500
# ==========================================================
# APPROVE RIDER APPLICATION
# ==========================================================

@app.route(
    "/api/admin/rider-applications/<int:application_id>/approve",
    methods=["POST"]
)
def approve_rider_application(application_id):

    try:

        # ======================================================
        # FIND APPLICATION
        # ======================================================

        application = RiderApplication.query.get(
            application_id
        )

        if not application:

            return jsonify({
                "success": False,
                "message":
                    "Rider application not found."
            }), 404

        # ======================================================
        # PREVENT DUPLICATE APPROVAL
        # ======================================================

        if (
            application.status == "Approved"
            and application.rider_id
        ):

            return jsonify({
                "success": False,
                "message":
                    "This rider application is already approved."
            }), 400

        # ======================================================
        # NORMALIZE PHONE
        # ======================================================

        phone = _normalize_phone(
            application.phone
        )

        if len(phone) != 10:

            return jsonify({
                "success": False,
                "message":
                    "Invalid rider mobile number."
            }), 400

        # ======================================================
        # CHECK EXISTING RIDER
        # ======================================================

        existing_rider = (
            DeliveryPerson.query
            .filter_by(phone=phone)
            .first()
        )

        if existing_rider:

            return jsonify({
                "success": False,
                "message":
                    "A delivery rider already exists with this phone number."
            }), 400

        # ======================================================
        # CHECK EXISTING AUTH ACCOUNT
        # ======================================================

        existing_auth = (
            RiderAuthAccount.query
            .filter_by(phone=phone)
            .first()
        )

        if existing_auth:

            return jsonify({
                "success": False,
                "message":
                    "A rider authentication account already exists with this phone number."
            }), 400

        # ======================================================
        # CREATE UNIQUE USERNAME
        # ======================================================

        username = f"rider_{phone}"

        existing_username = (
            DeliveryPerson.query
            .filter_by(username=username)
            .first()
        )

        if existing_username:

            username = (
                f"rider_{phone}_"
                f"{secrets.token_hex(3)}"
            )

        # ======================================================
        # CREATE DELIVERY PERSON
        # ======================================================

        rider = DeliveryPerson(

            name=application.full_name,

            username=username,

            phone=phone,

            is_active=True,

            is_online=False,

            is_available=True,

            latitude=None,

            longitude=None,

            last_seen=None,

            fcm_token=None,

            push_subscription=None,

            last_assignment=None
        )

        db.session.add(rider)

        # Get rider.id before creating auth account
        db.session.flush()

        # ======================================================
        # GENERATE ACTIVATION CODE
        # ======================================================

        activation_token = (
            f"{secrets.randbelow(1000000):06d}"
        )

        # ======================================================
        # HASH ACTIVATION CODE
        # ======================================================

        activation_token_hash = (
            hashlib.sha256(
                activation_token.encode("utf-8")
            ).hexdigest()
        )

        # ======================================================
        # ACTIVATION EXPIRY
        # 24 HOURS
        # ======================================================

        activation_expires_at = (
            datetime.utcnow()
            + timedelta(hours=24)
        )

        # ======================================================
        # CREATE RIDER AUTH ACCOUNT
        # ======================================================

        auth_account = RiderAuthAccount(

            rider_id=rider.id,

            phone=phone,

            password_hash=None,

            is_active=False,

            password_is_set=False,

            activation_token_hash=
                activation_token_hash,

            activation_expires_at=
                activation_expires_at
        )

        db.session.add(auth_account)

        # ======================================================
        # UPDATE APPLICATION
        # ======================================================

        application.status = "Approved"

        application.rider_id = rider.id

        application.reviewed_at = (
            datetime.utcnow()
        )

        application.rejection_reason = None

        # ======================================================
        # SAVE
        # ======================================================

        db.session.commit()

        # ======================================================
        # SUCCESS
        # ======================================================

        print(
            "=============================================="
        )
        print(
            "RIDЕR APPLICATION APPROVED"
        )
        print(
            "Application ID:",
            application.id
        )
        print(
            "Application Code:",
            application.application_code
        )
        print(
            "Rider ID:",
            rider.id
        )
        print(
            "Name:",
            application.full_name
        )
        print(
            "Phone:",
            phone
        )
        print(
            "Activation Code:",
            activation_token
        )
        print(
            "Expires:",
            activation_expires_at
        )
        print(
            "=============================================="
        )

        return jsonify({

            "success": True,

            "message":
                "Rider approved successfully.",

            "application_id":
                application.id,

            "application_code":
                application.application_code,

            "rider_id":
                rider.id,

            "full_name":
                application.full_name,

            "phone":
                phone,

            "username":
                rider.username,

            "activation_token":
                activation_token,

            "activation_expires_at":
                activation_expires_at.isoformat()

        }), 200

    except Exception as e:

        db.session.rollback()

        app.logger.exception(
            "Rider approval failed"
        )

        return jsonify({

            "success": False,

            "message":
                "Unable to approve rider.",

            "error":
                str(e)

        }), 500
# ==========================================================
# RIDER APPLICATION STATUS
# ==========================================================

@app.route(
    "/api/delivery/application-status",
    methods=["GET"]
)
def api_delivery_application_status():

    try:

        phone = _normalize_phone(
            request.args.get("phone")
        )

        if len(phone) != 10:

            return jsonify({
                "success": False,
                "message":
                    "Invalid mobile number."
            }), 400

        application = (
            RiderApplication.query
            .filter_by(
                phone=phone
            )
            .order_by(
                RiderApplication.id.desc()
            )
            .first()
        )

        if not application:

            return jsonify({
                "success": False,
                "message":
                    "No rider application found for this number."
            }), 404

        return jsonify({

            "success": True,

            "application": {

                "id":
                    application.id,

                "application_code":
                    application.application_code,

                "full_name":
                    application.full_name or "",

                "phone":
                    application.phone or "",

                "status":
                    application.status or "Pending",

                "rejection_reason":
                    application.rejection_reason or "",

                "rider_id":
                    application.rider_id,

                "reviewed_at":
                    application.reviewed_at.isoformat()
                    if application.reviewed_at
                    else None,

                "applied_at":
                    application.created_at.isoformat()
                    if application.created_at
                    else None
            }

        }), 200

    except Exception as e:

        app.logger.exception(
            "Rider application status failed"
        )

        return jsonify({

            "success": False,

            "message":
                "Unable to load application status.",

            "error":
                str(e)

        }), 500
# ==========================================================
# GENERATE / RESEND ACTIVATION CODE
# ==========================================================

@app.route(
    "/api/admin/rider-applications/<int:application_id>/activation-code",
    methods=["POST"]
)
def generate_rider_activation_code(application_id):

    try:

        # ======================================================
        # FIND APPLICATION
        # ======================================================

        application = RiderApplication.query.get(
            application_id
        )

        if not application:

            return jsonify({
                "success": False,
                "message": "Rider application not found."
            }), 404


        # ======================================================
        # MUST BE APPROVED
        # ======================================================

        if (
            application.status != "Approved"
            or not application.rider_id
        ):

            return jsonify({
                "success": False,
                "message":
                    "This rider is not approved."
            }), 400


        # ======================================================
        # FIND RIDER AUTH ACCOUNT
        # ======================================================

        auth_account = (
            RiderAuthAccount.query
            .filter_by(
                rider_id=application.rider_id
            )
            .first()
        )

        if not auth_account:

            return jsonify({
                "success": False,
                "message":
                    "Rider authentication account not found."
            }), 404


        # ======================================================
        # GENERATE NEW ACTIVATION TOKEN
        # ======================================================

        activation_token = f"{secrets.randbelow(1000000):06d}"


        # ======================================================
        # HASH NEW ACTIVATION TOKEN
        # ======================================================

        activation_token_hash = (
            hashlib.sha256(
                activation_token.encode("utf-8")
            ).hexdigest()
        )


        # ======================================================
        # NEW EXPIRY
        # 24 HOURS
        # ======================================================

        activation_expires_at = (
            datetime.utcnow()
            + timedelta(hours=24)
        )


        # ======================================================
        # UPDATE AUTH ACCOUNT
        # ======================================================

        auth_account.activation_token_hash = (
            activation_token_hash
        )

        auth_account.activation_expires_at = (
            activation_expires_at
        )

        auth_account.is_active = False
        auth_account.password_is_set = False
        auth_account.password_hash = None


        # ======================================================
        # SAVE
        # ======================================================

        db.session.commit()


        # ======================================================
        # SUCCESS
        # ======================================================

        return jsonify({

            "success": True,

            "message":
                "New activation code generated successfully.",

            "application_id":
                application.id,

            "rider_id":
                application.rider_id,

            "full_name":
                application.full_name,

            "phone":
                _normalize_phone(application.phone),

            "activation_token":
                activation_token,

            "activation_expires_at":
                activation_expires_at.isoformat()

        }), 200


    # ==========================================================
    # ERROR
    # ==========================================================

    except Exception as e:

        db.session.rollback()

        app.logger.exception(
            "Activation code generation failed"
        )

        return jsonify({

            "success": False,

            "message":
                "Unable to generate activation code.",

            "error":
                str(e)

        }), 500

# ==========================================================
# RIDER ACCOUNT ACTIVATION
# ==========================================================


@app.route(
    "/api/delivery/auth/activate",
    methods=["POST"]
)
def api_rider_activate():

    try:

        data = request.get_json(silent=True) or {}

        # =====================================================
        # GET DATA
        # =====================================================

        phone = _normalize_phone(
            data.get("phone")
        )

        activation_token = (
            data.get("activationToken")
            or data.get("activation_token")
            or ""
        ).strip()

        password = (
            data.get("password")
            or ""
        )

        # =====================================================
        # DEBUG
        # =====================================================

        print("")
        print("==============================================")
        print("🔐 RIDER ACTIVATION REQUEST")
        print("==============================================")
        print("Phone:", phone)
        print("Token received:", bool(activation_token))
        print("Password received:", bool(password))
        print("==============================================")


        # =====================================================
        # VALIDATE PHONE
        # =====================================================

        if len(phone) != 10:

            return jsonify({
                "success": False,
                "message":
                    "Enter a valid 10-digit mobile number."
            }), 400


        # =====================================================
        # VALIDATE ACTIVATION CODE
        # =====================================================

        if (
            not activation_token.isdigit()
            or len(activation_token) != 6
        ):

            return jsonify({
                "success": False,
                "message":
                    "Enter the 6-digit activation code."
            }), 400


        # =====================================================
        # VALIDATE PASSWORD
        # =====================================================

        if len(password) < 6:

            return jsonify({
                "success": False,
                "message":
                    "Password must be at least 6 characters."
            }), 400


        # =====================================================
        # FIND RIDER AUTH ACCOUNT
        # =====================================================

        account = (
            RiderAuthAccount.query
            .filter_by(phone=phone)
            .first()
        )

        if not account:

            print("❌ AUTH ACCOUNT NOT FOUND")

            return jsonify({
                "success": False,
                "message":
                    "No rider account found for this mobile number."
            }), 404


        # =====================================================
        # ALREADY ACTIVATED
        # =====================================================

        if account.password_is_set:

            return jsonify({
                "success": False,
                "message":
                    "This account has already been activated."
            }), 400


        # =====================================================
        # CHECK ACTIVATION HASH EXISTS
        # =====================================================

        if not account.activation_token_hash:

            print("❌ ACTIVATION HASH IS EMPTY")

            return jsonify({
                "success": False,
                "message":
                    "This activation code is no longer valid."
            }), 400


        # =====================================================
        # CHECK EXPIRATION FIRST
        # =====================================================

        if (
            account.activation_expires_at
            and datetime.utcnow()
            > account.activation_expires_at
        ):

            print("❌ ACTIVATION CODE EXPIRED")

            return jsonify({
                "success": False,
                "message":
                    "This activation code has expired. Please request a new code."
            }), 410


        # =====================================================
        # HASH RECEIVED ACTIVATION CODE
        # =====================================================

        token_hash = hashlib.sha256(
            activation_token.encode("utf-8")
        ).hexdigest()


        # =====================================================
        # DEBUG TOKEN MATCH
        # =====================================================

        print("Stored hash :", account.activation_token_hash)
        print("Received hash:", token_hash)


        # =====================================================
        # CHECK ACTIVATION CODE
        # =====================================================

        if not secrets.compare_digest(
            token_hash,
            account.activation_token_hash
        ):

            print("❌ ACTIVATION CODE DOES NOT MATCH")

            return jsonify({
                "success": False,
                "message":
                    "Invalid activation code."
            }), 401


        print("✅ ACTIVATION CODE MATCHED")


        # =====================================================
        # FIND RIDER
        # =====================================================

        rider = db.session.get(
            DeliveryPerson,
            account.rider_id
        )

        if not rider:

            return jsonify({
                "success": False,
                "message":
                    "Delivery partner profile not found."
            }), 404


        # =====================================================
        # CREATE PASSWORD
        # =====================================================

        account.password_hash = generate_password_hash(
            password
        )

        account.password_is_set = True

        account.is_active = True


        # =====================================================
        # DELETE ACTIVATION CODE
        # =====================================================

        account.activation_token_hash = None

        account.activation_expires_at = None


        # =====================================================
        # ACTIVATE RIDER
        # =====================================================

        rider.is_active = True


        # =====================================================
        # SAVE DATABASE
        # =====================================================

        db.session.commit()


        # =====================================================
        # SUCCESS LOG
        # =====================================================

        print("==============================================")
        print("✅ RIDER ACCOUNT ACTIVATED")
        print("Rider ID:", rider.id)
        print("Phone:", account.phone)
        print("==============================================")
        print("")


        # =====================================================
        # SUCCESS RESPONSE
        # =====================================================

        return jsonify({

            "success": True,

            "message":
                "Account activated successfully. You can now login.",

            "rider": {

                "id":
                    rider.id,

                "name":
                    rider.name or "",

                "phone":
                    account.phone or ""

            }

        }), 200


    # ==========================================================
    # ERROR
    # ==========================================================

    except Exception as e:

        db.session.rollback()

        app.logger.exception(
            "Rider activation failed"
        )

        print("")
        print("==============================================")
        print("❌ RIDER ACTIVATION ERROR")
        print(str(e))
        print("==============================================")
        print("")

        return jsonify({

            "success": False,

            "message":
                "Unable to activate account right now.",

            "error":
                str(e)

        }), 500


@app.route(
    "/api/delivery/auth/change-password",
    methods=["POST"]
)
def api_rider_change_password():

    try:
        data = request.get_json(silent=True) or {}

        phone = _normalize_phone(data.get("phone"))
        current_password = data.get("currentPassword") or data.get("current_password") or ""
        new_password = data.get("newPassword") or data.get("new_password") or ""
        confirm_password = data.get("confirmPassword") or data.get("confirm_password") or ""

        if len(phone) != 10:
            return jsonify({
                "success": False,
                "message": "Enter a valid 10-digit mobile number."
            }), 400

        if not current_password:
            return jsonify({
                "success": False,
                "message": "Current password is required."
            }), 400

        if len(new_password) < 6:
            return jsonify({
                "success": False,
                "message": "New password must be at least 6 characters."
            }), 400

        if new_password != confirm_password:
            return jsonify({
                "success": False,
                "message": "New passwords do not match."
            }), 400

        if current_password == new_password:
            return jsonify({
                "success": False,
                "message": "New password must be different from your current password."
            }), 400

        account = (
            RiderAuthAccount.query
            .filter_by(phone=phone)
            .first()
        )

        if not account:
            return jsonify({
                "success": False,
                "message": "Rider account not found."
            }), 404

        if not account.is_active or not account.password_is_set:
            return jsonify({
                "success": False,
                "message": "Your rider account is not active."
            }), 403

        if not account.password_hash:
            return jsonify({
                "success": False,
                "message": "Password is not configured."
            }), 403

        if not check_password_hash(
            account.password_hash,
            current_password
        ):
            return jsonify({
                "success": False,
                "message": "Current password is incorrect."
            }), 401

        account.password_hash = generate_password_hash(
            new_password
        )
        account.password_is_set = True
        account.is_active = True

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Password changed successfully."
        }), 200

    except Exception as e:
        db.session.rollback()
        app.logger.exception("Rider change password failed")

        return jsonify({
            "success": False,
            "message": "Unable to change password right now.",
            "error": str(e)
        }), 500


# ==========================================================
# RIDER REQUEST PASSWORD RESET OTP
# ==========================================================
# ==========================================================
# RIDER REQUEST PASSWORD RESET OTP
# ==========================================================

@app.route(
    "/api/delivery/auth/password-reset/request",
    methods=["POST"]
)
def api_rider_password_reset_request():

    try:

        data = request.get_json(silent=True) or {}

        # ======================================================
        # PHONE
        # ======================================================

        phone = _normalize_phone(
            data.get("phone")
        )

        if len(phone) != 10:

            return jsonify({
                "success": False,
                "message":
                    "Enter a valid 10-digit mobile number."
            }), 400

        # ======================================================
        # FIND AUTH ACCOUNT
        # ======================================================

        account = (
            RiderAuthAccount.query
            .filter_by(phone=phone)
            .first()
        )

        if not account:

            return jsonify({
                "success": False,
                "message":
                    "No delivery partner account found for this number."
            }), 404

        # ======================================================
        # CHECK ACCOUNT
        # ======================================================

        if (
            not account.is_active
            or not account.password_is_set
        ):

            return jsonify({
                "success": False,
                "message":
                    "Your delivery partner account is not active."
            }), 403

        # ======================================================
        # FIND RIDER
        # ======================================================

        rider = db.session.get(
            DeliveryPerson,
            account.rider_id
        )

        if not rider:

            return jsonify({
                "success": False,
                "message":
                    "Delivery partner profile not found."
            }), 404

        # ======================================================
        # CURRENT SERVER TIME
        # ======================================================

        now = datetime.utcnow()

        # ======================================================
        # INVALIDATE ALL OLD OTP REQUESTS
        # ======================================================

        RiderPasswordResetRequest.query.filter(
            RiderPasswordResetRequest.rider_id == rider.id,
            RiderPasswordResetRequest.used.is_(False)
        ).update(
            {
                "used": True
            },
            synchronize_session=False
        )

        # ======================================================
        # GENERATE NEW 6 DIGIT OTP
        # ======================================================

        otp = f"{secrets.randbelow(1000000):06d}"

        # ======================================================
        # HASH OTP
        # ======================================================

        otp_hash = hashlib.sha256(
            otp.encode("utf-8")
        ).hexdigest()

        # ======================================================
        # OTP VALID FOR 5 MINUTES
        # ======================================================

        expires_at = (
            now + timedelta(minutes=5)
        )

        # ======================================================
        # CREATE RESET REQUEST
        # ======================================================

        reset_request = RiderPasswordResetRequest(

            rider_id=rider.id,

            phone=phone,

            otp_code=otp,

            otp_hash=otp_hash,

            expires_at=expires_at,

            requested_at=now,

            used=False
        )

        db.session.add(
            reset_request
        )

        db.session.commit()

        # ======================================================
        # LOCAL TEST LOG
        # ======================================================

        print("")
        print("==============================================")
        print("🔐 PASSWORD RESET OTP")
        print("==============================================")
        print("Rider ID     :", rider.id)
        print("Phone        :", phone)
        print("OTP          :", otp)
        print("Requested At :", now.isoformat())
        print("Expires At   :", expires_at.isoformat())
        print("Valid For    : 300 seconds")
        print("==============================================")
        print("")

        # ======================================================
        # IMPORTANT
        # RETURN BOTH expires_at AND expires_in
        # ======================================================

        return jsonify({

            "success": True,

            "message":
                "Password reset OTP generated. Please contact RucHiGo admin.",

            "request_id":
                reset_request.id,

            "otp_valid_for":
                300,

            "expires_in":
                300,

            "expires_at":
                expires_at.isoformat(),

            "server_time":
                now.isoformat()

        }), 200

    except Exception as e:

        db.session.rollback()

        app.logger.exception(
            "Rider password reset request failed"
        )

        return jsonify({

            "success": False,

            "message":
                "Unable to create password reset request.",

            "error":
                str(e)

        }), 500
# ==========================================================
# ADMIN VIEW PASSWORD RESET REQUESTS
# ==========================================================

@app.route(
    "/api/admin/rider-password-reset-requests",
    methods=["GET"]
)
def admin_rider_password_reset_requests():

    try:
        now = datetime.utcnow()

        rows = (
            RiderPasswordResetRequest.query
            .filter(
                RiderPasswordResetRequest.used.is_(False),
                RiderPasswordResetRequest.expires_at > now
            )
            .order_by(
                RiderPasswordResetRequest.requested_at.desc()
            )
            .all()
        )

        result = []

        for row in rows:

            rider = db.session.get(
                DeliveryPerson,
                row.rider_id
            )

            result.append({
                "id": row.id,
                "rider_id": row.rider_id,
                "name":
                    rider.name if rider else "Delivery Partner",
                "phone":
                    row.phone,
                "otp":
                    row.otp_code,
                "expires_at":
                    row.expires_at.isoformat(),
                "requested_at":
                    row.requested_at.isoformat()
            })

        return jsonify({
            "success": True,
            "requests": result
        }), 200

    except Exception as e:

        app.logger.exception(
            "Admin password reset list failed"
        )

        return jsonify({
            "success": False,
            "message":
                "Unable to load password reset requests.",
            "error":
                str(e)
        }), 500


# ==========================================================
# ADMIN CANCEL RESET REQUEST
# ==========================================================

@app.route(
    "/api/admin/rider-password-reset-requests/<int:request_id>/cancel",
    methods=["POST"]
)
def admin_cancel_rider_password_reset(request_id):

    try:

        reset_request = db.session.get(
            RiderPasswordResetRequest,
            request_id
        )

        if not reset_request:

            return jsonify({
                "success": False,
                "message":
                    "Password reset request not found."
            }), 404

        reset_request.used = True

        db.session.commit()

        return jsonify({
            "success": True,
            "message":
                "Password reset request cancelled."
        }), 200

    except Exception as e:

        db.session.rollback()

        app.logger.exception(
            "Admin password reset cancellation failed"
        )

        return jsonify({
            "success": False,
            "message":
                "Unable to cancel reset request.",
            "error":
                str(e)
        }), 500


# ==========================================================
# RIDER CONFIRM PASSWORD RESET
# ==========================================================

@app.route(
    "/api/delivery/auth/password-reset/confirm",
    methods=["POST"]
)
def api_rider_password_reset_confirm():

    try:

        data = request.get_json(silent=True) or {}

        phone = _normalize_phone(
            data.get("phone")
        )

        otp = str(
            data.get("otp") or ""
        ).strip()

        new_password = (
            data.get("password")
            or ""
        )

        if len(phone) != 10:

            return jsonify({
                "success": False,
                "message":
                    "Enter a valid 10-digit mobile number."
            }), 400

        if not otp.isdigit() or len(otp) != 6:

            return jsonify({
                "success": False,
                "message":
                    "Enter the 6-digit OTP."
            }), 400

        if len(new_password) < 6:

            return jsonify({
                "success": False,
                "message":
                    "Password must be at least 6 characters."
            }), 400

        account = (
            RiderAuthAccount.query
            .filter_by(phone=phone)
            .first()
        )

        if not account:

            return jsonify({
                "success": False,
                "message":
                    "No rider account found."
            }), 404

        if not account.is_active:

            return jsonify({
                "success": False,
                "message":
                    "Your rider account is not active."
            }), 403

        reset_request = (
            RiderPasswordResetRequest.query
            .filter(
                RiderPasswordResetRequest.rider_id ==
                    account.rider_id,
                RiderPasswordResetRequest.phone ==
                    phone,
                RiderPasswordResetRequest.used.is_(False)
            )
            .order_by(
                RiderPasswordResetRequest.requested_at.desc()
            )
            .first()
        )

        if not reset_request:

            return jsonify({
                "success": False,
                "message":
                    "No active password reset request found. Request a new OTP."
            }), 400

        if datetime.utcnow() > reset_request.expires_at:

            reset_request.used = True
            db.session.commit()

            return jsonify({
                "success": False,
                "message":
                    "OTP has expired. Request a new OTP."
            }), 410

        received_hash = hashlib.sha256(
            otp.encode("utf-8")
        ).hexdigest()

        if not secrets.compare_digest(
            received_hash,
            reset_request.otp_hash
        ):

            return jsonify({
                "success": False,
                "message":
                    "Invalid OTP."
            }), 401

        account.password_hash = generate_password_hash(
            new_password
        )

        account.password_is_set = True
        account.is_active = True

        reset_request.used = True
        reset_request.otp_code = "000000"
        reset_request.otp_hash = hashlib.sha256(
            b"USED"
        ).hexdigest()

        db.session.commit()

        return jsonify({
            "success": True,
            "message":
                "Password reset successfully. You can now login."
        }), 200

    except Exception as e:

        db.session.rollback()

        app.logger.exception(
            "Rider password reset failed"
        )

        return jsonify({
            "success": False,
            "message":
                "Unable to reset password right now.",
            "error":
                str(e)
        }), 500
@app.route(
    "/api/delivery/order/<int:order_id>/payment-status",
    methods=["GET"]
)
@csrf.exempt
def delivery_order_payment_status(order_id):

    try:
        order = Order.query.get(order_id)

        if not order:
            return jsonify({
                "success": False,
                "paid": False,
                "message": "Order not found."
            }), 404

        paid = (
            order.payment_status == "Paid"
            and bool(order.payment_verified)
        )

        return jsonify({
            "success": True,
            "paid": paid,
            "payment_status": order.payment_status,
            "payment_verified": bool(
                order.payment_verified
            ),
            "order_id": order.order_id,
            "final_total": float(
                order.final_total or 0
            )
        }), 200

    except Exception as e:
        app.logger.exception(
            "Delivery payment status error: %s",
            e
        )

        return jsonify({
            "success": False,
            "paid": False,
            "message": "Unable to check payment status."
        }), 500


# =========================================================
# RESTAURANT PICKUP QR MANAGEMENT
# PHASE 1
# =========================================================

@app.route("/admin/restaurant-pickup-qr")
def restaurant_pickup_qr():

    restaurants = Restaurant.query.order_by(
        Restaurant.name.asc()
    ).all()

    return render_template(
        "admin/restaurant_pickup_qr.html",
        restaurants=restaurants
    )

# =========================================================
# GENERATE RESTAURANT PICKUP QR
# =========================================================

@app.route(
    "/admin/restaurant-pickup-qr/generate/<int:restaurant_id>",
    methods=["POST"]
)
def generate_restaurant_pickup_qr(restaurant_id):

    restaurant = Restaurant.query.get_or_404(
        restaurant_id
    )

    # Check if QR already exists
    existing_qr = RestaurantPickupQR.query.filter_by(
        restaurant_id=restaurant.id
    ).first()

    if existing_qr:

        flash(
            f"Pickup QR already exists for {restaurant.name}.",
            "info"
        )

        return redirect(
            url_for("restaurant_pickup_qr")
        )

    # Generate secure token
    qr_token = secrets.token_urlsafe(32)

    pickup_qr = RestaurantPickupQR(
        restaurant_id=restaurant.id,
        qr_token=qr_token,
        is_active=True
    )

    db.session.add(pickup_qr)

    db.session.commit()

    flash(
        f"Pickup QR generated for {restaurant.name}.",
        "success"
    )

    return redirect(
        url_for("restaurant_pickup_qr")
    )

# =========================================================
# VIEW RESTAURANT PICKUP QR
# =========================================================

@app.route(
    "/admin/restaurant-pickup-qr/view/<int:restaurant_id>"
)
def view_restaurant_pickup_qr(restaurant_id):

    restaurant = Restaurant.query.get_or_404(
        restaurant_id
    )

    pickup_qr = RestaurantPickupQR.query.filter_by(
        restaurant_id=restaurant.id
    ).first()

    if not pickup_qr:

        flash(
            "Pickup QR has not been generated yet.",
            "error"
        )

        return redirect(
            url_for("restaurant_pickup_qr")
        )

    return render_template(
        "admin/view_restaurant_pickup_qr.html",
        restaurant=restaurant,
        pickup_qr=pickup_qr
    )

@app.route(
    "/admin/restaurant-pickup-qr/image/<int:restaurant_id>"
)
def restaurant_pickup_qr_image(restaurant_id):

    restaurant = Restaurant.query.get_or_404(restaurant_id)

    pickup_qr = RestaurantPickupQR.query.filter_by(
        restaurant_id=restaurant.id
    ).first()

    if not pickup_qr:
        return "Pickup QR not found", 404

    # QR contains ONLY the permanent restaurant token
    qr_data = pickup_qr.qr_token

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4
    )

    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    output = io.BytesIO()

    img.save(
        output,
        format="PNG"
    )

    output.seek(0)

    return send_file(
        output,
        mimetype="image/png",
        download_name=f"{restaurant.name}_pickup_qr.png"
    )
@app.route(
    "/api/delivery/order/<int:order_id>/pickup/verify-qr",
    methods=["POST"]
)
def verify_pickup_qr(order_id):

    data = request.get_json(silent=True) or {}

    rider_id = data.get("rider_id")
    qr_token = str(
        data.get("qr_token") or ""
    ).strip()

    # =========================================================
    # BASIC VALIDATION
    # =========================================================

    if not rider_id:
        return jsonify({
            "success": False,
            "message": "Rider ID is required."
        }), 400

    if not qr_token:
        return jsonify({
            "success": False,
            "message": "QR token is required."
        }), 400

    # =========================================================
    # GET ORDER
    # =========================================================

    order = db.session.get(Order, order_id)

    if not order:
        return jsonify({
            "success": False,
            "message": "Order not found."
        }), 404

    # =========================================================
    # GET RIDER
    # =========================================================

    rider = db.session.get(
        DeliveryPerson,
        rider_id
    )

    if not rider:
        return jsonify({
            "success": False,
            "message": "Delivery person not found."
        }), 404

    # =========================================================
    # SECURITY CHECK 1
    # RIDER MUST BE ASSIGNED TO THIS EXACT ORDER
    # =========================================================

    assigned_rider_id = getattr(
        order,
        "delivery_person_id",
        None
    )

    if assigned_rider_id != rider.id:
        return jsonify({
            "success": False,
            "message": "This order is not assigned to you."
        }), 403

    # =========================================================
    # SECURITY CHECK 2
    # ORDER MUST HAVE RESTAURANT
    # =========================================================

    restaurant_id = getattr(
        order,
        "restaurant_id",
        None
    )

    if not restaurant_id:
        return jsonify({
            "success": False,
            "message": "Restaurant information is missing."
        }), 400

    # =========================================================
    # SECURITY CHECK 3
    # QR MUST EXIST
    # =========================================================

    pickup_qr = RestaurantPickupQR.query.filter_by(
        qr_token=qr_token
    ).first()

    if not pickup_qr:
        return jsonify({
            "success": False,
            "message": "Invalid restaurant pickup QR."
        }), 403

    # =========================================================
    # SECURITY CHECK 4
    # QR MUST BE ACTIVE
    # =========================================================

    if not pickup_qr.is_active:
        return jsonify({
            "success": False,
            "message": "This restaurant pickup QR is inactive."
        }), 403

    # =========================================================
    # SECURITY CHECK 5
    # QR MUST BELONG TO ORDER RESTAURANT
    # =========================================================

    if pickup_qr.restaurant_id != restaurant_id:
        return jsonify({
            "success": False,
            "message": "Wrong restaurant QR for this order."
        }), 403

    # =========================================================
    # ORDER STATUS CHECK
    # =========================================================

    order_status = (
        str(
            getattr(
                order,
                "status",
                ""
            ) or ""
        )
        .strip()
        .lower()
    )

    if order_status in {
        "cancelled",
        "canceled",
        "delivered",
        "completed"
    }:
        return jsonify({
            "success": False,
            "message": "This order cannot be picked up."
        }), 400

    # =========================================================
    # ALREADY PICKED UP
    # =========================================================

    if order.pickup_status in {
        "qr_verified",
        "restaurant_confirmed",
        "picked_up"
    }:

        return jsonify({
            "success": True,
            "message": "Pickup already verified.",
            "pickup_status": order.pickup_status,
            "status": order.status
        }), 200

    # =========================================================
    # CREATE / GET AUDIT RECORD
    # =========================================================

    verification = OrderPickupVerification.query.filter_by(
        order_id=order.id
    ).first()

    if not verification:

        verification = OrderPickupVerification(
            order_id=order.id,
            restaurant_id=restaurant_id,
            delivery_person_id=rider.id,
            status="pending"
        )

        db.session.add(verification)

    else:

        # -----------------------------------------------------
        # SECURITY:
        # VERIFICATION MUST BELONG TO SAME RIDER
        # -----------------------------------------------------

        if verification.delivery_person_id != rider.id:

            return jsonify({
                "success": False,
                "message": (
                    "Pickup verification belongs "
                    "to another rider."
                )
            }), 403

    # =========================================================
    # GENERATE SHORT-LIVED VERIFICATION TOKEN
    # =========================================================

    verification_token = secrets.token_urlsafe(32)

    verification.verification_token = (
        verification_token
    )

    verification.token_expires_at = (
        datetime.utcnow()
        + timedelta(minutes=5)
    )

    verification.status = "qr_scanned"

    verification.qr_scanned_at = (
        datetime.utcnow()
    )

    # =========================================================
    # UPDATE PICKUP STATUS
    # =========================================================

    order.pickup_status = "qr_verified"

    order.pickup_qr_scanned_at = (
        datetime.utcnow()
    )

    # =========================================================
    # IMPORTANT
    # RIDER SUCCESSFULLY COLLECTED ORDER
    # =========================================================

    order.status = "Picked Up"

    # =========================================================
    # MARK VERIFICATION SUCCESS
    # =========================================================

    verification.pickup_verified_at = (
        datetime.utcnow()
    )

    # =========================================================
    # SAVE DATABASE
    # =========================================================

    db.session.commit()

    # =========================================================
    # RESTAURANT LIVE STATUS UPDATE
    # =========================================================

    try:

        socketio.emit(
            "order_status_update",
            {
                "order_id": order.order_id,
                "status": order.status,
                "pickup_status": order.pickup_status,
                "delivery_person_id": (
                    order.delivery_person_id
                ),
                "restaurant_id": restaurant_id
            },
            room=f"order_{order.order_id}"
        )

        print(
            "========================================"
        )
        print(
            "📦 PICKUP SUCCESS"
        )
        print(
            "ORDER:",
            order.order_id
        )
        print(
            "STATUS:",
            order.status
        )
        print(
            "PICKUP STATUS:",
            order.pickup_status
        )
        print(
            "RIDER:",
            rider.id
        )
        print(
            "RESTAURANT:",
            restaurant_id
        )
        print(
            "📤 RESTAURANT LIVE UPDATE SENT"
        )
        print(
            "========================================"
        )

    except Exception as socket_error:

        print(
            "⚠️ Pickup Socket.IO update error:",
            socket_error
        )

    # =========================================================
    # RESPONSE TO RIDER APP
    # =========================================================

    return jsonify({

        "success": True,

        "message": (
            "Restaurant pickup verified "
            "successfully."
        ),

        "status": order.status,

        "pickup_status": (
            order.pickup_status
        ),

        "verification_status": (
            verification.status
        ),

        "verification_token": (
            verification_token
        ),

        "token_expires_at": (
            verification.token_expires_at.isoformat()
            if verification.token_expires_at
            else None
        ),

        "restaurant_id": restaurant_id,

        "order_id": order.order_id,

        "delivery_person_id": (
            order.delivery_person_id
        )

    }), 200
@app.route(
    "/api/delivery/order/<int:order_id>/pickup/start",
    methods=["POST"]
)
def start_pickup_verification(order_id):

    data = request.get_json(silent=True) or {}
    rider_id = data.get("rider_id")

    if not rider_id:
        return jsonify({
            "success": False,
            "message": "Rider ID is required."
        }), 400

    order = Order.query.get(order_id)

    if not order:
        return jsonify({
            "success": False,
            "message": "Order not found."
        }), 404

    rider = DeliveryPerson.query.get(rider_id)

    if not rider:
        return jsonify({
            "success": False,
            "message": "Delivery person not found."
        }), 404

    # Rider must be assigned to this exact order
    if order.delivery_person_id != rider.id:
        return jsonify({
            "success": False,
            "message": "You are not assigned to this order."
        }), 403

    order_status = (
        str(order.status or "")
        .strip()
        .lower()
    )

    if order_status in [
        "cancelled",
        "canceled",
        "delivered",
        "completed"
    ]:
        return jsonify({
            "success": False,
            "message": "This order is no longer eligible for pickup."
        }), 400

    # IMPORTANT:
    # Don't restart verification if QR was already verified.
    if order.pickup_status in [
        "qr_verified",
        "restaurant_confirmed",
        "picked_up"
    ]:
        return jsonify({
            "success": True,
            "message": "Pickup verification already completed.",
            "pickup_status": order.pickup_status
        }), 200

    order.pickup_status = "verification_started"
    order.pickup_verification_started_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Pickup verification started.",
        "pickup_status": order.pickup_status
    }), 200
# ==========================================================
# RIDER APPLICATION ROUTE REGISTRATION
# ==========================================================

# ------------------ DB INIT ------------------

# ------------------ RUN 
# Your routes here...

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 5000)
    )

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=True
    )