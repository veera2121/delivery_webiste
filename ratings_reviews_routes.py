"""Ratings and reviews API routes for RucHiGO.

Register this Blueprint once in two_apis_app.py:
    from ratings_reviews_routes import ratings_reviews_bp
    app.register_blueprint(ratings_reviews_bp)
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import func

from extensions import db
from models import Order, Restaurant, RestaurantReview

ratings_reviews_bp = Blueprint("ratings_reviews", __name__)

def _rr_normalize_phone(value):
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits

def _rr_order_phone_matches(order, submitted_phone):
    entered = _rr_normalize_phone(submitted_phone)
    stored = _rr_normalize_phone(getattr(order, "phone", ""))
    return bool(entered and stored and entered == stored)

def _rr_delivered(order):
    return (getattr(order, "status", "") or "").strip().lower() in {
        "delivered", "completed"
    }

def _rr_order_restaurant_id(order):
    # Most current RucHiGO Order schemas store restaurant_id directly.
    value = getattr(order, "restaurant_id", None)
    if value is not None:
        return int(value)
    restaurant = getattr(order, "restaurant", None)
    return int(restaurant.id) if restaurant is not None else None

def _rr_review_json(review):
    return {
        "id": review.id,
        "restaurant_id": review.restaurant_id,
        "location_id": review.location_id,
        "order_id": review.order_id,
        "customer_name": review.customer_name or "Customer",
        "rating": int(review.rating),
        "comment": review.comment or "",
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }

@ratings_reviews_bp.get("/api/app/restaurants/<int:restaurant_id>/reviews")
def api_restaurant_reviews_list(restaurant_id):
    location_id_raw = request.args.get("location_id", "").strip()
    if not location_id_raw.isdigit():
        return jsonify(success=False, message="A valid location_id is required."), 400
    location_id = int(location_id_raw)

    restaurant = Restaurant.query.get(restaurant_id)
    if not restaurant:
        return jsonify(success=False, message="Restaurant not found."), 404

    # STRICT isolation: this API only serves reviews for the restaurant's
    # assigned delivery location. Do not remove this check to bypass errors.
    restaurant_location_id = getattr(restaurant, "delivery_location_id", None)
    if restaurant_location_id is None or int(restaurant_location_id) != location_id:
        return jsonify({
            "success": True, "restaurant_id": restaurant_id,
            "location_id": location_id, "rating": None,
            "review_count": 0, "reviews": []
        })

    query = RestaurantReview.query.filter_by(
        restaurant_id=restaurant_id, location_id=location_id
    )
    review_count = query.count()
    average = db.session.query(func.avg(RestaurantReview.rating)).filter_by(
        restaurant_id=restaurant_id, location_id=location_id
    ).scalar()

    try:
        page = max(1, int(request.args.get("page", 1) or 1))
        per_page = min(50, max(1, int(request.args.get("per_page", 10) or 10)))
    except (TypeError, ValueError):
        return jsonify(success=False, message="page and per_page must be integers."), 400
    reviews = query.order_by(
        RestaurantReview.created_at.desc(), RestaurantReview.id.desc()
    ).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "success": True,
        "restaurant_id": restaurant_id,
        "location_id": location_id,
        "rating": round(float(average), 1) if average is not None else None,
        "review_count": review_count,
        "reviews": [_rr_review_json(r) for r in reviews],
        "page": page,
        "per_page": per_page,
    })

@ratings_reviews_bp.post("/api/app/reviews")
def api_restaurant_review_create():
    payload = request.get_json(silent=True) or {}
    order_key = str(payload.get("order_id", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    customer_name_input = str(payload.get("customer_name", "")).strip()
    comment = str(payload.get("comment", "")).strip()
    rating_raw = payload.get("rating")

    try:
        rating = int(rating_raw)
    except (TypeError, ValueError):
        return jsonify(success=False, message="Choose a rating from 1 to 5."), 400
    if rating < 1 or rating > 5:
        return jsonify(success=False, message="Choose a rating from 1 to 5."), 400
    if len(comment) > 2000:
        return jsonify(success=False, message="Review must be 2000 characters or fewer."), 400
    if not order_key or not phone:
        return jsonify(success=False, message="Order ID and phone are required."), 400

    # Accept either public order_id or numeric database ID, matching the current
    # My Orders serializer's exposed fields.
    order = None
    if order_key.isdigit():
        order = Order.query.filter(
            (Order.order_id == order_key) | (Order.id == int(order_key))
        ).first()
    else:
        order = Order.query.filter_by(order_id=order_key).first()

    if not order:
        return jsonify(success=False, message="Order not found."), 404
    if not _rr_order_phone_matches(order, phone):
        return jsonify(success=False, message="Order phone number does not match."), 403
    if not _rr_delivered(order):
        return jsonify(success=False, message="You can review only a delivered order."), 400

    restaurant_id = _rr_order_restaurant_id(order)
    location_id = getattr(order, "delivery_location_id", None)
    if not restaurant_id or not location_id:
        return jsonify(
            success=False,
            message="This order is missing restaurant/location details. Please contact support."
        ), 409

    restaurant = Restaurant.query.get(restaurant_id)
    if not restaurant:
        return jsonify(success=False, message="Restaurant not found for this order."), 409

    # Ensure the order's historical location and restaurant assignment agree.
    # If your business intentionally supports a restaurant in multiple locations,
    # model that relationship explicitly rather than weakening isolation.
    restaurant_location_id = getattr(restaurant, "delivery_location_id", None)
    if restaurant_location_id is None or int(restaurant_location_id) != int(location_id):
        return jsonify(
            success=False,
            message="The order location does not match this restaurant's service location."
        ), 409

    existing = RestaurantReview.query.filter_by(order_id=order.id).first()
    if existing:
        return jsonify(success=False, message="This order has already been reviewed."), 409

    customer_name = (
        customer_name_input[:120]
        or getattr(order, "customer_name", None)
        or "Customer"
    )
    review = RestaurantReview(
        restaurant_id=restaurant_id,
        location_id=int(location_id),  # server-derived from the order
        order_id=order.id,
        customer_id=getattr(order, "customer_id", None),
        customer_name=customer_name,
        phone=_rr_normalize_phone(phone),
        rating=rating,
        comment=comment or None,
    )
    db.session.add(review)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        # The unique order_id constraint prevents concurrent duplicate reviews.
        return jsonify(
            success=False,
            message="Could not save the review. It may already have been submitted."
        ), 409

    return jsonify(
        success=True,
        message="Thank you for reviewing your order!",
        review=_rr_review_json(review)
    ), 201

@ratings_reviews_bp.get("/api/app/orders/<int:order_db_id>/review-status")
def api_order_review_status(order_db_id):
    phone = request.args.get("phone", "")
    order = Order.query.get(order_db_id)
    if not order:
        return jsonify(success=False, message="Order not found."), 404
    if not _rr_order_phone_matches(order, phone):
        return jsonify(success=False, message="Order phone number does not match."), 403

    review = RestaurantReview.query.filter_by(order_id=order.id).first()
    return jsonify({
        "success": True,
        "eligible": _rr_delivered(order),
        "reviewed": review is not None,
        "review": _rr_review_json(review) if review else None,
    })
