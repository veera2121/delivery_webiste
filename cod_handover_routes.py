from datetime import date
from decimal import Decimal

from flask import (
    request,
    redirect,
    url_for,
    render_template,
    flash,
    session,
)
from sqlalchemy import func

from cod_handover_service import (
    create_handover_batch,
    receive_handover_batch,
    cancel_draft_batch,
)


def register_cod_handover_routes(app, db, Order, DeliveryPerson):
    from models import (
        CODCollection,
        CODCollectionAudit,
        CODHandoverBatch,
        CODHandoverBatchItem,
    )

    ONLINE_TYPES = {
        "online",
        "razorpay",
        "upi",
        "card",
        "netbanking",
    }

    def admin_guard():
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return None

    def admin_name():
        return str(
            session.get("admin_username")
            or session.get("admin_name")
            or "admin"
        )[:120]

    def is_online(order):
        payment_type = str(
            getattr(order, "payment_type", "") or ""
        ).strip().lower()

        return payment_type in ONLINE_TYPES

    def order_business_date(order):
        stamp = (
            getattr(order, "delivered_time", None)
            or getattr(order, "updated_at", None)
        )

        if stamp is None:
            return None

        return stamp.date() if hasattr(stamp, "date") else stamp

    def order_amount(order):
        get_total = getattr(order, "get_final_total", None)

        value = (
            get_total()
            if callable(get_total)
            else (getattr(order, "final_total", 0) or 0)
        )

        return Decimal(str(value)).quantize(Decimal("0.01"))

    def eligible_orders_for_date(business_date):
        """
        Find delivered, non-online orders that:
        - Match the selected business date.
        - Have not already been reconciled.
        - Are not reserved by an active handover batch.
        """
        delivered_orders = (
            Order.query.filter(
                func.lower(Order.status) == "delivered"
            )
            .order_by(Order.id.asc())
            .all()
        )

        dated_orders = [
            order
            for order in delivered_orders
            if (
                order_business_date(order) == business_date
                and not is_online(order)
            )
        ]

        if not dated_orders:
            return []

        order_ids = [order.id for order in dated_orders]

        cod_rows = CODCollection.query.filter(
            CODCollection.order_id.in_(order_ids)
        ).all()

        cod_by_order = {
            row.order_id: row for row in cod_rows
        }

        active_rows = (
            db.session.query(CODHandoverBatchItem.order_id)
            .filter(
                CODHandoverBatchItem.order_id.in_(order_ids),
                CODHandoverBatchItem.released_at.is_(None),
            )
            .all()
        )

        active_ids = {row[0] for row in active_rows}

        result = []

        for order in dated_orders:
            collection = cod_by_order.get(order.id)

            if (
                collection
                and str(collection.status or "").lower()
                == "reconciled"
            ):
                continue

            if order.id in active_ids:
                continue

            result.append({
                "order": order,
                "amount": order_amount(order),
            })

        return result

    def batch_order_details(batches):
        """
        Build order details without depending on an optional
        CODHandoverBatchItem.order relationship.
        """
        output = {}

        for batch in batches:
            items = (
                CODHandoverBatchItem.query
                .filter_by(batch_id=batch.id)
                .order_by(CODHandoverBatchItem.id.asc())
                .all()
            )

            details = []

            for item in items:
                order = Order.query.filter_by(
                    id=item.order_id
                ).first()

                restaurant = (
                    getattr(order, "restaurant", None)
                    if order
                    else None
                )

                if order:
                    restaurant_name = (
                        getattr(restaurant, "name", None)
                        or getattr(order, "restaurant_id", None)
                        or "—"
                    )
                else:
                    restaurant_name = "Order not found"

                details.append({
                    "item": item,
                    "order": order,
                    "restaurant_name": restaurant_name,
                })

            output[batch.id] = details

        return output

    @app.route("/admin/cod-handover", methods=["GET", "POST"])
    def admin_cod_handover():
        guard = admin_guard()

        if guard:
            return guard

        riders = DeliveryPerson.query.order_by(
            DeliveryPerson.name.asc()
        ).all()

        rider_id = str(
            request.values.get("rider_id", "") or ""
        ).strip()

        try:
            business_date = date.fromisoformat(
                request.values.get(
                    "business_date",
                    date.today().isoformat(),
                )
            )
        except (ValueError, TypeError):
            business_date = date.today()
            flash(
                "Invalid date; showing today.",
                "warning",
            )

        # Create a draft batch.
        if (
            request.method == "POST"
            and request.form.get("action") == "create"
        ):
            try:
                posted_rider_id = int(
                    request.form.get("rider_id", "0")
                )

                posted_date = date.fromisoformat(
                    request.form.get("business_date", "")
                )

                batch = create_handover_batch(
                    db,
                    Order,
                    CODCollection,
                    CODHandoverBatch,
                    CODHandoverBatchItem,
                    posted_rider_id,
                    posted_date,
                    admin_name(),
                )

                flash(
                    f"Draft batch #{batch.id} created with "
                    f"{len(batch.items)} order(s). "
                    "Review the order list before recording "
                    "the rider handover.",
                    "success",
                )

                return redirect(
                    url_for(
                        "admin_cod_handover",
                        rider_id=posted_rider_id,
                        business_date=posted_date.isoformat(),
                        focus_batch_id=batch.id,
                    )
                )

            except Exception as exc:
                db.session.rollback()

                app.logger.exception(
                    "COD batch creation failed"
                )

                flash(str(exc), "danger")

                return redirect(
                    url_for(
                        "admin_cod_handover",
                        rider_id=request.form.get(
                            "rider_id", ""
                        ),
                        business_date=request.form.get(
                            "business_date",
                            date.today().isoformat(),
                        ),
                    )
                )

        # Orders eligible for the selected rider/date.
        eligible_orders = []

        if rider_id.isdigit():
            eligible_orders = [
                item
                for item in eligible_orders_for_date(
                    business_date
                )
                if int(
                    item["order"].delivery_person_id or 0
                ) == int(rider_id)
            ]

        # Summarize available orders for all riders.
        available = eligible_orders_for_date(business_date)

        available_by_rider = {}

        for entry in available:
            order = entry["order"]
            rid = int(order.delivery_person_id or 0)

            row = available_by_rider.setdefault(
                rid,
                {
                    "count": 0,
                    "amount": Decimal("0.00"),
                },
            )

            row["count"] += 1
            row["amount"] += entry["amount"]

        # Load batches for the selected date and optional rider.
        batches_query = CODHandoverBatch.query.filter_by(
            business_date=business_date
        )

        if rider_id.isdigit():
            batches_query = batches_query.filter_by(
                rider_id=int(rider_id)
            )

        batches = (
            batches_query
            .order_by(CODHandoverBatch.created_at.desc())
            .all()
        )

        # Count draft and unresolved short/over batches.
        batch_summary = {}

        unresolved_batches = CODHandoverBatch.query.filter(
            CODHandoverBatch.business_date == business_date,
            CODHandoverBatch.status.in_(
                ["draft", "short", "over"]
            ),
        ).all()

        for batch in unresolved_batches:
            rid = int(batch.rider_id)

            row = batch_summary.setdefault(
                rid,
                {
                    "open_count": 0,
                    "draft_expected": Decimal("0.00"),
                    "exceptions": 0,
                },
            )

            row["open_count"] += 1

            if batch.status == "draft":
                row["draft_expected"] += Decimal(
                    str(batch.expected_total or 0)
                )
            else:
                row["exceptions"] += 1

        # Build rider summary rows for the template.
        rider_summaries = []

        for rider in riders:
            rid = int(rider.id)

            available_row = available_by_rider.get(
                rid,
                {
                    "count": 0,
                    "amount": Decimal("0.00"),
                },
            )

            batch_row = batch_summary.get(
                rid,
                {
                    "open_count": 0,
                    "draft_expected": Decimal("0.00"),
                    "exceptions": 0,
                },
            )

            rider_summaries.append({
                "rider": rider,
                "available_count": available_row["count"],
                "available_amount": available_row["amount"],
                "open_batch_count": batch_row["open_count"],
                "draft_expected": batch_row["draft_expected"],
                "exceptions": batch_row["exceptions"],
            })

        batch_details = batch_order_details(batches)

        focus_batch_id = request.args.get(
            "focus_batch_id",
            type=int,
        )

        return render_template(
            "cod_handover.html",
            riders=riders,
            rider_summaries=rider_summaries,
            selected_rider=rider_id,
            selected_date=business_date,
            eligible_orders=eligible_orders,
            batches=batches,
            batch_details=batch_details,
            focus_batch_id=focus_batch_id,
        )

    @app.route(
        "/admin/cod-handover/<int:batch_id>/receive",
        methods=["POST"],
    )
    def admin_cod_handover_receive(batch_id):
        guard = admin_guard()

        if guard:
            return guard

        batch = CODHandoverBatch.query.filter_by(
            id=batch_id
        ).first()

        if batch is None:
            flash(
                "COD handover batch not found.",
                "danger",
            )
            return redirect(
                url_for("admin_cod_handover")
            )

        rider_id = batch.rider_id
        business_date = batch.business_date

        try:
            batch = receive_handover_batch(
                db,
                Order,
                CODCollection,
                CODCollectionAudit,
                CODHandoverBatch,
                CODHandoverBatchItem,
                batch_id,
                request.form.get("received_amount"),
                request.form.get("handover_reference"),
                request.form.get("notes"),
                admin_name(),
                request.form.get(
                    "rider_attested_full_collection"
                ) == "yes",
            )

            if batch.status == "reconciled":
                flash(
                    f"Batch #{batch.id} reconciled. "
                    f"₹{Decimal(str(batch.received_amount or 0)):.2f} "
                    "recorded; individual COD collections and "
                    "audit entries were saved. Restaurant "
                    "settlement remains a separate workflow.",
                    "success",
                )
            else:
                flash(
                    f"Batch #{batch.id} recorded as "
                    f"{batch.status.upper()} with difference "
                    f"₹{Decimal(str(batch.difference_amount or 0)):.2f}. "
                    "The orders were NOT reconciled. "
                    "Investigate the difference; this batch "
                    "cannot be submitted again as a draft.",
                    "warning",
                )

        except Exception as exc:
            db.session.rollback()

            app.logger.exception(
                "COD batch receipt failed"
            )

            flash(str(exc), "danger")

        return redirect(
            url_for(
                "admin_cod_handover",
                rider_id=rider_id,
                business_date=business_date.isoformat(),
                focus_batch_id=batch_id,
            )
        )

    @app.route(
        "/admin/cod-handover/<int:batch_id>/cancel",
        methods=["POST"],
    )
    def admin_cod_handover_cancel(batch_id):
        guard = admin_guard()

        if guard:
            return guard

        batch = CODHandoverBatch.query.filter_by(
            id=batch_id
        ).first()

        if batch is None:
            flash(
                "COD handover batch not found.",
                "danger",
            )
            return redirect(
                url_for("admin_cod_handover")
            )

        rider_id = batch.rider_id
        business_date = batch.business_date

        try:
            batch = cancel_draft_batch(
                db,
                CODHandoverBatch,
                CODHandoverBatchItem,
                batch_id,
            )

            flash(
                f"Draft batch #{batch.id} cancelled; "
                "history retained and orders released.",
                "success",
            )

        except Exception as exc:
            db.session.rollback()

            app.logger.exception(
                "COD batch cancellation failed"
            )

            flash(str(exc), "danger")

        return redirect(
            url_for(
                "admin_cod_handover",
                rider_id=rider_id,
                business_date=business_date.isoformat(),
                focus_batch_id=batch_id,
            )
        )