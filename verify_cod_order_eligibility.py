from two_apis_app import app
from models import Order, CODHandoverBatchItem

with app.app_context():
    print("=== ORDERS IN COD HANDOVER BATCH #1 ===")

    items = CODHandoverBatchItem.query.filter_by(batch_id=1).all()

    for item in items:
        order = db.session.get(Order, item.order_id) if False else None
        order = Order.query.get(item.order_id)

        if order is None:
            print("Order not found:", item.order_id)
            continue

        print({
            "order_id": order.id,
            "status": order.status,
            "payment_type": order.payment_type,
            "payment_status": order.payment_status,
            "payment_verified": order.payment_verified,
            "final_total": str(order.final_total),
            "delivered_time": str(order.delivered_time),
            "delivery_person_id": order.delivery_person_id,
            "batch_expected_amount": str(item.expected_amount),
            "item_released": item.released_at is not None,
        })
