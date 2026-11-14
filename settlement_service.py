from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_
from sqlalchemy.orm import lazyload

DEFAULT_COMMISSION_PERCENT = Decimal("10.00")
CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_line(restaurant_unit_price, customer_unit_price, quantity, commission_percent):
    """Calculate commission and restaurant payable using offer-price totals."""
    original = money(restaurant_unit_price)
    offer_price = money(customer_unit_price)
    qty = int(quantity)
    rate = Decimal(str(commission_percent)).quantize(Decimal("0.01"))

    if qty < 1:
        raise ValueError("Quantity must be at least 1.")
    if original < 0 or offer_price < 0:
        raise ValueError("Prices cannot be negative.")
    if rate < 0 or rate > 100:
        raise ValueError("Commission must be between 0 and 100%.")

    original_total = money(original * qty)
    offer_total = money(offer_price * qty)
    discount = money(max(original_total - offer_total, Decimal("0.00")))

    # Commission is based on the actual offer price.
    commission = money(offer_total * rate / Decimal("100"))
    payable = money(offer_total - commission)

    return {
        "quantity": qty,
        "restaurant_unit_price": original,
        "customer_unit_price": offer_price,
        "commission_percent": rate,
        "restaurant_gross": offer_total,
        "customer_item_value": offer_total,
        "markup_amount": money(offer_total - original_total),
        "commission_amount": commission,
        "restaurant_payable": payable,
    }

def get_restaurant_commission_percent(RestaurantSettlementTerms, restaurant_id):
    """Return the restaurant's currently agreed rate; default is 10% if not configured."""
    terms = RestaurantSettlementTerms.query.filter_by(restaurant_id=restaurant_id).first()
    if not terms:
        return DEFAULT_COMMISSION_PERCENT
    return Decimal(str(terms.commission_percent)).quantize(Decimal("0.01"))


def create_settlement_line(db, SettlementLine, order, order_item,
                           restaurant_unit_price, customer_unit_price,
                           commission_percent=DEFAULT_COMMISSION_PERCENT):
    """Create immutable price/commission snapshot inside the order transaction."""
    if order_item.id is None:
        db.session.flush()

    existing = SettlementLine.query.filter_by(order_item_id=order_item.id).first()
    if existing:
        return existing

    values = calculate_line(
        restaurant_unit_price=restaurant_unit_price,
        customer_unit_price=customer_unit_price,
        quantity=getattr(order_item, "quantity", 1) or 1,
        commission_percent=commission_percent,
    )
    line = SettlementLine(
        order_id=order.id,
        order_item_id=order_item.id,
        restaurant_id=order.restaurant_id,
        **values,
    )
    db.session.add(line)
    db.session.flush()
    return line


def is_delivered(order):
    return str(getattr(order, "status", "") or "").strip().lower() == "delivered"


def is_online(order):
    value = str(getattr(order, "payment_type", "") or "").strip().lower()
    return value in {"online", "razorpay", "upi", "card", "netbanking"}


def online_payment_confirmed(order):
    # Adapt this set if your gateway writes a different canonical status.
    status = str(getattr(order, "payment_status", "") or "").strip().lower()
    verified = bool(getattr(order, "payment_verified", False))
    return verified or status in {"paid", "success", "successful", "completed", "captured"}


def order_collection_verified(order, CODCollection):
    if is_online(order):
        return online_payment_confirmed(order)
    cod = CODCollection.query.filter_by(order_id=order.id).first()
    if not cod:
        return False
    return cod.status == "reconciled" and money(cod.collected_amount) == money(cod.expected_amount)



def get_order_lines(order, SettlementLine):
    """Return settlement snapshots for an order."""
    return SettlementLine.query.filter_by(order_id=order.id).all()


def generate_weekly_drafts(db, Order, Restaurant, SettlementLine, RestaurantSettlement,
                           CODCollection, period_start, period_end):
    """
    Create or refresh draft settlements for the week.
    Period is inclusive. Only delivered, collected orders qualify.
    Drafts with assigned lines are not silently rewritten.
    """
    if period_end < period_start:
        raise ValueError("Week end cannot be before week start.")

    # Settlement period is based on delivery date, not order-placement date.
    # The existing model has delivered_time; updated_at is a fallback for older rows.
    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt_exclusive = datetime.combine(period_end + timedelta(days=1), datetime.min.time())
    orders = Order.query.all()

    eligible_by_restaurant = {}
    missing_by_restaurant = {}
    blocked_by_restaurant = {}

    for order in orders:
        rid = getattr(order, "restaurant_id", None)
        if not rid or not is_delivered(order):
            continue

        delivered_at = getattr(order, "delivered_time", None) or getattr(order, "updated_at", None)
        if delivered_at is None:
            # Do not silently guess which week a delivered order belongs to.
            missing_by_restaurant[rid] = missing_by_restaurant.get(rid, 0) + 1
            continue
        delivered_date = delivered_at.date() if hasattr(delivered_at, "date") else delivered_at
        if delivered_date < period_start or delivered_date > period_end:
            continue

        lines = get_order_lines(order, SettlementLine)
        if not lines:
            missing_by_restaurant[rid] = missing_by_restaurant.get(rid, 0) + 1
            continue

        if not order_collection_verified(order, CODCollection):
            blocked_by_restaurant[rid] = blocked_by_restaurant.get(rid, 0) + 1
            continue

        # A refresh must retain lines already attached to this same draft,
        # while never pulling lines from another settlement.
        draft_for_week = RestaurantSettlement.query.filter_by(
            restaurant_id=rid,
            period_start=period_start,
            period_end=period_end,
        ).first()
        if draft_for_week and draft_for_week.status != "draft":
            continue
        allowed_settlement_id = draft_for_week.id if draft_for_week else None
        unsettled = [
            line for line in lines
            if line.settlement_id is None or line.settlement_id == allowed_settlement_id
        ]
        if not unsettled:
            continue
        eligible_by_restaurant.setdefault(rid, []).append((order, unsettled))

    all_restaurant_ids = set(eligible_by_restaurant) | set(missing_by_restaurant) | set(blocked_by_restaurant)
    created_or_updated = []

    for rid in sorted(all_restaurant_ids):
        settlement = RestaurantSettlement.query.filter_by(
            restaurant_id=rid,
            period_start=period_start,
            period_end=period_end,
        ).first()

        if settlement and settlement.status != "draft":
            created_or_updated.append(settlement)
            continue

        if not settlement:
            settlement = RestaurantSettlement(
                restaurant_id=rid,
                period_start=period_start,
                period_end=period_end,
                status="draft",
            )
            db.session.add(settlement)
            db.session.flush()

        rows = eligible_by_restaurant.get(rid, [])
        lines = [line for order, order_lines in rows for line in order_lines]
        order_ids = {order.id for order, order_lines in rows}

        settlement.order_count = len(order_ids)
        settlement.food_gross = money(sum((money(x.restaurant_gross) for x in lines), Decimal("0")))
        settlement.customer_item_value = money(sum((money(x.customer_item_value) for x in lines), Decimal("0")))
        settlement.markup_total = money(sum((money(x.markup_amount) for x in lines), Decimal("0")))
        settlement.commission_total = money(sum((money(x.commission_amount) for x in lines), Decimal("0")))
        settlement.adjustment_total = Decimal("0.00")
        settlement.payout_total = money(settlement.food_gross - settlement.commission_total)
        settlement.missing_snapshot_count = missing_by_restaurant.get(rid, 0) + blocked_by_restaurant.get(rid, 0)

        for line in lines:
            line.settlement_id = settlement.id

        if settlement.missing_snapshot_count:
            settlement.notes = (
                f"Review required: {missing_by_restaurant.get(rid, 0)} delivered order(s) missing original-price snapshots; "
                f"{blocked_by_restaurant.get(rid, 0)} order(s) have unverified collection. "
                "Resolve before approval."
            )
        else:
            settlement.notes = "Draft generated. Review totals and payment reconciliation before approval."

        created_or_updated.append(settlement)

    db.session.commit()
    return created_or_updated




def approve_settlement(db, RestaurantSettlement, settlement_id, admin_name=None):
    from sqlalchemy import select

    table = RestaurantSettlement.__table__

    # Lock only the settlement table row. No ORM relationships are joined.
    locked_id = db.session.execute(
        select(table.c.id)
        .where(table.c.id == settlement_id)
        .with_for_update()
    ).scalar_one_or_none()

    if locked_id is None:
        raise ValueError("Settlement not found.")

    # Load the ORM object separately; this query does not request a row lock.
    settlement = RestaurantSettlement.query.filter_by(id=locked_id).first()

    if not settlement:
        raise ValueError("Settlement not found.")

    if settlement.status != "draft":
        raise ValueError("Only draft settlements can be approved.")

    if settlement.missing_snapshot_count:
        raise ValueError(
            "Cannot approve: missing price snapshots or unverified payment collections must be resolved."
        )

    if settlement.payout_total < 0:
        raise ValueError("Cannot approve a negative payout.")

    settlement.status = "approved"
    settlement.approved_at = datetime.utcnow()
    settlement.approved_by = (admin_name or "admin")[:120]

    db.session.commit()
    return settlement

def record_payout(
    db,
    RestaurantSettlement,
    SettlementPayout,
    settlement_id,
    amount,
    payment_reference,
    paid_on,
    payment_method="bank_transfer",
    notes=None,
    recorded_by=None,
):
    from sqlalchemy import select
    from datetime import datetime

    # Lock only the settlement table row; avoid ORM relationship joins.
    table = RestaurantSettlement.__table__

    locked_id = db.session.execute(
        select(table.c.id)
        .where(table.c.id == settlement_id)
        .with_for_update()
    ).scalar_one_or_none()

    if locked_id is None:
        raise ValueError("Settlement not found.")

    # Load the ORM object separately, without requesting a row lock.
    settlement = (
        RestaurantSettlement.query
        .filter_by(id=locked_id)
        .first()
    )

    if not settlement:
        raise ValueError("Settlement not found.")

    if settlement.status != "approved":
        raise ValueError("Only approved settlements can be marked paid.")

    # Prevent duplicate payout records.
    if SettlementPayout.query.filter_by(
        settlement_id=settlement.id
    ).first():
        raise ValueError("A payout is already recorded for this settlement.")

    amount = money(amount)

    if amount != money(settlement.payout_total):
        raise ValueError(
            f"Payout amount must match approved total ₹{money(settlement.payout_total)}."
        )

    reference = str(payment_reference or "").strip()
    if not reference:
        raise ValueError("Payment reference/UTR is required.")

    payout = SettlementPayout(
        settlement_id=settlement.id,
        amount=amount,
        payment_reference=reference[:160],
        paid_on=paid_on,
        payment_method=(payment_method or "bank_transfer")[:40],
        notes=notes,
        recorded_by=(recorded_by or "admin")[:120],
    )

    db.session.add(payout)
    settlement.status = "paid"
    settlement.paid_at = datetime.utcnow()

    db.session.commit()
    return payout


def reconcile_cod(db, Order, CODCollection, order_id, collected_amount,
                  expected_amount=None, collected_by="rider", handover_reference=None,
                  notes=None, reconciled_by=None):
    order = Order.query.filter_by(id=order_id).with_for_update().first()
    if not order:
        raise ValueError("Order not found.")
    if not is_delivered(order):
        raise ValueError("COD can only be reconciled after the order is delivered.")
    if is_online(order):
        raise ValueError("This is an online-payment order, not COD.")
    if expected_amount is None:
        computed_total = order.get_final_total() if hasattr(order, "get_final_total") else getattr(order, "final_total", 0)
        expected = money(computed_total)
    else:
        expected = money(expected_amount)
    collected = money(collected_amount)
    status = "reconciled" if collected == expected else ("short" if collected < expected else "over")
    existing = CODCollection.query.filter_by(order_id=order.id).first()
    if existing:
        if existing.status == "reconciled":
            raise ValueError("COD is already reconciled. Use an audited adjustment workflow to change it.")
        existing.expected_amount = expected
        existing.collected_amount = collected
        existing.collected_by = collected_by
        existing.handover_reference = handover_reference
        existing.notes = notes
        existing.reconciled_by = reconciled_by
        existing.reconciled_at = datetime.utcnow()
        existing.status = status
        record = existing
    else:
        record = CODCollection(
            order_id=order.id,
            expected_amount=expected,
            collected_amount=collected,
            collected_by=collected_by,
            handover_reference=handover_reference,
            notes=notes,
            reconciled_by=reconciled_by,
            status=status,
        )
        db.session.add(record)
    db.session.commit()
    return record
