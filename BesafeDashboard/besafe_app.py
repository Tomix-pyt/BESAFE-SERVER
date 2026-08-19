import os

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import join_room
from flask_cors import CORS
from flask_jwt_extended import (JWTManager, create_access_token,jwt_required, get_jwt_identity)
from datetime import timedelta
from config import Config
from db import (save_agency, get_agency_by_id, get_agency_by_email,get_agency_by_phone, update_agency, update_agency_password, verify_agency_password,
                update_agency_location, get_nearest_agencies,agencies_have_location,save_alert, get_alert_by_id, get_alerts_for_agency,update_alert_status, get_alert_counts_for_agency,
                save_location_ping, get_latest_location, get_location_track)
from utils import calculate_priority, priority_label, call_nlp_model
from db import get_reports_for_agency, get_report_by_id, get_report_counts_for_agency, update_report_status, update_report_analysis, update_alert_analysis
from modelApi import call_gpt_model
from auth.routes import auth_bp
from user.routes import user_bp
from safety.routes import safety_bp
from notifications.routes import notifications_bp
from safechat.routes import safechat_bp
from jobs.safety_check_job import start_safety_check_job
from socket_instance import socketio

import sys
sys.dont_write_bytecode = True

app = Flask(__name__)
app.config["SECRET_KEY"]               = Config.SECRET_KEY
app.config["JWT_SECRET_KEY"]           = Config.JWT_SECRET
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)
app.config["UPLOAD_FOLDER"]            = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MAPBOX_TOKEN"]            = Config.MAPBOX_TOKEN

CORS(app, origins="*")
socketio.init_app(app, cors_allowed_origins="*", logger=False, engineio_logger=False)
jwt      = JWTManager(app)

# ── Global error handlers
from exceptions import (
    AppException, BadRequestException, NotFoundException,
    UnauthorizedAccessException, ForbiddenAccessException,
    TooManyAttemptsException, ConflictException,
    UnprocessableEntityException, PayloadTooLargeException,
    InternalServerErrorException,
)

@app.errorhandler(AppException)
def handle_app_exception(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), error.status_code

@app.errorhandler(BadRequestException)
def handle_bad_request(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 400

@app.errorhandler(NotFoundException)
def handle_not_found(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 404

@app.errorhandler(UnauthorizedAccessException)
def handle_unauthorized(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 401

@app.errorhandler(ForbiddenAccessException)
def handle_forbidden(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 403

@app.errorhandler(TooManyAttemptsException)
def handle_too_many_attempts(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 429

@app.errorhandler(ConflictException)
def handle_conflict(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 409

@app.errorhandler(UnprocessableEntityException)
def handle_unprocessable(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 422

@app.errorhandler(PayloadTooLargeException)
def handle_payload_too_large(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 413

@app.errorhandler(InternalServerErrorException)
def handle_internal_error(error):
    return jsonify({"success": False, "message": error.message, "code": error.code}), 500

@app.errorhandler(400)
def handle_400(e):
    return jsonify({"success": False, "message": "Bad request", "code": 114}), 400

@app.errorhandler(401)
def handle_401(e):
    return jsonify({"success": False, "message": "Unauthorized", "code": 108}), 401

@app.errorhandler(403)
def handle_403(e):
    return jsonify({"success": False, "message": "Forbidden", "code": 109}), 403

@app.errorhandler(404)
def handle_404(e):
    return jsonify({"success": False, "message": "Route not found", "code": 117}), 404

@app.errorhandler(405)
def handle_405(e):
    return jsonify({"success": False, "message": "Method not allowed", "code": 114}), 405

@app.errorhandler(413)
def handle_413(e):
    return jsonify({"success": False, "message": "Request entity too large", "code": 115}), 413

@app.errorhandler(422)
def handle_422(e):
    return jsonify({"success": False, "message": "Unprocessable entity", "code": 116}), 422

@app.errorhandler(429)
def handle_429(e):
    return jsonify({"success": False, "message": "Too many requests", "code": 113}), 429

@app.errorhandler(500)
def handle_500(e):
    return jsonify({"success": False, "message": "Internal server error", "code": 101}), 500

# ── Register mobile app auth routes
app.register_blueprint(auth_bp, url_prefix="/v1/auth")
app.register_blueprint(user_bp, url_prefix="/v1/user")
app.register_blueprint(safety_bp, url_prefix="/v1/safety")
app.register_blueprint(notifications_bp, url_prefix="/v1/notifications")
app.register_blueprint(safechat_bp, url_prefix="/v1/safechat")


# ═══════════════════════════════════════════════════════════════
#  HELPER FUNTIONS
# ═══════════════════════════════════════════════════════════════

def serialize_alert(doc: dict) -> dict:
    """Convert a raw MongoDB alert document to a JSON-safe dict."""
    from datetime import datetime
    created = doc.get("created_at")
    if isinstance(created, datetime):
        created = created.isoformat()
    return {
        "id":               str(doc["_id"]),
        "user_id":          doc.get("user_id", ""),
        "user_name":        doc.get("user_name", "Unknown"),
        "user_phone":       doc.get("user_phone", ""),
        "user_photo":       doc.get("user_photo", ""),
        "transcribed_text": doc.get("transcribed_text", ""),
        "confidence":       round(float(doc.get("confidence", 0)), 4),
        "gps_lat":          doc.get("gps_lat"),
        "gps_lng":          doc.get("gps_lng"),
        "status":           doc.get("status", "active"),
        "analysis_status":  doc.get("analysis_status", "pending"),
        "ai_analysis":      doc.get("ai_analysis"),
        "sos_contacts":     doc.get("sos_contacts", []),
        "agency_id":        doc.get("agency_id", ""),
        "created_at":       created,
    }


def enrich(alert: dict) -> dict:
    """Attach computed priority score and label to a serialized alert."""
    p = calculate_priority(alert)
    alert["priority"]       = p
    alert["priority_label"] = priority_label(p)
    return alert


#  AUTHENTICATION — Agency register / login

@app.route("/",)
def home ():
    return render_template('home.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', mapbox_token=app.config["MAPBOX_TOKEN"])

@app.route('/login')
def login_page():
    return render_template('login.html', mapbox_token=app.config["MAPBOX_TOKEN"])


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/auth/register", methods=["POST"]) # route to registeration
def register():
    data = request.json or {}

# Validate top-level fields
    required_fields = [
        "name",
        "phone_number",
        "email",
        "password",
        "region"
    ]
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    # Validate location
    location = data.get("location")

    if not location:
        return jsonify({"error": "location is required"}), 400
    # Check duplicates
    if get_agency_by_email(data["email"]) or get_agency_by_phone(data["phone_number"]):
        return jsonify({"error": "Phone number or email already registered"}), 409

# Save agency
    new_id = save_agency(
        name=data["name"],
        phone_number=data["phone_number"],
        email=data["email"],
        password=data["password"],
        region=data["region"],
        lat=location["lat"],
        lng=location["lng"]
    )

    return jsonify({
        "success": True,"message": "Agency registered","id": new_id }), 201


@app.route("/auth/login", methods=["POST"]) #login route
def login():
    data   = request.json or {}
    agency = get_agency_by_email(data.get("email", ""))

    if not agency or not verify_agency_password(agency=agency, password=data.get("password")):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_access_token(identity=str(agency["_id"]))
    return jsonify({
        "token": token,
        "agency": {
            "id":     str(agency["_id"]),
            "name":   agency["name"],
            "email":  agency["email"],
            "region": agency["region"],
            "phone_number": agency.get("phone_number", ""),
            "location": agency.get("location"),
        }
    })


@app.route("/auth/me", methods=["GET"]) # this is to confirm that a jwt token is sill valid which i set to be an agency id
@jwt_required()
def me():
    agency = get_agency_by_id(get_jwt_identity())
    if not agency:
        return jsonify({"error": "Agency not found"}), 404
    return jsonify({
        "id":     str(agency["_id"]),
        "name":   agency["name"],
        "email":  agency["email"],
        "region": agency["region"],
        "phone_number": agency.get("phone_number", ""),
        "location": agency.get("location"),
    })


#  ALERT INTAKE — This is the api that will be called by the app, it is my though of it go through it and see what we can add and remove

@app.route("/alert", methods=["POST"])
def receive_alert():
    """
    Expected body:
    { 
        "transcribed_text": "...",
        "gps":        { "lat": 15.5, "lng": 32.5 },
        "user_id":    "...",
        "user_name":  "Fatima Ahmed",
        "user_phone": "+249912345678",
        "user_photo": "https://...",        (optional)
        "sos_contacts": ["+249912345678", "+249987654321"]
    }
    """
    data = request.json or {}
    for field in ["transcribed_text", "gps_lat","gps_lng", "user_id",
                  "user_name", "user_phone"]:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    # 1. Send transcribed text to NLP model
    label,confidence,x= call_nlp_model(data["transcribed_text"])
    if not label:
        return jsonify({"error": "NLP service unavailable"}), 503

    # 2. Only proceed if it's actually a threat
    if label != "Threat":
        return jsonify({"status": "Non-Threat", "confidence": confidence})

    # 3. Route alert to agency via location proximity or broadcast
    if agencies_have_location():
        try:
            target_agency = get_nearest_agencies(data["gps_lat"], data["gps_lng"], limit=1)
        except Exception as e:
             return jsonify({"error": e})
    if not target_agency:
        return jsonify({"message":"error in loading nearest agencies"})
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
            agency_id = str(target_agency[0]["_id"])
        )
    saved_doc = get_alert_by_id(alert_id)
    if saved_doc:
            payload = enrich(serialize_alert(saved_doc))
            agency_id = target_agency[0]["_id"]
            socketio.emit("new_alert", payload, to=f"agency_{agency_id}")

    return jsonify({
        "status":       "Threat",
        "confidence":   confidence,
        "alert_id":     str(alert_id),
        "agencies":     target_agency[0]["name"]
    })


# ═══════════════════════════════════════════════════════════════
#  AGENCY — Nearby lookup
# ═══════════════════════════════════════════════════════════════

@app.route("/v1/agency/nearby", methods=["GET"])
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

    nearest_agencies= get_nearest_agencies(lat, lng, limit=5)
    agencies = []
    for agency in nearest_agencies:
        loc = agency.get("location")
        agencies.append({
            "id": str(agency["_id"]),
            "name": agency.get("name", ""),
            "phone": agency.get("phone_number", ""),
            "location": {"lat": loc['coordinates'][0], "lng": loc['coordinates'][1]},
            "distance": round(agency.get("distance_metres", 0) / 1000, 2) if loc else None,
        })

    return jsonify({"agencies": agencies})


# ═══════════════════════════════════════════════════════════════
#  LIVE LOCATION — I was hoping this will be called by the app every 5–10 seconds
# ═══════════════════════════════════════════════════════════════

@app.route("/location/update", methods=["POST"])
def update_location():
    """
    Expected body: { "alert_id": "...", "lat": 15.5, "lng": 32.5 }
    The app calls this continuously while a threat is active.
    """
    data = request.json or {}
    for field in ["alert_id", "lat", "lng"]:
        if data.get(field) is None:
            return jsonify({"error": f"{field} is required"}), 400

    # Save the ping
    save_location_ping(
        alert_id=data["alert_id"],
        lat=data["lat"],
        lng=data["lng"]
    )

    # Forward the update to the dashboard via WebSocket
    try:
        alert = get_alert_by_id(data["alert_id"])
        if alert and alert.get("agency_id") and alert.get("status") != "resolved":
            socketio.emit("location_update", {
                "alert_id": data["alert_id"],
                "lat":      data["lat"],
                "lng":      data["lng"],
            }, to=f"agency_{alert['agency_id']}")
    except Exception as e:
        print(f"[LOCATION FORWARD ERROR] {e}")

    return jsonify({"status": "ok"})


# ═══════════════════════════════════════════════════════════════
#  DASHBOARD API — JWT protected (agency dashboard calls these)
# ═══════════════════════════════════════════════════════════════

@app.route("/alerts", methods=["GET"])
@jwt_required()
def get_alerts():
    """
    Returns all alerts for the logged-in agency, sorted by priority.
    Query param: ?status=active|acknowledged|resolved|all  (default: active)
    """
    agency_id = get_jwt_identity()
    status    = request.args.get("status", "active")

    raw    = get_alerts_for_agency(agency_id, status=status)
    result = [enrich(serialize_alert(a)) for a in raw]
    result.sort(key=lambda x: x["priority"], reverse=True)
    return jsonify(result)

@app.route("/agency/update", methods=["PATCH"]) # this is the route that is used in the setting to update the agncies stuff
@jwt_required()
def update_agency_details():
    """
    Agency updates their own name, region, phone, email.
    Body: { name, region, phone_number, email }
    """
    agency_id = get_jwt_identity()
    data      = request.json or {}

    for field in ["name", "region", "phone_number", "email"]:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    # Make sure the new phone number isn't already taken by another agency
    existing = get_agency_by_phone(data["phone_number"])
    if existing and str(existing["_id"]) != agency_id:
        return jsonify({"error": "Phone number is already registered to another agency"}), 409
    new_details ={
        "name":         data["name"],
        "region":       data["region"],
        "phone_number": data["phone_number"],
        "email":        data["email"].lower(),
    }
    updated = update_agency(agency_id,new_details )

    if not updated:
        return jsonify({"error": "Update failed"}), 500

    return jsonify({"success": True, "message": "Details updated successfully!"})


@app.route("/agency/location", methods=["PATCH"])
@jwt_required()
def set_agency_location():
    """
    Update the agency's headquarters location pin.
    Body: { "lat": 15.5007, "lng": 32.5599 }
    """
    agency_id = get_jwt_identity()
    data = request.json or {}
    lat = data.get("lat")
    lng = data.get("lng")
    if lat is None or lng is None:
        return jsonify({"error": "lat and lng are required"}), 400
    update_agency_location(agency_id, lat, lng)
    return jsonify({"success": True, "message": "Location Updated Successfully!"})


@app.route("/agency/password", methods=["PATCH"]) # this is to update the password in settings
@jwt_required()
def update_agency_password_route():
    """
    Agency changes their own password.
    Body: { current_password, new_password }
    """
    agency_id = get_jwt_identity()
    data      = request.json or {}

    current = data.get("current_password", "")
    new_pw  = data.get("new_password", "")

    agency = get_agency_by_id(agency_id)
    if not agency or not verify_agency_password(agency, current):
        return jsonify({"error": "Current password is incorrect"}), 401
    try:
        update_agency_password(agency_id, new_pw)
        return jsonify({"success": True, "message": "Password updated"})
    except Exception:
        return jsonify({"error":"Password update failed"})

# this is not implemented now for privacy reasons and other reasons
@app.route("/alerts/<alert_id>", methods=["GET"])
@jwt_required()
def get_alert(alert_id):
    """
    Returns a single alert with its full GPS track attached.
    This is usedd when an officer opens the detail panel and clicks Track Live.
    """
    doc = get_alert_by_id(alert_id)
    if not doc:
        return jsonify({"error": "Alert not found"}), 404

    result          = enrich(serialize_alert(doc))
    result["track"] = get_location_track(alert_id)   # full movement trail
    result["latest_location"] = get_latest_location(alert_id)
    return jsonify(result)


@app.route("/alerts/<alert_id>/status", methods=["PATCH"])
@jwt_required()
def patch_status(alert_id):
    """
    Officer marks an alert as acknowledged or resolved.
    Body: { "status": "acknowledged" | "resolved" }
    """
    data       = request.json or {}
    new_status = data.get("status")

    if new_status not in ("acknowledged", "resolved"):
        return jsonify({"error": "status must be 'acknowledged' or 'resolved'"}), 400

    updated = update_alert_status(alert_id, new_status)
    if not updated:
        return jsonify({"error": "Alert not found or already at that status"}), 404

    # Notify dashboard of the status change
    alert = get_alert_by_id(alert_id)
    if alert and alert.get("agency_id"):
        socketio.emit("alert_status_update", {
            "alert_id": alert_id,
            "status":   new_status,
        }, to=f"agency_{alert['agency_id']}")

    return jsonify({"status": "updated"})


@app.route("/stats", methods=["GET"]) # this is the route that is refreshed every 30 second bt the dashboard to get stats on the detail of alerts in thier database
@jwt_required()
def stats():
    """
    Returns alert counts for the navbar summary pills.
    { active, acknowledged, resolved, total }
    """
    agency_id = get_jwt_identity()
    return jsonify(get_alert_counts_for_agency(agency_id))


# ═══════════════════════════════════════════════════════════════
#  AGENCY — Safe Chat Reports dashboard
# ═══════════════════════════════════════════════════════════════

@app.route("/agency/reports", methods=["GET"])
@jwt_required()
def agency_get_reports():
    agency_id = get_jwt_identity()
    status = request.args.get("status", "all")
    raw = get_reports_for_agency(agency_id, status=status)
    result = [serialize_report_for_agency(r) for r in raw]
    return jsonify(result)


@app.route("/agency/reports/<report_id>", methods=["GET"])
@jwt_required()
def agency_get_report(report_id):
    agency_id = get_jwt_identity()
    report = get_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    if str(report.get("assignedAgencyId")) != agency_id:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(serialize_report_for_agency(report))


@app.route("/agency/reports/<report_id>/status", methods=["PATCH"])
@jwt_required()
def agency_update_report_status(report_id):
    agency_id = get_jwt_identity()
    data = request.json or {}
    new_status = data.get("status")

    if new_status not in ("triaged", "reviewing", "resolved", "closed"):
        return jsonify({"error": "status must be 'triaged', 'reviewing', 'resolved', or 'closed'"}), 400

    report = get_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    if str(report.get("assignedAgencyId")) != agency_id:
        return jsonify({"error": "Report not found"}), 404

    updated = update_report_status(report_id, new_status)
    if not updated:
        return jsonify({"error": "Report not found or already at that status"}), 404

    socketio.emit("report_status_update", {
        "report_id": report_id,
        "status": new_status,
    }, to=f"agency_{agency_id}")

    return jsonify({"status": "updated"})


@app.route("/agency/reports/<report_id>/analyze", methods=["POST"])
@jwt_required()
def agency_analyze_report(report_id):
    agency_id = get_jwt_identity()
    report = get_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    if str(report.get("assignedAgencyId")) != agency_id:
        return jsonify({"error": "Report not found"}), 404

    category = report.get("category", "")
    description = report.get("description", "")
    timing = report.get("timing", "")
    frequency = report.get("frequency", "")
    attachments = report.get("attachments", [])

    analysis = call_gpt_model(category, description, timing, frequency, attachments=attachments)
    if analysis.get("identified_pattern_type") == "Pipeline_Error":
        detail = analysis.get("error_message", "Unknown AI error")
        return jsonify({"error": "AI analysis failed", "detail": detail}), 500

    updated = update_report_analysis(report_id, analysis)
    if not updated:
        return jsonify({"error": "Failed to update report"}), 500

    socketio.emit("report_analyzed", {
        "report_id": report_id,
        "ai_Analysis": analysis,
    }, to=f"agency_{agency_id}")

    return jsonify({"success": True, "analysis": analysis})


@app.route("/alerts/<alert_id>/analyze", methods=["POST"])
@jwt_required()
def agency_analyze_alert(alert_id):
    agency_id = get_jwt_identity()
    alert = get_alert_by_id(alert_id)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404
    if str(alert.get("agency_id")) != agency_id:
        return jsonify({"error": "Alert not found"}), 404

    transcribed_text = alert.get("transcribed_text", "")

    analysis = call_gpt_model("threats", transcribed_text, "just-now", "first")
    if analysis.get("identified_pattern_type") == "Pipeline_Error":
        detail = analysis.get("error_message", "Unknown AI error")
        return jsonify({"error": "AI analysis failed", "detail": detail}), 500

    updated = update_alert_analysis(alert_id, analysis)
    if not updated:
        return jsonify({"error": "Failed to update alert"}), 500

    socketio.emit("alert_analyzed", {
        "alert_id": alert_id,
        "ai_analysis": analysis,
    }, to=f"agency_{agency_id}")

    return jsonify({"success": True, "analysis": analysis})


@app.route("/agency/reports/stats", methods=["GET"])
@jwt_required()
def agency_report_stats():
    agency_id = get_jwt_identity()
    return jsonify(get_report_counts_for_agency(agency_id))


def serialize_report_for_agency(doc):
    from datetime import datetime
    created = doc.get("createdAt")
    if isinstance(created, datetime):
        created = created.isoformat()
    updated = doc.get("updatedAt")
    if isinstance(updated, datetime):
        updated = updated.isoformat()
    loc = doc.get("location")
    return {
        "id": str(doc["_id"]),
        "userId": str(doc.get("userId", "")),
        "category": doc.get("category", ""),
        "description": doc.get("description", ""),
        "timing": doc.get("timing", ""),
        "frequency": doc.get("frequency", ""),
        "location": loc,
        "status": doc.get("status", "pending_analysis"),
        "priority": doc.get("priority", "low"),
        "assignedAgencyId": doc.get("assignedAgencyId"),
        "attachments": doc.get("attachments", []),
        "ai_Analysis": doc.get("ai_Analysis"),
        "createdAt": created,
        "updatedAt": updated,
    }


# ═══════════════════════════════════════════════════════════════
#  SOCKET.IO EVENTS
# ═══════════════════════════════════════════════════════════════

from auth.helpers import verify_jwt
from db import get_user_by_id

@socketio.on("connect")
def on_connect():
    print("[WS] Client connected")

@socketio.on("disconnect")
def on_disconnect():
    print("[WS] Client disconnected")

@socketio.on("join")
def on_join(data):
    agency_id = data.get("agency_id")
    if agency_id:
        join_room(f"agency_{agency_id}")
        print(f"[WS] Agency {agency_id} joined room")

@socketio.on("safety:auth")
def on_safety_auth(data):
    token = (data or {}).get("token", "").strip()
    if not token:
        return

    payload = verify_jwt(token, "access")
    if not payload:
        return

    user_id = payload.get("id")
    if not user_id:
        return

    user = get_user_by_id(user_id)
    if not user:
        return

    join_room(f"user_{user_id}")
    print(f"[WS] User {user_id} authenticated and joined room")

@socketio.on("safety:location")
def on_safety_location(data):
    data = data or {}
    token = data.get("token", "").strip()
    if not token:
        return

    payload = verify_jwt(token, "access")
    if not payload:
        return

    user_id = payload.get("id")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None or longitude is None:
        return

    user = get_user_by_id(user_id)
    if not user:
        return

    from services.safety_check_service import update_location

    loc = {"latitude": latitude, "longitude": longitude}
    update_location(user_id, loc)


# ═══════════════════════════════════════════════════════════════
#  BACKGROUND JOBS
# ═══════════════════════════════════════════════════════════════

start_safety_check_job()





# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    socketio.run(
        app,
        debug=Config.DEBUG,
    )
