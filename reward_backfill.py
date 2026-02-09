from app import app          # 👈 adjust filename if needed
from models import Customer, Order
from reward_engine import calculate_coins
from extensions import db

with app.app_context():

    customers = Customer.query.all()

    for c in customers:
        if c.coins and c.coins > 0:
            continue  # skip users who already have coins

        orders = Order.query.filter_by(customer_id=c.id).all()
        total_spent = sum(o.total_amount for o in orders)

        coins = calculate_coins(total_spent)

        if coins > 0:
            c.coins = coins
            c.last_reward_coins = coins

    db.session.commit()

print("✅ All old users received full coins from history")
