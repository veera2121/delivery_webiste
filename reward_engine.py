from datetime import datetime
from models import RewardSetting, RewardEvent, CoinLedger, Customer,RewardBadge
from extensions import db


# -------------------------
# Active Reward Event
# -------------------------
def get_active_event():
    return RewardEvent.query.filter(
        RewardEvent.active == True,
        RewardEvent.start_time <= datetime.utcnow(),
        RewardEvent.end_time >= datetime.utcnow()
    ).first()


# -------------------------
# Calculate Coins
# -------------------------
def calculate_coins(amount):
    setting = RewardSetting.query.first()

    if not setting:
        return 0

    base = (amount // setting.earn_per_rupees) * setting.earn_coins

    event = get_active_event()
    if event:
        base = int(base * event.multiplier)

    return int(base)

# -------------------------
# Add Coins After Order
# -------------------------
def add_coins(customer_id, amount, order_id):
    if not customer_id:
        print(f"[add_coins] Invalid customer_id for order {order_id}")
        return 0

    already = CoinLedger.query.filter_by(order_id=order_id).first()
    if already:
        print(f"[add_coins] Coins already added for order {order_id}")
        return 0

    setting = RewardSetting.query.first()
    if not setting:
        print("[add_coins] No RewardSetting found")
        return 0

    coins = int((amount // setting.earn_per_rupees) * setting.earn_coins)
    if coins <= 0:
        print(f"[add_coins] Calculated coins 0 for order {order_id}")
        return 0

    customer = Customer.query.get(customer_id)
    if not customer:
        print(f"[add_coins] Customer not found: {customer_id}")
        return 0

    customer.coins = (customer.coins or 0) + coins
    customer.last_reward_coins = coins

    update_customer_badge(customer)

    log = CoinLedger(
        customer_id=customer_id,
        order_id=order_id,
        coins=coins,
        action=f"Earned from order ₹{amount}"
    )

    db.session.add(customer)
    db.session.add(log)
    db.session.commit()
    print(f"[add_coins] Added {coins} coins to customer {customer_id} for order {order_id}")
    return coins


# -------------------------
# Redeem Coins
# -------------------------


# --------------------------
# Redeem coins utility
# --------------------------
def redeem_coins(customer_id, coins_to_use, order_id, order_total):
    customer = Customer.query.get(customer_id)
    setting = RewardSetting.query.first()

    if not customer or not setting:
        return False, "System error", 0

    if coins_to_use <= 0:
        return False, "No coins entered", 0

    if coins_to_use < setting.min_redeem_coins:
        return False, f"Minimum {setting.min_redeem_coins} coins required for redemption", 0

    if coins_to_use > customer.coins:
        return False, "Not enough coins", 0

    max_allowed_coins = (order_total * 100) // (setting.max_redeem_percent * setting.coin_value_rupees * 100)
    # Optional: you can set max coins usage per order
    # max_allowed_coins = int(order_total * setting.max_redeem_percent / 100 / setting.coin_value_rupees)

    if coins_to_use > max_allowed_coins:
        coins_to_use = max_allowed_coins

    discount = coins_to_use * setting.coin_value_rupees

    # Deduct coins from customer
    customer.coins -= coins_to_use

    # Log in CoinLedger
    log = CoinLedger(
        customer_id=customer_id,
        order_id=order_id,
        coins=-coins_to_use,
        action=f"Redeemed for order #{order_id} (₹{discount})"
    )
    db.session.add(log)
    db.session.commit()

    return True, f"Redeemed {coins_to_use} coins for ₹{discount}", discount

from models import RewardBadge, db

def update_customer_badge(customer):

    # ✅ Prevent None coins crash
    if customer.coins is None:
        customer.coins = 0

    badge = RewardBadge.query.filter(
        RewardBadge.active == True,
        RewardBadge.required_coins <= int(customer.coins)
    ).order_by(
        RewardBadge.required_coins.desc()
    ).first()

    if badge:
        customer.badge_id = badge.id
def get_next_badge_target(customer):

    coins = customer.coins or 0

    next_badge = RewardBadge.query.filter(
        RewardBadge.active == True,
        RewardBadge.required_coins > coins
    ).order_by(
        RewardBadge.required_coins.asc()
    ).first()

    if next_badge:
        return next_badge.required_coins

    return coins   # user already at top badge


# --------------------------
# Checkout route
# --------------------------

