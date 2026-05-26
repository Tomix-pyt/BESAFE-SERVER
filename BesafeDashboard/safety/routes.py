from flask import Blueprint, g, jsonify, request

from auth.middleware import require_auth, require_onboarded
from db import get_user_by_id
from services.safety_check_service import (
    cancel,
    confirm,
    extend,
    get_active,
    start,
    stop,
    update_location,
)
from services.safety_service import analyze_text
from services.sos_service import send_sos

safety_bp = Blueprint("safety", __name__)


# ── POST /analyze
@safety_bp.route("/analyze", methods=["POST"])
@require_auth
def analyze():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"message": "Text is required"}), 400

    try:
        result = analyze_text(text, str(g.current_user["_id"]))
        return jsonify({"message": "Analysis complete", "data": result}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 503


# ── POST /sos
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


# ── POST /check-in/start
@safety_bp.route("/check-in/start", methods=["POST"])
@require_auth
def check_in_start():
    data = request.get_json(silent=True) or {}
    activity = data.get("activity", "").strip()
    interval_minutes = data.get("intervalMinutes")

    if not activity:
        return jsonify({"message": "Activity is required"}), 400
    if not interval_minutes:
        return jsonify({"message": "Interval is required"}), 400

    user_id = str(g.current_user["_id"])
    check = start(
        user_id=user_id,
        activity=activity,
        interval_minutes=int(interval_minutes),
        contact_ids=data.get("contactIds", []),
    )

    check["_id"] = str(check["_id"])
    return jsonify({"message": "Safety check started", "data": {"check": check}}), 200


# ── POST /check-in/confirm
@safety_bp.route("/check-in/confirm", methods=["POST"])
@require_auth
def check_in_confirm():
    try:
        check = confirm(str(g.current_user["_id"]))
        check["_id"] = str(check["_id"])
        return jsonify({"message": "Safety check confirmed", "data": {"check": check}}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 404


# ── POST /check-in/cancel
@safety_bp.route("/check-in/cancel", methods=["POST"])
@require_auth
def check_in_cancel():
    result = cancel(str(g.current_user["_id"]))
    return jsonify({"message": "Safety check cancelled", "data": result}), 200


# ── GET /check-in/active
@safety_bp.route("/check-in/active", methods=["GET"])
@require_auth
def check_in_active():
    check = get_active(str(g.current_user["_id"]))
    if check:
        check["_id"] = str(check["_id"])
    return jsonify({"message": "Active safety check", "data": {"check": check}}), 200


# ── POST /check-in/extend
@safety_bp.route("/check-in/extend", methods=["POST"])
@require_auth
def check_in_extend():
    data = request.get_json(silent=True) or {}
    additional_minutes = data.get("additionalMinutes")
    if not additional_minutes:
        return jsonify({"message": "Additional minutes are required"}), 400

    try:
        check = extend(str(g.current_user["_id"]), int(additional_minutes))
        check["_id"] = str(check["_id"])
        return jsonify({"message": "Safety check extended", "data": {"check": check}}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 404


# ── PATCH /check-in/location
@safety_bp.route("/check-in/location", methods=["PATCH"])
@require_auth
def check_in_location():
    data = request.get_json(silent=True) or {}
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None or longitude is None:
        return jsonify({"message": "Latitude and longitude are required"}), 400

    check = update_location(str(g.current_user["_id"]), {"latitude": latitude, "longitude": longitude})
    if check:
        check["_id"] = str(check["_id"])
    return jsonify({"message": "Location updated", "data": {"check": check}}), 200


# ── POST /check-in/stop
@safety_bp.route("/check-in/stop", methods=["POST"])
@require_auth
def check_in_stop():
    data = request.get_json(silent=True) or {}
    end_location = data.get("endLocation")

    try:
        check = stop(str(g.current_user["_id"]), end_location)
        check["_id"] = str(check["_id"])
        return jsonify({"message": "Safety check stopped", "data": {"check": check}}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 404
