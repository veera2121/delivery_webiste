from firebase_admin import messaging


# ==========================================================
# GENERIC FCM PUSH NOTIFICATION
# ==========================================================

def send_push_notification(
    title,
    body,
    target_type="topic",
    target_value="all_users",
    data=None
):
    print("")
    print("==================================================")
    print("📲 FCM SEND START")
    print("==================================================")

    print(f"TITLE: {title}")
    print(f"BODY: {body}")
    print(f"TARGET TYPE: {target_type}")
    print(f"TARGET VALUE: {target_value}")

    # ------------------------------------------------------
    # PREPARE DATA
    # ------------------------------------------------------

    raw_data = data or {}

    print("")
    print("----- RAW FCM DATA -----")

    for key, value in raw_data.items():
        print(f"{key}: {value!r}")

    fcm_data = {
        str(key): str(value)
        for key, value in raw_data.items()
    }

    print("")
    print("----- FINAL FCM DATA -----")

    for key, value in fcm_data.items():
        print(f"{key}: {value!r}")

    # ------------------------------------------------------
    # CREATE MESSAGE
    # ------------------------------------------------------

    message = messaging.Message(
        data=fcm_data
    )

    # ------------------------------------------------------
    # TARGET
    # ------------------------------------------------------

    if target_type == "topic":
        message.topic = target_value

        print("")
        print(f"🎯 FCM TARGET TOPIC: {target_value}")

    elif target_type == "token":
        message.token = target_value

        token_preview = (
            f"{target_value[:15]}..."
            if target_value
            else "EMPTY"
        )

        print("")
        print(f"🎯 FCM TARGET TOKEN: {token_preview}")

    else:
        print("")
        print(
            f"⚠️ UNKNOWN FCM TARGET TYPE: {target_type}"
        )

    # ------------------------------------------------------
    # SEND
    # ------------------------------------------------------

    try:
        print("")
        print("🚀 SENDING FCM...")

        response = messaging.send(message)

        print("")
        print("✅ FCM SENT SUCCESSFULLY")
        print(f"FCM RESPONSE: {response}")

        print("==================================================")
        print("📲 FCM SEND END")
        print("==================================================")
        print("")

        return response

    except Exception as error:

        print("")
        print("❌ FCM SEND FAILED")
        print(f"FCM ERROR TYPE: {type(error).__name__}")
        print(f"FCM ERROR: {error}")

        print("==================================================")
        print("📲 FCM SEND END")
        print("==================================================")
        print("")

        return None


# ==========================================================
# NEW ORDER NOTIFICATION TO DELIVERY RIDER
# ==========================================================

def send_new_order_notification(rider, order):

    print("")
    print("==================================================")
    print("📦 NEW DELIVERY ORDER NOTIFICATION")
    print("==================================================")

    # ------------------------------------------------------
    # RIDER DEBUG
    # ------------------------------------------------------

    print("")
    print("----- RIDER INFORMATION -----")

    print(f"RIDER ID: {getattr(rider, 'id', None)}")
    print(f"RIDER NAME: {getattr(rider, 'name', None)}")
    print(f"RIDER PHONE: {getattr(rider, 'phone', None)}")

    fcm_token = getattr(
        rider,
        "fcm_token",
        None
    )

    print(
        f"FCM TOKEN EXISTS: "
        f"{bool(fcm_token)}"
    )

    if fcm_token:
        print(
            f"FCM TOKEN PREVIEW: "
            f"{fcm_token[:20]}..."
        )

    # ------------------------------------------------------
    # FCM TOKEN CHECK
    # ------------------------------------------------------

    if not fcm_token:

        print("")
        print(
            f"⚠️ RIDER {getattr(rider, 'name', 'Unknown')} "
            f"HAS NO FCM TOKEN"
        )

        print(
            f"❌ Order {getattr(order, 'order_id', None)} "
            f"notification NOT sent"
        )

        print("==================================================")
        print("📦 NOTIFICATION END")
        print("==================================================")
        print("")

        return False

    # ------------------------------------------------------
    # ORDER BASIC INFO
    # ------------------------------------------------------

    print("")
    print("----- ORDER INFORMATION -----")

    print(f"ORDER DATABASE ID: {getattr(order, 'id', None)}")
    print(f"ORDER NUMBER: {getattr(order, 'order_id', None)}")
    print(f"CUSTOMER: {getattr(order, 'customer_name', None)}")
    print(f"CUSTOMER PHONE: {getattr(order, 'phone', None)}")
    print(f"ORDER STATUS: {getattr(order, 'status', None)}")
    print(f"PAYMENT TYPE: {getattr(order, 'payment_type', None)}")
    print(f"FINAL TOTAL: {getattr(order, 'final_total', None)}")
    print(f"DISTANCE: {getattr(order, 'distance_km', None)}")

    # ------------------------------------------------------
    # RESTAURANT
    # ------------------------------------------------------

    restaurant_name = ""

    if order.restaurant:

        restaurant_name = (
            order.restaurant.name
            or ""
        )

    print(
        f"RESTAURANT: {restaurant_name}"
    )

    # ======================================================
    # DELIVERY CHARGE DEBUG
    # ======================================================

    print("")
    print("==================================================")
    print("💰 DELIVERY CHARGE DEBUG")
    print("==================================================")

    delivery_charge = getattr(
        order,
        "delivery_charge",
        None
    )

    print(
        "RAW order.delivery_charge:"
    )

    print(
        f"VALUE: {delivery_charge!r}"
    )

    print(
        f"TYPE: {type(delivery_charge).__name__}"
    )

    # ------------------------------------------------------
    # NONE CHECK
    # ------------------------------------------------------

    if delivery_charge is None:

        print("")
        print(
            "⚠️ DELIVERY CHARGE IS NONE"
        )

        print(
            "Using fallback value: 0"
        )

        delivery_charge = 0

    # ------------------------------------------------------
    # ZERO CHECK
    # ------------------------------------------------------

    try:
        numeric_delivery_charge = float(
            delivery_charge
        )
    except (
        TypeError,
        ValueError
    ):
        numeric_delivery_charge = None

    if numeric_delivery_charge == 0:

        print("")
        print(
            "⚠️ DELIVERY CHARGE IS ZERO"
        )

        print(
            "This means order.delivery_charge "
            "is 0 at notification time."
        )

        print(
            "Check where delivery_charge is "
            "calculated and saved before rider assignment."
        )

    else:

        print("")
        print(
            "✅ DELIVERY CHARGE IS NON-ZERO"
        )

    print(
        f"FINAL DELIVERY CHARGE TO SEND: "
        f"{delivery_charge}"
    )

    print("==================================================")

    # ======================================================
    # RIDER EARNING
    # ======================================================

    print("")
    print("----- RIDER EARNING DEBUG -----")

    rider_earning = getattr(
        order,
        "rider_earning",
        None
    )

    print(
        f"RAW RIDER EARNING: "
        f"{rider_earning!r}"
    )

    print(
        f"RIDER EARNING TYPE: "
        f"{type(rider_earning).__name__}"
    )

    if rider_earning is None:
        print(
            "ℹ️ Rider earning is not configured."
        )
    else:
        print(
            f"✅ Rider earning found: "
            f"{rider_earning}"
        )

    # ======================================================
    # EXPIRY
    # ======================================================

    assignment_expires_at = (
        order.assignment_expires_at.isoformat()
        if order.assignment_expires_at
        else ""
    )

    print("")
    print("----- ASSIGNMENT EXPIRY -----")

    print(
        f"assignment_expires_at: "
        f"{assignment_expires_at!r}"
    )

    # ======================================================
    # BUILD FCM DATA
    # ======================================================

    data = {

        "type": "new_order",

        "order_id": str(
            order.id
        ),

        "order_number": str(
            order.order_id or ""
        ),

        "customer_name": str(
            order.customer_name or ""
        ),

        "customer_phone": str(
            order.phone or ""
        ),

        "restaurant_name": str(
            restaurant_name
        ),

        "total": str(
            order.final_total or 0
        ),

        "payment_type": str(
            order.payment_type or "COD"
        ),

        "address": str(
            order.address or ""
        ),

        "distance": str(
            order.distance_km or 0
        ),

        # IMPORTANT
        "delivery_charge": str(
            delivery_charge
        ),

        "rider_earning": (
            str(rider_earning)
            if rider_earning is not None
            else ""
        ),

        "assignment_expires_at": (
            assignment_expires_at
        ),
    }

    # ======================================================
    # DEBUG FINAL PAYLOAD
    # ======================================================

    print("")
    print("==================================================")
    print("📨 FINAL FCM PAYLOAD")
    print("==================================================")

    for key, value in data.items():

        print(
            f"{key}: {value!r}"
        )

    print("==================================================")

    # ======================================================
    # NOTIFICATION TEXT
    # ======================================================

    title = "New Delivery Order"

    body = (
        f"Order #{order.order_id} "
        f"• Delivery ₹{delivery_charge} "
        f"• {order.distance_km or 0} km"
    )

    print("")
    print("----- NOTIFICATION DISPLAY -----")

    print(
        f"TITLE: {title}"
    )

    print(
        f"BODY: {body}"
    )

    # ======================================================
    # SEND FCM
    # ======================================================

    response = send_push_notification(

        title=title,

        body=body,

        target_type="token",

        target_value=fcm_token,

        data=data
    )

    # ======================================================
    # RESULT
    # ======================================================

    if response:

        print("")
        print(
            "✅ NEW ORDER NOTIFICATION SENT"
        )

        print(
            f"RIDER: {rider.name}"
        )

        print(
            f"ORDER: {order.order_id}"
        )

        print(
            f"DELIVERY CHARGE SENT: "
            f"₹{delivery_charge}"
        )

        print("==================================================")
        print("📦 NOTIFICATION END")
        print("==================================================")
        print("")

        return True

    print("")
    print(
        "❌ NEW ORDER NOTIFICATION FAILED"
    )

    print(
        f"RIDER: {rider.name}"
    )

    print(
        f"ORDER: {order.order_id}"
    )

    print("==================================================")
    print("📦 NOTIFICATION END")
    print("==================================================")
    print("")

    return False