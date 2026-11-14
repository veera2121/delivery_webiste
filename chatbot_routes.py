
import time

from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user
from sqlalchemy import desc

from models import Order
from chatbot import generate_chatbot_reply

chatbot_bp = Blueprint("chatbot", __name__)


@chatbot_bp.route("/api/customer/chat", methods=["POST"])
def customer_chat():
    request_start = time.perf_counter()

    if not current_user.is_authenticated:
        return jsonify({
            "error": "Please log in to use customer support."
        }), 401

    customer_id = getattr(current_user, "id", None)

    if current_user.__class__.__name__ != "Customer" or not customer_id:
        return jsonify({"error": "Customer account required."}), 403

    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    if not isinstance(message, str):
        return jsonify({"error": "Invalid message."}), 400

    message = message.strip()

    if not message or len(message) > 1000:
        return jsonify({
            "error": "Enter a message of up to 1000 characters."
        }), 400

    try:
        db_start = time.perf_counter()

        latest_orders = (
            Order.query
            .filter_by(customer_id=customer_id)
            .order_by(desc(Order.id))
            .limit(5)
            .all()
        )

        order_context = [
            {
                "order_id": order.order_id,
                "status": order.status,
                "payment_status": order.payment_status,
                "total": float(order.final_total or 0),
            }
            for order in latest_orders
        ]

        context = (
            f"Verified orders: {order_context}"
            if order_context
            else "No orders linked to this customer account were found."
        )

        current_app.logger.info(
            "Chatbot database time: %.3fs",
            time.perf_counter() - db_start,
        )

        chatbot_start = time.perf_counter()

        reply = generate_chatbot_reply(
            message,
            customer_context=context,
        )

        current_app.logger.info(
            "Chatbot processing time: %.3fs",
            time.perf_counter() - chatbot_start,
        )

        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("Chatbot returned an empty reply")

        current_app.logger.info(
            "Chatbot total request time: %.3fs",
            time.perf_counter() - request_start,
        )

        return jsonify({"reply": reply}), 200

    except Exception:
        current_app.logger.exception("Customer chatbot request failed")

        return jsonify({
            "error": "Customer support is temporarily unavailable."
        }), 503
