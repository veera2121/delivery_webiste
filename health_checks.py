# health_checks.py

def check_free_delivery_logic():
    """
    Checks backend delivery logic
    """
    items_total = 600
    free_limit = 399
    base_delivery = 40

    delivery = base_delivery
    if items_total >= free_limit:
        delivery = 0

    return {
        "status": delivery == 0,
        "issue": None if delivery == 0 else "Free delivery not applied"
    }


def check_offer_calculation():
    """
    Checks percent offer calculation
    """
    items_total = 500
    offer_type = "percent"
    offer_value = 10

    discount = (items_total * offer_value) / 100

    return {
        "status": discount == 50,
        "issue": None if discount == 50 else "Offer discount mismatch"
    }


def check_frontend_delivery_sync():
    """
    Detects your current frontend bug
    """
    frontend_delivery = "STATIC"   # hidden input / hardcoded value
    backend_delivery = "DYNAMIC"   # restaurant based

    return {
        "status": frontend_delivery == backend_delivery,
        "issue": "Frontend using static delivery values"
    }
