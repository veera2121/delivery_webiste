from math import radians, sin, cos, sqrt, atan2
from datetime import datetime, timedelta

from flask import current_app

from models import (
    db,
    Order,
    DeliveryPerson,
    DeliverySettings,
    DeliveryAssignmentAttempt,
)

from notification_service import (
    send_new_order_notification
)


# ==========================================================
# CONSTANTS
# ==========================================================

ASSIGNMENT_TIMEOUT_SECONDS = 30

# Previous Reject/Expired attempts are tracked per order+rider in the DB.
# This prevents the same rider receiving the same order again.

# ----------------------------------------------------------
# Route batching
# ----------------------------------------------------------

MAX_BATCH_ORDERS = 2

MAX_BATCH_DESTINATION_DISTANCE_KM = 1.5

BATCHABLE_RIDER_ORDER_STATUSES = [
    "Out for Delivery",
    "Picked Up",
    "Started",
]

ACTIVE_RIDER_ORDER_STATUSES = [
    "Assignment Pending",
    "Out for Delivery",
    "Picked Up",
    "Started",
]


# ==========================================================
# STATUS CONSTANTS
# ==========================================================

ASSIGNMENT_PENDING_STATUS = "Assignment Pending"

OUT_FOR_DELIVERY_STATUS = "Out for Delivery"

READY_STATUS = "Ready"

RIDER_PENDING_RESPONSE = "Pending"

RIDER_ACCEPTED_RESPONSE = "Accepted"

RIDER_REJECTED_RESPONSE = "Rejected"

RIDER_EXPIRED_RESPONSE = "Expired"

# Terminal outcomes that exclude a rider from future attempts on this order.
TERMINAL_ATTEMPT_STATUSES = {
    RIDER_REJECTED_RESPONSE,
    RIDER_EXPIRED_RESPONSE,
}


# ==========================================================
# PERSISTENT ORDER/RIDER ASSIGNMENT HISTORY
# ==========================================================

def _attempts_for_order(order_id):
    return DeliveryAssignmentAttempt.query.filter_by(order_id=order_id)


def _terminal_attempt_for_rider(order_id, rider_id):
    """Return a prior rejected/expired attempt for this exact rider/order."""
    return (
        _attempts_for_order(order_id)
        .filter(
            DeliveryAssignmentAttempt.rider_id == rider_id,
            DeliveryAssignmentAttempt.status.in_(TERMINAL_ATTEMPT_STATUSES),
        )
        .order_by(DeliveryAssignmentAttempt.id.desc())
        .first()
    )


def attempted_rider_ids_for_order(order_id):
    """Riders who already rejected or timed out on this order."""
    rows = (
        _attempts_for_order(order_id)
        .filter(DeliveryAssignmentAttempt.status.in_(TERMINAL_ATTEMPT_STATUSES))
        .with_entities(DeliveryAssignmentAttempt.rider_id)
        .distinct()
        .all()
    )
    return {row[0] for row in rows if row[0] is not None}


def _sync_legacy_terminal_outcome(order):
    """Backfill history if a legacy reject/expiry route cleared the rider ID.

    The currently deployed reject route sets order.rider_response and clears
    delivery_person_id. The assignment row retains the rider ID, so use the
    latest still-pending attempt to reconcile it to Rejected/Expired.
    """
    if not order or order.delivery_person_id is not None:
        return

    outcome = (getattr(order, "rider_response", None) or "").strip()
    if outcome not in TERMINAL_ATTEMPT_STATUSES:
        return

    attempt = (
        _attempts_for_order(order.id)
        .filter(DeliveryAssignmentAttempt.status == RIDER_PENDING_RESPONSE)
        .order_by(DeliveryAssignmentAttempt.id.desc())
        .first()
    )
    if attempt:
        attempt.status = outcome
        attempt.resolved_at = (
            getattr(order, "rejected_at", None) or datetime.utcnow()
        )
        db.session.flush()
        print(
            f"🧾 HISTORY RECONCILED: order={order.id} "
            f"rider={attempt.rider_id} outcome={outcome}"
        )


def record_assignment_attempt(order, rider, now=None):
    """Create a Pending history row for a newly offered assignment.

    Returns False if this rider has already rejected/timed out on the order,
    or if a duplicate pending offer already exists for this order/rider.
    Caller commits the order and history in the same transaction.
    """
    if not order or not rider:
        return False

    _sync_legacy_terminal_outcome(order)

    terminal = _terminal_attempt_for_rider(order.id, rider.id)
    if terminal:
        print(
            f"⛔ ASSIGNMENT HISTORY BLOCK: order={order.order_id} "
            f"rider={rider.id} previous outcome={terminal.status}"
        )
        return False

    pending = (
        _attempts_for_order(order.id)
        .filter(
            DeliveryAssignmentAttempt.rider_id == rider.id,
            DeliveryAssignmentAttempt.status == RIDER_PENDING_RESPONSE,
        )
        .order_by(DeliveryAssignmentAttempt.id.desc())
        .first()
    )
    if pending:
        print(
            f"⛔ DUPLICATE OFFER BLOCK: order={order.order_id} "
            f"rider={rider.id} already has a pending attempt"
        )
        return False

    now = now or datetime.utcnow()
    attempt = DeliveryAssignmentAttempt(
        order_id=order.id,
        rider_id=rider.id,
        status=RIDER_PENDING_RESPONSE,
        assigned_at=now,
        expires_at=getattr(order, "assignment_expires_at", None),
        resolved_at=None,
    )
    db.session.add(attempt)
    db.session.flush()
    return True


def record_assignment_outcome(order_id, rider_id, status, resolved_at=None):
    """Record Rejected/Expired/Accepted for a rider/order from a Flask route.

    Call this before clearing order.delivery_person_id in the accept/reject
    route. It intentionally does not commit; the route's transaction commits.
    """
    status = (status or "").strip().title()
    allowed = {RIDER_PENDING_RESPONSE, RIDER_REJECTED_RESPONSE,
               RIDER_EXPIRED_RESPONSE, RIDER_ACCEPTED_RESPONSE}
    if status not in allowed:
        raise ValueError(f"Unsupported assignment outcome: {status}")

    attempt = (
        _attempts_for_order(order_id)
        .filter(
            DeliveryAssignmentAttempt.rider_id == rider_id,
            DeliveryAssignmentAttempt.status == RIDER_PENDING_RESPONSE,
        )
        .order_by(DeliveryAssignmentAttempt.id.desc())
        .first()
    )

    now = resolved_at or datetime.utcnow()
    if attempt is None:
        # Fallback for assignments made before history rows were introduced.
        attempt = DeliveryAssignmentAttempt(
            order_id=order_id,
            rider_id=rider_id,
            status=status,
            assigned_at=now,
            resolved_at=now if status != RIDER_PENDING_RESPONSE else None,
        )
        db.session.add(attempt)
    else:
        attempt.status = status
        attempt.resolved_at = now if status != RIDER_PENDING_RESPONSE else None

    db.session.flush()
    return attempt


# ==========================================================
# DISTANCE
# ==========================================================

def haversine(
    lat1,
    lon1,
    lat2,
    lon2
):
    """
    Returns distance between two GPS points in KM.
    """

    R = 6371.0

    lat1 = radians(float(lat1))
    lon1 = radians(float(lon1))

    lat2 = radians(float(lat2))
    lon2 = radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

    return R * c


def calculate_distance_km(
    latitude_1,
    longitude_1,
    latitude_2,
    longitude_2
):
    return haversine(
        latitude_1,
        longitude_1,
        latitude_2,
        longitude_2
    )


# ==========================================================
# RIDER ACTIVE ORDER CHECK
# ==========================================================

def rider_has_active_order(
    rider_id,
    exclude_order_id=None
):
    """
    Returns any unresolved assignment or active delivery.
    """

    query = Order.query.filter(
        Order.delivery_person_id == rider_id,
        Order.status.in_(
            ACTIVE_RIDER_ORDER_STATUSES
        )
    )

    if exclude_order_id is not None:

        query = query.filter(
            Order.id != exclude_order_id
        )

    return query.first()


# ==========================================================
# GET ALL ACTIVE ORDERS FOR RIDER
# ==========================================================

def get_active_orders_for_rider(
    rider_id
):
    """
    Returns active orders for a rider.
    """

    return (
        Order.query
        .filter(
            Order.delivery_person_id == rider_id,
            Order.status.in_(
                ACTIVE_RIDER_ORDER_STATUSES
            )
        )
        .order_by(
            Order.id.asc()
        )
        .all()
    )


# ==========================================================
# FIND NEAREST RIDER EXCLUDING RIDERS
# ==========================================================

def find_nearest_rider_excluding(
    order,
    excluded_rider_ids=None
):
    excluded_rider_ids = set(
        excluded_rider_ids or []
    )

    settings = DeliverySettings.query.first()

    if not settings:
        return None

    if not settings.auto_assign_enabled:
        return None

    restaurant = getattr(
        order,
        "restaurant",
        None
    )

    if not restaurant:
        return None

    if (
        restaurant.latitude is None
        or restaurant.longitude is None
    ):
        return None

    radius = float(
        settings.rider_search_radius
        or 5
    )

    query = DeliveryPerson.query.filter(
        DeliveryPerson.is_active.is_(True),
        DeliveryPerson.is_online.is_(True),
        DeliveryPerson.is_available.is_(True),
        DeliveryPerson.latitude.isnot(None),
        DeliveryPerson.longitude.isnot(None)
    )

    if excluded_rider_ids:

        query = query.filter(
            ~DeliveryPerson.id.in_(
                excluded_rider_ids
            )
        )

    riders = query.all()

    candidates = []

    for rider in riders:

        # --------------------------------------------------
        # Normal assignment NEVER allows second order
        # --------------------------------------------------

        active_order = rider_has_active_order(
            rider.id
        )

        if active_order:

            print(
                f"⛔ Rider {rider.id} "
                f"already has order "
                f"{active_order.order_id}"
            )

            continue

        distance = haversine(
            restaurant.latitude,
            restaurant.longitude,
            rider.latitude,
            rider.longitude
        )

        if distance > radius:
            continue

        candidates.append({
            "rider": rider,
            "distance": distance
        })

    if not candidates:
        return None

    candidates.sort(
        key=lambda candidate: (
            candidate["distance"],
            candidate["rider"].last_assignment
            or datetime.min,
            candidate["rider"].id
        )
    )

    return candidates[0]["rider"]


# ==========================================================
# FIND AVAILABLE RIDERS
# ==========================================================

def find_available_riders():

    riders = DeliveryPerson.query.filter(
        DeliveryPerson.is_active.is_(True),
        DeliveryPerson.is_online.is_(True),
        DeliveryPerson.is_available.is_(True)
    ).all()

    valid_riders = []

    for rider in riders:

        active_order = rider_has_active_order(
            rider.id
        )

        if active_order:

            if rider.is_available:
                rider.is_available = False

            print(
                f"⛔ Rider {rider.id} "
                f"has active order "
                f"{active_order.order_id}"
            )

            continue

        valid_riders.append(
            rider
        )

    db.session.commit()

    print(
        "Matched available riders:",
        len(valid_riders)
    )

    return valid_riders


# ==========================================================
# FIND NEAREST RIDER
# ==========================================================

def find_nearest_rider(order):
    """Find the nearest eligible rider who has not rejected/timed out on this order."""
    if not order:
        return None
    _sync_legacy_terminal_outcome(order)
    excluded_rider_ids = attempted_rider_ids_for_order(order.id)
    return find_nearest_rider_excluding(
        order,
        excluded_rider_ids=excluded_rider_ids,
    )


# ==========================================================
# ROUTE BATCHING
# ==========================================================

def find_route_batch_rider(order, excluded_rider_ids=None):
    """
    Find a rider who is already delivering one order and
    whose current delivery destination is close to the
    new order's destination.

    IMPORTANT:
    This function does NOT use rider.is_available because
    an active rider is intentionally unavailable for normal
    assignment.

    Batch rules:

        1. New order must be Ready.
        2. New order must not already be assigned.
        3. Rider must be active.
        4. Rider must be online.
        5. Rider must have exactly one active delivery.
        6. Active delivery must be accepted/ongoing.
        7. New destination must be <= 1.5 KM from current
           delivery destination.
        8. Maximum batch size = 2.
    """

    if not order:
        return None

    if order.status != READY_STATUS:

        print(
            f"⛔ BATCH: Order "
            f"{getattr(order, 'order_id', None)} "
            f"is not Ready."
        )

        return None

    if order.delivery_person_id is not None:
        return None

    if (
        order.latitude is None
        or order.longitude is None
    ):

        print(
            f"⛔ BATCH: Order "
            f"{order.order_id} "
            f"has no customer coordinates."
        )

        return None

    excluded_rider_ids = set(excluded_rider_ids or [])

    riders_query = DeliveryPerson.query.filter(
        DeliveryPerson.is_active.is_(True),
        DeliveryPerson.is_online.is_(True),
    )
    if excluded_rider_ids:
        riders_query = riders_query.filter(
            ~DeliveryPerson.id.in_(excluded_rider_ids)
        )
    riders = riders_query.all()

    best_rider = None
    best_distance = float("inf")

    for rider in riders:

        # --------------------------------------------------
        # Get currently active orders
        # --------------------------------------------------

        active_orders = (
            Order.query
            .filter(
                Order.delivery_person_id == rider.id,
                Order.status.in_(
                    BATCHABLE_RIDER_ORDER_STATUSES
                )
            )
            .order_by(
                Order.id.asc()
            )
            .all()
        )

        # --------------------------------------------------
        # Rider must already be carrying exactly one order
        # --------------------------------------------------

        if len(active_orders) != 1:

            if len(active_orders) >= MAX_BATCH_ORDERS:

                print(
                    f"⛔ BATCH: Rider {rider.id} "
                    f"already has {len(active_orders)} "
                    f"active orders."
                )

            continue

        current_order = active_orders[0]

        # --------------------------------------------------
        # Current destination coordinates
        # --------------------------------------------------

        if (
            current_order.latitude is None
            or current_order.longitude is None
        ):

            print(
                f"⚠️ BATCH: Current order "
                f"{current_order.order_id} "
                f"has no destination coordinates."
            )

            continue

        # --------------------------------------------------
        # New destination vs current destination
        # --------------------------------------------------

        distance = calculate_distance_km(
            current_order.latitude,
            current_order.longitude,
            order.latitude,
            order.longitude
        )

        print(
            f"📦 BATCH CHECK | "
            f"New: {order.order_id} | "
            f"Rider: {rider.id} {rider.name} | "
            f"Current: {current_order.order_id} | "
            f"Destination distance: "
            f"{distance:.2f} KM"
        )

        # --------------------------------------------------
        # Distance condition
        # --------------------------------------------------

        if distance > MAX_BATCH_DESTINATION_DISTANCE_KM:

            print(
                f"❌ BATCH REJECTED | "
                f"Rider {rider.id} | "
                f"{distance:.2f} KM > "
                f"{MAX_BATCH_DESTINATION_DISTANCE_KM} KM"
            )

            continue

        # --------------------------------------------------
        # Best candidate
        # --------------------------------------------------

        if distance < best_distance:

            best_distance = distance

            best_rider = rider

    if best_rider:

        print(
            "========================================"
        )

        print(
            "✅ ROUTE BATCH RIDER FOUND"
        )

        print(
            "Rider:",
            best_rider.id,
            best_rider.name
        )

        print(
            "Destination distance:",
            round(best_distance, 2),
            "KM"
        )

        print(
            "========================================"
        )

    else:

        print(
            f"ℹ️ No route batch rider "
            f"found for {order.order_id}"
        )

    return best_rider


# ==========================================================
# ASSIGN NORMAL ORDER
# ==========================================================

def assign_delivery_to_order(
    order,
    rider
):

    if not order or not rider:
        return False

    # ======================================================
    # ORDER MUST BE AVAILABLE
    # ======================================================

    if order.delivery_person_id is not None:

        print(
            f"⛔ Order {order.order_id} "
            f"already assigned."
        )

        return False

    if order.status != READY_STATUS:

        print(
            f"⛔ Order {order.order_id} "
            f"is not Ready."
        )

        return False

    _sync_legacy_terminal_outcome(order)
    if _terminal_attempt_for_rider(order.id, rider.id):
        print(
            f"⛔ BLOCKED REPEAT RIDER: order={order.order_id} "
            f"rider={rider.id} already rejected/expired this order."
        )
        return False

    # ======================================================
    # RIDER VALIDATION
    # ======================================================

    if not rider.is_active:
        return False

    if not rider.is_online:
        return False

    if not rider.is_available:
        return False

    # ======================================================
    # CRITICAL NORMAL ASSIGNMENT PROTECTION
    # ======================================================

    active_order = rider_has_active_order(
        rider.id
    )

    if active_order:

        print(
            f"⛔ BLOCKED SECOND ORDER: "
            f"Rider {rider.id} already has "
            f"{active_order.order_id}"
        )

        rider.is_available = False

        db.session.commit()

        return False

    # ======================================================
    # ASSIGN
    # ======================================================

    try:

        now = datetime.utcnow()

        order.delivery_person_id = rider.id

        order.delivery_boy_name = (
            rider.name
        )

        order.delivery_boy_phone = (
            rider.phone
        )

        order.status = (
            ASSIGNMENT_PENDING_STATUS
        )

        order.rider_response = (
            RIDER_PENDING_RESPONSE
        )

        order.assigned_at = now

        order.assignment_expires_at = (
            now
            + timedelta(
                seconds=
                    ASSIGNMENT_TIMEOUT_SECONDS
            )
        )

        order.accepted_at = None

        order.rejected_at = None

        # --------------------------------------------------
        # Lock rider
        # --------------------------------------------------

        rider.is_available = False

        rider.last_assignment = now

        # Persist assignment history atomically with the order assignment.
        if not record_assignment_attempt(order, rider, now=now):
            db.session.rollback()
            return False

        db.session.commit()

        print(
            "========================================"
        )

        print(
            "✅ ORDER ASSIGNED"
        )

        print(
            "Order:",
            order.order_id
        )

        print(
            "Rider:",
            rider.id,
            rider.name
        )

        print(
            "Timeout:",
            ASSIGNMENT_TIMEOUT_SECONDS,
            "seconds"
        )

        print(
            "Expires:",
            order.assignment_expires_at
        )

        print(
            "========================================"
        )

        # ==================================================
        # SEND NOTIFICATION
        # ==================================================

        try:

            notification_sent = (
                send_new_order_notification(
                    rider,
                    order
                )
            )

            if not notification_sent:

                current_app.logger.warning(
                    "Order %s assigned to rider %s "
                    "but FCM notification was not sent.",
                    order.order_id,
                    rider.id
                )

        except Exception:

            current_app.logger.exception(
                "Order %s assigned to rider %s "
                "but notification failed.",
                order.order_id,
                rider.id
            )

        return True

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Failed to assign order %s "
            "to rider %s.",
            getattr(
                order,
                "order_id",
                None
            ),
            getattr(
                rider,
                "id",
                None
            )
        )

        return False


# ==========================================================
# ASSIGN BATCH ORDER
# ==========================================================

def assign_batch_order_to_rider(
    order,
    rider
):
    """
    Controlled second-order assignment.

    This does NOT automatically accept the order.

    The order is placed into:

        Assignment Pending
        rider_response = Pending

    The rider must still Accept / Reject.

    IMPORTANT:
    Rider remains unavailable during this 30-second
    batch decision window.
    """

    if not order or not rider:
        return False

    # ======================================================
    # NEW ORDER VALIDATION
    # ======================================================

    if order.status != READY_STATUS:

        print(
            f"⛔ BATCH ASSIGN BLOCKED: "
            f"{order.order_id} is not Ready."
        )

        return False

    if order.delivery_person_id is not None:

        print(
            f"⛔ BATCH ASSIGN BLOCKED: "
            f"{order.order_id} already assigned."
        )

        return False

    _sync_legacy_terminal_outcome(order)
    if _terminal_attempt_for_rider(order.id, rider.id):
        print(
            f"⛔ BATCH HISTORY BLOCK: order={order.order_id} "
            f"rider={rider.id} already rejected/expired this order."
        )
        return False

    # ======================================================
    # RIDER VALIDATION
    # ======================================================

    if not rider.is_active:
        return False

    if not rider.is_online:
        return False

    # ======================================================
    # ACTIVE ORDERS
    # ======================================================

    active_orders = (
        Order.query
        .filter(
            Order.delivery_person_id == rider.id,
            Order.status.in_(
                BATCHABLE_RIDER_ORDER_STATUSES
            )
        )
        .order_by(
            Order.id.asc()
        )
        .all()
    )

    # Must have exactly one current delivery.
    if len(active_orders) != 1:

        print(
            f"⛔ BATCH ASSIGN BLOCKED: "
            f"Rider {rider.id} has "
            f"{len(active_orders)} active orders."
        )

        return False

    current_order = active_orders[0]

    # ======================================================
    # COORDINATES
    # ======================================================

    if (
        current_order.latitude is None
        or current_order.longitude is None
        or order.latitude is None
        or order.longitude is None
    ):

        print(
            "⛔ BATCH ASSIGN BLOCKED: "
            "Missing destination coordinates."
        )

        return False

    # ======================================================
    # DESTINATION DISTANCE
    # ======================================================

    distance = calculate_distance_km(
        current_order.latitude,
        current_order.longitude,
        order.latitude,
        order.longitude
    )

    if distance > MAX_BATCH_DESTINATION_DISTANCE_KM:

        print(
            f"⛔ BATCH ASSIGN BLOCKED: "
            f"{distance:.2f} KM > "
            f"{MAX_BATCH_DESTINATION_DISTANCE_KM} KM"
        )

        return False

    # ======================================================
    # ASSIGN
    # ======================================================

    try:

        now = datetime.utcnow()

        order.delivery_person_id = rider.id

        order.delivery_boy_name = (
            rider.name
        )

        order.delivery_boy_phone = (
            rider.phone
        )

        # --------------------------------------------------
        # IMPORTANT:
        # Rider must still accept this second order.
        # --------------------------------------------------

        order.status = (
            ASSIGNMENT_PENDING_STATUS
        )

        order.rider_response = (
            RIDER_PENDING_RESPONSE
        )

        order.assigned_at = now

        order.assignment_expires_at = (
            now
            + timedelta(
                seconds=
                    ASSIGNMENT_TIMEOUT_SECONDS
            )
        )

        order.accepted_at = None

        order.rejected_at = None

        # --------------------------------------------------
        # Rider remains unavailable.
        # --------------------------------------------------

        rider.is_available = False

        rider.last_assignment = now

        if not record_assignment_attempt(order, rider, now=now):
            db.session.rollback()
            return False

        db.session.commit()

        print(
            "========================================"
        )

        print(
            "🚚 ROUTE BATCH ORDER ASSIGNED"
        )

        print(
            "NEW ORDER:",
            order.order_id
        )

        print(
            "CURRENT ORDER:",
            current_order.order_id
        )

        print(
            "RIDER:",
            rider.id,
            rider.name
        )

        print(
            "DESTINATION DISTANCE:",
            round(distance, 2),
            "KM"
        )

        print(
            "TIMEOUT:",
            ASSIGNMENT_TIMEOUT_SECONDS,
            "seconds"
        )

        print(
            "EXPIRES:",
            order.assignment_expires_at
        )

        print(
            "========================================"
        )

        # ==================================================
        # SEND NOTIFICATION
        # ==================================================

        try:

            notification_sent = (
                send_new_order_notification(
                    rider,
                    order
                )
            )

            if not notification_sent:

                current_app.logger.warning(
                    "Batch order %s assigned to rider %s "
                    "but notification was not sent.",
                    order.order_id,
                    rider.id
                )

        except Exception:

            current_app.logger.exception(
                "Batch order %s notification failed.",
                order.order_id
            )

        return True

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Failed to batch assign order %s "
            "to rider %s.",
            getattr(
                order,
                "order_id",
                None
            ),
            getattr(
                rider,
                "id",
                None
            )
        )

        return False


# ==========================================================
# AUTO ASSIGN ORDER
# ==========================================================

def auto_assign_order(order):
    # Clean expired assignments and persist their rider history first.
    cleanup_all_expired_assignments()

    if not order:
        return False

    if order.delivery_person_id is not None:

        print(
            f"⚠️ Order already assigned "
            f"to rider "
            f"{order.delivery_person_id}"
        )

        return False

    if order.status != READY_STATUS:

        print(
            f"⚠️ Order status is "
            f"'{order.status}', "
            f"not Ready"
        )

        return False

    _sync_legacy_terminal_outcome(order)
    excluded_rider_ids = attempted_rider_ids_for_order(order.id)
    if excluded_rider_ids:
        print(
            f"🧾 AUTO-ASSIGN HISTORY: order={order.order_id} "
            f"excluding prior riders={sorted(excluded_rider_ids)}"
        )

    settings = DeliverySettings.query.first()

    if not settings:

        print(
            "❌ No DeliverySettings found"
        )

        return False

    if not settings.auto_assign_enabled:

        print(
            "❌ Auto assignment disabled"
        )

        return False

    # ======================================================
    # 1. TRY ROUTE BATCHING FIRST
    # ======================================================

    batch_rider = find_route_batch_rider(
        order, excluded_rider_ids=excluded_rider_ids
    )

    if batch_rider:

        print(
            "========================================"
        )

        print(
            "🚚 TRYING ROUTE BATCH"
        )

        print(
            "ORDER:",
            order.order_id
        )

        print(
            "RIDER:",
            batch_rider.id,
            batch_rider.name
        )

        print(
            "========================================"
        )

        batch_result = (
            assign_batch_order_to_rider(
                order,
                batch_rider
            )
        )

        if batch_result:

            print(
                f"✅ ROUTE BATCH SUCCESS: "
                f"{order.order_id}"
            )

            return True

        print(
            f"⚠️ Route batch failed for "
            f"{order.order_id}. "
            f"Trying normal assignment."
        )

    # ======================================================
    # 2. NORMAL NEAREST RIDER
    # ======================================================

    rider = find_nearest_rider_excluding(
        order, excluded_rider_ids=excluded_rider_ids
    )

    if not rider:

        print(
            f"❌ No available rider "
            f"for order "
            f"{order.order_id}"
        )

        return False

    print(
        "✅ Normal rider found:",
        rider.name
    )

    return assign_delivery_to_order(
        order,
        rider
    )


# ==========================================================
# CLEAN EXPIRED RIDER ASSIGNMENTS
# ==========================================================

def cleanup_expired_assignments_for_rider(
    rider
):

    if not rider:
        return 0

    now = datetime.utcnow()

    expired_orders = (
        Order.query
        .filter(
            Order.delivery_person_id == rider.id,

            Order.status ==
                ASSIGNMENT_PENDING_STATUS,

            Order.rider_response ==
                RIDER_PENDING_RESPONSE,

            Order.assignment_expires_at.isnot(None),

            Order.assignment_expires_at <= now
        )
        .all()
    )

    if not expired_orders:

        return 0

    released_count = 0

    for order in expired_orders:

        print(
            "========================================"
        )

        print(
            "⏰ EXPIRED ASSIGNMENT"
        )

        print(
            "ORDER:",
            order.order_id
        )

        print(
            "RIDER:",
            rider.id,
            rider.name
        )

        print(
            "EXPIRED AT:",
            order.assignment_expires_at
        )

        # --------------------------------------------------
        # Record this rider's timeout before clearing assignment fields.
        # --------------------------------------------------
        record_assignment_outcome(
            order.id, rider.id, RIDER_EXPIRED_RESPONSE,
            resolved_at=order.assignment_expires_at or now,
        )

        # --------------------------------------------------
        # Return order to Ready
        # --------------------------------------------------

        order.status = READY_STATUS

        order.rider_response = RIDER_EXPIRED_RESPONSE
        # Preserve the timeout time so the order does not immediately
        # return to the same dispatch loop as a fresh order.
        order.rejected_at = now

        order.delivery_person_id = None

        order.assigned_at = None

        order.assignment_expires_at = None

        if hasattr(
            order,
            "delivery_boy_name"
        ):

            order.delivery_boy_name = None

        if hasattr(
            order,
            "delivery_boy_phone"
        ):

            order.delivery_boy_phone = None

        released_count += 1

    # ======================================================
    # CRITICAL:
    # DO NOT RELEASE RIDER IF ANOTHER ACTIVE ORDER EXISTS
    # ======================================================

    remaining_active_orders = (
        Order.query
        .filter(
            Order.delivery_person_id == rider.id,
            Order.status.in_(
                ACTIVE_RIDER_ORDER_STATUSES
            )
        )
        .count()
    )

    if remaining_active_orders == 0:

        rider.is_available = True

        print(
            f"✅ RIDER {rider.id} "
            f"RELEASED — no active orders"
        )

    else:

        rider.is_available = False

        print(
            f"🔒 RIDER {rider.id} "
            f"REMAINS UNAVAILABLE — "
            f"{remaining_active_orders} "
            f"active order(s)"
        )

    db.session.commit()

    print(
        f"✅ Released {released_count} "
        f"expired assignment(s)"
    )

    return released_count

# ==========================================================
# CLEAN ALL EXPIRED ASSIGNMENTS
# SERVER-WIDE CLEANUP
# ==========================================================
# ==========================================================
# SERVER-WIDE CLEAN EXPIRED ASSIGNMENTS
# ==========================================================

def cleanup_all_expired_assignments():

    print("========================================")
    print("🧹 SERVER-WIDE ASSIGNMENT CLEANUP")
    print("========================================")

    now = datetime.utcnow()

    expired_orders = (
        Order.query
        .filter(
            Order.status == ASSIGNMENT_PENDING_STATUS,

            Order.rider_response.in_([
                RIDER_PENDING_RESPONSE,
                RIDER_EXPIRED_RESPONSE
            ]),

            Order.assignment_expires_at.isnot(None),

            Order.assignment_expires_at <= now
        )
        .all()
    )

    if not expired_orders:

        print("✅ No expired assignments found")
        return 0

    released_count = 0
    affected_rider_ids = set()

    for order in expired_orders:

        print("----------------------------------------")
        print("⏰ EXPIRED ASSIGNMENT")
        print("ORDER:", order.order_id)
        print("RIDER:", order.delivery_person_id)
        print("RESPONSE:", order.rider_response)
        print("EXPIRES:", order.assignment_expires_at)

        if order.delivery_person_id is not None:
            affected_rider_ids.add(order.delivery_person_id)
            record_assignment_outcome(
                order.id, order.delivery_person_id, RIDER_EXPIRED_RESPONSE,
                resolved_at=order.assignment_expires_at or now,
            )

        # Return order to Ready
        order.status = READY_STATUS
        order.rider_response = RIDER_EXPIRED_RESPONSE
        # Store expiry time for the retry cooldown.
        order.rejected_at = now

        # Release rider
        order.delivery_person_id = None
        order.assigned_at = None
        order.assignment_expires_at = None

        if hasattr(order, "delivery_boy_name"):
            order.delivery_boy_name = None

        if hasattr(order, "delivery_boy_phone"):
            order.delivery_boy_phone = None

        released_count += 1

    # ----------------------------------------
    # Recalculate rider availability
    # ----------------------------------------

    for rider_id in affected_rider_ids:

        rider = DeliveryPerson.query.get(rider_id)

        if not rider:
            continue

        remaining_active_orders = (
            Order.query
            .filter(
                Order.delivery_person_id == rider.id,
                Order.status.in_(
                    ACTIVE_RIDER_ORDER_STATUSES
                )
            )
            .count()
        )

        if remaining_active_orders == 0:

            rider.is_available = True

            print(
                f"✅ RIDER {rider.id} RELEASED"
            )

        else:

            rider.is_available = False

            print(
                f"🔒 RIDER {rider.id} STILL BUSY "
                f"WITH {remaining_active_orders} ACTIVE ORDER(S)"
            )

    db.session.commit()

    print("========================================")
    print(
        f"✅ RELEASED {released_count} "
        f"EXPIRED ASSIGNMENT(S)"
    )
    print("========================================")

    return released_count
# ==========================================================
# ASSIGN WAITING ORDER TO RIDER
# ==========================================================

def assign_waiting_order_to_rider(
    rider
):

    print(
        "========================================"
    )

    print(
        "CHECK WAITING ORDER FOR RIDER:",
        rider.id if rider else None,
        rider.name if rider else None
    )

    print(
        "========================================"
    )

    # ======================================================
    # RIDER VALIDATION
    # ======================================================

    if not rider:

        print(
            "STOP: rider missing"
        )

        return None

    if not rider.is_active:

        print(
            "STOP: rider inactive"
        )

        return None

    if not rider.is_online:

        print(
            "STOP: rider offline"
        )

        return None

    # ======================================================
    # CLEAN EXPIRED ASSIGNMENTS
    # ======================================================

    cleanup_expired_assignments_for_rider(
        rider
    )

    db.session.refresh(
        rider
    )

    # ======================================================
    # RIDER MUST BE AVAILABLE FOR NORMAL ASSIGNMENT
    # ======================================================

    if not rider.is_available:

        print(
            f"STOP: Rider {rider.id} "
            f"is not available."
        )

        return None

    if (
        rider.latitude is None
        or rider.longitude is None
    ):

        print(
            "STOP: rider location missing"
        )

        return None

    # ======================================================
    # CRITICAL ACTIVE ORDER CHECK
    # ======================================================

    active_order = rider_has_active_order(
        rider.id
    )

    if active_order:

        rider.is_available = False

        db.session.commit()

        print(
            f"⛔ STOP: Rider already has "
            f"{active_order.order_id}"
        )

        return None

    # ======================================================
    # SETTINGS
    # ======================================================

    settings = DeliverySettings.query.first()

    if not settings:
        return None

    if not settings.auto_assign_enabled:
        return None

    radius = float(
        settings.rider_search_radius
        or 5
    )

    # ======================================================
    # READY ORDERS
    # ======================================================

    ready_orders = (
        Order.query
        .filter(
            Order.status == READY_STATUS,
            Order.delivery_person_id.is_(None)
        )
        .order_by(Order.created_at.asc(), Order.id.asc())
        .all()
    )

    # ======================================================
    # CHECK ORDERS: exclude only riders with a prior terminal attempt.
    # Other eligible riders can receive the order immediately.
    # ======================================================

    for order in ready_orders:
        _sync_legacy_terminal_outcome(order)
        previous_attempt = _terminal_attempt_for_rider(order.id, rider.id)
        if previous_attempt:
            print(
                f"⏭️ SKIP RIDER {rider.id} FOR {order.order_id}: "
                f"already {previous_attempt.status.lower()} this order."
            )
            continue

        pending_attempt = (
            _attempts_for_order(order.id)
            .filter(
                DeliveryAssignmentAttempt.rider_id == rider.id,
                DeliveryAssignmentAttempt.status == RIDER_PENDING_RESPONSE,
            )
            .order_by(DeliveryAssignmentAttempt.id.desc())
            .first()
        )
        if pending_attempt:
            print(
                f"⏭️ SKIP DUPLICATE: rider={rider.id} "
                f"order={order.order_id} already has a pending history row."
            )
            continue

        # --------------------------------------------------
        # RESTAURANT
        # --------------------------------------------------

        restaurant = (
            order.restaurant
        )

        if not restaurant:
            continue

        if (
            restaurant.latitude is None
            or restaurant.longitude is None
        ):
            continue

        # --------------------------------------------------
        # DISTANCE
        # --------------------------------------------------

        distance = haversine(
            float(
                restaurant.latitude
            ),
            float(
                restaurant.longitude
            ),
            float(
                rider.latitude
            ),
            float(
                rider.longitude
            )
        )

        print(
            f"Order {order.order_id}: "
            f"{distance:.2f} KM"
        )

        if distance > radius:
            continue

        # --------------------------------------------------
        # FINAL AVAILABILITY CHECK
        # --------------------------------------------------

        db.session.refresh(
            rider
        )

        if not rider.is_available:

            print(
                f"⛔ Rider {rider.id} "
                f"is no longer available."
            )

            return None

        active_order = rider_has_active_order(
            rider.id
        )

        if active_order:

            rider.is_available = False

            db.session.commit()

            print(
                f"⛔ Rider received another "
                f"order already: "
                f"{active_order.order_id}"
            )

            return None

        # --------------------------------------------------
        # ASSIGN
        # --------------------------------------------------

        result = assign_delivery_to_order(
            order,
            rider
        )

        if result:

            print(
                "========================================"
            )

            print(
                "✅ WAITING ORDER ASSIGNED"
            )

            print(
                "ORDER:",
                order.order_id
            )

            print(
                "RIDER:",
                rider.id,
                rider.name
            )

            print(
                f"DISTANCE: "
                f"{distance:.2f} KM"
            )

            print(
                "========================================"
            )

            return order

        db.session.refresh(
            rider
        )

        if not rider.is_available:
            return None

    # ======================================================
    # NOTHING FOUND
    # ======================================================

    print(
        f"ℹ️ No eligible waiting Ready "
        f"order within {radius} KM "
        f"for {rider.name}"
    )

    return None