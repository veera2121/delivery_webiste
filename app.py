import os
import math
import secrets
import uuid
import pandas as pd

from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from sqlalchemy import or_, case
from sqlalchemy.orm import joinedload
from werkzeug.security import generate_password_hash, check_password_hash



from models import db 
# ------------------ APP ------------------
app = Flask(
    __name__,
    static_folder="static",       # your static folder
    static_url_path="/static"     # URL path for static files
)
app.config["SECRET_KEY"] = "my-super-secret-key-123"
app.config["WTF_CSRF_ENABLED"] = False

# ------------------ DATABASE ------------------
# ------------------ DATABASE ------------------
db_url = os.getenv("DATABASE_URL")
if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    print("✅ Using PostgreSQL database")
else:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    INSTANCE_PATH = os.path.join(BASE_DIR, "instance")
    os.makedirs(INSTANCE_PATH, exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///" + os.path.join(INSTANCE_PATH, "restaurants.db")
    )

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ------------------ INIT EXTENSIONS ------------------
db.init_app(app)        # ✅ THIS IS THE FIX
csrf = CSRFProtect(app)
migrate = Migrate(app, db)




from models import (
    Restaurant, RestaurantUser, MenuItem, Order,
    OrderItem, DeliveryPerson, FoodItem, OTP,
    CouponUsage, RestaurantOffer, Customer
)

# ------------------ BLUEPRINTS ------------------
from users.routes import users_bp
app.register_blueprint(users_bp, url_prefix="/users")

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
# ------------------ ADMIN CONFIG ------------------
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password123"
app = Flask(__name__, static_folder="static", static_url_path="/static")

from flask import request
from flask import request, session, render_template
 # make sure you have this function or library
from datetime import datetime
@app.route("/")
def home():
    selected_location = request.args.get("location", "").strip()

    # 🔹 Filter restaurants by selected location
    if selected_location:
        restaurants = Restaurant.query.filter_by(location=selected_location).all()
    else:
        restaurants = Restaurant.query.all()

    # 🔹 List of all locations for dropdown
    all_locations = [
        loc[0]
        for loc in db.session.query(Restaurant.location).distinct()
        if loc[0]
    ]

    # 🔹 Trending items (ONLY from selected location)
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
        trending_items = []  # no location → no trending

    # 🔹 User location from session
    user_lat = session.get("user_lat")
    user_lng = session.get("user_lng")
    user_location_set = user_lat is not None and user_lng is not None

    now = datetime.now().time()

    # 🔹 Calculate delivery + open status
    for r in restaurants:
        # ===== DELIVERY CHECK =====
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

        # ===== OPEN / CLOSED CHECK =====
        if r.opening_time and r.closing_time:
            r.is_open = r.opening_time <= now <= r.closing_time
        else:
            r.is_open = False

    # ⭐ SORT: AVAILABLE FIRST
    restaurants.sort(
        key=lambda r: (
            not r.deliverable,   # deliverable first
            not r.is_open        # open first
        )
    )

    # 🔹 Handle AJAX requests
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template(
            "_restaurants.html",
            restaurants=restaurants, 
            trending_items=trending_items, 
            now=now
        )

    # 🔹 Full page render
    return render_template(
        "index.html",
        restaurants=restaurants,
        all_locations=all_locations,
        selected_location=selected_location,
        trending_items=trending_items,
        user_location_set=user_location_set,
        now=now
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



@app.route("/myorders", methods=["GET", "POST"])
def myorders():
    orders = []
    restaurant_id = None

    if request.method == "POST":
        phone = request.form.get("phone")
        order_id = request.form.get("order_id")

        query = Order.query

        if phone:
            query = query.filter(Order.phone == phone)

        if order_id:
            query = query.filter(Order.order_id == order_id)

        orders = query.order_by(Order.created_at.desc()).all()

        if orders:
            # Take restaurant ID from first order
            restaurant_id = orders[0].restaurant.id

        else:
            flash("No orders found. Please check details.", "warning")

    return render_template("myorders.html", orders=orders, restaurant_id=restaurant_id)

from sqlalchemy import func

from sqlalchemy import func
from datetime import datetime

@app.route("/cart/<int:restaurant_id>")
def cart_page(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    cart_items = session.get("cart", [])

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

    # 🔹 DELIVERY LOGIC
    base_delivery = 30
    delivery_charge = 0 if items_total >= 499 else base_delivery

    # 🔹 FREE DELIVERY MESSAGE
    if items_total >= 499:
        free_delivery_msg = "🎉 Free delivery applied"
    else:
        free_delivery_msg = f"Add ₹{499 - items_total} more for free delivery"

    # 🔹 FIRST-TIME USER CHECK
    phone = session.get("phone")
    device_fingerprint = session.get("device_fingerprint")

    delivered_orders = Order.query.filter(
        ((Order.phone == phone) | (Order.device_fingerprint == device_fingerprint)) &
        (func.lower(Order.status) == "delivered")
    ).count()

    first_time_user = delivered_orders == 0

    # 🔹 FETCH ACTIVE OFFER FOR RESTAURANT
    active_offer = RestaurantOffer.query.filter_by(
        restaurant_id=restaurant.id,
        is_active=True
    ).first()

    # 🔹 CHECK IF OFFER ALREADY USED
    offer_already_used = False
    if active_offer:
        previous_offer_order = Order.query.filter(
            (Order.restaurant_id == restaurant.id) &
            ((Order.phone == phone) | (Order.device_fingerprint == device_fingerprint)) &
            (Order.restaurant_offer_id == active_offer.id) &
            (func.lower(Order.status) == "delivered")
        ).first()
        if previous_offer_order:
            offer_already_used = True
        
    return render_template(
        "cart.html",
        restaurant=restaurant,
        items=items,
        items_total=items_total,
        delivery_charge=delivery_charge,
        free_delivery_msg=free_delivery_msg,
        first_time_user=first_time_user,
        active_offer=active_offer,
        offer_already_used=offer_already_used   # <-- Pass flag to template
    )

import random
from datetime import datetime

def generate_otp():
    return str(random.randint(100000, 999999))
from datetime import datetime

def is_restaurant_open(restaurant):
    now = datetime.now().time()

    if not restaurant.opening_time or not restaurant.closing_time:
        return False

    # Normal same-day timing
    if restaurant.opening_time < restaurant.closing_time:
        return restaurant.opening_time <= now <= restaurant.closing_time

    # Overnight timing (e.g., 8 PM – 2 AM)
    return now >= restaurant.opening_time or now <= restaurant.closing_time


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

from datetime import datetime, timedelta
from models import Order, OrderItem, RestaurantOffer, Restaurant
from utils import generate_otp, generate_order_code
from sqlalchemy import func
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
    map_link = request.form.get("map_link")
    device_fingerprint = request.form.get("device_fingerprint")

    apply_offer = request.form.get("apply_offer") == "true"
    apply_coupon = request.form.get("apply_coupon") == "true"

    # ================= ITEMS =================
    item_names = request.form.getlist("item_name[]")
    quantities = request.form.getlist("quantity[]")
    prices = request.form.getlist("price[]")

    if not item_names:
        flash("Cart is empty", "danger")
        return redirect("/")

    restaurant = Restaurant.query.get_or_404(restaurant_id)

    # ================= RESTAURANT OPEN CHECK =================
    if not is_restaurant_open(restaurant):
        flash("Restaurant is currently closed.", "danger")
        return redirect(url_for("menu", restaurant_id=restaurant_id))

    # ================= ITEMS TOTAL =================
    items_total = sum(
        int(quantities[i]) * float(prices[i])
        for i in range(len(item_names))
    )

    # ================= DELIVERY CHARGE =================
    delivery_charge = restaurant.delivery_charge or 0
    if restaurant.free_delivery_limit and items_total >= restaurant.free_delivery_limit:
        delivery_charge = 0

    # ================= SESSION =================
    session["phone"] = phone
    session["device_fingerprint"] = device_fingerprint

    # ================= RESTAURANT OFFER =================
    offer_discount = 0
    offer_used = None

    offer_data = get_active_offer_for_restaurant(
        restaurant_id,
        device_fingerprint
    )

    if (
        apply_offer and
        offer_data["id"] and
        not offer_data["already_used"] and
        items_total >= offer_data["min_order_amount"]
    ):
        offer_used = RestaurantOffer.query.get(offer_data["id"])

        if offer_data["offer_type"] == "percent":
            offer_discount = (items_total * offer_data["offer_value"]) / 100

        elif offer_data["offer_type"] == "flat":
            offer_discount = offer_data["offer_value"]

        elif offer_data["offer_type"] == "free_delivery":
            delivery_charge = 0

    # ================= COUPON (ONLY IF OFFER NOT APPLIED) =================
    coupon_discount = 0
    coupon_used = None

    delivered_orders = Order.query.filter(
        ((Order.phone == phone) | (Order.device_fingerprint == device_fingerprint)),
        func.lower(Order.status) == "delivered"
    ).count()

    first_time_user = delivered_orders == 0

    if (
        offer_discount == 0 and
        apply_coupon and
        first_time_user and
        items_total >= 199
    ):
        coupon_discount = min(items_total * 0.30, 60)
        coupon_used = "FIRST30"

    # ================= FINAL TOTAL =================
    total_discount = offer_discount + coupon_discount
    final_total = round(items_total + delivery_charge - total_discount, 2)

    # ================= OTP =================
    order_otp = generate_otp()

    # ================= CREATE ORDER =================
    new_order = Order(
        restaurant_id=restaurant_id,
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
        device_fingerprint=device_fingerprint,
        items_total=items_total,
        discount=coupon_discount,
        restaurant_offer_discount=offer_discount,
        restaurant_offer_id=offer_used.id if offer_used else None,
        delivery_charge=delivery_charge,
        final_total=final_total,
        coupon_used=coupon_used,
        map_link=map_link,
        otp=order_otp
    )

    db.session.add(new_order)
    db.session.commit()

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

    flash(f"Order placed successfully! Order ID: {new_order.order_id}", "success")
    return redirect(url_for("myorders", restaurant_id=restaurant_id))


# ------------------ SUPER ADMIN ------------------
@csrf.exempt
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USERNAME and request.form.get("password") == ADMIN_PASSWORD:
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
    pagination = q.paginate(page=page, per_page=10)
    orders = pagination.items

    # ---------------- DELIVERY PERSONS & RESTAURANTS ----------------
    delivery_persons = DeliveryPerson.query.order_by(DeliveryPerson.name).all()
    restaurants = Restaurant.query.all()

    # ---------------- ADMIN STATISTICS ----------------
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())

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

        # Today's delivered orders & revenue
        "total_orders_today": Order.query.filter(
            db.func.date(Order.created_at) == today,
            Order.status == "Delivered"
        ).count(),
        "total_revenue_today": sum(
            o.get_final_total() for o in Order.query.filter(
                db.func.date(Order.created_at) == today,
                Order.status == "Delivered"
            ).all()
        ),

        # Weekly statistics
        "week_orders": Order.query.filter(Order.created_at >= week_start).count(),
        "total_revenue": sum(o.get_final_total() for o in Order.query.filter_by(status="Delivered").all()),
        "weekly_revenue": sum(
            o.get_final_total() for o in Order.query.filter(
                Order.created_at >= week_start,
                Order.status == "Delivered"
            ).all()
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
            "completed": len([o for o in r_orders if o.status == "Delivered"])
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
        restaurant_stats=restaurant_performance
    )


# ---------------- ASSIGN DELIVERY PERSON ----------------


@app.route("/restaurant/update_status/<int:order_id>", methods=["POST"])
def update_status(order_id):
    if not session.get("restaurant_logged_in"):
        return redirect(url_for("restaurant_login"))

    new_status = request.form.get("status")
    order = Order.query.get(order_id)
    if not order:
        flash("Order not found!", "danger")
        return redirect(url_for("restaurant_dashboard"))

    order.status = new_status
    db.session.commit()

    flash("Order status updated!", "success")
    return redirect(url_for("restaurant_dashboard"))



@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))

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
@app.route("/restaurant/dashboard")
def restaurant_dashboard():
    restaurant_id = session.get("restaurant_id")
    if not restaurant_id:
        return redirect(url_for("restaurant_login"))

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    # Fetch orders only for this restaurant
    orders = Order.query.filter_by(
        restaurant_id=restaurant_id
    ).order_by(Order.created_at.desc()).all()

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
        "active_orders": len([o for o in orders if o.status in ["Preparing", "Out for Delivery"]]),
        "today_earnings": sum(o.get_final_total() for o in delivered_today_orders),
        "today_cod_amount": sum(o.get_final_total() for o in delivered_today_orders if o.payment_type == "COD"),
        "today_online_amount": sum(o.get_final_total() for o in delivered_today_orders if o.payment_type == "Online"),
        "weekly_orders": len([o for o in orders if o.created_at.date() >= week_ago]),
        "weekly_earnings": sum(o.get_final_total() for o in orders if o.created_at.date() >= week_ago and o.status == "Delivered"),
        "weekly_delivered_orders": len([o for o in orders if o.created_at.date() >= week_ago and o.status == "Delivered"])
    }

    # ✅ FIXED: Only this restaurant’s delivery boys
    delivery_persons = DeliveryPerson.query.filter_by(
        restaurant_id=restaurant_id
    ).order_by(DeliveryPerson.name).all()

    return render_template(
        "restaurant_dashboard.html",
        stats=stats,
        orders=orders,
        delivery_persons=delivery_persons
    )


@app.route("/restaurant/update_status/<int:order_id>", methods=["POST"])
def restaurant_update_status(order_id):  # renamed
    if not session.get("restaurant_logged_in"):
        return redirect(url_for("restaurant_login"))

    new_status = request.form.get("status")
    order = Order.query.get(order_id)
    if not order:
        flash("Order not found!", "danger")
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






@app.route("/delivery/login", methods=["GET", "POST"])
def delivery_login():
    if request.method == "POST":
        phone = request.form.get("phone")
        password = request.form.get("password")

        dp = DeliveryPerson.query.filter_by(phone=phone).first()

        if dp and dp.check_password(password):
            session["delivery_logged_in"] = True
            session["delivery_person_id"] = dp.id
            session["delivery_person_name"] = dp.name
            session["restaurant_id"] = dp.restaurant_id  # ✅ IMPORTANT

            return redirect(url_for("delivery_dashboard"))

        flash("Invalid login!", "danger")

    return render_template("delivery_login.html")

@app.route("/delivery/dashboard", methods=["GET", "POST"])
def delivery_dashboard():
    if not session.get("delivery_logged_in"):
        return redirect(url_for("delivery_login"))

    dp_id = session.get("delivery_person_id")

    # ---------- SUBMIT OTP ----------
    if request.method == "POST":
        order_id = request.form.get("order_id")
        entered_otp = request.form.get("otp")

        order = Order.query.get(int(order_id))

        if order and order.otp == entered_otp:
            order.status = "Delivered"
            order.delivered_time = datetime.utcnow()
            db.session.commit()
            flash(f"Order {order.order_id} marked Delivered", "success")
        else:
            flash("Invalid OTP!", "danger")

        return redirect(url_for("delivery_dashboard"))

    # ---------- GET ORDERS ----------
    
    orders = Order.query.filter(
        Order.delivery_person_id == dp_id,
        Order.status != "Delivered"
    ).order_by(
        case(
            (Order.status == "Assigned", 0),
            (Order.status == "Out for Delivery", 1),
            else_=2
        ),
        Order.created_at.desc()
    ).all()

    # ---------- STATS ----------
    stats = {
        "total": Order.query.filter_by(delivery_person_id=dp_id).count(),
        "pending": Order.query.filter_by(delivery_person_id=dp_id, status="Assigned").count(),
        "delivered": Order.query.filter_by(delivery_person_id=dp_id, status="Delivered").count(),
    }

    # ---------- AJAX AUTO REFRESH ----------
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template(
            "delivery_dashboard.html",
            orders=orders
        )

    # ---------- FULL PAGE ----------
    return render_template(
        "delivery_dashboard.html",
        orders=orders,
        stats=stats
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
    session.pop("delivery_logged_in", None)
    session.pop("delivery_person_id", None)
    session.pop("delivery_person_name", None)
    return redirect(url_for("delivery_login"))

@app.route("/admin/add_delivery_person", methods=["GET", "POST"])
def add_delivery_person():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        password = request.form.get("password")
        restaurant_id = request.form.get("restaurant_id")  # ✅ FROM FORM

        if not all([name, phone, password, restaurant_id]):
            flash("All fields are required!", "danger")
            return redirect(url_for("add_delivery_person"))

        if DeliveryPerson.query.filter_by(phone=phone).first():
            flash("Phone already exists!", "danger")
            return redirect(url_for("add_delivery_person"))

        dp = DeliveryPerson(
            name=name,
            phone=phone,
            restaurant_id=restaurant_id   # ✅ CORRECT LINK
        )
        dp.set_password(password)

        db.session.add(dp)
        db.session.commit()

        flash("Delivery person added successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    restaurants = Restaurant.query.order_by(Restaurant.name).all()
    return render_template(
        "add_delivery_person.html",
        restaurants=restaurants
    )


@app.route("/admin/add_restaurant", methods=["GET", "POST"])
def add_restaurant():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        email = request.form.get("email")
        address = request.form.get("address")
        sheet_url = request.form.get("sheet_url")
        location = request.form.get("location")  # <-- get location

        if not name or not phone or not email or not sheet_url:
            flash("Name, phone, email, and Google Sheet URL are required!", "danger")
            return redirect(url_for("add_restaurant"))

        if Restaurant.query.filter_by(name=name).first():
            flash("Restaurant already exists!", "danger")
            return redirect(url_for("add_restaurant"))

        # Save restaurant INCLUDING location
        restaurant = Restaurant(
            name=name,
            phone=phone,
            email=email,
            address=address,
            sheet_url=sheet_url,
            location=location   # <-- SAVE IT HERE
        )

        db.session.add(restaurant)
        db.session.commit()

        flash(f"Restaurant {name} added successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_restaurant.html")



@app.route("/menu/<int:restaurant_id>")
def menu(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)

    if not restaurant.sheet_url:
        return "Error: No Google Sheet URL set for this restaurant"

    try:
        # Load CSV directly
        df = pd.read_csv(restaurant.sheet_url)
        items = df.to_dict(orient="records")

        # Group items by category
        menu_by_category = {}
        for item in items:
            category = item.get('category', 'Other')
            menu_by_category.setdefault(category, []).append(item)

        return render_template("menu.html", restaurant=restaurant, menu_by_category=menu_by_category)

    except Exception as e:
        return f"Error loading menu: {e}"

@app.route("/assign_delivery/<int:order_id>", methods=["POST"])
def assign_delivery(order_id):
    delivery_person_id = request.form.get("delivery_person_id")
    order = Order.query.get(order_id)

    if not order:
        flash("Order not found!", "danger")
        return redirect(url_for("restaurant_dashboard"))

    if not delivery_person_id:
        flash("Please select a delivery person!", "warning")
        return redirect(url_for("restaurant_dashboard"))

    dp = DeliveryPerson.query.get(int(delivery_person_id))
    if not dp:
        flash("Delivery person not found!", "danger")
        return redirect(url_for("restaurant_dashboard"))

    # ✅ ONLY ASSIGN DELIVERY BOY
    order.delivery_person_id = dp.id
    order.delivery_boy_name = dp.name
    order.delivery_boy_phone = dp.phone
    order.status = "Out for Delivery"

    db.session.commit()

    flash("Delivery person assigned successfully.", "success")
    return redirect(url_for("restaurant_dashboard"))



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

    # ✅ ONLY completed orders (Delivered + Not Delivered)
    history = Order.query.filter(
    Order.delivery_person_id == delivery_person_id,
    Order.status.in_(["Delivered", "Customer Not Available"])
    ).order_by(Order.updated_at.desc()).all()

    # Classify orders by day
    for o in history:
        if o.created_at.date() == today:
            o.day_category = "Today"
        elif o.created_at.date() == yesterday:
            o.day_category = "Yesterday"
        else:
            o.day_category = "Older"

    # ✅ Totals ONLY for Delivered orders
    totals = {}
    for day in ["Today", "Yesterday", "Older"]:
        day_orders = [
            o for o in history
            if o.day_category == day and o.status == "Delivered"
        ]

        totals[day] = {
            "count": len(day_orders),
            "cod_amount": sum(
                o.get_final_total() for o in day_orders if o.payment_type == "COD"
            ),
            "online_amount": sum(
                o.get_final_total() for o in day_orders if o.payment_type == "Online"
            ),
        }

    return render_template(
        "delivery_history.html",
        history=history,
        totals=totals
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




@app.route('/restaurants')
def restaurants_page():
    selected_location = request.args.get('location', '')  # get selected location from URL

    # Fetch restaurants
    if selected_location:
        restaurants = Restaurant.query.filter_by(location=selected_location).all()
    else:
        restaurants = Restaurant.query.all()

    # Get all unique locations from DB for dropdown
    all_locations = [loc[0] for loc in db.session.query(Restaurant.location).distinct().all() if loc[0]]

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

@app.route("/admin/reports")
def admin_reports():
    restaurants = Restaurant.query.all()

    restaurant_id = request.args.get("restaurant_id")
    report_type = request.args.get("type", "day")   # day / week
    from_date = request.args.get("from")
    to_date = request.args.get("to")

    # ---------- CASE STATEMENTS (SQLAlchemy 2.x compatible) ----------
    delivered_case = case((Order.status == "Delivered", 1), else_=0)
    cancelled_case = case((Order.status == "Cancelled", 1), else_=0)

    items_case = case((Order.status == "Delivered", Order.items_total), else_=0)
    delivery_case = case((Order.status == "Delivered", Order.delivery_charge), else_=0)

    coupon_discount_case = case((Order.status == "Delivered", Order.discount), else_=0)
    restaurant_offer_case = case((Order.status == "Delivered", Order.restaurant_offer_discount), else_=0)

    # ---------- MAIN REPORT QUERY ----------
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
                func.coalesce(func.sum(items_case), 0) +
                func.coalesce(func.sum(delivery_case), 0) -
                func.coalesce(func.sum(coupon_discount_case), 0) -
                func.coalesce(func.sum(restaurant_offer_case), 0)
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
        query = query.add_columns(func.date(Order.created_at).label("period")).group_by(
            Restaurant.name, func.date(Order.created_at)
        )
    else:
        query = query.add_columns(func.strftime('%Y-%W', Order.created_at).label("period")).group_by(
            Restaurant.name, func.strftime('%Y-%W', Order.created_at)
        )

    # ---------- ORDER ----------
    query = query.order_by(func.date(Order.created_at).desc(), Restaurant.name.asc())
    reports = query.all()

    # ---------- SUMMARY QUERY ----------
    summary_query = (
        db.session.query(
            Restaurant.name.label("restaurant"),
            func.coalesce(func.sum(case((Order.status == "Delivered", Order.items_total), else_=0)), 0).label("items_total"),
            func.coalesce(func.sum(case((Order.status == "Delivered", Order.delivery_charge), else_=0)), 0).label("delivery_total"),
            func.coalesce(func.sum(case((Order.status == "Delivered", Order.discount), else_=0)), 0).label("coupon_discount_total"),
            func.coalesce(func.sum(case((Order.status == "Delivered", Order.restaurant_offer_discount), else_=0)), 0).label("restaurant_offer_total"),
            (
                func.coalesce(func.sum(case((Order.status == "Delivered", Order.items_total), else_=0)), 0) +
                func.coalesce(func.sum(case((Order.status == "Delivered", Order.delivery_charge), else_=0)), 0) -
                func.coalesce(func.sum(case((Order.status == "Delivered", Order.discount), else_=0)), 0) -
                func.coalesce(func.sum(case((Order.status == "Delivered", Order.restaurant_offer_discount), else_=0)), 0)
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

    return render_template(
        "admin_reports.html",
        restaurants=restaurants,
        reports=reports,
        summary=summary,
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

@app.route("/profile")
def profile():
    if "customer_id" not in session:
        return render_template("profile.html", logged_in=False)

    customer = Customer.query.get(session["customer_id"])
    return render_template("profile.html", logged_in=True, customer=customer)

   

# Logout
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully")
    return redirect(url_for("users.login"))  # <-- use users.login

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
    if coupon_code != "FIRST30":
        return jsonify({"success": False, "message": "Invalid coupon code."})

    # Check if user has any delivered orders (first-time check)
    delivered_orders = Order.query.filter(
        ((Order.phone == phone) | (Order.device_fingerprint == device_fingerprint)) &
        (func.lower(Order.status) == "delivered")
    ).count()

    if delivered_orders > 0:
        return jsonify({"success": False, "message": "Coupon valid for first-time users only."})

    # Minimum items total to apply coupon
    if items_total < 199:
        return jsonify({"success": False, "message": "Order must be at least ₹199 to apply coupon."})

    # Apply discount: 30% off capped at 60
    discount = min(items_total * 0.30, 60)

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





@app.route("/dashboard/restaurant/<int:restaurant_id>/edit", methods=["GET", "POST"])
def edit_restaurant_card(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)

    if request.method == "POST":
        restaurant.name = request.form.get("name")
        restaurant.address = request.form.get("address")
        restaurant.phone = request.form.get("phone")
        restaurant.email = request.form.get("email")

        restaurant.is_veg = request.form.get("is_veg") == "yes"
        restaurant.rating = float(request.form.get("rating") or 4.0)
        restaurant.price_level = request.form.get("price_level")
        restaurant.delivery_time = request.form.get("delivery_time")
        restaurant.popular_items = request.form.get("popular_items")

        restaurant.delivery_charge = float(request.form.get("delivery_charge") or 30)
        restaurant.free_delivery_limit = float(request.form.get("free_delivery_limit") or 499)

        # Open / Close times
        opening_time_str = request.form.get("opening_time")
        closing_time_str = request.form.get("closing_time")
        restaurant.latitude = request.form.get("latitude") or None
        restaurant.longitude = request.form.get("longitude") or None
        restaurant.delivery_radius_km = request.form.get("delivery_radius_km") or 5

        if opening_time_str:
            restaurant.opening_time = datetime.strptime(opening_time_str, "%H:%M").time()
        if closing_time_str:
            restaurant.closing_time = datetime.strptime(closing_time_str, "%H:%M").time()
    
        db.session.commit()
        flash("Restaurant card updated successfully!", "success")
        return redirect(url_for("restaurant_dashboard", restaurant_id=restaurant.id))

    return render_template("dashboard/edit_restaurant_card.html", restaurant=restaurant)


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



@app.route("/test-icon")
def test_icon():
    return app.send_static_file("icons/icon-192.png")

# ------------------ DB INIT ------------------

# ------------------ RUN ------------------
# Your routes here...

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)