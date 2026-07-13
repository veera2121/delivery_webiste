from models import MenuItem

def get_recommendations(cart, restaurant_id):

    if not cart:
        return []

    # Get all categories in cart
    cart_categories = []

    cart_ids = []

    for item in cart:

        cart_ids.append(item["id"])

        if item.get("category"):

            cart_categories.append(
                item["category"].strip().lower()
            )

    recommendations = []

    items = MenuItem.query.filter_by(
        restaurant_id=restaurant_id,
        availability="yes"
    ).all()
    
    for item in items:

        data = item.extra_data or {}
        print(item.name, data)

        # Only Add-ons
        recommend_for = str(
            data.get("recommend_for", "")
        ).strip().lower()

        # Skip only items that don't have any recommendation target
        if not recommend_for:
            continue

        # Don't recommend already added items
        if item.id in cart_ids:
            continue

        recommend_for = str(
            data.get("recommend_for", "")
        ).lower()

        # Recommend to all
        if recommend_for == "all":
            recommendations.append(item)
            continue

        recommend_list = [

            x.strip()

            for x in recommend_for.split(",")

        ]

        # Match category
        for category in cart_categories:

            if category in recommend_list:

                recommendations.append(item)

                break

    recommendations.sort(

        key=lambda x:

        int(

            (x.extra_data or {}).get(
                "addon_priority",
                99
            )

        )

    ) 
    print("Cart Categories:", cart_categories)

    items = MenuItem.query.filter_by(
        restaurant_id=restaurant_id,
        availability="yes"
    ).all()

    print("Total Menu Items:", len(items))

    for item in items:
        print("--------------------------------")
        print("Item:", item.name)
        print("Category:", item.category)
        print("Extra Data:", item.extra_data)
        print("Final Recommendations:")

    for r in recommendations:
        print(
            r.name,
            r.extra_data.get("recommend_for"),
            r.extra_data.get("addon_priority")
        )
    return recommendations[:12]