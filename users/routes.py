from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from models import Customer, db  # OTP removed from import
import secrets
from flask_login import login_user
from flask_login import LoginManager, current_user
from firebase_admin import messaging 
from extensions import csrf

users_bp = Blueprint("users", __name__, template_folder="../../templates")
@users_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        name = request.form.get("name", "").strip()
        is_new_user = request.form.get("is_new_user") == "1"

        # Validate mobile
        if not mobile.isdigit() or len(mobile) != 10:
            flash("Please enter a valid 10-digit mobile number", "error")
            return redirect(url_for("users.login"))

        if not name:
            flash("Please enter your name", "error")
            return redirect(url_for("users.login"))

        # Normalize mobile with +91
        normalized_mobile = "+91" + mobile[-10:]

        customer = Customer.query.filter(
            (Customer.mobile == normalized_mobile) |
            (Customer.mobile == mobile)
        ).first()

        if is_new_user:
            if customer:
                flash("User already exists. Please login.", "error")
                return redirect(url_for("users.login"))

            customer = Customer(mobile=normalized_mobile, name=name)
            db.session.add(customer)
            db.session.commit()
            flash(f"Welcome {customer.name}! Your account has been created.", "success")

        else:
            if not customer:
                flash("User not found. Please sign up.", "error")
                return redirect(url_for("users.login"))

        login_user(customer, remember=False)
        session.permanent = True
        flash(f"Welcome back {customer.name}!", "success")

        return redirect(url_for("profile"))

    return render_template("login.html")
@users_bp.route("/save-token", methods=["POST"])
@csrf.exempt
def save_token():
    from flask import request, jsonify
    from datetime import datetime
    from models import FCMToken, db
    from flask_login import current_user

    data = request.get_json()
    token = data.get("token") if data else None

    print("TOKEN RECEIVED:", token)

    if not token:
        return jsonify({"error": "No token received"}), 400

    # 🔥 Remove same token duplicates first
    FCMToken.query.filter_by(token=token).delete()

    # 🔥 If user logged in, remove old tokens of that user
    if current_user.is_authenticated:
        FCMToken.query.filter_by(user_id=current_user.id).delete()

    # Save fresh token
    new_token = FCMToken(
        user_id=current_user.id if current_user.is_authenticated else None,
        token=token,
        created_at=datetime.utcnow()
    )

    db.session.add(new_token)
    db.session.commit()

    print("✅ Token saved cleanly")

    return jsonify({"status": "success"}), 200

from firebase_admin import messaging
from models import FCMToken


def send_push_notification_all(title, body):

    tokens = list(set([t.token for t in FCMToken.query.all()]))

    if not tokens:
        print("No tokens to send to!")
        return

    message = messaging.MulticastMessage(
        data={   # ✅ DATA ONLY
            "title": title,
            "body": body,
            "url": "/"
        },
        tokens=tokens
    )

    response = messaging.send_each_for_multicast(message)

    print("Success:", response.success_count)
    print("Failure:", response.failure_count)

    # 🔥 Remove invalid tokens automatically
    for idx, resp in enumerate(response.responses):
        if not resp.success:
            token = tokens[idx]
            print("❌ Removing invalid token:", token)
            FCMToken.query.filter_by(token=token).delete()

    db.session.commit()
# ============================================================
# FUTURE OTP ROUTES (COMMENTED)
# If you remove OTP completely, these can be deleted
# ============================================================

"""
# Helper to generate OTP
def generate_otp():
    return str(secrets.randbelow(900000) + 100000)  # 6-digit

# Dummy SMS sender
def send_sms(mobile, message):
    print(f"SMS to {mobile}: {message}")

# Twilio OTP Login (currently unused)
from twilio.base.exceptions import TwilioRestException

@users_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    mobile = session.get("mobile")
    if not mobile:
        flash("Session expired. Please login again.")
        return redirect(url_for("users.login"))

    if request.method == "GET":
        return render_template("verify_otp.html", mobile=mobile, allow_resend=True)

    otp_entered = request.form.get("otp", "").strip()

    try:
        verification_check = twilio_client.verify.services(TWILIO_VERIFY_SID).verification_checks.create(
            to=mobile,
            code=otp_entered
        )
    except TwilioRestException as e:
        flash(f"OTP verification failed: {e.msg}")
        return redirect(url_for("users.verify_otp"))

    if verification_check.status == "approved":
        customer = Customer.query.filter_by(mobile=mobile).first()
        if not customer:
            customer = Customer(mobile=mobile)
            db.session.add(customer)
            db.session.commit()

        session["customer_id"] = customer.id
        session.pop("mobile", None)
        flash("Login successful!")
        return redirect(url_for("profile"))

    else:
        flash("Invalid OTP. Try again!")
        return redirect(url_for("users.verify_otp"))


@users_bp.route("/send-otp", methods=["POST"])
def resend_otp():
    mobile = request.form.get("mobile", "").strip()

    if not mobile.isdigit() or len(mobile) != 10:
        return jsonify({"error": "Invalid mobile number"}), 400

    mobile_e164 = "+91" + mobile

    OTP.query.filter_by(mobile=mobile_e164, purpose="login").delete()
    db.session.commit()

    otp = generate_otp()
    otp_row = OTP(
        mobile=mobile_e164,
        otp_hash=generate_password_hash(otp),
        purpose="login",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        attempts=0
    )
    db.session.add(otp_row)
    db.session.commit()

    send_sms(mobile_e164, f"Your OTP is {otp}")

    return jsonify({"status": "OTP resent", "otp": otp})
"""
