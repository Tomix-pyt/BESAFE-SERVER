from flask import Blueprint, g, request

from auth.middleware import require_auth, require_onboarded
from db import get_user_by_id, update_alert_status, get_alert_by_id
from models.alert import get_active_alerts_for_user
from exceptions import (
    BadRequestException,
    NotFoundException,
    InternalServerErrorException,
)
from helpers.response import ok_response
from socket_instance import socketio
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
        raise BadRequestException("Text is required")

    try:
        result = analyze_text(text, str(g.current_user["_id"]))
        return ok_response("Analysis complete", result)
    except Exception as e:
        raise InternalServerErrorException(str(e))


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
        raise NotFoundException("User not found")
    if not user.get("emergencyContacts"):
        raise BadRequestException("No emergency contacts on file. Add contacts before sending SOS.")

    try:
        result = send_sos(user, payload)
        return ok_response("SOS dispatched", result)
    except Exception as e:
        raise InternalServerErrorException(str(e))


# ── POST /im-safe
@safety_bp.route("/im-safe", methods=["POST"])
@require_auth
def im_safe():
    user_id = str(g.current_user["_id"])

    active_alerts = get_active_alerts_for_user(user_id)
    if not active_alerts:
        return ok_response("No active alerts found", {"notifiedAgencies": 0})

    notified = set()
    for alert in active_alerts:
        update_alert_status(str(alert["_id"]), "resolved")
        agency_id = alert.get("agency_id")
        if agency_id:
            socketio.emit("alert_status_update", {
                "alert_id": str(alert["_id"]),
                "status": "resolved",
                "im_safe": True,
            }, room=f"agency_{agency_id}")
            notified.add(agency_id)

    return ok_response("I'm Safe acknowledged", {"notifiedAgencies": len(notified)})


# ── POST /check-in/start
@safety_bp.route("/check-in/start", methods=["POST"])
@require_auth
def check_in_start():
    data = request.get_json(silent=True) or {}
    activity = data.get("activity", "").strip()
    interval_minutes = data.get("intervalMinutes")

    if not activity:
        raise BadRequestException("Activity is required")
    if not interval_minutes:
        raise BadRequestException("Interval is required")

    user_id = str(g.current_user["_id"])
    check = start(
        user_id=user_id,
        activity=activity,
        interval_minutes=int(interval_minutes),
        contact_ids=data.get("contactIds", []),
    )

    check["_id"] = str(check["_id"])
    return ok_response("Safety check started", {"check": check})


# ── POST /check-in/confirm
@safety_bp.route("/check-in/confirm", methods=["POST"])
@require_auth
def check_in_confirm():
    try:
        check = confirm(str(g.current_user["_id"]))
        check["_id"] = str(check["_id"])
        return ok_response("Safety check confirmed", {"check": check})
    except Exception as e:
        raise NotFoundException(str(e))


# ── POST /check-in/cancel
@safety_bp.route("/check-in/cancel", methods=["POST"])
@require_auth
def check_in_cancel():
    result = cancel(str(g.current_user["_id"]))
    return ok_response("Safety check cancelled", result)


# ── GET /check-in/active
@safety_bp.route("/check-in/active", methods=["GET"])
@require_auth
def check_in_active():
    check = get_active(str(g.current_user["_id"]))
    if check:
        check["_id"] = str(check["_id"])
    return ok_response("Active safety check", {"check": check})


# ── POST /check-in/extend
@safety_bp.route("/check-in/extend", methods=["POST"])
@require_auth
def check_in_extend():
    data = request.get_json(silent=True) or {}
    additional_minutes = data.get("additionalMinutes")
    if not additional_minutes:
        raise BadRequestException("Additional minutes are required")

    try:
        check = extend(str(g.current_user["_id"]), int(additional_minutes))
        check["_id"] = str(check["_id"])
        return ok_response("Safety check extended", {"check": check})
    except Exception as e:
        raise NotFoundException(str(e))


# ── PATCH /check-in/location
@safety_bp.route("/check-in/location", methods=["PATCH"])
@require_auth
def check_in_location():
    data = request.get_json(silent=True) or {}
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None or longitude is None:
        raise BadRequestException("Latitude and longitude are required")

    check = update_location(str(g.current_user["_id"]), {"latitude": latitude, "longitude": longitude})
    if check:
        check["_id"] = str(check["_id"])
    return ok_response("Location updated", {"check": check})


# ── POST /check-in/stop
@safety_bp.route("/check-in/stop", methods=["POST"])
@require_auth
def check_in_stop():
    data = request.get_json(silent=True) or {}
    end_location = data.get("endLocation")

    try:
        check = stop(str(g.current_user["_id"]), end_location)
        check["_id"] = str(check["_id"])
        return ok_response("Safety check stopped", {"check": check})
    except Exception as e:
        raise NotFoundException(str(e))
