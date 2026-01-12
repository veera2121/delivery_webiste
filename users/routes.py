from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from models import Customer, db  # OTP removed from import
import secrets

users_bp = Blueprint("users", __name__, template_folder="../../templates")


# ---------------- LOGIN / SIGNUP (NON-OTP) ----------------
@users_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        name = request.form.get("name", "").strip()
        is_new_user = request.form.get("is_new_user") == "1"

        # Validate input
        if not mobile.isdigit() or len(mobile) != 10:
            flash("Please enter a valid 10-digit mobile number")
            return redirect(url_for("users.login"))

        if not name:
            flash("Please enter your name")
            return redirect(url_for("users.login"))

        mobile_e164 = "+91" + mobile

        # Check if user exists
        customer = Customer.query.filter_by(mobile=mobile_e164).first()

        if is_new_user:
            if customer:
                flash("User already exists. Please login.")
                return redirect(url_for("users.login"))

            # Create new user
            customer = Customer(mobile=mobile_e164, name=name)
            db.session.add(customer)
            db.session.commit()
            flash("Account created successfully!")
        else:
            if not customer:
                flash("User not found. Please sign up.")
                return redirect(url_for("users.login"))

        # Set session
        session["customer_id"] = customer.id 
        session.permanent = True
        flash(f"Welcome {customer.name}!")
        return redirect(url_for("profile"))

    return render_template("login.html")


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
