# models.py

from datetime import datetime, date, time
import pytz

from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship
from sqlalchemy import CheckConstraint
from flask_login import UserMixin

from extensions import db   # ✅ ONLY ONE db, coming from extensions.py
restaurant_categories = db.Table(
    "restaurant_categories",
    db.Column("restaurant_id", db.Integer, db.ForeignKey("restaurant.id")),
    db.Column("category_id", db.Integer, db.ForeignKey("category.id"))
)
class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # ================= BASIC INFO =================
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(500))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(200))
    sheet_url = db.Column(db.String(500))
    location = db.Column(db.String(100))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # ================= CATEGORY =================
    category_type = db.Column(
        db.String(20),
        nullable=False,
        default="restaurant"
    )

    # ================= CARD DETAILS =================
    is_veg = db.Column(db.Boolean, default=True)
    rating = db.Column(db.Float, default=4.0)
    price_level = db.Column(db.String(10), default="₹₹")
    delivery_time = db.Column(db.String(20), default="30–40 mins")
    
    # ================= ORDER ACCEPTANCE =================
    is_accepting_orders = db.Column(db.Boolean, default=True, nullable=False)
    accept_orders_until = db.Column(db.Time, nullable=True)

    popular_items = db.Column(
        db.String(255),
        default="Biryani • Pizza • Rolls • Chinese"
    )

    # ================= STATUS =================
    start_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="coming_soon")

    # ================= DELIVERY =================
    delivery_charge = db.Column(db.Float, default=30, nullable=False)
    free_delivery_limit = db.Column(db.Float, default=499, nullable=False)
    force_delivery_charge = db.Column(db.Boolean, default=False, nullable=False)
    timezone = db.Column(
    db.String(50),
    default="Asia/Kolkata",
    nullable=False
    )

    # ================= OPEN / CLOSE =================
    opening_time = db.Column(db.Time, default=time(10, 0))
    closing_time = db.Column(db.Time, default=time(22, 0))

    # ================= LOCATION =================
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    delivery_radius_km = db.Column(db.Float, default=5)

    # ================= 🔥 LIMITED DROP =================
    is_limited_drop = db.Column(db.Boolean, default=False)
    limited_item_name = db.Column(db.String(100))
    limited_total_qty = db.Column(db.Integer, default=0)
    limited_remaining_qty = db.Column(db.Integer, default=0)
    limited_start_datetime = db.Column(db.DateTime)
    limited_end_datetime = db.Column(db.DateTime)

    # ================= RELATIONSHIPS =================
    users = db.relationship("RestaurantUser", backref="restaurant", lazy=True)
    orders = db.relationship("Order", backref="restaurant", lazy=True)
    delivery_persons = db.relationship("DeliveryPerson", backref="restaurant", lazy=True)
    menu_items = db.relationship("MenuItem", backref="restaurant", lazy=True)
    offers = db.relationship("RestaurantOffer", backref="restaurant", lazy=True) 
    categories = db.relationship(
        "Category",
        secondary=restaurant_categories,
        backref="restaurants",
        lazy="subquery"   # loads categories automatically
    )



    # ================= CONSTRAINT =================
    __table_args__ = (
        CheckConstraint(
            "category_type IN ('restaurant', 'bakery')",
            name="category_type_check"
        ),
    )

    # ================= ACTIVE OFFER =================
    @property
    def active_offer(self):
        now = datetime.utcnow()
        return next(
            (
                o for o in self.offers
                if o.is_active
                and o.start_date
                and o.end_date
                and o.start_date <= now <= o.end_date
            ),
            None
        )

    # ================= ORDER LOGIC =================


    from datetime import datetime, date
    import pytz

    @property
    def can_accept_orders(self):
        # 🌍 Local time (for opening hours)
        tz = pytz.timezone(self.timezone or "Asia/Kolkata")
        now_local = datetime.now(tz)
        now_time = now_local.time()

        # ❌ Sold out
        if self.is_limited_drop and self.sold_out:
            return False

        # ❌ Manual OFF
        if not self.is_accepting_orders:
            return False

        # ❌ Suspended
        if self.status == "suspended":
            return False

        # ❌ Coming soon
        if self.status == "coming_soon":
            if not self.start_date or date.today() < self.start_date:
                return False

        # 🕒 LIMITED DROP (UTC ONLY — FIXED)
        if self.is_limited_drop and self.limited_start_datetime and self.limited_end_datetime:
            now_utc = datetime.utcnow()
            if not (self.limited_start_datetime <= now_utc <= self.limited_end_datetime):
                return False

        # 🕒 Opening & closing hours (LOCAL)
        if self.opening_time and self.closing_time:
            if self.opening_time < self.closing_time:
                if not (self.opening_time <= now_time <= self.closing_time):
                    return False
            else:
                # Overnight
                if not (now_time >= self.opening_time or now_time <= self.closing_time):
                    return False

        # ⏸ Accept orders until
        if self.accept_orders_until and now_time > self.accept_orders_until:
            return False

        return True


    # ================= LIMITED DROP HELPERS =================
    @property
    def sold_out(self):
        return self.is_limited_drop and self.limited_remaining_qty <= 0

    @property
    def stock_percent(self):
        if not self.is_limited_drop or self.limited_total_qty == 0:
            return 100
        return int((self.limited_remaining_qty / self.limited_total_qty) * 100)

    @property
    def stock_warning(self):
        if not self.is_limited_drop:
            return False
        threshold = max(5, int(self.limited_total_qty * 0.1))
        return self.limited_remaining_qty <= threshold

    @property
    def display_item(self):
        return self.limited_item_name if self.is_limited_drop else self.popular_items

# ----------------- Restaurant Admin User -----------------
class RestaurantUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# ----------------- Menu Item -----------------
class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurant.id"),
        nullable=False
    )

    # BASIC
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))          # Cakes, Custom Cakes
    description = db.Column(db.Text)

    # PRICING
    price = db.Column(db.Float, default=0)
    weight_prices = db.Column(db.Text)            # 0.5kg:350,1kg:650

    # MEDIA
    image_url = db.Column(db.String(500))

    # STATUS / TYPE
    availability = db.Column(db.String(10), default="yes")
    type = db.Column(db.String(20), default="ordinary")  
    # ordinary | cool

    # EXTRA
    flavour = db.Column(db.Text)
    order_type = db.Column(db.String(20))  # instant | custom

# ----------------- Delivery Person -----------------
class DeliveryPerson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    username = db.Column(db.String(100), unique=True)
    password_hash = db.Column(db.String(200))
    phone = db.Column(db.String(20), unique=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
     # ✅ ADD THESE
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    last_seen = db.Column(db.DateTime)

    is_active = db.Column(db.Boolean, default=True)
    is_online = db.Column(db.Boolean, default=False)  # ✅ real-time status

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Order(db.Model):
   
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    order_id = db.Column(db.String(64), unique=True, index=True)

    # ---------------- CUSTOMER DETAILS ----------------
    customer_name = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    alt_phone = db.Column(db.String(20))
    email = db.Column(db.String(200))
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)

    # ---------------- ORDER TOTALS ----------------
    items_total = db.Column(db.Float, default=0.0)          # Sum of all items
    discount = db.Column(db.Float, default=0.0)             # FIRST30 discount
    delivery_charge = db.Column(db.Float, default=0.0)
    final_total = db.Column(db.Float, default=0.0)          # items_total - discount + delivery_charge
    coupon_used = db.Column(db.String(50), nullable=True)
    device_fingerprint = db.Column(db.Text, nullable=True)

    restaurant_offer_discount = db.Column(db.Float, default=0)
    # ---------------- ORDER STATUS ----------------
    status = db.Column(db.String(50), default="Pending")    # Pending / Completed / Cancelled
    otp = db.Column(db.String(10))

    # ---------------- PAYMENT & ORDER TYPE ----------------
    payment_type = db.Column(db.String(20), nullable=True)  # COD / Online
    order_type = db.Column(db.String(50))                   # Delivery / Pickup
    # ---------------- REWARD SYSTEM ----------------
    coins_given = db.Column(db.Boolean, default=False, nullable=False)

    # 🔥 COIN REDEMPTION
    coins_redeemed = db.Column(db.Integer, default=0, nullable=False)
    coins_discount_amount = db.Column(db.Float, default=0.0, nullable=False)

            # ---------------- ADDRESS ----------------
    house_no = db.Column(db.String(255))
    landmark = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    pincode = db.Column(db.String(20))
    address_type = db.Column(db.String(50))                # Home / Office
    delivery_note = db.Column(db.Text)                     # Optional instructions
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    map_link = db.Column(db.String(300))
    address = db.Column(db.String(500))
    
    # ---------------- RELATIONSHIPS ----------------
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    delivery_person_id = db.Column(db.Integer, db.ForeignKey('delivery_person.id'), nullable=True)
    delivery_person = db.relationship("DeliveryPerson", backref="orders", lazy=True)
    items = db.relationship("OrderItem", backref="order", lazy=True)

    # ---------------- TIMESTAMPS ----------------
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    delivered_time = db.Column(db.DateTime, nullable=True)
    not_delivered_time = db.Column(db.DateTime, nullable=True)

    # ---------------- DELIVERY FEEDBACK ----------------
    delay_reason = db.Column(db.String(300))
    cancel_reason = db.Column(db.String(300))
    not_delivered_reason = db.Column(db.String(300))
    delivery_attempts = db.Column(db.Integer, default=0)
    delivery_feedback = db.Column(db.String(300), nullable=True)
    packing_photo = db.Column(db.String(300))
    delivered_photo = db.Column(db.String(300))
    distance_km = db.Column(db.Float)
    profit_amount = db.Column(db.Float, default=0.0)
    admin_notes = db.Column(db.String(300)) 
    
    
  
 
    restaurant_offer_id = db.Column(
        db.Integer,
        db.ForeignKey('restaurant_offer.id'),
        nullable=True
    )

    restaurant_offer_discount = db.Column(
        db.Float,
        default=0
    )

    
    # ---------------- HELPER FUNCTION ----------------
    def get_final_total(self):
        items_total = self.items_total or 0
        delivery = self.delivery_charge or 0
        discount = self.discount or 0
        return round(items_total + delivery - discount, 2)
    
# ----------------- Order Item -----------------
class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    item_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)

    def item_total(self):
        return round((self.price or 0) * (self.quantity or 0), 2)
# ----------------- Category -----------------
class Category(db.Model):
    __tablename__ = "category"   # ⭐ VERY IMPORTANT
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    image = db.Column(db.String(200))

# ----------------- Food Item (For Trending & Analytics) ----------------- 
class FoodItem(db.Model):
    __tablename__ = "food_item"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey('restaurant.id'),
        nullable=False
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey('category.id'),
        nullable=False
    )

    order_count = db.Column(db.Integer, default=0)

    # ✅ ADD THESE
    restaurant = db.relationship("Restaurant", backref="food_items")
    category = db.relationship("Category", backref="food_items")
# ----------------- Customer / App User -----------------
class Customer(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), default="User")
    mobile = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 🔥 Reward Coins
    coins = db.Column(db.Integer, default=0)

    # ✅ Used ONLY for animation trigger
    last_reward_coins = db.Column(db.Integer, default=0)

    # Orders
    orders = db.relationship("Order", backref="customer", lazy=True)

    # Coin history
    coin_logs = db.relationship("CoinLedger", backref="customer", lazy=True)

    badge_id = db.Column(
        db.Integer,
        db.ForeignKey("reward_badge.id")
    )
    badge = db.relationship("RewardBadge")

class OTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    mobile = db.Column(db.String(15), nullable=False, index=True)

    otp_hash = db.Column(db.String(255), nullable=False)

    purpose = db.Column(db.String(30), nullable=False)  # login | order_receive

    order_id = db.Column(db.Integer, nullable=True)

    attempts = db.Column(db.Integer, default=0)

    expires_at = db.Column(db.DateTime, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)



class CouponUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coupon_code = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    device_fingerprint = db.Column(db.Text, nullable=True)

    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class RestaurantOffer(db.Model):
    __tablename__ = "restaurant_offer"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"))
    title = db.Column(db.String(200))
    description = db.Column(db.String(300))
    offer_type = db.Column(db.String(50))
    offer_value = db.Column(db.Float)
    min_order_amount = db.Column(db.Float, default=0.0)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
class PlatformOffer(db.Model):
    __tablename__ = "platform_offer"

    id = db.Column(db.Integer, primary_key=True)
    coupon_code = db.Column(db.String(50), unique=True)

    offer_type = db.Column(db.String(20))   # percent / flat
    offer_value = db.Column(db.Float)       # 30 = 30%

    min_order_amount = db.Column(db.Float, default=0)
    max_discount = db.Column(db.Float)      # eg: 60

    free_delivery = db.Column(db.Boolean, default=False)  # ✅ NEW

    is_first_order = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
         # ✅ ADD THIS
    
class OrderAssignment(db.Model):
    __tablename__ = "order_assignment"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("order.id"),
        nullable=False
    )

    delivery_person_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_person.id"),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default="assigned"
    )
    # assigned | accepted | rejected | expired

    assigned_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    responded_at = db.Column(
        db.DateTime,
        nullable=True
    )

    order = db.relationship("Order", backref="assignments")
    delivery_person = db.relationship("DeliveryPerson", backref="assignments")
    assign_type = db.Column(db.String(20), default="auto")
# auto | manual



class UserFeedback(db.Model):
    __tablename__ = "user_feedback"

    id = db.Column(db.Integer, primary_key=True)  # ✅ real PK

    feedback_id = db.Column(
        db.String(20),
        unique=True,
        nullable=False,
        default=lambda: f"FB{int(datetime.utcnow().timestamp())}"
    )

    user_id = db.Column(db.Integer, nullable=True)
    user_name = db.Column(db.String(100))
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120))
    order_id = db.Column(db.String(50))
    issue_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default="Normal")
    status = db.Column(db.String(20), default="Pending")

    assigned_to = db.Column(db.String(100))
    admin_note = db.Column(db.Text)
    source = db.Column(db.String(20), default="web")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)
class RestaurantDelivery(db.Model):
    __tablename__ = "restaurant_delivery"

    id = db.Column(db.Integer, primary_key=True)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurant.id"),
        nullable=False
    )

    delivery_person_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_person.id"),
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "restaurant_id",
            "delivery_person_id",
            name="unique_restaurant_delivery"
        ),
    )
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(15))

    # Address fields
    address_line = db.Column(db.String(255))
    landmark = db.Column(db.String(100))
    area = db.Column(db.String(100))
    city = db.Column(db.String(50))
    pincode = db.Column(db.String(10))

    created_at = db.Column(db.DateTime, default=datetime.utcnow) 
    coins = db.Column(db.Integer, default=0)
class DeliverySettings(db.Model):
    __tablename__ = "delivery_settings"

    id = db.Column(db.Integer, primary_key=True)

    # Distance slabs (km)
    base_distance = db.Column(db.Float, default=3)
    base_charge = db.Column(db.Integer, default=30)

    slab_1_upto = db.Column(db.Float, default=6)
    slab_1_charge = db.Column(db.Integer, default=40)

    slab_2_upto = db.Column(db.Float, default=9)
    slab_2_charge = db.Column(db.Integer, default=55)

    slab_3_upto = db.Column(db.Float, default=12)
    slab_3_charge = db.Column(db.Integer, default=70)

    max_charge = db.Column(db.Integer, default=90)

    # Free delivery
    free_delivery_min_order = db.Column(db.Integer, default=499)

    # Surge / Night
    night_surge = db.Column(db.Integer, default=0)   # ₹
    is_night_surge_active = db.Column(db.Boolean, default=False)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    shop_name = db.Column(db.String(50), nullable=False)  # which restaurant
    is_combo = db.Column(db.Boolean, default=False)
    combo_items = db.Column(db.String(200))  # optional, for combo names

class ShopSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_name = db.Column(db.String(50), unique=True)
    min_delivery_amount = db.Column(db.Float, default=0)  # minimum delivery




class RewardSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    earn_per_rupees = db.Column(db.Integer, default=100)
    earn_coins = db.Column(db.Integer, default=10)
    coin_value_rupees = db.Column(db.Float, default=0.10)
    min_redeem_coins = db.Column(db.Integer, default=500)
    max_redeem_percent = db.Column(db.Integer, default=20)
    coins_expiry_days = db.Column(db.Integer, default=180)


class RewardEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    multiplier = db.Column(db.Float, default=1.0)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True)

class CoinLedger(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customer.id"),
        nullable=False
    )

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("order.id"),
        nullable=True
    )

    coins = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class RewardBadge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    required_coins = db.Column(db.Integer, nullable=False)
    benefits = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
