from app import app, db
from models import FoodItem, Category

with app.app_context():
    # Add categories
    biryani_cat = Category(name="Biryani")
    pizza_cat = Category(name="Pizza")
    db.session.add_all([biryani_cat, pizza_cat])
    db.session.commit()

    # Add food items
    items = [
        FoodItem(name="Chicken Biryani", price=180, restaurant_id=1, category_id=biryani_cat.id, order_count=0),
        FoodItem(name="Veg Pizza", price=250, restaurant_id=1, category_id=pizza_cat.id, order_count=0),
    ]
    db.session.add_all(items)
    db.session.commit()

    print("✅ FoodItem table seeded successfully!")
