from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


CENT = Decimal("0.01")

ONLINE_TYPES = {
    "online",
    "razorpay",
    "upi",
    "card",
    "netbanking",
}


def money(value):
    return Decimal(
        str(value if value is not None else "0")
    ).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def _delivered(order):
    return (
        str(getattr(order, "status", "") or "")
        .strip()
        .lower()
        == "delivered"
    )


def _online(order):
    return (
        str(getattr(order, "payment_type", "") or "")
        .strip()
        .lower()
        in ONLINE_TYPES
    )


def _date(order):
    stamp = (
        getattr(order, "delivered_time", None)
        or getattr(order, "updated_at", None)
    )

    if stamp is None:
        return None

    return stamp.date() if hasattr(stamp, "date") else stamp


def _total(order):
    get_total = getattr(order, "get_final_total", None)

    value = (
        get_total()
        if callable(get_total)
        else getattr(order, "final_total", 0)
    )

    return money(value)


def create_handover_batch(
    db,
    Order,
    CODCollection,
    CODHandoverBatch,
    CODHandoverBatchItem,
    rider_id,
    business_date,
    admin_name,
):
    """
    Create a draft handover batch for all eligible delivered COD
    orders belonging to the selected rider and business date.

    Creating a draft reserves orders. It does not reconcile COD.
    """

    if not rider_id:
        raise ValueError("Select a rider.")

    orders = (
        Order.query
        .filter_by(delivery_person_id=int(rider_id))
        .order_by(Order.id)
        .all()
    )

    eligible = []

    for order in orders:
        if not _delivered(order):
            continue

        if _online(order):
            continue

        if _date(order) != business_date:
            continue

        cod = CODCollection.query.filter_by(
            order_id=order.id
        ).first()

        if (
            cod
            and str(cod.status or "").lower()
            == "reconciled"
        ):
            continue

        active = (
            CODHandoverBatchItem.query
            .filter_by(order_id=order.id)
            .filter(
                CODHandoverBatchItem.released_at.is_(None)
            )
            .first()
        )

        if active:
            continue

        amount = _total(order)

        if amount < 0:
            raise ValueError(
                f"Order {order.id} has a negative total."
            )

        eligible.append((order, amount))

    if not eligible:
        raise ValueError(
            "No eligible delivered COD orders found "
            "for this rider/date."
        )

    total = money(
        sum(
            (amount for _, amount in eligible),
            Decimal("0.00"),
        )
    )

    batch = CODHandoverBatch(
        rider_id=int(rider_id),
        business_date=business_date,
        expected_total=total,
        status="draft",
        created_by=(admin_name or "admin")[:120],
    )

    try:
        db.session.add(batch)
        db.session.flush()

        for order, amount in eligible:
            db.session.add(
                CODHandoverBatchItem(
                    batch_id=batch.id,
                    order_id=order.id,
                    expected_amount=amount,
                )
            )

        db.session.commit()

    except IntegrityError:
        db.session.rollback()

        raise ValueError(
            "An order was batched concurrently or is already "
            "in an active batch. Reload and try again."
        )

    return batch


def receive_handover_batch(
    db,
    Order,
    CODCollection,
    CODCollectionAudit,
    CODHandoverBatch,
    CODHandoverBatchItem,
    batch_id,
    received_amount,
    handover_reference,
    notes,
    admin_name,
    rider_attested_full_collection=False,
):
    """
    Record the physical rider handover.

    Exact amount:
        Requires rider attestation, revalidates every order,
        reconciles individual CODCollection records and writes
        CODCollectionAudit records.

    Short or over amount:
        Records the exception on the batch without reconciling
        individual orders.
    """

    table = CODHandoverBatch.__table__

    locked_id = db.session.execute(
        select(table.c.id)
        .where(table.c.id == batch_id)
        .with_for_update()
    ).scalar_one_or_none()

    if locked_id is None:
        raise ValueError("Batch not found.")

    batch = CODHandoverBatch.query.filter_by(
        id=locked_id
    ).first()

    if batch.status != "draft":
        raise ValueError(
            "Only a draft batch can receive a handover."
        )

    received = money(received_amount)

    if received < 0:
        raise ValueError(
            "Received amount cannot be negative."
        )

    reference = str(
        handover_reference or ""
    ).strip()

    if not reference:
        raise ValueError(
            "Handover reference is required."
        )

    items = CODHandoverBatchItem.query.filter_by(
        batch_id=batch.id
    ).all()

    if not items:
        raise ValueError(
            "This batch has no orders; it cannot be received."
        )

    expected = money(batch.expected_total)
    difference = money(received - expected)

    # Store the receipt attempt.
    batch.received_amount = received
    batch.difference_amount = difference
    batch.handover_reference = reference[:160]
    batch.notes = (notes or "").strip() or None
    batch.received_by = (admin_name or "admin")[:120]
    batch.received_at = datetime.utcnow()

    if difference < 0:
        # Short batch: record an exception only.
        batch.status = "short"

    elif difference > 0:
        # Over batch: record an exception only.
        batch.status = "over"

    else:
        # Exact amount: rider must attest to full collection.
        if not rider_attested_full_collection:
            raise ValueError(
                "Confirm the rider attested that the full "
                "amount was collected for every order."
            )

        # Revalidate all orders before reconciling.
        # The batch may have become stale since it was created.
        for item in items:
            order = (
                Order.query
                .filter_by(id=item.order_id)
                .with_for_update()
                .first()
            )

            if not order:
                raise ValueError(
                    f"Order {item.order_id} no longer exists."
                )

            if not _delivered(order) or _online(order):
                raise ValueError(
                    f"Order {item.order_id} is no longer an "
                    "eligible delivered COD order."
                )

            assigned_rider = int(
                getattr(order, "delivery_person_id", 0) or 0
            )

            if assigned_rider != int(batch.rider_id):
                raise ValueError(
                    f"Order {item.order_id} is no longer "
                    "assigned to this rider."
                )

            if _date(order) != batch.business_date:
                raise ValueError(
                    f"Order {item.order_id} does not match "
                    "the batch business date."
                )

            if item.released_at is not None:
                raise ValueError(
                    f"Order {item.order_id} was released "
                    "from this batch."
                )

            existing = CODCollection.query.filter_by(
                order_id=item.order_id
            ).first()

            if (
                existing
                and str(existing.status or "").lower()
                == "reconciled"
            ):
                raise ValueError(
                    f"Order {item.order_id} is already "
                    "reconciled."
                )

        # All checks passed; reconcile every order.
        batch.status = "reconciled"

        for item in items:
            item_amount = money(item.expected_amount)

            existing = CODCollection.query.filter_by(
                order_id=item.order_id
            ).first()

            # Record audit history before updating the collection.
            db.session.add(
                CODCollectionAudit(
                    order_id=item.order_id,
                    batch_id=batch.id,
                    previous_status=(
                        existing.status if existing else None
                    ),
                    previous_expected_amount=(
                        money(existing.expected_amount)
                        if existing
                        else None
                    ),
                    previous_collected_amount=(
                        money(existing.collected_amount)
                        if existing
                        else None
                    ),
                    previous_reference=(
                        existing.handover_reference
                        if existing
                        else None
                    ),
                    new_status="reconciled",
                    changed_by=(admin_name or "admin")[:120],
                    reason=(
                        f"Exact handover batch #{batch.id}; "
                        "rider full-collection attestation; "
                        f"reference {reference}."
                    ),
                )
            )

            if existing:
                existing.expected_amount = item_amount
                existing.collected_amount = item_amount
                existing.collected_by = "rider"
                existing.handover_reference = reference[:160]
                existing.notes = (
                    f"Recorded via COD handover batch #{batch.id}."
                )
                existing.reconciled_by = (
                    admin_name or "admin"
                )[:120]
                existing.reconciled_at = datetime.utcnow()
                existing.status = "reconciled"

            else:
                db.session.add(
                    CODCollection(
                        order_id=item.order_id,
                        expected_amount=item_amount,
                        collected_amount=item_amount,
                        collected_by="rider",
                        handover_reference=reference[:160],
                        notes=(
                            f"Recorded via COD handover "
                            f"batch #{batch.id}."
                        ),
                        reconciled_by=(
                            admin_name or "admin"
                        )[:120],
                        reconciled_at=datetime.utcnow(),
                        status="reconciled",
                    )
                )

    db.session.commit()

    return batch


def cancel_draft_batch(
    db,
    CODHandoverBatch,
    CODHandoverBatchItem,
    batch_id,
):
    """
    Cancel a draft only.

    The batch history remains in the database, while its items
    are released so eligible orders can be included in another
    batch.
    """

    table = CODHandoverBatch.__table__

    locked_id = db.session.execute(
        select(table.c.id)
        .where(table.c.id == batch_id)
        .with_for_update()
    ).scalar_one_or_none()

    if locked_id is None:
        raise ValueError("Batch not found.")

    batch = CODHandoverBatch.query.filter_by(
        id=locked_id
    ).first()

    if batch.status != "draft":
        raise ValueError(
            "Only a draft batch can be cancelled."
        )

    now = datetime.utcnow()

    items = CODHandoverBatchItem.query.filter_by(
        batch_id=batch.id
    ).all()

    for item in items:
        item.released_at = now

    batch.status = "cancelled"

    batch.notes = (
        (batch.notes or "")
        + f" Cancelled {now.isoformat()}"
    ).strip()

    db.session.commit()

    return batch