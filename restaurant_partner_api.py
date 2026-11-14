"""
RucHiGO Restaurant Partners API
================================

Add this file as: restaurant_partner_api.py

In app.py, AFTER app, db, csrf, socketio and model imports are initialized,
add:

    from restaurant_partner_api import register_restaurant_partner_api
    register_restaurant_partner_api(app, socketio, csrf)

This module reuses the existing RestaurantUser, Restaurant, Order, OrderItem,
MenuItem and SQLAlchemy models. It does not create tables or modify the DB.

Authentication:
- POST /api/restaurant-partner/login returns a signed bearer token.
- Flutter sends: Authorization: Bearer <token>
- Tokens expire after 30 days. Logout on the client by deleting the token.

Set a strong, private SECRET_KEY environment variable in production.
"""

from datetime import datetime, timedelta
from functools import wraps
import json
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import func

from extensions import db
from models import Restaurant, RestaurantUser, Order, OrderItem, MenuItem, RestaurantOffer, RestaurantPartnerDeviceToken


restaurant_partner_api = Blueprint(
    "restaurant_partner_api",
    __name__,
    url_prefix="/api/restaurant-partner",
)

TOKEN_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


# Restaurant-side statuses that the API allows the restaurant to set.
# Delivery-only statuses are intentionally excluded.
RESTAURANT_ALLOWED_STATUSES = {
    "Accepted",
    "Confirmed",
    "Preparing",
    "Ready",
    "Rejected",
    "Cancelled",
}
DELIVERY_ONLY_STATUSES = {
    "Assignment Pending",
    "Started",
    "Picked Up",
    "Out for Delivery",
    "Delivered",
}


def _serializer():
    secret = current_app.config.get("SECRET_KEY")
    if not secret or secret == "my-super-secret-key-123":
        # Avoid issuing mobile API tokens with the development fallback secret.
        raise RuntimeError(
            "Set a strong SECRET_KEY environment variable before enabling "
            "Restaurant Partners API authentication."
        )
    return URLSafeTimedSerializer(secret, salt="ruchigo-restaurant-partner-api-v1")


def _json_error(message, status=400):
    return jsonify({"success": False, "message": message}), status


def _float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _iso(value):
    return value.isoformat() if value else None


def _restaurant_token(user):
    return _serializer().dumps({
        "user_id": user.id,
        "restaurant_id": user.restaurant_id,
        "kind": "restaurant_partner",
    })


def restaurant_partner_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")

        if scheme.lower() != "bearer" or not token.strip():
            return _json_error("Authentication token required.", 401)

        try:
            payload = _serializer().loads(
                token.strip(),
                max_age=TOKEN_MAX_AGE_SECONDS,
            )
        except SignatureExpired:
            return _json_error("Session expired. Please log in again.", 401)
        except (BadSignature, ValueError, TypeError):
            return _json_error("Invalid authentication token.", 401)
        except RuntimeError:
            current_app.logger.exception("Restaurant API secret configuration error")
            return _json_error("Authentication is not configured on the server.", 500)

        if payload.get("kind") != "restaurant_partner":
            return _json_error("Invalid token type.", 401)

        user = db.session.get(RestaurantUser, payload.get("user_id"))
        if not user or user.restaurant_id != payload.get("restaurant_id"):
            return _json_error("Restaurant account not found.", 401)

        restaurant = db.session.get(Restaurant, user.restaurant_id)
        if not restaurant:
            return _json_error("Restaurant not found.", 401)

        # Optional account status check. Do not assume every deployment has
        # the same status values; only explicitly suspended/inactive is blocked.
        restaurant_status = str(getattr(restaurant, "status", "") or "").lower()
        if restaurant_status in {"suspended", "inactive", "disabled"}:
            return _json_error("This restaurant account is not active.", 403)

        request.restaurant_partner_user = user
        request.restaurant_partner_restaurant = restaurant
        return fn(*args, **kwargs)

    return wrapper


def _order_json(order, include_items=True):
    items = []
    if include_items:
        for item in (getattr(order, "items", None) or []):
            items.append({
                "id": getattr(item, "id", None),
                "name": getattr(item, "item_name", None) or "",
                "quantity": int(getattr(item, "quantity", 0) or 0),
                "price": _float(getattr(item, "price", 0)),
                "weight": getattr(item, "weight", None) or "",
                "category": getattr(item, "category", None) or "",
                "unit": getattr(item, "unit", None) or "",
                "item_type": getattr(item, "item_type", None) or "",
                "image_url": getattr(item, "image_url", None) or "",
            })


    # Deliberately do not return the delivery OTP in restaurant APIs.
    return {
        "id": order.id,
        "order_id": getattr(order, "order_id", None) or str(order.id),
        "restaurant_id": getattr(order, "restaurant_id", None),
        "status": getattr(order, "status", None) or "Pending",
        "customer_name": getattr(order, "customer_name", None) or "",
        "items": items,
        "items_count": len(items),
        "items_total": _float(getattr(order, "items_total", 0)),
        "discount": _float(getattr(order, "discount", 0)),
        "restaurant_offer_discount": _float(
            getattr(order, "restaurant_offer_discount", 0)
        ),
        "delivery_charge": _float(getattr(order, "delivery_charge", 0)),
        "final_total": _float(
            order.get_final_total()
            if callable(getattr(order, "get_final_total", None))
            else getattr(order, "final_total", 0)
        ),
        "payment_type": getattr(order, "payment_type", None) or "",
        "payment_status": getattr(order, "payment_status", None) or "",
        "payment_method_used": getattr(order, "payment_method_used", None) or "",
        "order_type": getattr(order, "order_type", None) or "",
        "delivery_person_id": getattr(order, "delivery_person_id", None),
        "created_at": _iso(getattr(order, "created_at", None)),
        "updated_at": _iso(getattr(order, "updated_at", None)),
        "delivered_time": _iso(getattr(order, "delivered_time", None)),
        "cancel_reason": getattr(order, "cancel_reason", None) or "",
    }


def _get_owned_order(restaurant_id, order_id):
    return Order.query.filter_by(
        id=order_id,
        restaurant_id=restaurant_id,
    ).first()


def _dispatch_when_ready(order):
    """Call the existing dispatch service after an order becomes Ready."""
    try:
        from dispatch_service import auto_assign_order
        result = auto_assign_order(order)
        current_app.logger.info(
            "Restaurant API dispatch result for order %s: %r",
            getattr(order, "order_id", order.id),
            result,
        )
        return result
    except Exception:
        current_app.logger.exception(
            "Auto-dispatch failed for order %s",
            getattr(order, "order_id", order.id),
        )
        # The order status remains Ready; dispatch can be retried operationally.
        return None


def _emit_customer_status(order):
    """Keep the existing customer tracking Socket.IO event compatible."""
    socketio = current_app.extensions.get("ruchigo_restaurant_socketio")
    if not socketio:
        return
    try:
        socketio.emit(
            "order_status_update",
            {"order_id": order.id, "status": order.status},
            room=f"order_{order.id}",
        )
    except Exception:
        current_app.logger.exception("Could not emit order status update")


@restaurant_partner_api.post("/login")
def restaurant_partner_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    password = data.get("password")

    if not username or not isinstance(password, str) or not password:
        return _json_error("Username and password are required.", 400)

    user = RestaurantUser.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return _json_error("Invalid username or password.", 401)

    restaurant = db.session.get(Restaurant, user.restaurant_id)
    if not restaurant:
        return _json_error("Restaurant account is not linked to a restaurant.", 403)

    status = str(getattr(restaurant, "status", "") or "").lower()
    if status in {"suspended", "inactive", "disabled"}:
        return _json_error("This restaurant account is not active.", 403)

    try:
        token = _restaurant_token(user)
    except RuntimeError:
        current_app.logger.exception("Set SECRET_KEY before issuing API tokens")
        return _json_error("Authentication is not configured on the server.", 500)

    return jsonify({
        "success": True,
        "message": "Login successful.",
        "token": token,
        "token_type": "Bearer",
        "expires_in": TOKEN_MAX_AGE_SECONDS,
        "user": {
            "id": user.id,
            "username": user.username,
            "restaurant_id": restaurant.id,
            "restaurant_name": restaurant.name or "",
        },
    })


@restaurant_partner_api.get("/me")
@restaurant_partner_required
def restaurant_partner_me():
    user = request.restaurant_partner_user
    restaurant = request.restaurant_partner_restaurant
    return jsonify({
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
        },
        "restaurant": {
            "id": restaurant.id,
            "name": restaurant.name or "",
            "address": getattr(restaurant, "address", None) or "",
            "phone": getattr(restaurant, "phone", None) or "",
            "email": getattr(restaurant, "email", None) or "",
            "location": getattr(restaurant, "location", None) or "",
            "status": getattr(restaurant, "status", None) or "",
            "is_accepting_orders": bool(
                getattr(restaurant, "is_accepting_orders", True)
            ),
            "opening_time": str(getattr(restaurant, "opening_time", "") or ""),
            "closing_time": str(getattr(restaurant, "closing_time", "") or ""),
            "is_visible": bool(getattr(restaurant, "is_visible", True)),
            "is_accepting_orders": bool(getattr(restaurant, "is_accepting_orders", True)),
        },
    })


@restaurant_partner_api.post("/logout")
@restaurant_partner_required
def restaurant_partner_logout():
    # Signed bearer tokens are stateless. The Flutter app must delete its
    # locally stored token. A server-side token blacklist would require storage.
    return jsonify({
        "success": True,
        "message": "Logged out. Delete the stored token on this device.",
    })


@restaurant_partner_api.get("/dashboard")
@restaurant_partner_required
def restaurant_partner_dashboard():
    restaurant = request.restaurant_partner_restaurant
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    tomorrow_start = today_start + timedelta(days=1)
    week_start = today_start - timedelta(days=6)

    base = Order.query.filter_by(restaurant_id=restaurant.id)
    today_orders = base.filter(
        Order.created_at >= today_start,
        Order.created_at < tomorrow_start,
    ).all()
    week_orders = base.filter(Order.created_at >= week_start).all()

    active_statuses = {
        "Pending", "Placed", "Accepted", "Confirmed", "Preparing",
        "Ready", "Assignment Pending", "Out for Delivery", "Started",
    }
    today_earnings = sum(
        _float(
            o.get_final_total()
            if callable(getattr(o, "get_final_total", None))
            else getattr(o, "final_total", 0)
        )
        for o in today_orders
        if (getattr(o, "status", "") or "").lower() not in {
            "cancelled", "canceled", "rejected", "declined", "pending payment"
        }
    )
    week_earnings = sum(
        _float(
            o.get_final_total()
            if callable(getattr(o, "get_final_total", None))
            else getattr(o, "final_total", 0)
        )
        for o in week_orders
        if (getattr(o, "status", "") or "").lower() not in {
            "cancelled", "canceled", "rejected", "declined", "pending payment"
        }
    )

    return jsonify({
        "success": True,
        "restaurant": {
            "id": restaurant.id,
            "name": restaurant.name or "",
            "is_accepting_orders": bool(
                getattr(restaurant, "is_accepting_orders", True)
            ),
        },
        "stats": {
            "today_orders": len(today_orders),
            "delivered_today": sum(
                1 for o in today_orders if o.status == "Delivered"
            ),
            "pending_today": sum(
                1 for o in today_orders
                if (o.status or "").lower() in {"pending", "placed", "pending payment"}
            ),
            "cancelled_today": sum(
                1 for o in today_orders
                if (o.status or "").lower() in {"cancelled", "canceled", "rejected", "declined"}
            ),
            "active_orders": sum(
                1 for o in base.all() if (o.status or "") in active_statuses
            ),
            "today_earnings": round(today_earnings, 2),
            "today_cod_amount": round(sum(
                _float(getattr(o, "get_final_total", lambda: getattr(o, "final_total", 0))())
                for o in today_orders
                if (getattr(o, "payment_type", "") or "").lower() == "cod"
                and (o.status or "").lower() not in {"cancelled", "canceled", "rejected", "declined"}
            ), 2),
            "today_online_amount": round(sum(
                _float(getattr(o, "get_final_total", lambda: getattr(o, "final_total", 0))())
                for o in today_orders
                if (getattr(o, "payment_type", "") or "").lower() == "online"
                and (o.status or "").lower() not in {"cancelled", "canceled", "rejected", "declined"}
            ), 2),
            "weekly_orders": len(week_orders),
            "weekly_earnings": round(week_earnings, 2),
        },
    })


@restaurant_partner_api.get("/orders")
@restaurant_partner_required
def restaurant_partner_orders():
    restaurant = request.restaurant_partner_restaurant
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = request.args.get("per_page", DEFAULT_PAGE_SIZE, type=int)
    per_page = min(max(per_page or DEFAULT_PAGE_SIZE, 1), MAX_PAGE_SIZE)
    status = (request.args.get("status") or "").strip()

    query = Order.query.filter_by(restaurant_id=restaurant.id)
    if status:
        query = query.filter(func.lower(Order.status) == status.lower())

    pagination = query.order_by(Order.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    return jsonify({
        "success": True,
        "orders": [_order_json(o) for o in pagination.items],
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        },
    })


@restaurant_partner_api.get("/orders/<int:order_id>")
@restaurant_partner_required
def restaurant_partner_order_detail(order_id):
    restaurant = request.restaurant_partner_restaurant
    order = _get_owned_order(restaurant.id, order_id)
    if not order:
        return _json_error("Order not found.", 404)
    return jsonify({"success": True, "order": _order_json(order)})


def _update_order_status(restaurant, order, new_status):
    normalized = str(new_status or "").strip().lower().replace("_", " ")
    status_map = {
        "accept": "Accepted",
        "accepted": "Accepted",
        "confirm": "Confirmed",
        "confirmed": "Confirmed",
        "prepare": "Preparing",
        "preparing": "Preparing",
        "ready": "Ready",
        "reject": "Rejected",
        "rejected": "Rejected",
        "cancel": "Cancelled",
        "cancelled": "Cancelled",
    }
    canonical = status_map.get(normalized)
    if not canonical or canonical not in RESTAURANT_ALLOWED_STATUSES:
        return _json_error(
            "Invalid status. Allowed values: Accepted, Confirmed, Preparing, Ready, Rejected, Cancelled.",
            400,
        )

    old_status = str(order.status or "").strip()
    old_key = old_status.lower().replace("_", " ")

    if old_key in {s.lower() for s in DELIVERY_ONLY_STATUSES}:
        return _json_error(
            "Delivery has started or finished. Restaurant cannot change this status.",
            409,
        )

    if old_key in {"delivered", "cancelled", "canceled", "rejected", "declined", "completed"}:
        return _json_error("This order is already closed.", 409)

    if old_key == "pending payment":
        return _json_error(
            "This order is waiting for payment. Do not accept it until payment is confirmed.",
            409,
        )

    if old_status.lower() == canonical.lower():
        return jsonify({
            "success": True,
            "message": "Order already has this status.",
            "order": _order_json(order),
        })

    # Rejection/cancellation is permitted only before preparation/dispatch.
    if canonical in {"Rejected", "Cancelled"} and old_key in {
        "preparing", "ready", "assignment pending"
    }:
        return _json_error(
            "This order has progressed too far to reject/cancel from the restaurant app.",
            409,
        )

    # Avoid allowing arbitrary backwards movement in the normal lifecycle.
    progression = {
        "pending": 0,
        "placed": 0,
        "accepted": 1,
        "confirmed": 1,
        "preparing": 2,
        "ready": 3,
    }
    if canonical in {"Accepted", "Confirmed", "Preparing", "Ready"}:
        old_level = progression.get(old_key)
        new_level = progression[canonical.lower()]
        if old_level is not None and new_level < old_level:
            return _json_error("Order status cannot move backwards.", 409)

    order.status = canonical
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to update restaurant order status")
        return _json_error("Could not update order status.", 500)

    dispatch_result = None
    if canonical == "Ready":
        dispatch_result = _dispatch_when_ready(order)

    _emit_customer_status(order)

    return jsonify({
        "success": True,
        "message": "Order status updated.",
        "order": _order_json(order),
        "dispatch_triggered": canonical == "Ready",
        "dispatch_result": (
            dispatch_result if isinstance(dispatch_result, (str, int, float, bool, dict, list, type(None)))
            else str(dispatch_result)
        ),
    })


@restaurant_partner_api.post("/orders/<int:order_id>/status")
@restaurant_partner_required
def restaurant_partner_update_order_status(order_id):
    restaurant = request.restaurant_partner_restaurant
    order = _get_owned_order(restaurant.id, order_id)
    if not order:
        return _json_error("Order not found.", 404)

    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not new_status:
        return _json_error("JSON field 'status' is required.", 400)

    return _update_order_status(restaurant, order, new_status)


@restaurant_partner_api.post("/orders/<int:order_id>/accept")
@restaurant_partner_required
def restaurant_partner_accept_order(order_id):
    restaurant = request.restaurant_partner_restaurant
    order = _get_owned_order(restaurant.id, order_id)
    if not order:
        return _json_error("Order not found.", 404)
    return _update_order_status(restaurant, order, "Accepted")


@restaurant_partner_api.post("/orders/<int:order_id>/reject")
@restaurant_partner_required
def restaurant_partner_reject_order(order_id):
    restaurant = request.restaurant_partner_restaurant
    order = _get_owned_order(restaurant.id, order_id)
    if not order:
        return _json_error("Order not found.", 404)

    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "").strip()[:500]
    result = _update_order_status(restaurant, order, "Rejected")

    # Persist rejection reason only if the existing model supports it.
    # Avoid a second write when the status update itself failed.
    response, status_code = result if isinstance(result, tuple) else (result, 200)
    if status_code < 400 and reason and hasattr(order, "cancel_reason"):
        try:
            order.cancel_reason = reason
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Could not save rejection reason")
    return result


@restaurant_partner_api.get("/menu")
@restaurant_partner_required
def restaurant_partner_menu():
    restaurant = request.restaurant_partner_restaurant
    items = MenuItem.query.filter_by(
        restaurant_id=restaurant.id
    ).order_by(MenuItem.category.asc(), MenuItem.name.asc()).all()

    return jsonify({
        "success": True,
        "items": [{
            "id": item.id,
            "name": item.name or "",
            "description": getattr(item, "description", None) or "",
            "category": getattr(item, "category", None) or "",
            "price": _float(getattr(item, "price", 0)),
            "mrp": _float(getattr(item, "mrp", 0)),
            "unit": getattr(item, "unit", None) or "",
            "image_url": getattr(item, "image_url", None) or "",
            "item_type": getattr(item, "item_type", None) or "",
            "availability": getattr(item, "availability", None) or "yes",
            "is_special": bool(getattr(item, "is_special", False)),
        } for item in items],
    })


@restaurant_partner_api.patch("/menu/<int:item_id>/availability")
@restaurant_partner_required
def restaurant_partner_update_menu_availability(item_id):
    restaurant = request.restaurant_partner_restaurant
    item = MenuItem.query.filter_by(
        id=item_id,
        restaurant_id=restaurant.id,
    ).first()
    if not item:
        return _json_error("Menu item not found.", 404)

    data = request.get_json(silent=True) or {}
    if "availability" not in data:
        return _json_error("JSON field 'availability' is required.", 400)

    raw = str(data.get("availability") or "").strip().lower()
    values = {
        "yes": "yes",
        "available": "yes",
        "true": "yes",
        "1": "yes",
        "no": "no",
        "unavailable": "no",
        "false": "no",
        "0": "no",
    }
    if raw not in values:
        return _json_error("Availability must be 'yes' or 'no'.", 400)

    item.availability = values[raw]
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to update menu availability")
        return _json_error("Could not update menu availability.", 500)

    return jsonify({
        "success": True,
        "message": "Menu availability updated.",
        "item": {
            "id": item.id,
            "name": item.name or "",
            "availability": item.availability,
        },
    })


# Restaurant partner self-service settings. These endpoints only ever access the
# restaurant attached to the authenticated bearer token; clients cannot submit a restaurant_id.
PARTNER_SETTING_FIELDS = {
    "card_image_url": str, "logo_url": str, "card_tags": str,
    "homepage_position": int, "is_featured": bool, "is_popular": bool,
    "is_sponsored": bool, "is_visible": bool,
    "visibility_start_at": str, "visibility_end_at": str,
    "opening_soon_minutes": int, "last_order_time": str,
    "temporarily_closed": bool, "temporary_closed_until": str,
    "estimated_preparation_minutes": int, "delivery_radius_km": float,
    "delivery_surge_charge": float, "minimum_order_amount": float,
    "delivery_time": str, "opening_time": str, "closing_time": str,
    "accept_orders_until": str,
    "max_active_orders": int, "busy_mode": bool,
    "busy_prep_extra_minutes": int, "auto_resume_at": str,
    "is_accepting_orders": bool,
    "break_enabled": bool,
    "break_start_time": str,
    "break_end_time": str,
}


def _parse_partner_setting(field, value):
    if field in {"is_featured", "is_popular", "is_sponsored", "is_visible",
                 "temporarily_closed", "busy_mode", "is_accepting_orders",
                 "break_enabled"}:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if field in {"homepage_position", "opening_soon_minutes", "estimated_preparation_minutes",
                 "max_active_orders", "busy_prep_extra_minutes"}:
        if value in (None, "") and field == "max_active_orders":
            return None
        result = int(value)
        if field == "homepage_position" and result < 0: raise ValueError("Display order cannot be negative.")
        if field in {"opening_soon_minutes", "busy_prep_extra_minutes"} and result < 0: raise ValueError("Minutes cannot be negative.")
        if field == "estimated_preparation_minutes" and result < 1: raise ValueError("Preparation time must be at least 1 minute.")
        if field == "max_active_orders" and result < 1: raise ValueError("Order limit must be at least 1, or blank for unlimited.")
        return result
    if field in {"delivery_radius_km", "delivery_surge_charge", "minimum_order_amount"}:
        result = float(value or 0)
        if result < 0: raise ValueError(f"{field.replace('_', ' ').title()} cannot be negative.")
        return result
    if field in {"last_order_time", "opening_time", "closing_time", "accept_orders_until",
                 "break_start_time", "break_end_time"}:
        raw = str(value or "").strip()
        if not raw: return None
        # Support HTML/Flutter time inputs and SQLAlchemy Time fields.
        from datetime import time as dt_time
        try: return dt_time.fromisoformat(raw[:8])
        except ValueError: raise ValueError(f"Use HH:MM for {field.replace('_', ' ')}.")
    if field in {"temporary_closed_until", "auto_resume_at", "visibility_start_at", "visibility_end_at"}:
        raw = str(value or "").strip()
        if not raw: return None
        from datetime import datetime as dt
        try:
            parsed = dt.fromisoformat(raw.replace("T", " "))
            # App UI submits local IST time; existing project convention stores UTC-naive.
            from zoneinfo import ZoneInfo
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            return parsed.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        except Exception: raise ValueError(f"Use YYYY-MM-DD HH:MM for {field.replace('_', ' ')}.")
    raw = str(value or "").strip()
    return raw or None


@restaurant_partner_api.get("/settings")
@restaurant_partner_required
def restaurant_partner_settings():
    restaurant = request.restaurant_partner_restaurant
    settings = {}
    for field in PARTNER_SETTING_FIELDS:
        value = getattr(restaurant, field, None)
        if field in {"last_order_time", "opening_time", "closing_time", "accept_orders_until",
                 "break_start_time", "break_end_time"}:
            value = value.strftime("%H:%M") if value else ""
        elif field in {"temporary_closed_until", "auto_resume_at", "visibility_start_at", "visibility_end_at"}:
            value = value.strftime("%Y-%m-%d %H:%M") if value else ""
        settings[field] = value
    offer = RestaurantOffer.query.filter_by(restaurant_id=restaurant.id).order_by(
        RestaurantOffer.id.desc()
    ).first()
    offer_data = None
    if offer:
        offer_data = {
            "id": offer.id,
            "title": getattr(offer, "title", "") or "",
            "description": getattr(offer, "description", "") or "",
            "offer_type": getattr(offer, "offer_type", "percent") or "percent",
            "offer_value": _float(getattr(offer, "offer_value", 0)),
            "min_order_amount": _float(getattr(offer, "min_order_amount", 0)),
            "start_date": getattr(offer, "start_date", None).strftime("%Y-%m-%d") if getattr(offer, "start_date", None) else "",
            "end_date": getattr(offer, "end_date", None).strftime("%Y-%m-%d") if getattr(offer, "end_date", None) else "",
            "is_active": bool(getattr(offer, "is_active", False)),
            "promotional_badge": getattr(offer, "promotional_badge", "") or "",
            "coupon_code": getattr(offer, "coupon_code", "") or "",
            "coupon_eligible": bool(getattr(offer, "coupon_eligible", True)),
        }
    items = MenuItem.query.filter_by(restaurant_id=restaurant.id).order_by(MenuItem.category.asc(), MenuItem.name.asc()).all()
    return jsonify({"success": True, "settings": settings, "offer": offer_data,
                    "menu_items": [{"id": item.id, "name": item.name or "",
                                    "category": getattr(item, "category", "") or "",
                                    "is_special": bool(getattr(item, "is_special", False))}
                                   for item in items]})


@restaurant_partner_api.patch("/settings")
@restaurant_partner_required
def restaurant_partner_update_settings():
    restaurant = request.restaurant_partner_restaurant
    data = request.get_json(silent=True) or {}
    try:
        for field, converter in PARTNER_SETTING_FIELDS.items():
            if field not in data or not hasattr(restaurant, field):
                continue
            setattr(restaurant, field, _parse_partner_setting(field, data[field]))
        special_ids = {int(x) for x in (data.get("special_menu_item_ids") or [])}
        for item in MenuItem.query.filter_by(restaurant_id=restaurant.id).all():
            if hasattr(item, "is_special"):
                item.is_special = item.id in special_ids
        offer_data = data.get("offer")
        if isinstance(offer_data, dict):
            title = str(offer_data.get("title") or "").strip()
            offer = RestaurantOffer.query.filter_by(restaurant_id=restaurant.id).order_by(
                RestaurantOffer.id.desc()
            ).first()
            offer_keys = ["title", "description", "offer_type", "offer_value", "min_order_amount",
                          "start_date", "end_date", "is_active", "promotional_badge", "coupon_code", "coupon_eligible"]
            has_offer = any(str(offer_data.get(k) or "").strip() for k in offer_keys if k not in {"is_active", "coupon_eligible"}) or offer_data.get("is_active")
            if has_offer:
                if offer is None:
                    offer = RestaurantOffer(restaurant_id=restaurant.id)
                    db.session.add(offer)
                offer.title = title or "Restaurant Offer"
                offer.description = str(offer_data.get("description") or "").strip() or None
                offer.offer_type = str(offer_data.get("offer_type") or "percent")
                if offer.offer_type not in {"percent", "flat", "free_delivery"}:
                    raise ValueError("Offer type must be percent, flat, or free_delivery.")
                offer.offer_value = float(offer_data.get("offer_value") or 0)
                offer.min_order_amount = float(offer_data.get("min_order_amount") or 0)
                from datetime import datetime as dt_datetime
                for key in ("start_date", "end_date"):
                    raw = str(offer_data.get(key) or "").strip()
                    setattr(offer, key, dt_datetime.fromisoformat(raw + "T00:00:00") if raw else None)
                offer.is_active = bool(offer_data.get("is_active", False))
                if hasattr(offer, "promotional_badge"): offer.promotional_badge = str(offer_data.get("promotional_badge") or "").strip() or None
                if hasattr(offer, "coupon_code"): offer.coupon_code = str(offer_data.get("coupon_code") or "").strip() or None
                if hasattr(offer, "coupon_eligible"): offer.coupon_eligible = bool(offer_data.get("coupon_eligible", True))
        db.session.commit()
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        return _json_error(str(exc), 400)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not save restaurant partner settings")
        return _json_error("Could not save settings. Confirm the database migration has been applied.", 500)
    return jsonify({"success": True, "message": "Restaurant settings saved."})



@restaurant_partner_api.get("/delivery-partners")
@restaurant_partner_required
def restaurant_partner_delivery_partners():
    """List delivery partners already linked to this restaurant."""
    from models import DeliveryPerson, RestaurantDelivery

    restaurant = request.restaurant_partner_restaurant
    assigned_ids = db.session.query(
        RestaurantDelivery.delivery_person_id
    ).filter(
        RestaurantDelivery.restaurant_id == restaurant.id
    ).subquery()

    riders = DeliveryPerson.query.filter(
        DeliveryPerson.id.in_(assigned_ids)
    ).order_by(DeliveryPerson.name.asc()).all()

    return jsonify({
        "success": True,
        "delivery_partners": [{
            "id": rider.id,
            "name": rider.name or "",
            "phone": rider.phone or "",
            "is_active": bool(getattr(rider, "is_active", True)),
            "is_online": bool(getattr(rider, "is_online", False)),
            "is_available": bool(getattr(rider, "is_available", False)),
            "last_seen": _iso(getattr(rider, "last_seen", None)),
        } for rider in riders],
    })



@restaurant_partner_api.post("/notifications/register")
@restaurant_partner_required
def restaurant_partner_register_notification_token():
    """Register/refresh the FCM token for the signed-in restaurant account."""
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    platform = str(data.get("platform") or "android").strip().lower()[:24]
    if not token or len(token) > 512:
        return _json_error("A valid notification token is required.", 400)

    user = request.restaurant_partner_user
    restaurant = request.restaurant_partner_restaurant
    record = RestaurantPartnerDeviceToken.query.filter_by(token=token).first()
    if record is None:
        record = RestaurantPartnerDeviceToken(
            user_id=user.id, restaurant_id=restaurant.id, token=token,
            platform=platform or "android", is_active=True,
        )
        db.session.add(record)
    else:
        record.user_id = user.id
        record.restaurant_id = restaurant.id
        record.platform = platform or "android"
        record.is_active = True
        record.updated_at = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not save restaurant partner FCM token")
        return _json_error("Could not register notifications on this device.", 500)
    return jsonify({"success": True, "message": "Order notifications enabled."})


@restaurant_partner_api.post("/notifications/unregister")
@restaurant_partner_required
def restaurant_partner_unregister_notification_token():
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    user = request.restaurant_partner_user
    if token:
        record = RestaurantPartnerDeviceToken.query.filter_by(token=token, user_id=user.id).first()
        if record:
            record.is_active = False
            record.updated_at = datetime.utcnow()
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Could not deactivate restaurant partner FCM token")
                return _json_error("Could not unregister this device.", 500)
    return jsonify({"success": True, "message": "Device notifications unregistered."})


def _firebase_messaging():
    """Return Firebase Messaging, initializing the default app if necessary.

    Supported credentials:
    - FIREBASE_KEY environment variable containing service-account JSON text
    - FIREBASE_KEY containing a path to a service-account JSON file
    - firebase_key.json beside the Flask app or in the current working directory

    If the main application already initialized Firebase Admin, its default app
    is reused.
    """
    import firebase_admin
    from firebase_admin import credentials, messaging

    try:
        firebase_admin.get_app()
    except ValueError:
        raw_key = (os.environ.get("FIREBASE_KEY") or "").strip()
        credential = None

        if raw_key:
            if raw_key.startswith("{"):
                credential = credentials.Certificate(json.loads(raw_key))
            else:
                key_path = Path(raw_key).expanduser()
                if not key_path.is_file():
                    raise RuntimeError(
                        "FIREBASE_KEY must contain service-account JSON or a valid file path."
                    )
                credential = credentials.Certificate(str(key_path))
        else:
            candidates = [
                Path(current_app.root_path) / "firebase_key.json",
                Path.cwd() / "firebase_key.json",
            ]
            key_path = next((candidate for candidate in candidates if candidate.is_file()), None)
            if key_path is None:
                raise RuntimeError(
                    "Firebase Admin is not initialized and no FIREBASE_KEY or firebase_key.json was found."
                )
            credential = credentials.Certificate(str(key_path))

        firebase_admin.initialize_app(credential)

    return messaging


def send_restaurant_partner_new_order_notification(restaurant_id, order):
    """Send high-priority FCM after a customer order has committed.

    Call only after the order's db.session.commit() succeeds. Push failure must
    never fail or roll back the customer's order.
    """
    records = RestaurantPartnerDeviceToken.query.filter_by(
        restaurant_id=restaurant_id, is_active=True
    ).all()
    tokens = [record.token for record in records]
    if not tokens:
        return 0

    order_id = str(getattr(order, "order_id", None) or getattr(order, "id", ""))
    customer_name = str(getattr(order, "customer_name", None) or "Customer").strip()
    try:
        item_count = len(getattr(order, "items", None) or [])
    except Exception:
        item_count = 0
    total_value = getattr(order, "final_total", None)
    if total_value is None and callable(getattr(order, "get_final_total", None)):
        try:
            total_value = order.get_final_total()
        except Exception:
            total_value = 0
    try:
        total_text = f"₹{float(total_value or 0):.0f}"
    except (TypeError, ValueError):
        total_text = ""
    body_parts = [f"Customer: {customer_name}"]
    if item_count:
        body_parts.append(f"{item_count} item(s)")
    if total_text:
        body_parts.append(total_text)
    body = " • ".join(body_parts) + ". Tap to accept."

    try:
        messaging = _firebase_messaging()
        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=f"NEW ORDER #{order_id}", body=body),
            data={
                "type": "new_order",
                "order_id": order_id,
                "restaurant_id": str(restaurant_id),
                "customer_name": customer_name,
            },
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="ruchigo_new_orders",
                    sound="new_order",
                    priority="max",
                    default_vibrate_timings=False,
                    vibrate_timings_millis=[0, 700, 250, 700, 250, 1000],
                ),
            ),
        )
        sender = getattr(messaging, "send_each_for_multicast", None)
        response = sender(message) if sender else messaging.send_multicast(message)
        for record, result in zip(records, response.responses):
            if not result.success and type(result.exception).__name__ in {"UnregisteredError", "InvalidArgumentError"}:
                record.is_active = False
        if any(not result.success for result in response.responses):
            db.session.commit()
        return response.success_count
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to send restaurant partner new-order push")
        return 0


def register_restaurant_partner_api(app, socketio, csrf=None):
    """
    Register routes and exempt this bearer-token API blueprint from Flask-WTF
    form CSRF validation. Bearer tokens are sent in the Authorization header.
    """
    if "restaurant_partner_api" not in app.blueprints:
        app.extensions["ruchigo_restaurant_socketio"] = socketio
        app.register_blueprint(restaurant_partner_api)
        if csrf is not None:
            csrf.exempt(restaurant_partner_api)
