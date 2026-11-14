import csv
import io
from datetime import date, datetime, timedelta

from flask import request, redirect, url_for, render_template, flash, Response, session
from sqlalchemy import func

from settlement_service import (
    generate_weekly_drafts,
    approve_settlement,
    record_payout,
    reconcile_cod,
    money,
    is_delivered,
    is_online,
    get_restaurant_commission_percent,
)


def register_settlement_routes(app, db, Order, OrderItem, Restaurant):
    """Register RucHiGO settlement routes.

    Location filtering uses Restaurant.delivery_location_id.
    This module does not register the separate COD bulk-handover routes.
    """
    from models import (
        SettlementLine,
        RestaurantSettlement,
        SettlementPayout,
        CODCollection,
        RestaurantSettlementTerms,
        DeliveryLocationSettings,
    )

    def _require_admin():
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return None

    def _admin_name():
        return str(
            session.get("admin_username") or session.get("admin_name") or "admin"
        )[:120]

    def _get_location_context(raw_value=None):
        """Return validated location selection, location rows, and matching restaurant IDs."""
        location_filter = (
            request.values.get("location_id", "all")
            if raw_value is None
            else str(raw_value)
        )
        location_filter = (location_filter or "all").strip()

        locations = DeliveryLocationSettings.query.order_by(
            DeliveryLocationSettings.location.asc()
        ).all()

        valid_ids = {loc.id for loc in locations}
        if location_filter not in ("all", "unassigned"):
            try:
                location_id = int(location_filter)
                if location_id not in valid_ids:
                    location_filter = "all"
            except (TypeError, ValueError):
                location_filter = "all"

        if location_filter == "all":
            restaurant_ids = None
        elif location_filter == "unassigned":
            restaurant_ids = {
                rid
                for (rid,) in db.session.query(Restaurant.id)
                .filter(Restaurant.delivery_location_id.is_(None))
                .all()
            }
        else:
            location_id = int(location_filter)
            restaurant_ids = {
                rid
                for (rid,) in db.session.query(Restaurant.id)
                .filter(Restaurant.delivery_location_id == location_id)
                .all()
            }

        return location_filter, locations, restaurant_ids

    def _filtered_settlement_query(period_start=None, period_end=None, location_filter="all"):
        query = RestaurantSettlement.query.join(
            Restaurant, Restaurant.id == RestaurantSettlement.restaurant_id
        )

        if period_start is not None:
            query = query.filter(RestaurantSettlement.period_start == period_start)
        if period_end is not None:
            query = query.filter(RestaurantSettlement.period_end == period_end)

        if location_filter == "unassigned":
            query = query.filter(Restaurant.delivery_location_id.is_(None))
        elif location_filter != "all":
            try:
                location_id = int(location_filter)
            except (TypeError, ValueError):
                location_id = None
            if location_id is not None:
                query = query.filter(Restaurant.delivery_location_id == location_id)

        return query

    @app.route("/admin/settlements", methods=["GET", "POST"])
    def admin_settlements():
        guard = _require_admin()
        if guard:
            return guard

        today = date.today()
        default_start = today - timedelta(days=today.weekday() + 7)
        default_end = default_start + timedelta(days=6)

        try:
            period_start = date.fromisoformat(
                request.values.get("start", default_start.isoformat())
            )
            period_end = date.fromisoformat(
                request.values.get("end", default_end.isoformat())
            )
            if period_end < period_start:
                raise ValueError("Week end cannot be before week start.")
        except ValueError:
            flash("Invalid date range. Please select a valid start and end date.", "danger")
            period_start, period_end = default_start, default_end

        location_filter, locations, filtered_restaurant_ids = _get_location_context()

        if request.method == "POST" and request.form.get("action") == "save_commission":
            try:
                restaurant_id = int(request.form.get("restaurant_id", "0"))
                restaurant = Restaurant.query.get(restaurant_id)
                if not restaurant:
                    raise ValueError("Restaurant not found.")

                # Prevent changing a restaurant outside the selected location via a forged form.
                if (
                    filtered_restaurant_ids is not None
                    and restaurant_id not in filtered_restaurant_ids
                ):
                    raise ValueError("That restaurant is outside the selected location.")

                rate = money(request.form.get("commission_percent"))
                if rate < 0 or rate > 100:
                    raise ValueError("Commission must be between 0 and 100%.")

                terms = RestaurantSettlementTerms.query.filter_by(
                    restaurant_id=restaurant_id
                ).first()
                if not terms:
                    terms = RestaurantSettlementTerms(restaurant_id=restaurant_id)
                    db.session.add(terms)

                terms.commission_percent = rate
                terms.updated_at = datetime.utcnow()
                terms.updated_by = _admin_name()
                db.session.commit()
                flash(
                    "Restaurant commission terms saved. This applies to new order snapshots only.",
                    "success",
                )
            except Exception as exc:
                db.session.rollback()
                flash(str(exc), "danger")

            return redirect(
                url_for(
                    "admin_settlements",
                    start=period_start.isoformat(),
                    end=period_end.isoformat(),
                    location_id=location_filter,
                )
            )

        if request.method == "POST" and request.form.get("action") == "generate":
            try:
                # NOTE: generate_weekly_drafts currently generates drafts across all locations.
                # The selected location filters the report after generation; it does not limit generation.
                generated = generate_weekly_drafts(
                    db,
                    Order,
                    Restaurant,
                    SettlementLine,
                    RestaurantSettlement,
                    CODCollection,
                    period_start,
                    period_end,
                )
                flash(
                    f"Draft generation completed. {len(generated)} restaurant settlement(s) reviewed across all locations.",
                    "success",
                )
            except Exception as exc:
                db.session.rollback()
                app.logger.exception("Settlement draft generation failed")
                flash(str(exc), "danger")

            return redirect(
                url_for(
                    "admin_settlements",
                    start=period_start.isoformat(),
                    end=period_end.isoformat(),
                    location_id=location_filter,
                )
            )

        settlements = _filtered_settlement_query(
            period_start, period_end, location_filter
        ).order_by(RestaurantSettlement.created_at.desc()).all()

        # Delivered COD orders awaiting cash collection reconciliation for this period/location.
        delivered_orders = Order.query.filter(Order.status.ilike("delivered")).all()
        cod_pending = []

        for order in delivered_orders:
            if (
                filtered_restaurant_ids is not None
                and order.restaurant_id not in filtered_restaurant_ids
            ):
                continue
            if is_online(order):
                continue

            delivered_at = getattr(order, "delivered_time", None) or getattr(
                order, "updated_at", None
            )
            if not delivered_at:
                continue

            delivered_date = (
                delivered_at.date() if hasattr(delivered_at, "date") else delivered_at
            )
            if delivered_date < period_start or delivered_date > period_end:
                continue

            cod = CODCollection.query.filter_by(order_id=order.id).first()
            if not cod or cod.status != "reconciled":
                cod_pending.append(order)

        restaurant_query = Restaurant.query
        if filtered_restaurant_ids is not None:
            restaurant_query = restaurant_query.filter(
                Restaurant.id.in_(filtered_restaurant_ids)
            )
        restaurants = restaurant_query.order_by(Restaurant.name.asc()).all()

        commission_terms = {
            term.restaurant_id: term.commission_percent
            for term in RestaurantSettlementTerms.query.all()
        }

        summary = {
            "count": len(settlements),
            "draft": sum(1 for s in settlements if s.status == "draft"),
            "approved": sum(1 for s in settlements if s.status == "approved"),
            "paid": sum(1 for s in settlements if s.status == "paid"),
            "payout": money(
                sum((money(s.payout_total) for s in settlements), money(0))
            ),
        }

        return render_template(
            "settlements.html",
            settlements=settlements,
            summary=summary,
            period_start=period_start,
            period_end=period_end,
            cod_pending=cod_pending,
            restaurants=restaurants,
            commission_terms=commission_terms,
            locations=locations,
            location_filter=location_filter,
        )

    @app.route("/admin/settlements/<int:settlement_id>", methods=["GET", "POST"])
    def admin_settlement_detail(settlement_id):
        guard = _require_admin()
        if guard:
            return guard

        settlement = RestaurantSettlement.query.get_or_404(settlement_id)

        if request.method == "POST":
            action = request.form.get("action")
            try:
                if action == "approve":
                    approve_settlement(
                        db, RestaurantSettlement, settlement.id, _admin_name()
                    )
                    flash(
                        "Settlement approved. Record the actual bank transfer next.",
                        "success",
                    )
                elif action == "payout":
                    record_payout(
                        db,
                        RestaurantSettlement,
                        SettlementPayout,
                        settlement.id,
                        request.form.get("amount"),
                        request.form.get("payment_reference"),
                        date.fromisoformat(
                            request.form.get("paid_on")
                            or date.today().isoformat()
                        ),
                        request.form.get("payment_method") or "bank_transfer",
                        request.form.get("notes"),
                        _admin_name(),
                    )
                    flash("Payout recorded successfully.", "success")
                else:
                    flash("Unknown action.", "danger")
            except Exception as exc:
                db.session.rollback()
                app.logger.exception("Settlement action failed")
                flash(str(exc), "danger")

            return redirect(
                url_for("admin_settlement_detail", settlement_id=settlement.id)
            )

        lines = SettlementLine.query.filter_by(
            settlement_id=settlement.id
        ).order_by(SettlementLine.order_id.asc()).all()
        payouts = SettlementPayout.query.filter_by(
            settlement_id=settlement.id
        ).all()

        return render_template(
            "settlement_detail.html",
            settlement=settlement,
            lines=lines,
            payouts=payouts,
        )

    @app.route("/admin/settlements/cod/<int:order_id>", methods=["POST"])
    def admin_reconcile_cod(order_id):
        guard = _require_admin()
        if guard:
            return guard

        try:
            reconcile_cod(
                db,
                Order,
                CODCollection,
                order_id,
                collected_amount=request.form.get("collected_amount"),
                expected_amount=request.form.get("expected_amount") or None,
                collected_by=request.form.get("collected_by") or "rider",
                handover_reference=request.form.get("handover_reference"),
                notes=request.form.get("notes"),
                reconciled_by=_admin_name(),
            )
            flash(
                "COD reconciliation saved. Any short/over amount remains flagged for review.",
                "success",
            )
        except Exception as exc:
            db.session.rollback()
            app.logger.exception("COD reconciliation failed")
            flash(str(exc), "danger")

        return redirect(request.referrer or url_for("admin_settlements"))

    @app.route("/admin/settlements/export.csv")
    def admin_settlement_export():
        guard = _require_admin()
        if guard:
            return guard

        try:
            start = date.fromisoformat(request.args.get("start", ""))
            end = date.fromisoformat(request.args.get("end", ""))
            if end < start:
                raise ValueError
        except ValueError:
            return "Invalid or missing start/end date.", 400

        location_filter, locations, _restaurant_ids = _get_location_context(
            request.args.get("location_id", "all")
        )

        rows = _filtered_settlement_query(
            start, end, location_filter
        ).order_by(RestaurantSettlement.restaurant_id.asc()).all()

        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(
            [
                "Settlement ID",
                "Restaurant",
                "Location",
                "Period Start",
                "Period End",
                "Status",
                "Eligible Orders",
                "Original Food Gross",
                "Customer Item Value",
                "Markup",
                "Commission",
                "Adjustments",
                "Restaurant Payout",
                "Review Required",
            ]
        )

        for s in rows:
            restaurant = s.restaurant
            location_name = (
                restaurant.delivery_location_settings.location
                if restaurant
                and getattr(restaurant, "delivery_location_settings", None)
                else "Unassigned"
            )
            writer.writerow(
                [
                    s.id,
                    restaurant.name if restaurant else s.restaurant_id,
                    location_name,
                    s.period_start,
                    s.period_end,
                    s.status,
                    s.order_count,
                    s.food_gross,
                    s.customer_item_value,
                    s.markup_total,
                    s.commission_total,
                    s.adjustment_total,
                    s.payout_total,
                    s.missing_snapshot_count,
                ]
            )

        return Response(
            stream.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=ruchigo-settlements-{start}-{end}.csv"
                )
            },
        )

    # ================= SETTLEMENT REPORTS =================
    @app.route("/admin/settlement-reports", methods=["GET"])
    def admin_settlement_reports():
        guard = _require_admin()
        if guard:
            return guard

        location_filter, locations, _restaurant_ids = _get_location_context(
            request.args.get("location_id", "all")
        )

        settlements = _filtered_settlement_query(
            location_filter=location_filter
        ).order_by(RestaurantSettlement.created_at.desc()).all()

        return render_template(
            "settlement_reports.html",
            settlements=settlements,
            locations=locations,
            location_filter=location_filter,
        )
