
"""RucHiGo App Update Manager.

Standalone Flask blueprint using the AndroidAppUpdate model
from models.py and the existing admin_logged_in session.
"""

import re
import secrets

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import SQLAlchemyError

# IMPORTANT: Import the model from your own models.py, not Flask.
from models import db, AndroidAppUpdate


app_updates_bp = Blueprint("app_updates", __name__)

VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def version_tuple(value):
    """Convert 1.2.3 into (1, 2, 3)."""
    return tuple(int(x) for x in value.split("."))


def get_settings():
    """Read the single application update settings record."""
    return db.session.get(AndroidAppUpdate, 1)


def admin_required():
    """Protect admin-only pages."""
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    return None


# ============================================================
# ADMIN APP UPDATE MANAGER
# URL: /admin/app-updates
# ============================================================

@app_updates_bp.route(
    "/admin/app-updates",
    methods=["GET", "POST"],
)
def manage_app_updates():

    denied = admin_required()
    if denied is not None:
        return denied

    settings = get_settings()

    if request.method == "POST":

        # CSRF security check
        token = session.get("app_updates_csrf")
        submitted_token = request.form.get("csrf_token", "")

        if (
            not token
            or not secrets.compare_digest(
                submitted_token,
                token,
            )
        ):
            abort(400, description="Invalid security token")

        latest = request.form.get(
            "latest_version", ""
        ).strip()

        minimum = request.form.get(
            "minimum_version", ""
        ).strip()

        message = request.form.get(
            "update_message", ""
        ).strip()

        enabled = request.form.get("enabled") == "on"

        # Validate version format
        if (
            not VERSION.fullmatch(latest)
            or not VERSION.fullmatch(minimum)
        ):
            flash(
                "Versions must use the format 1.2.3.",
                "error",
            )

        elif version_tuple(minimum) > version_tuple(latest):
            flash(
                "Minimum version cannot exceed latest version.",
                "error",
            )

        elif not message or len(message) > 1000:
            flash(
                "Enter release notes (1-1000 characters).",
                "error",
            )

        else:
            try:
                if settings is None:
                    settings = AndroidAppUpdate(id=1)
                    db.session.add(settings)

                settings.enabled = enabled
                settings.latest_version = latest
                settings.minimum_version = minimum
                settings.update_message = message

                db.session.commit()

                flash(
                    "App update settings saved successfully.",
                    "success",
                )

                return redirect(
                    url_for("app_updates.manage_app_updates")
                )

            except SQLAlchemyError:
                db.session.rollback()

                flash(
                    "Unable to save update settings. "
                    "Please try again.",
                    "error",
                )

    # Generate CSRF token for the admin form
    if "app_updates_csrf" not in session:
        session["app_updates_csrf"] = secrets.token_urlsafe(32)

    return render_template(
        "app_update_manager.html",
        settings=settings,
        csrf_token=session["app_updates_csrf"],
    )


# ============================================================
# PUBLIC FLUTTER VERSION API
# URL: /api/app/version-policy
# ============================================================

@app_updates_bp.get("/api/app/version-policy")
def version_policy():

    try:
        settings = get_settings()

        response = jsonify({
            "success": True,
            "enabled": (
                settings.enabled if settings else False
            ),
            "latest_version": (
                settings.latest_version if settings else "1.0.0"
            ),
            "minimum_version": (
                settings.minimum_version if settings else "1.0.0"
            ),
            "update_message": (
                settings.update_message
                if settings
                else "A new RucHiGo version is available."
            ),
        })

        response.headers["Cache-Control"] = "no-store"
        return response

    except SQLAlchemyError:
        db.session.rollback()

        response = jsonify({
            "success": False,
            "error": "Version settings temporarily unavailable",
        })

        response.headers["Cache-Control"] = "no-store"
        return response, 503
