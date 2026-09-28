from app import app, db
from models import Restaurant, RestaurantPickupQR
import secrets


with app.app_context():

    restaurants = Restaurant.query.all()

    created = 0
    existing = 0

    for restaurant in restaurants:

        qr = RestaurantPickupQR.query.filter_by(
            restaurant_id=restaurant.id
        ).first()

        if qr:
            print(
                f"✓ QR already exists: "
                f"{restaurant.name} "
                f"(ID: {restaurant.id})"
            )

            existing += 1
            continue

        qr_token = secrets.token_urlsafe(32)

        qr = RestaurantPickupQR(
            restaurant_id=restaurant.id,
            qr_token=qr_token,
            is_active=True
        )

        db.session.add(qr)

        print(
            f"✓ Creating QR: "
            f"{restaurant.name} "
            f"(ID: {restaurant.id})"
        )

        created += 1

    db.session.commit()

    print("\n===================================")
    print("RESTAURANT PICKUP QR SETUP COMPLETE")
    print("===================================")
    print(f"Created : {created}")
    print(f"Existing: {existing}")
    print(f"Total   : {len(restaurants)}")