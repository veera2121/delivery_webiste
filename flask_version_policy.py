
from flask import Blueprint, jsonify

version_policy_bp = Blueprint(
    "version_policy",
    __name__
)

@version_policy_bp.route(
    "/api/app/version",
    methods=["GET"]
)
def get_app_version():
    return jsonify({
        "latest_version": "1.0.0",
        "minimum_version": "1.0.0",
        "update_message": "Welcome to RucHiGo!",
        "force_update": False,
        "update_available": False
    }), 200
