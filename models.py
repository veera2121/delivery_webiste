# models.py

from datetime import datetime, date, time
import pytz
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship
from sqlalchemy import CheckConstraint
from flask_login import UserMixin
from sqlalchemy import Enum   # 👈 ADD THIS AT TOP
from extensions import db   # ✅ ONLY ONE db, coming from extensions.py
from sqlalchemy import Index, text
from users.restaurant_control import get_restaurant_order_control
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
    
    is_best_seller = db.Column(db.Boolean, nullable=False, server_default="0")
    is_fast_delivery = db.Column(db.Boolean, nullable=False, server_default="0")
    # ================= CATEGORY =================
    
        # ================= RESTAURANT BREAK SCHEDULE =================
    break_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default="0"
    )

    break_start_time = db.Column(
        db.Time,
        nullable=True
    )

    break_end_time = db.Column(
        db.Time,
        nullable=True
    )
    category_type = db.Column(db.String(20), nullable=False)
        # ================= CARD DETAILS =================
    is_veg = db.Column(db.Boolean, default=True)
    rating = db.Column(db.Float, default=4.0)
    price_level = db.Column(db.String(10), default="₹₹")
    delivery_time = db.Column(db.String(20), default="30–40 mins")
    
    # ================= ORDER ACCEPTANCE =================
    is_accepting_orders = db.Column(db.Boolean, default=True, nullable=False)
    accept_orders_until = db.Column(db.Time, nullable=True)
        # ========================================================
    # SUPER ADMIN ORDER OVERRIDE
    #
    # inherit    = follow normal restaurant rules
    # force_on   = admin explicitly enables
    # force_off  = admin explicitly disables
    # ========================================================

    admin_order_override = db.Column(
        db.String(20),
        nullable=False,
        default="inherit",
        server_default="inherit"
    )
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
    # LOCATION-WISE DELIVERY PRICING
    # ============================================================

    delivery_location_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "delivery_location_settings.id"
        ),
        nullable=True,
        index=True
    )

    delivery_location_settings = db.relationship(
        "DeliveryLocationSettings",
        back_populates="restaurants"
    )
    # ================= HOMEPAGE ORDER =================
    homepage_position = db.Column(db.Integer, default=999)
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
        result = get_restaurant_order_control(self)
        return result["allowed"]

    @property
    def order_control_status(self):
        return get_restaurant_order_control(self)
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
    # =========================================================
    # CREATE RESTAURANT PICKUP QR
    # =========================================================

    def create_restaurant_pickup_qr(restaurant_id):

        # Check whether this restaurant already has a QR
        existing_qr = RestaurantPickupQR.query.filter_by(
            restaurant_id=restaurant_id
        ).first()

        if existing_qr:
            return existing_qr

        # Generate secure random token
        qr_token = secrets.token_urlsafe(32)

        qr = RestaurantPickupQR(
            restaurant_id=restaurant_id,
            qr_token=qr_token,
            is_active=True
        )

        db.session.add(qr)
        db.session.commit()

        return qr

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

from sqlalchemy.dialects.postgresql import JSONB


class MenuItem(db.Model):
    __tablename__ = "menu_items"

    id = db.Column(db.Integer, primary_key=True)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurant.id"),
        nullable=False
    )

    # =========================
    # COMMON FIELDS
    # =========================
    name = db.Column(
        db.String(200),
        nullable=False
    )

    description = db.Column(db.Text)

    category = db.Column(
        db.String(100)
    )

    price = db.Column(
        db.Float,
        default=0
    )

    # =========================
    # GROCERY FIELDS
    # =========================
    mrp = db.Column(
        db.Float,
        default=0
    )

    unit = db.Column(
        db.String(50)
    )

    # =========================
    # IMAGE
    # =========================
    image_url = db.Column(
        db.String(500)
    )

    # =========================
    # STOCK / AVAILABILITY
    # =========================
    availability = db.Column(
        db.String(10),
        default="yes"
    )

    # restaurant / bakery / grocery
    item_type = db.Column(
        db.String(50),
        nullable=False
    )

    # =========================
    # FLEXIBLE DATA
    # =========================
    extra_data = db.Column(
        JSONB,
        default=dict
    )

    # Example extra_data:
    #
    # {
    #     "weight_options": "500ml,1L",
    #     "brand": "Amul"
    # }

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

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
        # ✅ NEW
    fcm_token = db.Column(db.Text)
        # ✅ NEW
    push_subscription = db.Column(db.Text)

    is_active = db.Column(db.Boolean, default=True)
    is_online = db.Column(db.Boolean, default=False)  # ✅ real-time status
    is_available = db.Column(db.Boolean, default=True)


    last_assignment = db.Column(db.DateTime)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class RiderApplication(db.Model):
    __tablename__ = "rider_application"

    id = db.Column(db.Integer, primary_key=True)

    application_code = db.Column(
        db.String(40),
        unique=True,
        nullable=False,
        index=True
    )

    full_name = db.Column(
        db.String(120),
        nullable=False
    )

    phone = db.Column(
        db.String(15),
        nullable=False,
        index=True
    )

    dob = db.Column(
        db.Date,
        nullable=True
    )

    address = db.Column(
        db.Text,
        nullable=False
    )

    city = db.Column(
        db.String(100),
        nullable=False
    )

    pincode = db.Column(
        db.String(10),
        nullable=False
    )

    vehicle_type = db.Column(
        db.String(40),
        nullable=True
    )

    vehicle_number = db.Column(
        db.String(40),
        nullable=True
    )

    aadhaar_front_path = db.Column(
        db.String(500),
        nullable=False
    )

    aadhaar_back_path = db.Column(
        db.String(500),
        nullable=False
    )

    pan_photo_path = db.Column(
        db.String(500),
        nullable=False
    )

    selfie_photo_path = db.Column(
        db.String(500),
        nullable=False
    )

    driving_license_path = db.Column(
        db.String(500),
        nullable=True
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="Pending",
        index=True
    )

    rejection_reason = db.Column(
        db.Text,
        nullable=True
    )

    review_note = db.Column(
        db.Text,
        nullable=True
    )

    rider_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_person.id"),
        nullable=True,
        index=True
    )

    submitted_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    reviewed_at = db.Column(
        db.DateTime,
        nullable=True
    )

    reviewed_by = db.Column(
        db.Integer,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class RiderAuthAccount(db.Model):
    __tablename__ = "rider_auth_account"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    rider_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_person.id"),
        nullable=False,
        unique=True,
        index=True
    )

    phone = db.Column(
        db.String(15),
        nullable=False,
        unique=True,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=True
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    password_is_set = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    activation_token_hash = db.Column(
        db.String(255),
        nullable=True
    )

    activation_expires_at = db.Column(
        db.DateTime,
        nullable=True
    )

    last_login_at = db.Column(
        db.DateTime,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

class RiderPasswordResetRequest(db.Model):
    __tablename__ = "rider_password_reset_requests"

    id = db.Column(db.Integer, primary_key=True)
    rider_id = db.Column(db.Integer, db.ForeignKey("delivery_person.id"), nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    otp_code = db.Column(db.String(6), nullable=False)
    otp_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    used = db.Column(db.Boolean, nullable=False, default=False, index=True)

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
    original_delivery_charge = db.Column(db.Float, nullable=True)
    final_total = db.Column(db.Float, default=0.0)          # items_total - discount + delivery_charge
    coupon_used = db.Column(db.String(50), nullable=True)
    device_fingerprint = db.Column(db.Text, nullable=True)

    restaurant_offer_discount = db.Column(db.Float, default=0)
    
    # ---------------- ORDER STATUS ----------------
    status = db.Column(db.String(50), default="Pending")    # Pending / Completed / Cancelled
    otp = db.Column(db.String(10))
    preparation_started_at = db.Column(
        db.DateTime,
        nullable=True
    )
    # ---------------- PAYMENT & ORDER TYPE ----------------
    payment_type = db.Column(db.String(20), nullable=True)  # COD / Online
    # ---------------- PAYMENT & ORDER TYPE ----------------

    # =====================================================
    # DELIVERY PRICING LOCATION
    # =====================================================

    delivery_location_id = db.Column(
        db.Integer,
        nullable=True,
        index=True
    )

    payment_status = db.Column(
        db.String(20),
        default="Pending"
    )  # Pending / Paid / Failed / Refunded

    payment_source = db.Column(
        db.String(30),
        nullable=True
    )  # Checkout / DeliveryQR / COD

    payment_method_used = db.Column(
        db.String(50),
        nullable=True
    )  # UPI / Card / NetBanking / Wallet / COD

    payment_id = db.Column(
        db.String(100),
        nullable=True
    )  # Razorpay payment ID

    payment_order_id = db.Column(
        db.String(100),
        nullable=True
    )  # Razorpay order ID

    payment_signature = db.Column(
        db.String(300),
        nullable=True
    )  # Razorpay signature verification

    payment_time = db.Column(
        db.DateTime,
        nullable=True
    )  # Payment completed time

    refund_status = db.Column(
        db.String(20),
        nullable=True
    )  # None / Processing / Refunded

    refund_amount = db.Column(
        db.Float,
        default=0.0
    )  # Refunded amount

    refund_time = db.Column(
        db.DateTime,
        nullable=True
    )  # Refund processed time

    refund_reason = db.Column(
        db.String(300),
        nullable=True
    )  # Reason for refund

    transaction_reference = db.Column(
        db.String(100),
        nullable=True
    )  # UTR number or transaction ID

    payment_verified = db.Column(
        db.Boolean,
        default=False
    )  # Payment verified or not
    payment_link_id = db.Column(
    db.String(100),
    nullable=True
    )

    payment_link_url = db.Column(
        db.String(500),
        nullable=True
    ) 
    payment_qr_url = db.Column(
    db.String(500),
    nullable=True
    )
    payment_qr_id = db.Column(
    db.String(100),
    nullable=True
    )

    payment_qr_image_url = db.Column(
        db.String(500),
        nullable=True
    )

    payment_qr_status = db.Column(
        db.String(30),
        default="active"
    ) 
    # ---------------- MANUAL ORDER EDITING ----------------

    manual_discount = db.Column(
        db.Float,
        default=0.0,
        nullable=False
    )

    extra_charge = db.Column(
        db.Float,
        default=0.0,
        nullable=False
    )

    is_order_edited = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    order_edit_reason = db.Column(
        db.String(500),
        nullable=True
    )

    order_edited_at = db.Column(
        db.DateTime,
        nullable=True
    )

    order_edited_by = db.Column(
        db.String(100),
        nullable=True
    )

    customer_edit_approved = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )
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
# All items, including removed ones
    all_items = db.relationship(
        "OrderItem",
        backref="order",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="OrderItem.id"
    )

    # Only active items for dashboards
    items = db.relationship(
        "OrderItem",
        primaryjoin=(
            "and_(Order.id == OrderItem.order_id, "
            "OrderItem.is_removed.is_(False))"
        ),
        lazy=True,
        viewonly=True,
        order_by="OrderItem.id"
    )

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
    
    whatsapp_confirmation_status = db.Column(
        db.String(30),
        default="not_required",
        nullable=False
    )

    whatsapp_confirmation_sent_at = db.Column(
        db.DateTime,
        nullable=True
    )

    whatsapp_confirmation_responded_at = db.Column(
        db.DateTime,
        nullable=True
    )
  
    whatsapp_confirmation_expires_at = db.Column(
        db.DateTime,
        nullable=True
    )
    restaurant_offer_id = db.Column(
        db.Integer,
        db.ForeignKey('restaurant_offer.id'),
        nullable=True
    )

    restaurant_offer_discount = db.Column(
        db.Float,
        default=0
    )
    assigned_at = db.Column(db.DateTime, nullable=True)

    assignment_expires_at = db.Column(db.DateTime, nullable=True)

    accepted_at = db.Column(db.DateTime, nullable=True)

    rejected_at = db.Column(db.DateTime, nullable=True)

    rider_response = db.Column(
        db.String(20),
        nullable=True,
        default="Pending"
    )
    # =========================================================
    # PICKUP VERIFICATION
    # =========================================================

    pickup_status = db.Column(
        db.String(30),
        default="waiting",
        nullable=False
    )
    # waiting
    # verification_started
    # qr_verified
    # restaurant_confirmed
    # picked_up
    # rejected
    # expired
    # cancelled


    pickup_verification_started_at = db.Column(
        db.DateTime,
        nullable=True
    )


    pickup_qr_scanned_at = db.Column(
        db.DateTime,
        nullable=True
    )


    pickup_verified_at = db.Column(
        db.DateTime,
        nullable=True
    )


    pickup_restaurant_confirmed_at = db.Column(
        db.DateTime,
        nullable=True
    )


    pickup_verified_by = db.Column(
        db.Integer,
        db.ForeignKey("restaurant_user.id"),
        nullable=True
    )
        
    # ---------------- HELPER FUNCTION ----------------
    def get_final_total(self):


        items_total = float(
            self.items_total or 0
        )

        delivery_charge = float(
            self.delivery_charge or 0
        )
        
        extra_charge = float(
            self.extra_charge or 0
        )

        coupon_discount = float(
            self.discount or 0
        )

        restaurant_discount = float(
            self.restaurant_offer_discount or 0
        )

        coins_discount = float(
            self.coins_discount_amount or 0
        )

        manual_discount = float(
            self.manual_discount or 0
        )

        total = (
            items_total
            + delivery_charge
            + extra_charge
            - coupon_discount
            - restaurant_discount
            - coins_discount
            - manual_discount
        )

        return round(
            max(total, 0),
            2
        )
    
# ----------------- Order Item -----------------
class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))

    item_name = db.Column(db.String(200))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)

    # Original menu price before any offer/discount
    original_unit_price = db.Column(db.Float, nullable=True)

    # Future-proof fields
    weight = db.Column(db.String(50), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    is_special = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.false()
    )
    mrp = db.Column(db.Float, nullable=True)
    discount = db.Column(db.Float, default=0)

    unit = db.Column(db.String(50), nullable=True)

    item_image = db.Column(db.String(500), nullable=True)

    item_type = db.Column(db.String(50), nullable=True)
    # grocery / restaurant / bakery

    food_item_id = db.Column(db.Integer, nullable=True)
    is_removed = db.Column(

        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.false()
    )
    def item_total(self):
        return round((self.price or 0) * (self.quantity or 0), 2)
# ----------------- Category -----------------
class Category(db.Model):
    __tablename__ = "category"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        nullable=False
    )

    image = db.Column(
        db.String(200),
        nullable=True
    )

    section = db.Column(
        db.String(50),
        nullable=False,
        default="food",
        server_default="food"
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default="true"
    )

    display_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0"
    )

    parent_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "category.id",
            ondelete="SET NULL"
        ),
        nullable=True
    )

    parent = db.relationship(
        "Category",
        remote_side=[id],
        backref=db.backref(
            "subcategories",
            lazy="dynamic"
        )
    )

    __table_args__ = (
        db.UniqueConstraint(
            "name",
            "section",
            name="uq_category_name_section"
        ),
    )

class CategoryLocation(db.Model):
    __tablename__ = "category_location"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "category.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    location = db.Column(
        db.String(100),
        nullable=False
    )

    category = db.relationship(
        "Category",
        backref=db.backref(
            "location_assignments",
            cascade="all, delete-orphan",
            lazy="select"
        )
    )

    __table_args__ = (
        db.UniqueConstraint(
            "category_id",
            "location",
            name="uq_category_location"
        ),
    )
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
# ============================================================
# CUSTOMER / APP USER
# NO CHANGES REQUIRED
# ============================================================

class Customer(UserMixin, db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(200), default="User")

    mobile = db.Column(
        db.String(20),
        unique=True,
        nullable=False
    )

    email = db.Column(db.String(200), nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    # Reward Coins
    coins = db.Column(db.Integer, default=0)

    # Used only for animation trigger
    last_reward_coins = db.Column(db.Integer, default=0)

    # Orders
    orders = db.relationship(
        "Order",
        backref="customer",
        lazy=True
    )

    # Coin history
    coin_logs = db.relationship(
        "CoinLedger",
        backref="customer",
        lazy=True
    )

    badge_id = db.Column(
        db.Integer,
        db.ForeignKey("reward_badge.id")
    )

    badge = db.relationship("RewardBadge")


# ============================================================
# OTP MODEL
# SUPPORTS CUSTOMER LOGIN, SIGNUP AND ORDER OTP
# ============================================================

class OTP(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    mobile = db.Column(
        db.String(15),
        nullable=False,
        index=True
    )

    otp_hash = db.Column(
        db.String(255),
        nullable=False
    )

    # customer_login | customer_signup | order_receive
    purpose = db.Column(
        db.String(30),
        nullable=False
    )

    order_id = db.Column(
        db.Integer,
        nullable=True
    )

    attempts = db.Column(
        db.Integer,
        default=0
    )

    expires_at = db.Column(
        db.DateTime,
        nullable=False
    )

    # NEW: 60-second resend cooldown
    resend_after = db.Column(
        db.DateTime,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


class CouponUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coupon_code = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    device_fingerprint = db.Column(db.Text, nullable=True)

    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ==========================
# Association Table (NEW)
# ==========================

offer_menu_items = db.Table(
    "offer_menu_items",

    db.Column(
        "offer_id",
        db.Integer,
        db.ForeignKey("restaurant_offer.id"),
        primary_key=True
    ),

    db.Column(
        "menu_item_id",
        db.Integer,
        db.ForeignKey("menu_items.id"),
        primary_key=True
    )
)

class RestaurantOffer(db.Model):
    __tablename__ = "restaurant_offer"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurant.id")
    )

    title = db.Column(db.String(200))
    description = db.Column(db.String(300))

    offer_type = db.Column(db.String(50))
    offer_value = db.Column(db.Float)

    min_order_amount = db.Column(db.Float, default=0.0)

    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)

    is_active = db.Column(db.Boolean, default=True)

    # Which menu items this offer applies to
    offer_scope = db.Column(
        db.String(20),
        nullable=False,
        default="all_items"

    )
        # NEW
    selected_items = db.relationship(
        "MenuItem",
        secondary=offer_menu_items,
        backref="restaurant_offers"
    )
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

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # Keep old pricing temporarily
    base_distance = db.Column(
        db.Float,
        default=3
    )

    base_charge = db.Column(
        db.Integer,
        default=30
    )

    slab_1_upto = db.Column(
        db.Float,
        default=6
    )

    slab_1_charge = db.Column(
        db.Integer,
        default=40
    )

    slab_2_upto = db.Column(
        db.Float,
        default=9
    )

    slab_2_charge = db.Column(
        db.Integer,
        default=55
    )

    slab_3_upto = db.Column(
        db.Float,
        default=12
    )

    slab_3_charge = db.Column(
        db.Integer,
        default=70
    )

    max_charge = db.Column(
        db.Integer,
        default=90
    )

    free_delivery_min_order = db.Column(
        db.Integer,
        default=499
    )

    night_surge = db.Column(
        db.Integer,
        default=0
    )

    is_night_surge_active = db.Column(
        db.Boolean,
        default=False
    )

    # ========================================================
    # RIDER ASSIGNMENT
    # ========================================================

    assignment_mode = db.Column(
        db.String(30),
        default="auto_override"
    )

    auto_assign_enabled = db.Column(
        db.Boolean,
        default=True
    )

    rider_search_radius = db.Column(
        db.Float,
        default=5
    )

    maximum_search_radius = db.Column(
        db.Float,
        default=10
    )

    rider_accept_timeout = db.Column(
        db.Integer,
        default=20
    )

    allow_manual_override = db.Column(
        db.Boolean,
        default=True
    )

    allow_multiple_orders = db.Column(
        db.Boolean,
        default=False
    )

    max_orders_per_rider = db.Column(
        db.Integer,
        default=1
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
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
    
class FCMToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('customer.id'))

    token = db.Column(db.String(255), unique=True, nullable=False)

    device = db.Column(db.String(50))   # android / ios / web
    city = db.Column(db.String(100))
    restaurant_id = db.Column(db.Integer)

    last_active = db.Column(db.DateTime)
    coins = db.Column(db.Integer, default=0)
    badge = db.Column(db.String(50))    # bronze / silver / gold

    created_at = db.Column(db.DateTime, default=datetime.utcnow)




class Offer(db.Model):
    __tablename__ = "offer"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)           # required
    body = db.Column(db.Text, nullable=False)                  # required
    discount = db.Column(db.Integer, nullable=False, default=0)

    coupon = db.Column(db.String(50), nullable=True)           # optional
    expiry = db.Column(db.DateTime, nullable=True)             # optional
    image = db.Column(db.String(500), nullable=True)           # optional
    link = db.Column(db.String(500), nullable=True)            # optional

class Location(db.Model):
    __tablename__ = "location"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

class RestaurantHomepageRanking(db.Model):
    __tablename__ = "restaurant_homepage_ranking"

    id = db.Column(db.Integer, primary_key=True)

    # =========================================================
    # RESTAURANT
    # =========================================================
    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurant.id"),
        nullable=False
    )

    # =========================================================
    # EXISTING RucHiGo LOCATION SYSTEM
    # =========================================================
    location_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_location_settings.id"),
        nullable=False
    )

    # =========================================================
    # NORMAL HOMEPAGE POSITION
    # =========================================================
    position = db.Column(
        db.Integer,
        default=999,
        nullable=False
    )

    # =========================================================
    # SPONSORED / PAID BANNER
    # =========================================================

    sponsored_enabled = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    sponsored_position = db.Column(
        db.Integer,
        default=999,
        nullable=False
    )

    sponsored_banner_url = db.Column(
        db.Text,
        nullable=True
    )

    sponsored_title = db.Column(
        db.String(200),
        nullable=True
    )

    sponsored_subtitle = db.Column(
        db.String(300),
        nullable=True
    )

    sponsored_start_at = db.Column(
        db.DateTime,
        nullable=True
    )

    sponsored_end_at = db.Column(
        db.DateTime,
        nullable=True
    )

    sponsored_payment_status = db.Column(
        db.String(30),
        default="pending",
        nullable=False
    )

    # =========================================================
    # ANALYTICS
    # =========================================================

    sponsored_impressions = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    sponsored_clicks = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    restaurant = db.relationship(
        "Restaurant",
        backref="homepage_rankings"
    )

    location = db.relationship(
        "DeliveryLocationSettings",
        backref="homepage_rankings"
    )

    # =========================================================
    # ONE RESTAURANT PER LOCATION
    # =========================================================

    __table_args__ = (
        db.UniqueConstraint(
            "restaurant_id",
            "location_id",
            name="unique_restaurant_location"
        ),
    )

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))
    phone = db.Column(db.String(15), unique=True, index=True)

    role = db.Column(db.String(50), default="staff")  
    # admin, manager, support, ops

    is_active = db.Column(db.Boolean, default=True)
    is_logged_in = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EmployeeOTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"))

    otp = db.Column(db.String(6))
    expires_at = db.Column(db.DateTime)

    is_used = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow) 

class EmployeeMeta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"))
    data = db.Column(db.JSON) 

class EmployeeSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    employee_id = db.Column(db.Integer)

    login_time = db.Column(db.DateTime)
    logout_time = db.Column(db.DateTime)

    is_active = db.Column(db.Boolean, default=True)

    ip_address = db.Column(db.String(50))

class OrderEditHistory(db.Model):

    __tablename__ = "order_edit_history"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("order.id"),
        nullable=False,
        index=True
    )

    action = db.Column(
        db.String(100),
        default="Order Updated",
        nullable=False
    )

    old_items = db.Column(
        db.Text,
        nullable=True
    )

    new_items = db.Column(
        db.Text,
        nullable=True
    )

    old_items_total = db.Column(
        db.Float,
        default=0.0
    )

    new_items_total = db.Column(
        db.Float,
        default=0.0
    )

    old_delivery_charge = db.Column(
        db.Float,
        default=0.0
    )

    new_delivery_charge = db.Column(
        db.Float,
        default=0.0
    )

    old_extra_charge = db.Column(
        db.Float,
        default=0.0
    )

    new_extra_charge = db.Column(
        db.Float,
        default=0.0
    )

    old_manual_discount = db.Column(
        db.Float,
        default=0.0
    )

    new_manual_discount = db.Column(
        db.Float,
        default=0.0
    )

    old_final_total = db.Column(
        db.Float,
        default=0.0
    )

    new_final_total = db.Column(
        db.Float,
        default=0.0
    )

    reason = db.Column(
        db.String(500),
        nullable=True
    )

    edited_by = db.Column(
        db.String(100),
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    order = db.relationship(
        "Order",
        backref=db.backref(
            "edit_history",
            lazy=True,
            cascade="all, delete-orphan"
        )
    )



class RiderSettlement(db.Model):

    __tablename__ = "rider_settlements"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    rider_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_person.id"),
        nullable=False
    )

    settlement_date = db.Column(
        db.Date,
        nullable=False
    )

    # Batch number for the same day
    batch_no = db.Column(
        db.Integer,
        default=1,
        nullable=False
    )

    # ==========================================================
    # ORDER COUNTS
    # ==========================================================

    total_deliveries = db.Column(
        db.Integer,
        default=0
    )

    cod_orders = db.Column(
        db.Integer,
        default=0
    )

    online_orders = db.Column(
        db.Integer,
        default=0
    )

    # ==========================================================
    # MONEY
    # ==========================================================

    cash_collected = db.Column(
        db.Float,
        default=0
    )

    online_amount = db.Column(
        db.Float,
        default=0
    )

    total_order_value = db.Column(
        db.Float,
        default=0
    )

    rider_earnings = db.Column(
        db.Float,
        default=0
    )

    cash_to_submit = db.Column(
        db.Float,
        default=0
    )

    platform_to_pay = db.Column(
        db.Float,
        default=0
    )

    # ==========================================================
    # STATUS
    # ==========================================================

    status = db.Column(
        db.String(30),
        default="Pending"
    )

    submitted_at = db.Column(
        db.DateTime,
        nullable=True
    )

    verified_at = db.Column(
        db.DateTime,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    rider = db.relationship(
        "DeliveryPerson",
        backref="settlements"
    )

    # Allow multiple batches per day,
    # but batch numbers must be unique.
    __table_args__ = (
        db.UniqueConstraint(
            "rider_id",
            "settlement_date",
            "batch_no",
            name="uq_rider_settlement_batch"
        ),
    )

    # =========================================================
# RESTAURANT UNIVERSAL PICKUP QR
# =========================================================

class RestaurantPickupQR(db.Model):

    __tablename__ = "restaurant_pickup_qr"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurant.id"),
        nullable=False,
        unique=True
    )

    qr_token = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    restaurant = db.relationship(
        "Restaurant",
        backref=db.backref(
            "pickup_qr",
            uselist=False
        )
    )
    # =========================================================
# ORDER PICKUP VERIFICATION
# =========================================================

class OrderPickupVerification(db.Model):

    __tablename__ = "order_pickup_verification"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # =====================================================
    # ORDER
    # =====================================================

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("order.id"),
        nullable=False,
        unique=True
    )

    # =====================================================
    # RESTAURANT
    # =====================================================

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurant.id"),
        nullable=False
    )

    # =====================================================
    # DELIVERY BOY
    # =====================================================

    delivery_person_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_person.id"),
        nullable=False
    )

    # =====================================================
    # VERIFICATION STATUS
    # =====================================================

    status = db.Column(
        db.String(30),
        default="pending",
        nullable=False
    )

    # pending
    # qr_scanned
    # restaurant_confirmed
    # pickup_success
    # rejected
    # expired
    # cancelled

    # =====================================================
    # QR SCAN
    # =====================================================

    qr_scanned_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # =====================================================
    # TEMPORARY VERIFICATION TOKEN
    # =====================================================

    verification_token = db.Column(
        db.String(255),
        unique=True,
        nullable=True
    )

    token_expires_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # =====================================================
    # RESTAURANT CONFIRMATION
    # =====================================================

    restaurant_confirmed_at = db.Column(
        db.DateTime,
        nullable=True
    )

    restaurant_confirmed_by = db.Column(
        db.Integer,
        db.ForeignKey("restaurant_user.id"),
        nullable=True
    )

    # =====================================================
    # FINAL PICKUP
    # =====================================================

    pickup_verified_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # =====================================================
    # TIMESTAMPS
    # =====================================================

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    order = db.relationship(
        "Order",
        backref=db.backref(
            "pickup_verification",
            uselist=False
        )
    )

    restaurant = db.relationship(
        "Restaurant"
    )

    delivery_person = db.relationship(
        "DeliveryPerson"
    )

    restaurant_user = db.relationship(
        "RestaurantUser"
    ) 


class HomeAnnouncement(db.Model):
    __tablename__ = "home_announcements"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    content = db.Column(db.Text)

    announcement_type = db.Column(
        db.String(30),
        nullable=False,
        default="notice"
    )

    priority = db.Column(
        db.String(20),
        nullable=False,
        default="normal"
    )

    icon = db.Column(db.String(100))
    image_url = db.Column(db.Text)

    button_text = db.Column(db.String(100))
    button_action = db.Column(db.String(300))

    # all / restaurant / bakery / grocery
    service = db.Column(
        db.String(30),
        nullable=False,
        default="all"
    )

    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)

    is_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    show_on_home = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    send_push = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    dismissible = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class HomeAnnouncementTarget(db.Model):
    __tablename__ = "home_announcement_targets"

    id = db.Column(db.Integer, primary_key=True)

    announcement_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "home_announcements.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    # all / location / service
    target_type = db.Column(
        db.String(30),
        nullable=False
    )

    # Example:
    # "Machilipatnam"
    # "Gudivada"
    # "grocery"
    target_value = db.Column(
        db.String(150),
        nullable=False
    )

    announcement = db.relationship(
        "HomeAnnouncement",
        backref=db.backref(
            "targets",
            cascade="all, delete-orphan"
        )
    )

# ============================================================
# DELIVERY LOCATION SETTINGS
# ============================================================

DEFAULT_DELIVERY_SLABS = [
    {
        "upto": 3,
        "charge": 30
    },
    {
        "upto": 6,
        "charge": 40
    },
    {
        "upto": 9,
        "charge": 55
    },
    {
        "upto": 12,
        "charge": 70
    }
]


class DeliveryLocationSettings(db.Model):
    __tablename__ = "delivery_location_settings"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # ========================================================
    # LOCATION
    # ========================================================

    location = db.Column(
        db.String(100),
        nullable=False,
        unique=True,
        index=True
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default="1"
    )
        # ========================================================
    # LOCATION RESTAURANT ORDER CONTROL
    # ========================================================

    restaurant_ordering_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default="1"
    )

    # ========================================================
    # LOCATION DELIVERY CONTROL
    # ========================================================

    delivery_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default="1"
    )

    # Customer-facing message
    ordering_disabled_message = db.Column(
        db.String(500),
        nullable=True
    )

    delivery_disabled_message = db.Column(
        db.String(500),
        nullable=True
    )
    # ========================================================
    # FLEXIBLE DELIVERY SLOTS
    #
    # Example:
    #
    # [
    #   {"upto": 3, "charge": 30},
    #   {"upto": 6, "charge": 40},
    #   {"upto": 9, "charge": 55},
    #   {"upto": 12, "charge": 70}
    # ]
    #
    # Can later contain 5, 6, 10, 20 slots without
    # changing the database structure.
    # ========================================================

    delivery_slabs = db.Column(
        db.JSON,
        nullable=False,
        default=lambda: [
            {
                "upto": 3,
                "charge": 30
            },
            {
                "upto": 6,
                "charge": 40
            },
            {
                "upto": 9,
                "charge": 55
            },
            {
                "upto": 12,
                "charge": 70
            }
        ]
    )

    # ========================================================
    # FALLBACK / LAST DISTANCE CHARGE
    #
    # Example:
    # Last slot = 12 km
    # Distance = 14 km
    # max_charge = 90
    #
    # Charge = ₹90
    # ========================================================

    max_charge = db.Column(
        db.Integer,
        nullable=False,
        default=90
    )

    # ========================================================
    # FREE DELIVERY
    #
    # Kept for future/configuration.
    #
    # IMPORTANT:
    # Your current business logic says free delivery should
    # come from an active offer, so this field is NOT used
    # by calculate_delivery_charge().
    # ========================================================

    free_delivery_min_order = db.Column(
        db.Integer,
        nullable=False,
        default=499
    )

    # ========================================================
    # NIGHT SURGE
    # ========================================================

    night_surge = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    is_night_surge_active = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default="0"
    )

    # ========================================================
    # TIMESTAMP
    # ========================================================

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # ========================================================
    # RELATIONSHIP
    # ========================================================

    restaurants = db.relationship(
        "Restaurant",
        back_populates="delivery_location_settings"
    )

    def __repr__(self):
        return (
            f"<DeliveryLocationSettings "
            f"id={self.id} "
            f"location='{self.location}'>"
        )


# ============================================================
# GLOBAL PLATFORM CONTROL
# ============================================================

class PlatformControl(db.Model):
    __tablename__ = "platform_controls"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    # ========================================================
    # GLOBAL PLATFORM
    # ========================================================

    platform_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default="1"
    )

    maintenance_mode = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default="0"
    )

    # ========================================================
    # GLOBAL RESTAURANT ORDERING
    # ========================================================

    restaurant_ordering_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default="1"
    )

    # Optional automatic restart
    restaurant_ordering_resume_at = db.Column(
        db.DateTime,
        nullable=True
    )

    restaurant_ordering_stop_reason = db.Column(
        db.String(500),
        nullable=True
    )

    # ========================================================
    # GLOBAL DELIVERY
    # ========================================================

    delivery_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default="1"
    )

    # ========================================================
    # CUSTOMER MESSAGES
    # ========================================================

    ordering_disabled_message = db.Column(
        db.String(500),
        nullable=False,
        default=(
            "Restaurants are temporarily not accepting "
            "new orders."
        )
    )

    delivery_disabled_message = db.Column(
        db.String(500),
        nullable=False,
        default=(
            "Delivery service is temporarily unavailable."
        )
    )

    maintenance_message = db.Column(
        db.String(500),
        nullable=False,
        default=(
            "We are currently performing maintenance."
        )
    )

    # ========================================================
    # TIMESTAMP
    # ========================================================

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<PlatformControl id={self.id}>"

# ============================================================
# ADMIN CONTROL AUDIT LOG
# ============================================================

class AdminControlLog(db.Model):
    __tablename__ = "admin_control_logs"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    admin_user_id = db.Column(
        db.Integer,
        nullable=True
    )

    action = db.Column(
        db.String(100),
        nullable=False
    )

    target_type = db.Column(
        db.String(50),
        nullable=False
    )

    target_id = db.Column(
        db.Integer,
        nullable=True
    )

    old_value = db.Column(
        db.Text,
        nullable=True
    )

    new_value = db.Column(
        db.Text,
        nullable=True
    )

    reason = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

class RestaurantMenuAlert(db.Model):
    __tablename__ = "restaurant_menu_alerts"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurant.id"),
        nullable=False,
        index=True
    )

    # ON / OFF
    enabled = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    # restaurant / category
    scope = db.Column(
        db.String(20),
        default="restaurant",
        nullable=False
    )

    # Used only when scope = category
    category = db.Column(
        db.String(150),
        nullable=True
    )

    title = db.Column(
        db.String(150),
        nullable=False,
        default="Important Notice"
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    # info / warning / emergency
    severity = db.Column(
        db.String(20),
        default="warning",
        nullable=False
    )

    # Optional expiry
    expires_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # restaurant / admin
    created_by = db.Column(
        db.String(30),
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    restaurant = db.relationship(
        "Restaurant",
        backref=db.backref(
            "menu_alerts",
            lazy=True
        )
    )



class RestaurantPartnerDeviceToken(db.Model):
    __tablename__ = "restaurant_partner_device_tokens"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurant_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("restaurant.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    token = db.Column(
        db.String(512),
        nullable=False,
        unique=True
    )

    platform = db.Column(
        db.String(24),
        nullable=False,
        default="android"
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        index=True
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self):
        return (
            f"<RestaurantPartnerDeviceToken "
            f"user_id={self.user_id} "
            f"restaurant_id={self.restaurant_id}>"
        )



class EmployeeLocationAssignment(db.Model):
    __tablename__ = "employee_location_assignment"

    id = db.Column(db.Integer, primary_key=True)

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("employee.id"),
        nullable=False,
        index=True
    )

    location = db.Column(
        db.String(100),
        nullable=False,
        index=True
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default="1"
    )

    assigned_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "employee_id",
            "location",
            name="uq_employee_location"
        ),
    )
# Add this class to models.py (after db is initialized and after Order/DeliveryPerson).
# Ensure models.py has: from datetime import datetime

class DeliveryAssignmentAttempt(db.Model):
    """Persistent history of each order offered to a delivery rider."""
    __tablename__ = "delivery_assignment_attempts"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, nullable=False, index=True)
    rider_id = db.Column(db.Integer, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="Pending", index=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index(
            "ix_delivery_assignment_order_rider_status",
            "order_id",
            "rider_id",
            "status",
        ),
    )



class SettlementLine(db.Model):
    __tablename__ = "settlement_line"

    id = db.Column(db.BigInteger, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False, index=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_item.id"), nullable=False, unique=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    restaurant_unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    customer_unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    commission_percent = db.Column(db.Numeric(5, 2), nullable=False)
    restaurant_gross = db.Column(db.Numeric(12, 2), nullable=False)
    customer_item_value = db.Column(db.Numeric(12, 2), nullable=False)
    markup_amount = db.Column(db.Numeric(12, 2), nullable=False)
    commission_amount = db.Column(db.Numeric(12, 2), nullable=False)
    restaurant_payable = db.Column(db.Numeric(12, 2), nullable=False)
    snapshot_created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    settlement_id = db.Column(db.BigInteger, db.ForeignKey("restaurant_settlement.id"), nullable=True, index=True)


class RestaurantSettlement(db.Model):
    __tablename__ = "restaurant_settlement"

    id = db.Column(db.BigInteger, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False, index=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft")
    order_count = db.Column(db.Integer, nullable=False, default=0)
    food_gross = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    customer_item_value = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    markup_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    commission_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    adjustment_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payout_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    missing_snapshot_count = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    approved_by = db.Column(db.String(120))
    paid_at = db.Column(db.DateTime)

    restaurant = db.relationship("Restaurant", lazy="joined")
    lines = db.relationship("SettlementLine", backref="settlement", lazy="select")


class SettlementPayout(db.Model):
    __tablename__ = "settlement_payout"

    id = db.Column(db.BigInteger, primary_key=True)
    settlement_id = db.Column(db.BigInteger, db.ForeignKey("restaurant_settlement.id"), nullable=False, unique=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.String(40), nullable=False, default="bank_transfer")
    payment_reference = db.Column(db.String(160), nullable=False)
    paid_on = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    recorded_by = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    settlement = db.relationship("RestaurantSettlement", lazy="joined")


class CODCollection(db.Model):
    __tablename__ = "cod_collection"

    id = db.Column(db.BigInteger, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False, unique=True)
    expected_amount = db.Column(db.Numeric(12, 2), nullable=False)
    collected_amount = db.Column(db.Numeric(12, 2), nullable=False)
    collected_by = db.Column(db.String(80), nullable=False, default="rider")
    handover_reference = db.Column(db.String(160))
    notes = db.Column(db.Text)
    reconciled_by = db.Column(db.String(120))
    reconciled_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default="reconciled")


class RestaurantSettlementTerms(db.Model):
    __tablename__ = "restaurant_settlement_terms"

    id = db.Column(db.BigInteger, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False, unique=True)
    commission_percent = db.Column(db.Numeric(5, 2), nullable=False, default=10)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.String(120))

    restaurant = db.relationship("Restaurant", lazy="joined")
class CODCollectionAudit(db.Model):
    __tablename__ = "cod_collection_audit"

    id = db.Column(db.BigInteger, primary_key=True)

    order_id = db.Column(
        db.Integer, db.ForeignKey("order.id"),
        nullable=False, index=True
    )
    batch_id = db.Column(
        db.BigInteger, db.ForeignKey("cod_handover_batch.id"),
        nullable=False, index=True
    )

    previous_status = db.Column(db.String(20))
    previous_expected_amount = db.Column(db.Numeric(12, 2))
    previous_collected_amount = db.Column(db.Numeric(12, 2))
    previous_reference = db.Column(db.String(160))

    new_status = db.Column(db.String(20), nullable=False)
    changed_by = db.Column(db.String(120), nullable=False)
    reason = db.Column(db.Text, nullable=False)

    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )



class CODHandoverBatch(db.Model):
    __tablename__ = "cod_handover_batch"

    id = db.Column(db.BigInteger, primary_key=True)

    rider_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_person.id"),
        nullable=False,
        index=True,
    )

    business_date = db.Column(db.Date, nullable=False, index=True)

    expected_total = db.Column(
        db.Numeric(12, 2), nullable=False, default=0
    )
    received_amount = db.Column(
        db.Numeric(12, 2), nullable=True
    )
    difference_amount = db.Column(
        db.Numeric(12, 2), nullable=True
    )

    status = db.Column(
        db.String(20), nullable=False, default="draft", index=True
    )

    handover_reference = db.Column(db.String(160))
    notes = db.Column(db.Text)

    created_by = db.Column(db.String(120), nullable=False)
    received_by = db.Column(db.String(120))
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    received_at = db.Column(db.DateTime)

    rider = db.relationship("DeliveryPerson", lazy="joined")
    items = db.relationship(
        "CODHandoverBatchItem",
        backref="batch",
        lazy="select",
        order_by="CODHandoverBatchItem.id",
    )


class CODHandoverBatchItem(db.Model):
    __tablename__ = "cod_handover_batch_item"

    id = db.Column(db.BigInteger, primary_key=True)

    batch_id = db.Column(
        db.BigInteger,
        db.ForeignKey("cod_handover_batch.id"),
        nullable=False,
        index=True,
    )

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("order.id"),
        nullable=False,
        index=True,
    )

    expected_amount = db.Column(
        db.Numeric(12, 2), nullable=False
    )

    added_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )

    # Set when an unreceived batch is cancelled.
    # The historical item is retained for audit purposes.
    released_at = db.Column(db.DateTime)

    order = db.relationship("Order", lazy="joined")


# An order can belong to only one active batch.
# Cancelled batches can release orders without deleting history.
Index(
    "uq_cod_handover_item_active_order",
    CODHandoverBatchItem.order_id,
    unique=True,
    postgresql_where=text("released_at IS NULL"),
)


# Add this class to models.py AFTER `db = SQLAlchemy(...)` is initialized.
# Do not create a second db object.
from datetime import datetime
from sqlalchemy import CheckConstraint, UniqueConstraint, Index

class RestaurantReview(db.Model):
    __tablename__ = "restaurant_reviews"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(
        db.Integer, db.ForeignKey("restaurant.id"), nullable=False, index=True
    )
    # Keep location_id nullable only for legacy data if needed. New reviews
    # are rejected by the route if the order has no location.
    location_id = db.Column(
        db.Integer, db.ForeignKey("delivery_location_settings.id"),
        nullable=False, index=True
    )
    order_id = db.Column(
        db.Integer, db.ForeignKey("order.id"), nullable=False, index=True
    )
    customer_id = db.Column(
        db.Integer, db.ForeignKey("customer.id"), nullable=True, index=True
    )
    customer_name = db.Column(db.String(120), nullable=False, default="Customer")
    phone = db.Column(db.String(20), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_restaurant_review_rating"),
        UniqueConstraint("order_id", name="uq_restaurant_review_order"),
        Index("ix_restaurant_review_restaurant_location", "restaurant_id", "location_id"),
    )

class SettlementAdjustment(db.Model):
    __tablename__ = 'settlement_adjustment'
    id = db.Column(db.BigInteger, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False, index=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_item.id'), nullable=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False, index=True)
    source_settlement_line_id = db.Column(db.BigInteger, db.ForeignKey('settlement_line.id'), nullable=True)
    settlement_id = db.Column(db.BigInteger, db.ForeignKey('restaurant_settlement.id'), nullable=True, index=True)
    operation_key = db.Column(db.String(100), nullable=False, unique=True)
    reason = db.Column(db.Text, nullable=False)
    commission_percent = db.Column(db.Numeric(5, 2), nullable=False)
    gross_delta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    customer_item_delta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    markup_delta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    commission_delta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payable_delta = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    created_by = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class CustomerPaymentAdjustment(db.Model):
    __tablename__ = 'customer_payment_adjustment'
    id = db.Column(db.BigInteger, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False, index=True)
    operation_key = db.Column(db.String(100), nullable=False, unique=True)
    kind = db.Column(db.String(30), nullable=False)  # refund_due / collection_due
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending / completed
    payment_method = db.Column(db.String(40), nullable=True)
    reference = db.Column(db.String(160), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_by = db.Column(db.String(120), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)


class AndroidAppUpdate(db.Model):
    __tablename__ = 'android_app_update_settings'
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    latest_version = db.Column(db.String(32), nullable=False, default='1.0.0')
    minimum_version = db.Column(db.String(32), nullable=False, default='1.0.0')
    update_message = db.Column(db.Text, nullable=False, default='A new RucHiGo version is available.')
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
