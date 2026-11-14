
import os
import re


def is_telugu(text):
    """Detect Telugu script in the customer's message."""
    return any("\u0C00" <= char <= "\u0C7F" for char in text)


def normalize(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def get_local_answer(message):
    """
    Return a verified-style support response for known FAQ intents.
    Return None when the question needs more knowledge or AI reasoning.
    """
    question = normalize(message)
    telugu = is_telugu(message)

    # Customer care contact details come from environment configuration.
    contact_terms = (
        "customer care number",
        "customer care phone",
        "customer support number",
        "support phone number",
        "helpline number",
        "contact number",
        "కస్టమర్ కేర్",
        "కస్టమర్ కేర్ నంబర్",
        "ఫోన్ నంబర్",
        "సపోర్ట్ నంబర్",
    )

    if any(term in question for term in contact_terms):
        phone = os.getenv("RUCHIGO_SUPPORT_PHONE", "").strip()
        email = os.getenv("RUCHIGO_SUPPORT_EMAIL", "").strip()

        contacts = []
        if phone:
            contacts.append(f"Phone: {phone}")
        if email:
            contacts.append(f"Email: {email}")

        if contacts:
            return (
                "RucHiGO customer support: " + " | ".join(contacts)
                if not telugu
                else "RucHiGO కస్టమర్ సపోర్ట్: " + " | ".join(contacts)
            )

        return (
            "I don't have a verified customer-care contact configured. "
            "Please use the Contact Us option on the RucHiGO website."
            if not telugu
            else "RucHiGO కస్టమర్ కేర్ వివరాలు ప్రస్తుతం అందుబాటులో లేవు. "
                 "దయచేసి వెబ్‌సైట్‌లోని Contact Us ఎంపికను ఉపయోగించండి."
        )

    faqs = [
        {
            "terms": (
                "otp not received", "otp not coming", "not getting otp",
                "otp problem", "ఓటిపి రావడం లేదు", "ఓటిపి రావట్లేదు",
                "otp రావడం లేదు",
            ),
            "en": (
                "Please check your registered phone number and network, "
                "wait briefly, and request a new OTP. Never share your OTP "
                "with anyone. If the issue continues, contact RucHiGO support."
            ),
            "te": (
                "మీరు నమోదు చేసిన ఫోన్ నంబర్, నెట్‌వర్క్‌ను తనిఖీ చేసి, "
                "కొద్దిసేపు వేచి మళ్లీ OTP కోరండి. మీ OTPని ఎవరితోనూ పంచుకోవద్దు. "
                "సమస్య కొనసాగితే RucHiGO సపోర్ట్‌ను సంప్రదించండి."
            ),
        },
        {
            "terms": (
                "cannot login", "can't login", "login problem",
                "unable to login", "login issue", "లాగిన్ కావడం లేదు",
                "లాగిన్ సమస్య",
            ),
            "en": (
                "Check your registered phone number and follow the login "
                "verification steps. If you cannot receive an OTP, try again "
                "after a short wait. Contact support if the issue persists."
            ),
            "te": (
                "మీరు నమోదు చేసిన ఫోన్ నంబర్‌ను తనిఖీ చేసి లాగిన్ ధృవీకరణ "
                "దశలను అనుసరించండి. OTP రాకపోతే కొద్దిసేపటి తర్వాత మళ్లీ ప్రయత్నించండి. "
                "సమస్య కొనసాగితే సపోర్ట్‌ను సంప్రదించండి."
            ),
        },
        {
            "terms": (
                "cart not working", "cannot add to cart", "can't add to cart",
                "cart problem", "కార్ట్ పనిచేయడం లేదు", "కార్ట్ సమస్య",
            ),
            "en": (
                "Refresh RucHiGO and try adding the item again. Check your "
                "internet connection and confirm the item is available. "
                "If it still fails, contact support with the item and restaurant name."
            ),
            "te": (
                "RucHiGO పేజీని రిఫ్రెష్ చేసి మళ్లీ ఐటమ్‌ను కార్ట్‌లో చేర్చండి. "
                "ఇంటర్నెట్ కనెక్షన్, ఐటమ్ లభ్యతను తనిఖీ చేయండి. ఇంకా సమస్య ఉంటే "
                "రెస్టారెంట్ పేరు, ఐటమ్ వివరాలతో సపోర్ట్‌ను సంప్రదించండి."
            ),
        },
        {
            "terms": (
                "payment pending", "payment failed", "money deducted",
                "amount deducted", "paid but order", "payment issue",
                "డబ్బులు కట్ అయ్యాయి", "పేమెంట్ ఫెయిల్", "పేమెంట్ సమస్య",
            ),
            "en": (
                "Check your order history and payment status. If money was "
                "deducted but your order is not confirmed, keep the transaction "
                "reference and contact support. I cannot confirm a refund without "
                "verified payment records. Never share your UPI PIN or OTP."
            ),
            "te": (
                "మీ ఆర్డర్ హిస్టరీ, పేమెంట్ స్టేటస్‌ను తనిఖీ చేయండి. డబ్బులు "
                "కట్ అయ్యి ఆర్డర్ నిర్ధారించబడకపోతే ట్రాన్సాక్షన్ రిఫరెన్స్‌ను "
                "భద్రపరచి సపోర్ట్‌ను సంప్రదించండి. పేమెంట్ రికార్డులు ధృవీకరించకుండా "
                "రిఫండ్‌ను నిర్ధారించలేను. మీ UPI PIN లేదా OTPని పంచుకోవద్దు."
            ),
        },
        {
            "terms": (
                "how to cancel", "cancel my order", "cancel order",
                "ఆర్డర్ క్యాన్సిల్", "ఆర్డర్ రద్దు",
            ),
            "en": (
                "Open your order history and check whether cancellation is "
                "available for your order. Eligibility may depend on its current "
                "status. I cannot cancel an order directly from this chat."
            ),
            "te": (
                "మీ ఆర్డర్ హిస్టరీలోకి వెళ్లి క్యాన్సిలేషన్ ఎంపిక ఉందో లేదో చూడండి. "
                "ఆర్డర్ ప్రస్తుత స్థితిని బట్టి రద్దు అవకాశం మారవచ్చు. ఈ చాట్ ద్వారా "
                "నేను నేరుగా ఆర్డర్‌ను రద్దు చేయలేను."
            ),
        },
        {
            "terms": (
                "refund", "money back", "refund status", "రిఫండ్",
                "డబ్బులు తిరిగి", "డబ్బు తిరిగి",
            ),
            "en": (
                "Check your order and payment details, then contact RucHiGO "
                "support with your order ID and transaction reference. I cannot "
                "verify a refund or promise a refund date without payment records."
            ),
            "te": (
                "మీ ఆర్డర్, పేమెంట్ వివరాలను తనిఖీ చేసి ఆర్డర్ ID మరియు ట్రాన్సాక్షన్ "
                "రిఫరెన్స్‌తో RucHiGO సపోర్ట్‌ను సంప్రదించండి. పేమెంట్ రికార్డులు "
                "లేకుండా రిఫండ్ స్థితిని లేదా తేదీని నిర్ధారించలేను."
            ),
        },
        {
            "terms": (
                "change phone number", "change mobile number",
                "update phone number", "change my number",
                "ఫోన్ నంబర్ మార్చాలి", "మొబైల్ నంబర్ మార్చాలి",
            ),
            "en": (
                "Check account settings for a phone-number update option. "
                "If it is unavailable, contact support for identity verification. "
                "Never share your OTP or password in this chat."
            ),
            "te": (
                "ఫోన్ నంబర్ మార్చే ఎంపిక కోసం మీ అకౌంట్ సెట్టింగ్స్‌ను చూడండి. "
                "ఆ ఎంపిక లేకపోతే గుర్తింపు ధృవీకరణ కోసం సపోర్ట్‌ను సంప్రదించండి. "
                "మీ OTP లేదా పాస్‌వర్డ్‌ను ఈ చాట్‌లో పంచుకోవద్దు."
            ),
        },
        {
            "terms": (
                "delivery charge", "delivery charges", "delivery fee",
                "delivery charges why", "డెలివరీ ఛార్జీలు",
                "డెలివరీ చార్జ్",
            ),
            "en": (
                "Check the delivery fee shown in your cart or at checkout. "
                "The exact charge depends on the rules applied to your order; "
                "I won't guess an amount that I cannot verify."
            ),
            "te": (
                "మీ కార్ట్ లేదా చెక్అవుట్‌లో చూపించిన డెలివరీ ఛార్జీని చూడండి. "
                "మీ ఆర్డర్‌కు వర్తించే నియమాలపై ఖచ్చితమైన ఛార్జీ ఆధారపడి ఉంటుంది. "
                "ధృవీకరించని మొత్తాన్ని నేను చెప్పను."
            ),
        },
        {
            "terms": (
                "website not working", "website not loading",
                "app not working", "page not loading",
                "వెబ్‌సైట్ పనిచేయడం లేదు", "యాప్ పనిచేయడం లేదు",
            ),
            "en": (
                "Check your internet connection, refresh the page, and reopen "
                "RucHiGO. If the problem continues, contact support and describe "
                "the page and error message."
            ),
            "te": (
                "ఇంటర్నెట్ కనెక్షన్‌ను తనిఖీ చేసి పేజీని రిఫ్రెష్ చేసి RucHiGOని "
                "మళ్లీ తెరవండి. సమస్య కొనసాగితే ఏ పేజీలో ఏ ఎర్రర్ వస్తుందో "
                "సపోర్ట్‌కు తెలియజేయండి."
            ),
        },
        {
            "terms": (
                "how does ruchigo work", "what is ruchigo",
                "how to order food", "how to place an order",
                "రుచిగో ఎలా పనిచేస్తుంది", "ఆర్డర్ ఎలా చేయాలి",
            ),
            "en": (
                "RucHiGO helps you browse available restaurants, select food "
                "items, review your cart, enter delivery details, and place an "
                "order using the payment options shown at checkout."
            ),
            "te": (
                "RucHiGOలో అందుబాటులో ఉన్న రెస్టారెంట్లను చూసి, ఆహార ఐటమ్‌లను "
                "ఎంచుకుని, కార్ట్‌ను తనిఖీ చేసి, డెలివరీ వివరాలు నమోదు చేసి, "
                "చెక్అవుట్‌లో చూపిన పేమెంట్ ఎంపికలతో ఆర్డర్ చేయవచ్చు."
            ),
        },
    ]

    for faq in faqs:
        if any(term in question for term in faq["terms"]):
            return faq["te"] if telugu else faq["en"]

    return None
