# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy.orm import relationship

db = SQLAlchemy()  # Keep this here, do NOT move to app.py

from datetime import time

class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(500))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(200))
    sheet_url = db.Column(db.String(500))  # CSV URL
    location = db.Column(db.String(100))  # Optional: location filter

    # Card fields
    is_veg = db.Column(db.Boolean, default=True)
    rating = db.Column(db.Float, default=4.0)
    price_level = db.Column(db.String(10), default="₹₹")
    delivery_time = db.Column(db.String(20), default="30–40 mins")
    popular_items = db.Column(db.String(255), default="Biryani • Pizza • Rolls • Chinese")

    # Delivery
    delivery_charge = db.Column(db.Float, default=30, nullable=False)
    free_delivery_limit = db.Column(db.Float, default=499, nullable=False)

    # Open/Close times
    opening_time = db.Column(db.Time, default=time(10, 0))  # 10:00 AM
    closing_time = db.Column(db.Time, default=time(22, 0))  # 10:00 PM
     # ADD THESE FIELDS
        # Delivery location
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    delivery_radius_km = db.Column(db.Float, default=5, nullable=True)

    # Relationships
    users = db.relationship("RestaurantUser", backref="restaurant", lazy=True)
    orders = db.relationship("Order", backref="restaurant", lazy=True)
    delivery_persons = db.relationship("DeliveryPerson", backref="restaurant", lazy=True)
    menu_items = db.relationship("MenuItem", backref="restaurant", lazy=True)
    offers = db.relationship("RestaurantOffer", backref="restaurant", lazy=True)

    @property
    def active_offer(self):
        now = datetime.utcnow()
        return next(
            (
                o for o in self.offers
                if o.is_active
                and o.start_date is not None
                and o.end_date is not None
                and o.start_date <= now <= o.end_date
            ),
            None
        )

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
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"))
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)


# ----------------- Delivery Person -----------------
class DeliveryPerson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    username = db.Column(db.String(100), unique=True)
    password_hash = db.Column(db.String(200))
    phone = db.Column(db.String(20), unique=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))

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
    device_fingerprint = db.Column(db.String(200), nullable=True)
    restaurant_offer_discount = db.Column(db.Float, default=0)
    # ---------------- ORDER STATUS ----------------
    status = db.Column(db.String(50), default="Pending")    # Pending / Completed / Cancelled
    otp = db.Column(db.String(10))

    # ---------------- PAYMENT & ORDER TYPE ----------------
    payment_type = db.Column(db.String(20), nullable=True)  # COD / Online
    order_type = db.Column(db.String(50))                   # Delivery / Pickup

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
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), default="User")  # optional default
    mobile = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship: a customer can have multiple orders
    orders = db.relationship("Order", backref="customer", lazy=True)




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
    device_fingerprint = db.Column(db.String(200))
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
