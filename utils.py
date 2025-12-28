# utils.py
import random
import string

def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

def generate_order_id(order_id):
    return f"ORD{str(order_id).zfill(5)}"
# utils.py
from datetime import datetime
from models import RestaurantOffer

def apply_restaurant_offer(items_total, delivery_charge, restaurant_id):
    now = datetime.utcnow()
    offer = RestaurantOffer.query.filter(
        RestaurantOffer.restaurant_id == restaurant_id,
        RestaurantOffer.is_active == True,
        RestaurantOffer.start_date <= now,
        RestaurantOffer.end_date >= now
    ).order_by(RestaurantOffer.id.desc()).first()

    if not offer or items_total < offer.min_order_amount:
        return 0, delivery_charge, None

    discount = 0
    if offer.offer_type == "percent":
        discount = (items_total * offer.offer_value) / 100
    elif offer.offer_type == "flat":
        discount = offer.offer_value
    elif offer.offer_type == "free_delivery":
        delivery_charge = 0

    return discount, delivery_charge, offer
# app.py (or utils.py)
import random
import string

def generate_order_code(order_db_id):
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{order_db_id}-{rand}"
