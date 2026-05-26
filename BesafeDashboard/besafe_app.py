from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, join_room
from flask_cors import CORS
from flask_jwt_extended import (JWTManager, create_access_token,jwt_required, get_jwt_identity)
from datetime import timedelta
from config import Config
from db import (save_agency, get_agency_by_id, get_agency_by_email,get_agency_by_phone, update_agency, update_agency_password, 
                verify_agency_password,save_alert, get_alert_by_id, get_alerts_for_agency,update_alert_status, get_alert_counts_for_agency,
                save_location_ping, get_latest_location, get_location_track)
from utils import calculate_priority, priority_label, send_sms, call_nlp_api
from auth.routes import auth_bp
from user.routes import user_bp
from safety.routes import safety_bp
from notifications.routes import notifications_bp

app = Flask(__name__)
app.config["SECRET_KEY"]               = Config.SECRET_KEY
app.config["JWT_SECRET_KEY"]           = Config.JWT_SECRET
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)

CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)
jwt      = JWTManager(app)

# ── Register mobile app auth routes
app.register_blueprint(auth_bp, url_prefix="/v1/auth")
app.register_blueprint(user_bp, url_prefix="/v1/user")
app.register_blueprint(safety_bp, url_prefix="/v1/safety")
app.register_blueprint(notifications_bp, url_prefix="/v1/notifications")


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
        "agency_id":        doc.get("agency_id", ""),
        "created_at":       created,
    } # this is to make sure the data gets in the database as it should without changing form


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
    return render_template('dashboard.html')  

@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route("/auth/register", methods=["POST"]) # route to registeration
def register():
    data = request.json or {}
    for field in ["name", "phone_number", "email", "password", "region"]:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400
    if get_agency_by_email(email=data['email']) or get_agency_by_phone(data['phone_number']):
        new_id=None
    else:
        new_id = save_agency(
            name=data["name"],
            phone_number=data["phone_number"],
            email=data["email"],
            password=data["password"],
            region=data["region"]
        )

    if new_id is None:
        return jsonify({"error": "Phone number or email already registered"}), 409

    return jsonify({"message": "Agency registered", "id": new_id}), 201


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
                  "user_name", "user_phone", "sos_contacts"]:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    # 1. Send transcribed text to the hosted NLP model
    prediction = call_nlp_api(data["transcribed_text"])
    if not prediction:
        return jsonify({"error": "NLP service unavailable"}), 503

    label      = prediction.get("prediction")
    confidence = float(prediction.get("confidence"))

    # 2. Only proceed if it's actually a threat
    if label != "Threat":
        return jsonify({"status": "Non-Threat", "confidence": confidence})

    # 3. Check each SOS contact — is it a registered agency or a family member?
    matched_agency = None
    for phone in data["sos_contacts"]:
        agency = get_agency_by_phone(phone)
        print(agency)
        if agency:
            matched_agency = agency     # this contact is a registered agency
        # else: THIS IS THE FUNTION I WROTE TO SEND SOS BUT I AM HAVING ISSUES FOR NOW SINCE AM TRYING TO UNDERSTAND THE PLATFORM BETTER
        #     # Regular contact — send SMS only
        #     send_sms(
        #         phone,
        #         f"SOS — {data['user_name']} may be in danger.\n"
        #         f"Location: https://maps.google.com/?q="
        #         f"https://maps.google.com/?q={data['gps_lat']},{data['gps_lng']}"
        #     )
        print('Sending message')

    # 4. Save the alert to MongoDB
    alert_id = save_alert(
        user_id=data["user_id"],
        user_name=data["user_name"],
        user_phone=data["user_phone"],
        user_photo=data.get("user_photo", ""),
        transcribed_text=data["transcribed_text"],
        confidence=confidence,
        gps_lat=data["gps_lat"],
        gps_lng=data["gps_lng"],
        sos_contacts=data["sos_contacts"],
        agency_id=str(matched_agency["_id"]) if matched_agency else None
    )

    # 5. Push to the matched agency's dashboard room via WebSocket
    if matched_agency:
        saved_doc = get_alert_by_id(alert_id)
        if saved_doc:
            payload = enrich(serialize_alert(saved_doc))
            socketio.emit(
                "new_alert", payload,
                room=f"agency_{str(matched_agency['_id'])}"
            )

    return jsonify({
        "status":     "threat",
        "alert_id":   alert_id,
        "confidence": confidence
    })


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
            }, room=f"agency_{alert['agency_id']}")
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

    # Make sure the new phone isn't already taken by another agency
    existing = get_agency_by_phone(data["phone_number"])
    if existing and str(existing["_id"]) != agency_id:
        return jsonify({"error": "That phone number is already registered to another agency"}), 409
    new_details ={
        "name":         data["name"],
        "region":       data["region"],
        "phone_number": data["phone_number"],
        "email":        data["email"].lower(),
    }
    updated = update_agency(agency_id,new_details )

    if not updated:
        return jsonify({"error": "Update failed"}), 500

    return jsonify({"message": "Details updated"})


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
        return jsonify({"message": "Password updated"})
    except Exception:
        return jsonify({"error":"Password update failed"})


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
        }, room=f"agency_{alert['agency_id']}")

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
#  SOCKET.IO EVENTS
# ═══════════════════════════════════════════════════════════════

@socketio.on("connect")
def on_connect():
    print("[WS] Client connected")

@socketio.on("join")
def on_join(data):
    agency_id = data.get("agency_id")
    if agency_id:
        join_room(f"agency_{agency_id}")
        print(f"[WS] Agency {agency_id} joined room") # my debug code

@socketio.on("disconnect")
def on_disconnect():
    print("[WS] Client disconnected")


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    socketio.run(
        app,
        debug=Config.DEBUG
    )
