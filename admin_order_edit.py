import json

from datetime import datetime

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

        if order.status in locked_statuses:

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

                if remove_value == "1":

                    db.session.delete(
                        order_item
                    )

                    continue

                new_quantity = safe_int(
                    request.form.get(
                        f"quantity_{order_item.id}"
                    ),
                    order_item.quantity or 1
                )

                if new_quantity < 1:

                    raise ValueError(
                        f"Quantity for "
                        f"{order_item.item_name} "
                        f"must be at least 1."
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

                quantity_value = (
                    new_quantities[index]
                    if index < len(
                        new_quantities
                    )
                    else 1
                )

                quantity = safe_int(
                    quantity_value,
                    1
                )

                if quantity < 1:

                    raise ValueError(
                        f"Quantity for "
                        f"{selected_menu_item.name} "
                        f"must be at least 1."
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
                    order_id=order.id
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

            order.customer_edit_approved = (
                request.form.get(
                    "customer_edit_approved"
                ) == "1"
            )

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

            # =========================================
            # ONLINE PAYMENT SAFETY
            # =========================================

            is_paid_online = (
                str(
                    order.payment_type or ""
                ).lower() == "online"
                and str(
                    order.payment_status or ""
                ).lower() == "paid"
            )

            if (
                is_paid_online
                and amount_difference > 0
                and not order.customer_edit_approved
            ):

                raise ValueError(
                    "Customer approval is required "
                    "because this paid online order "
                    "total has increased."
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