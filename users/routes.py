from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from models import Customer, OTP, db
import secrets

# Dummy SMS sender (for now just prints)
def send_sms(mobile, message):
    print(f"SMS to {mobile}: {message}")

users_bp = Blueprint("users", __name__, template_folder="templates")

# Helper to generate OTP
def generate_otp():
    return str(secrets.randbelow(900000) + 100000)  # 6-digit
# ---------------- LOGIN / SIGNUP ----------------
from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from app import twilio_client, TWILIO_VERIFY_SID

users_bp = Blueprint("users", __name__, template_folder="../../templates")

@users_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()

        # Validate input
        if not mobile.isdigit() or len(mobile) != 10:
            flash("Please enter a valid 10-digit mobile number")
            return redirect(url_for("users.login"))

        # Convert to E.164 format for India
        mobile_e164 = "+91" + mobile
        session["mobile"] = mobile_e164

        try:
            # Send OTP using Twilio Verify
            verification = twilio_client.verify \
                .services(TWILIO_VERIFY_SID) \
                .verifications \
                .create(to=mobile_e164, channel="sms")

            flash("OTP sent to your mobile")
            return redirect(url_for("users.verify_otp"))

        except Exception as e:
            flash(f"Failed to send OTP: {str(e)}")
            return redirect(url_for("users.login"))

    return render_template("login.html")

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
        # Twilio verified successfully — log in user
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

# ---------------- RESEND OTP ----------------
@users_bp.route("/send-otp", methods=["POST"])
def resend_otp():
    mobile = request.form.get("mobile", "").strip()

    # Validate input
    if not mobile.isdigit() or len(mobile) != 10:
        return jsonify({"error": "Invalid mobile number"}), 400

    # Convert to E.164 format (for future Twilio)
    mobile_e164 = "+91" + mobile

    # Delete previous OTPs
    OTP.query.filter_by(mobile=mobile_e164, purpose="login").delete()
    db.session.commit()

    # Generate new OTP
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

    # Send SMS (dummy for now)
    send_sms(mobile_e164, f"Your OTP is {otp}")

    # For testing, return OTP (remove in production)
    return jsonify({"status": "OTP resent", "otp": otp})
