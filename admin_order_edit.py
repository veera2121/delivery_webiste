import json
import math

from datetime import datetime
from sqlalchemy import select
from models import SettlementLine, CODCollection, CODHandoverBatchItem

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    current_app
)


def register_admin_order_edit(
    app,
    db,
    Order,
    OrderItem,
    MenuItem,
    OrderEditHistory
):

    # =====================================================
    # HELPERS
    # =====================================================

    def safe_float(value, default=0.0):

        try:
            return float(value)

        except (TypeError, ValueError):
            return default


    def safe_int(value, default=1):

        try:
            return int(value)

        except (TypeError, ValueError):
            return default


    def menu_item_is_available(menu_item):

        value = str(
            menu_item.availability or ""
        ).strip().lower()

        return value in {
            "yes",
            "available",
            "true",
            "1",
            "in stock",
            "instock"
        }


    def make_items_snapshot(items):

        return [
            {
                "id": item.id,
                "item_name": item.item_name,
                "quantity": int(
                    item.quantity or 0
                ),
                "price": float(
                    item.price or 0
                ),
                "weight": item.weight,
                "category": item.category,
                "unit": item.unit,
                "item_type": item.item_type,
                "is_removed": bool(item.is_removed),
                "line_total": item.item_total()
            }
            for item in items
        ]


    # =====================================================
    # ADMIN EDIT ORDER ROUTE
    # =====================================================

    @app.route(
        "/admin/order/<int:order_id>/edit",
        methods=["GET", "POST"],
        endpoint="admin_edit_order"
    )
    def admin_edit_order(order_id):

        if not session.get("admin_logged_in"):

            flash(
                "Please login as admin.",
                "danger"
            )

            return redirect(
                url_for("admin_login")
            )

        order = Order.query.get_or_404(
            order_id
        )

        locked_statuses = {
            "Delivered",
            "Cancelled",
            "Refunded"
        }

        if str(order.status or "").strip().lower() in {x.lower() for x in locked_statuses}:

            flash(
                "Delivered, cancelled or refunded "
                "orders cannot be edited.",
                "danger"
            )

            return redirect(
                url_for("admin_dashboard")
            )

        # ---------------------------------------------
        # LOAD THIS RESTAURANT'S EXISTING MENU
        # ---------------------------------------------

        all_menu_items = (
            MenuItem.query
            .filter_by(
                restaurant_id=order.restaurant_id
            )
            .order_by(
                MenuItem.category.asc(),
                MenuItem.name.asc()
            )
            .all()
        )

        available_menu_items = [
            menu_item
            for menu_item in all_menu_items
            if menu_item_is_available(menu_item)
        ]

        if request.method == "GET":

            return render_template(
                "admin_edit_order.html",
                order=order,
                menu_items=available_menu_items
            )

        edit_reason = request.form.get(
            "edit_reason",
            ""
        ).strip()

        if not edit_reason:

            flash(
                "Please enter the reason for editing.",
                "danger"
            )

            return redirect(
                url_for(
                    "admin_edit_order",
                    order_id=order.id
                )
            )

        # Serialize concurrent edits to this order and reload its current state.
        db.session.execute(
            select(Order.id).where(Order.id == order.id).with_for_update()
        ).scalar_one()
        db.session.expire(order)

        # Locking and accounting are handled in the same transaction below.
        # A snapshot alone is not a reason to block an edit.
        from models import CODCollection, CODHandoverBatchItem
        from adjustment_service import record_item_changes, record_customer_balance, new_edit_key
        has_cod = CODCollection.query.filter_by(order_id=order.id).first() is not None
        has_handover = CODHandoverBatchItem.query.filter(
            CODHandoverBatchItem.order_id == order.id,
            CODHandoverBatchItem.released_at.is_(None)
        ).first() is not None
        payment_finalized = (
            has_cod or has_handover or bool(order.payment_verified)
            or str(order.payment_status or '').strip().lower()
            in {'paid', 'success', 'successful', 'completed', 'captured'}
        )
        edit_key = new_edit_key()
        before_items = {
            x.id: (int(x.quantity or 0), x.price or 0, bool(x.is_removed))
            for x in order.items
        }
        old_items = list(order.items)

        old_items_snapshot = (
            make_items_snapshot(old_items)
        )

        old_items_total = float(
            order.items_total or 0
        )

        old_delivery_charge = float(
            order.delivery_charge or 0
        )

        old_extra_charge = float(
            order.extra_charge or 0
        )

        old_manual_discount = float(
            order.manual_discount or 0
        )

        old_final_total = float(
            order.get_final_total()
        )

        try:

            # =========================================
            # UPDATE OR REMOVE EXISTING ITEMS
            # =========================================

            for order_item in list(order.items):

                remove_value = request.form.get(
                    f"remove_item_{order_item.id}"
                )

                if order_item.is_removed:
                    continue

                if remove_value == "1":
                    order_item.is_removed = True
                    continue

                # Require the submitted quantity; never silently reuse the old value.
                quantity_key = f"quantity_{order_item.id}"
                quantity_value = request.form.get(quantity_key)
                if quantity_value is None or not quantity_value.strip():
                    raise ValueError(
                        f"Missing quantity for {order_item.item_name}. "
                        "Refresh the page and try again."
                    )
                try:
                    new_quantity = int(quantity_value)
                except (TypeError, ValueError):
                    raise ValueError(
                        f"Invalid quantity for {order_item.item_name}."
                    )
                if new_quantity < 1:
                    raise ValueError(
                        f"Quantity for {order_item.item_name} must be at least 1."
                    )

                order_item.quantity = (
                    new_quantity
                )

            db.session.flush()

            # =========================================
            # ADD ITEMS FROM RESTAURANT MENU
            # =========================================

            new_menu_item_ids = (
                request.form.getlist(
                    "new_menu_item_id[]"
                )
            )

            new_quantities = (
                request.form.getlist(
                    "new_item_quantity[]"
                )
            )

            for index, menu_item_id in enumerate(
                new_menu_item_ids
            ):

                menu_item_id = str(
                    menu_item_id or ""
                ).strip()

                if not menu_item_id:
                    continue

                selected_menu_item = (
                    MenuItem.query
                    .filter_by(
                        id=safe_int(
                            menu_item_id,
                            0
                        ),
                        restaurant_id=(
                            order.restaurant_id
                        )
                    )
                    .first()
                )

                if not selected_menu_item:

                    raise ValueError(
                        "The selected menu item "
                        "was not found."
                    )

                if not menu_item_is_available(
                    selected_menu_item
                ):

                    raise ValueError(
                        f"{selected_menu_item.name} "
                        f"is currently unavailable."
                    )

                if index >= len(new_quantities):
                    raise ValueError(
                        f"Missing quantity for new item {selected_menu_item.name}."
                    )
                quantity_value = str(new_quantities[index]).strip()
                try:
                    quantity = int(quantity_value)
                except (TypeError, ValueError):
                    raise ValueError(
                        f"Invalid quantity for new item {selected_menu_item.name}."
                    )
                if quantity < 1:
                    raise ValueError(
                        f"Quantity for {selected_menu_item.name} must be at least 1."
                    )

                new_order_item = OrderItem(

                    order_id=order.id,

                    item_name=(
                        selected_menu_item.name
                    ),

                    quantity=quantity,

                    price=round(
                        float(
                            selected_menu_item.price
                            or 0
                        ),
                        2
                    ),

                    category=getattr(
                        selected_menu_item,
                        "category",
                        None
                    ),

                    item_image=getattr(
                        selected_menu_item,
                        "image_url",
                        None
                    ),

                    item_type=getattr(
                        selected_menu_item,
                        "item_type",
                        None
                    )
                )

                db.session.add(
                    new_order_item
                )

            db.session.flush()

            # =========================================
            # CONFIRM AT LEAST ONE ITEM REMAINS
            # =========================================

            remaining_items = (
                OrderItem.query
                .filter_by(
                    order_id=order.id,
                    is_removed=False
                )
                .order_by(
                    OrderItem.id.asc()
                )
                .all()
            )

            if not remaining_items:

                raise ValueError(
                    "The order must contain "
                    "at least one item."
                )

            # =========================================
            # UPDATE CHARGES
            # =========================================

            delivery_charge = safe_float(
                request.form.get(
                    "delivery_charge"
                ),
                order.delivery_charge or 0
            )

            extra_charge = safe_float(
                request.form.get(
                    "extra_charge"
                ),
                order.extra_charge or 0
            )

            manual_discount = safe_float(
                request.form.get(
                    "manual_discount"
                ),
                order.manual_discount or 0
            )

            if not all(math.isfinite(v) for v in (delivery_charge, extra_charge, manual_discount)):
                raise ValueError("Charges and discounts must be finite numbers.")

            if delivery_charge < 0:

                raise ValueError(
                    "Delivery charge cannot "
                    "be negative."
                )

            if extra_charge < 0:

                raise ValueError(
                    "Extra charge cannot "
                    "be negative."
                )

            if manual_discount < 0:

                raise ValueError(
                    "Manual discount cannot "
                    "be negative."
                )

            order.delivery_charge = round(
                delivery_charge,
                2
            )

            order.extra_charge = round(
                extra_charge,
                2
            )

            order.manual_discount = round(
                manual_discount,
                2
            )

            # A form checkbox is not proof of customer authorization.
            # Do not grant approval based on an admin-submitted value.
            order.customer_edit_approved = False

            # =========================================
            # RECALCULATE ITEMS TOTAL
            # =========================================

            order.items_total = round(
                sum(
                    item.item_total()
                    for item in remaining_items
                ),
                2
            )

            new_final_total = (
                order.get_final_total()
            )

            amount_difference = round(
                new_final_total
                - old_final_total,
                2
            )

            # Record pending refund/collection instead of falsely approving payment.
            # Gateway and COD ledgers are NOT marked paid/refunded here.
            after_items = {
                x.id: (int(x.quantity or 0), x.price or 0, bool(x.is_removed))
                for x in OrderItem.query.filter_by(order_id=order.id).all()
            }
            record_item_changes(
                db, order, before_items, after_items, edit_reason,
                str(session.get('admin_username') or 'Super Admin'), edit_key
            )
            record_customer_balance(
                db, order, old_final_total, new_final_total, edit_reason,
                str(session.get('admin_username') or 'Super Admin'),
                edit_key, payment_finalized
            )

            order.final_total = (
                new_final_total
            )

            order.is_order_edited = True

            order.order_edit_reason = (
                edit_reason
            )

            order.order_edited_at = (
                datetime.utcnow()
            )

            order.order_edited_by = (
                "Super Admin"
            )

            order.updated_at = (
                datetime.utcnow()
            )

            db.session.flush()

            updated_items = (
                OrderItem.query
                .filter_by(
                    order_id=order.id
                )
                .order_by(
                    OrderItem.id.asc()
                )
                .all()
            )

            new_items_snapshot = (
                make_items_snapshot(
                    updated_items
                )
            )

            # =========================================
            # SAVE EDIT HISTORY
            # =========================================

            history = OrderEditHistory(

                order_id=order.id,

                action="Admin Updated Order",

                old_items=json.dumps(
                    old_items_snapshot,
                    ensure_ascii=False
                ),

                new_items=json.dumps(
                    new_items_snapshot,
                    ensure_ascii=False
                ),

                old_items_total=(
                    old_items_total
                ),

                new_items_total=(
                    order.items_total
                ),

                old_delivery_charge=(
                    old_delivery_charge
                ),

                new_delivery_charge=(
                    order.delivery_charge
                ),

                old_extra_charge=(
                    old_extra_charge
                ),

                new_extra_charge=(
                    order.extra_charge
                ),

                old_manual_discount=(
                    old_manual_discount
                ),

                new_manual_discount=(
                    order.manual_discount
                ),

                old_final_total=(
                    old_final_total
                ),

                new_final_total=(
                    new_final_total
                ),

                reason=edit_reason,

                edited_by="Super Admin"
            )

            db.session.add(history)

            db.session.commit()

            flash(
                f"Order updated successfully. "
                f"New total ₹{new_final_total:.2f}",
                "success"
            )

            return redirect(
                url_for(
                    "admin_edit_order",
                    order_id=order.id
                )
            )

        except ValueError as error:

            db.session.rollback()

            flash(
                str(error),
                "danger"
            )

            return redirect(
                url_for(
                    "admin_edit_order",
                    order_id=order.id
                )
            )

        except Exception as error:

            db.session.rollback()

            current_app.logger.exception(
                "Admin order edit failed "
                "for order ID %s: %s",
                order.id,
                error
            )

            flash(
                "Unable to update the order. "
                "Please check the server logs.",
                "danger"
            )

            return redirect(
                url_for(
                    "admin_edit_order",
                    order_id=order.id
                )
            )