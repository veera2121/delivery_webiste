from app import app, db
from models import Category, CategoryLocation, Restaurant


with app.app_context():

    # Get all existing restaurant locations
    location_rows = (
        db.session.query(Restaurant.location)
        .filter(
            Restaurant.location.isnot(None),
            Restaurant.location != ""
        )
        .distinct()
        .all()
    )

    locations = sorted({
        str(row[0]).strip()
        for row in location_rows
        if str(row[0]).strip()
    })

    categories = Category.query.order_by(Category.id).all()

    created = 0

    for category in categories:

        existing_locations = {
            assignment.location
            for assignment in category.location_assignments
        }

        for location in locations:

            if location in existing_locations:
                continue

            db.session.add(
                CategoryLocation(
                    category_id=category.id,
                    location=location
                )
            )

            created += 1

    db.session.commit()

    print()
    print("===== CATEGORY LOCATION BACKFILL =====")
    print("Categories:", len(categories))
    print("Locations:", locations)
    print("Assignments created:", created)
    print("======================================")