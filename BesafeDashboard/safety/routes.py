from flask import Blueprint, g, jsonify, request

from auth.middleware import require_auth, require_onboarded
from db import get_user_by_id
from services.sos_service import send_sos

safety_bp = Blueprint("safety", __name__)


@safety_bp.route("/sos", methods=["POST"])
@require_auth
@require_onboarded
def sos():
    data = request.get_json(silent=True) or {}
    message = data.get("message")
    location = data.get("location")

    payload = {}
    if isinstance(message, str):
        payload["message"] = message
    if (
        isinstance(location, dict)
        and isinstance(location.get("latitude"), (int, float))
        and isinstance(location.get("longitude"), (int, float))
    ):
        payload["location"] = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
        }

    user_id = str(g.current_user["_id"])
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404
    if not user.get("emergencyContacts"):
        return jsonify({"message": "No emergency contacts on file. Add contacts before sending SOS."}), 400

    try:
        result = send_sos(user, payload)
        return jsonify({"message": "SOS dispatched", "data": result}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
