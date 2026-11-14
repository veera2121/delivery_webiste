# ============================================================
# RESTAURANT ORDER CONTROL ENGINE
# ============================================================

from datetime import datetime
import pytz

from extensions import db


def get_restaurant_order_control(restaurant):
    """
    Central source of truth for whether a restaurant
    can accept new orders.

    Control hierarchy:

        1. Platform
        2. Location
        3. Restaurant admin override
        4. Restaurant normal rules
        5. Restaurant status
        6. Limited drop
        7. Opening / closing hours
        8. Restaurant break schedule
        9. Accept-orders-until

    IMPORTANT:
    - Global STOP does not modify restaurant.is_accepting_orders
    - Location STOP does not modify restaurant.is_accepting_orders
    - force_on does not bypass global/location shutdown
    - Delivery availability is handled separately
    """

    # ========================================================
    # IMPORT HERE TO AVOID CIRCULAR IMPORT
    # ========================================================

    from models import PlatformControl

    # ========================================================
    # GLOBAL PLATFORM CONTROL
    # ========================================================

    platform = PlatformControl.query.first()

    if platform:

        # ----------------------------------------------------
        # PLATFORM ENABLED
        # ----------------------------------------------------

        if not platform.platform_enabled:
            return {
                "allowed": False,
                "reason": "PLATFORM_DISABLED",
                "message": "RucHiGo is temporarily unavailable."
            }

        # ----------------------------------------------------
        # MAINTENANCE MODE
        # ----------------------------------------------------

        if platform.maintenance_mode:
            return {
                "allowed": False,
                "reason": "MAINTENANCE_MODE",
                "message": (
                    platform.maintenance_message
                    or "We are currently performing maintenance."
                )
            }

        # ----------------------------------------------------
        # GLOBAL RESTAURANT ORDERING
        # ----------------------------------------------------

        if not platform.restaurant_ordering_enabled:

            # Automatic resume
            if (
                platform.restaurant_ordering_resume_at
                and datetime.utcnow()
                >= platform.restaurant_ordering_resume_at
            ):

                platform.restaurant_ordering_enabled = True
                platform.restaurant_ordering_resume_at = None
                platform.restaurant_ordering_stop_reason = None

                db.session.commit()

            else:
                return {
                    "allowed": False,
                    "reason": "GLOBAL_ORDERING_DISABLED",
                    "message": (
                        platform.ordering_disabled_message
                        or
                        "Restaurants are temporarily not accepting "
                        "new orders."
                    )
                }

    # ========================================================
    # LOCATION CONTROL
    # ========================================================

    location = restaurant.delivery_location_settings

    if location:

        # ----------------------------------------------------
        # LOCATION ACTIVE
        # ----------------------------------------------------

        if not location.is_active:
            return {
                "allowed": False,
                "reason": "LOCATION_DISABLED",
                "message": (
                    f"{location.location} is currently unavailable."
                )
            }

        # ----------------------------------------------------
        # LOCATION RESTAURANT ORDERING
        # ----------------------------------------------------

        if not location.restaurant_ordering_enabled:
            return {
                "allowed": False,
                "reason": "LOCATION_ORDERING_DISABLED",
                "message": (
                    location.ordering_disabled_message
                    or
                    f"Ordering is temporarily unavailable "
                    f"in {location.location}."
                )
            }

    # ========================================================
    # RESTAURANT ADMIN OVERRIDE
    # ========================================================

    if restaurant.admin_order_override == "force_off":
        return {
            "allowed": False,
            "reason": "RESTAURANT_ADMIN_DISABLED",
            "message": (
                "This restaurant is temporarily unavailable."
            )
        }

    # ========================================================
    # FORCE ON
    #
    # force_on skips the restaurant's own
    # is_accepting_orders check.
    #
    # It DOES NOT bypass:
    # - platform disabled
    # - maintenance
    # - global ordering stop
    # - location ordering stop
    # - suspended status
    # - coming soon
    # - limited drop restrictions
    # - restaurant hours
    # - accept_orders_until
    # ========================================================

    force_on = (
        restaurant.admin_order_override == "force_on"
    )

    # ========================================================
    # NORMAL RESTAURANT ORDER ACCEPTANCE
    # ========================================================

    if not force_on:

        if not restaurant.is_accepting_orders:
            return {
                "allowed": False,
                "reason": "RESTAURANT_NOT_ACCEPTING",
                "message": (
                    "This restaurant is currently not "
                    "accepting orders."
                )
            }

    # ========================================================
    # SUSPENDED
    # ========================================================

    if restaurant.status == "suspended":
        return {
            "allowed": False,
            "reason": "RESTAURANT_SUSPENDED",
            "message": (
                "This restaurant is temporarily unavailable."
            )
        }

    # ========================================================
    # COMING SOON
    # ========================================================

    if restaurant.status == "coming_soon":

        tz = pytz.timezone(
            restaurant.timezone or "Asia/Kolkata"
        )

        local_date = datetime.now(tz).date()

        if (
            not restaurant.start_date
            or local_date < restaurant.start_date
        ):
            return {
                "allowed": False,
                "reason": "COMING_SOON",
                "message": (
                    "This restaurant is coming soon."
                )
            }

    # ========================================================
    # LIMITED DROP - SOLD OUT
    # ========================================================

    if (
        restaurant.is_limited_drop
        and restaurant.sold_out
    ):
        return {
            "allowed": False,
            "reason": "LIMITED_DROP_SOLD_OUT",
            "message": (
                "Today's limited item is sold out."
            )
        }

    # ========================================================
    # LIMITED DROP - ACTIVE TIME
    # ========================================================

    if (
        restaurant.is_limited_drop
        and restaurant.limited_start_datetime
        and restaurant.limited_end_datetime
    ):

        now_utc = datetime.utcnow()

        if not (
            restaurant.limited_start_datetime
            <= now_utc
            <= restaurant.limited_end_datetime
        ):
            return {
                "allowed": False,
                "reason": "LIMITED_DROP_INACTIVE",
                "message": (
                    "This limited drop is not currently active."
                )
            }

    # ========================================================
    # RESTAURANT OPENING / CLOSING HOURS
    # ========================================================

    tz = pytz.timezone(
        restaurant.timezone or "Asia/Kolkata"
    )

    now_local = datetime.now(tz)
    now_time = now_local.time()

    if (
        restaurant.opening_time
        and restaurant.closing_time
    ):

        # ----------------------------------------------------
        # NORMAL SAME-DAY HOURS
        # Example: 09:00 -> 22:00
        # ----------------------------------------------------

        if restaurant.opening_time < restaurant.closing_time:

            if not (
                restaurant.opening_time
                <= now_time
                <= restaurant.closing_time
            ):
                return {
                    "allowed": False,
                    "reason": "OUTSIDE_HOURS",
                    "message": (
                        "This restaurant is currently closed."
                    )
                }

        # ----------------------------------------------------
        # OVERNIGHT HOURS
        # Example: 18:00 -> 02:00
        # ----------------------------------------------------

        else:

            if not (
                now_time >= restaurant.opening_time
                or
                now_time <= restaurant.closing_time
            ):
                return {
                    "allowed": False,
                    "reason": "OUTSIDE_HOURS",
                    "message": (
                        "This restaurant is currently closed."
                    )
                }

    # ========================================================
    # RESTAURANT BREAK SCHEDULE
    # ========================================================
    # A recurring daily break. Handles both same-day breaks
    # (e.g. 14:00-17:00) and overnight breaks (e.g. 23:00-01:00).
    # Break end is exclusive: orders resume at the end time.
    # ========================================================

    if (
        getattr(restaurant, "break_enabled", False)
        and restaurant.break_start_time is not None
        and restaurant.break_end_time is not None
    ):
        break_start = restaurant.break_start_time
        break_end = restaurant.break_end_time

        if break_start != break_end:
            if break_start < break_end:
                in_break = break_start <= now_time < break_end
            else:
                in_break = (
                    now_time >= break_start
                    or now_time < break_end
                )

            if in_break:
                return {
                    "allowed": False,
                    "reason": "RESTAURANT_BREAK",
                    "message": (
                        "This restaurant is on a break. Orders will "
                        f"resume at {break_end.strftime('%I:%M %p')}."
                    )
                }

    # ========================================================
    # ACCEPT ORDERS UNTIL
    # ========================================================

    if (
        restaurant.accept_orders_until
        and now_time >= restaurant.accept_orders_until
    ):
        return {
            "allowed": False,
            "reason": "ACCEPT_UNTIL_REACHED",
            "message": (
                "This restaurant is no longer accepting "
                "orders today."
            )
        }

    # ========================================================
    # EVERYTHING OK
    # ========================================================

    return {
        "allowed": True,
        "reason": "AVAILABLE",
        "message": "Restaurant is accepting orders."
    }