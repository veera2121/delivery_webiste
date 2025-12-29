def calculate_totals(restaurant, items_total):
    # Delivery
    delivery = restaurant.delivery_charge or 0

    if restaurant.free_delivery_limit and items_total >= restaurant.free_delivery_limit:
        delivery = 0

    # Offer
    offer_discount = 0
    active_offer = RestaurantOffer.query.filter_by(
        restaurant_id=restaurant.id,
        is_active=True
    ).first()

    if active_offer:
        min_order = active_offer.min_order_amount or 0
        if items_total >= min_order:
            if active_offer.offer_type == "percent":
                offer_discount = (items_total * active_offer.offer_value) / 100
            elif active_offer.offer_type == "flat":
                offer_discount = active_offer.offer_value
            elif active_offer.offer_type == "free_delivery":
                delivery = 0

    # Coupon
    coupon_discount = 0
    if offer_discount == 0 and items_total >= 199:
        coupon_discount = min(items_total * 0.30, 60)

    final_total = round(items_total + delivery - (offer_discount + coupon_discount), 2)

    return {
        "delivery": delivery,
        "offer_discount": offer_discount,
        "coupon_discount": coupon_discount,
        "final_total": final_total
    }
