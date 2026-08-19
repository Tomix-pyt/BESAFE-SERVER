from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from db import (
    save_alert,
    get_alert_by_id,
    get_alerts_for_agency,
    update_alert_status,
    assign_alert_staff,
    update_alert_analysis,
    save_location_ping,
    get_latest_location,
    get_location_track,
    get_staff_by_id,
    get_nearest_agencies,
    agencies_have_location,
)
from utils import calculate_priority, priority_label, call_nlp_model
from modelApi import call_gpt_model
from socket_instance import socketio

alerts_bp = Blueprint("alerts", __name__)


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def serialize_alert(doc: dict) -> dict:
    """Convert a raw MongoDB alert document to a JSON-safe dict."""
    if not doc:
        return None
    created = doc.get("created_at")
    if isinstance(created, datetime):
        created = created.isoformat()
    assigned_at = doc.get("assigned_at")
    if isinstance(assigned_at, datetime):
        assigned_at = assigned_at.isoformat()
    return {
        "id":                  str(doc["_id"]),
        "user_id":             doc.get("user_id", ""),
        "user_name":           doc.get("user_name", "Unknown"),
        "user_phone":          doc.get("user_phone", ""),
        "user_photo":          doc.get("user_photo", ""),
        "transcribed_text":    doc.get("transcribed_text", ""),
        "confidence":          round(float(doc.get("confidence", 0)), 4),
        "gps_lat":             doc.get("gps_lat"),
        "gps_lng":             doc.get("gps_lng"),
        "status":              doc.get("status", "active"),
        "analysis_status":     doc.get("analysis_status", "pending"),
        "ai_analysis":         doc.get("ai_analysis"),
        "sos_contacts":        doc.get("sos_contacts", []),
        "agency_id":           doc.get("agency_id", ""),
        "assigned_staff_id":   doc.get("assigned_staff_id"),
        "assigned_staff_name": doc.get("assigned_staff_name"),
        "assigned_at":         assigned_at,
        "created_at":          created,
    }


def enrich(alert: dict) -> dict:
    """Attach computed priority score and label to a serialized alert."""
    if not alert:
        return {}
    p = calculate_priority(alert)
    alert["priority"] = p
    alert["priority_label"] = priority_label(p)
    return alert


# ─────────────────────────────────────────────────────────────
#  1. MOBILE SOS INTAKE (Citizen Mobile App Trigger)
# ─────────────────────────────────────────────────────────────

@alerts_bp.route("/alert", methods=["POST"])
def receive_alert():
    """
    Called by citizen mobile app when a voice distress trigger or SOS is activated.
    """
    data = request.json or {}
    for field in ["transcribed_text", "gps_lat", "gps_lng", "user_id", "user_name", "user_phone"]:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    # 1. Send transcribed text to NLP model
    label, confidence, _ = call_nlp_model(data["transcribed_text"])
    if not label:
        return jsonify({"error": "NLP service unavailable"}), 503

    # 2. Only proceed if it's actually a threat
    if label != "Threat":
        return jsonify({"status": "Non-Threat", "confidence": confidence})

    # 3. Route alert to agency via location proximity
    target_agency = None
    if agencies_have_location():
        try:
            target_agency = get_nearest_agencies(data["gps_lat"], data["gps_lng"], limit=1)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if not target_agency:
        return jsonify({"message": "Error in locating nearest emergency agencies"}), 500

    alert_id = save_alert(
        user_id=data["user_id"],
        user_name=data["user_name"],
        user_phone=data["user_phone"],
        user_photo=data.get("user_photo", ""),
        transcribed_text=data["transcribed_text"],
        confidence=confidence,
        label=label,
        gps_lat=data["gps_lat"],
        gps_lng=data["gps_lng"],
        agency_id=str(target_agency[0]["_id"])
    )

    saved_doc = get_alert_by_id(alert_id)
    if saved_doc:
        payload = enrich(serialize_alert(saved_doc))
        agency_id = target_agency[0]["_id"]
        socketio.emit("new_alert", payload, to=f"agency_{agency_id}")

    return jsonify({
        "status": "Threat",
        "confidence": confidence,
        "alert_id": str(alert_id),
        "agency_name": target_agency[0]["name"]
    })


@alerts_bp.route("/v1/agency/nearby", methods=["GET"])
def agency_nearby():
    """
    Returns agencies sorted by distance from the given lat/lng.
    Query: ?lat=6.5244&lng=3.3792&limit=10
    """
    try:
        lat = float(request.args.get("lat", 0))
        lng = float(request.args.get("lng", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "lat and lng are required numeric params"}), 400

    nearest_agencies = get_nearest_agencies(lat, lng, limit=5)
    agencies = []
    for agency in nearest_agencies:
        loc = agency.get("location")
        agencies.append({
            "id": str(agency["_id"]),
            "name": agency.get("name", ""),
            "phone": agency.get("phone_number", ""),
            "location": {"lat": loc['coordinates'][0], "lng": loc['coordinates'][1]} if loc else None,
            "distance": round(agency.get("distance_metres", 0) / 1000, 2) if loc else None,
        })

    return jsonify({"agencies": agencies})


# ─────────────────────────────────────────────────────────────
#  2. AGENCY ALERTS MANAGEMENT (Feed, Status, Assign, XAI)
# ─────────────────────────────────────────────────────────────

@alerts_bp.route("/alerts", methods=["GET"])
@jwt_required()
def get_alerts():
    agency_id = get_jwt_identity()
    status = request.args.get("status")
    limit = int(request.args.get("limit", 100))

    raw = get_alerts_for_agency(agency_id, status=status, limit=limit)
    result = [enrich(serialize_alert(a)) for a in raw]
    return jsonify(result)


@alerts_bp.route("/alerts/<alert_id>", methods=["GET"])
@jwt_required()
def get_alert(alert_id):
    doc = get_alert_by_id(alert_id)
    if not doc:
        return jsonify({"error": "Alert not found"}), 404
    result = enrich(serialize_alert(doc))
    return jsonify(result)


@alerts_bp.route("/alerts/<alert_id>/status", methods=["PATCH"])
@jwt_required()
def patch_status(alert_id):
    data = request.json or {}
    new_status = data.get("status")

    if new_status not in ("acknowledged", "resolved"):
        return jsonify({"error": "status must be 'acknowledged' or 'resolved'"}), 400

    updated = update_alert_status(alert_id, new_status)
    if not updated:
        return jsonify({"error": "Alert not found or already at that status"}), 404

    alert = get_alert_by_id(alert_id)
    if alert and alert.get("agency_id"):
        socketio.emit("alert_status_update", {
            "alert_id": alert_id,
            "status": new_status,
        }, to=f"agency_{alert['agency_id']}")

    return jsonify({"status": "updated"})


@alerts_bp.route("/alerts/<alert_id>/assign", methods=["PATCH"])
@jwt_required()
def assign_alert_route(alert_id):
    data = request.json or {}
    staff_id = data.get("staff_id")
    staff_name = data.get("staff_name")

    if staff_id and not staff_name:
        staff = get_staff_by_id(staff_id)
        if staff:
            staff_name = staff.get("name", "Dispatcher")

    success = assign_alert_staff(alert_id, staff_id, staff_name)
    if not success:
        return jsonify({"error": "Alert not found or assignment failed"}), 404

    agency_id = get_jwt_identity()
    socketio.emit("alert_assigned", {
        "alert_id": alert_id,
        "staff_id": staff_id,
        "staff_name": staff_name,
    }, to=f"agency_{agency_id}")

    return jsonify({
        "success": True,
        "message": f"Alert assigned to {staff_name}" if staff_id else "Alert unassigned",
        "assigned_staff_id": staff_id,
        "assigned_staff_name": staff_name,
    })


@alerts_bp.route("/alerts/<alert_id>/analyze", methods=["POST"])
@jwt_required()
def analyze_alert_route(alert_id):
    alert = get_alert_by_id(alert_id)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404

    category = alert.get("label", "Threat")
    description = alert.get("transcribed_text", "")
    timing = "Ongoing Emergency"
    frequency = "Immediate Dispatch Required"

    analysis = call_gpt_model(category, description, timing, frequency)
    if analysis.get("identified_pattern_type") == "Pipeline_Error":
        return jsonify({"error": "AI analysis pipeline failed", "details": analysis}), 502

    update_alert_analysis(alert_id, analysis)

    return jsonify({
        "success": True,
        "analysis": analysis,
        "status": "triaged"
    })


# ─────────────────────────────────────────────────────────────
#  3. LIVE GPS LOCATION TELEMETRY & VECTOR TRACKING
# ─────────────────────────────────────────────────────────────

@alerts_bp.route("/location/update", methods=["POST"])
@alerts_bp.route("/alerts/<alert_id>/location", methods=["POST"])
def update_location(alert_id=None):
    data = request.json or {}
    target_alert_id = alert_id or data.get("alert_id")
    lat = data.get("lat")
    lng = data.get("lng")

    if not target_alert_id or lat is None or lng is None:
        return jsonify({"error": "alert_id, lat, and lng are required"}), 400

    save_location_ping(
        alert_id=target_alert_id,
        lat=lat,
        lng=lng
    )

    try:
        alert = get_alert_by_id(target_alert_id)
        if alert and alert.get("agency_id") and alert.get("status") != "resolved":
            socketio.emit("location_update", {
                "alert_id": target_alert_id,
                "lat": float(lat),
                "lng": float(lng),
                "recorded_at": datetime.now().isoformat()
            }, to=f"agency_{alert['agency_id']}")
    except Exception as e:
        print(f"[Location Ping Error]: {e}")

    return jsonify({"status": "received"})


@alerts_bp.route("/alerts/<alert_id>/location", methods=["GET"])
@jwt_required()
def get_alert_location(alert_id):
    loc = get_latest_location(alert_id)
    if not loc:
        return jsonify({"error": "No location data for this alert"}), 404
    return jsonify({
        "alert_id": alert_id,
        "lat": loc["lat"],
        "lng": loc["lng"],
        "recorded_at": loc["recorded_at"].isoformat()
    })


@alerts_bp.route("/alerts/<alert_id>/track", methods=["GET"])
@jwt_required()
def get_alert_track(alert_id):
    points = get_location_track(alert_id)
    return jsonify({
        "alert_id": alert_id,
        "point_count": len(points),
        "track": points
    })
