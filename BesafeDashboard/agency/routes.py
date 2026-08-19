from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

from db import (
    save_agency,
    get_agency_by_id,
    get_agency_by_email,
    get_agency_by_phone,
    update_agency,
    update_agency_password,
    verify_agency_password,
    update_agency_location,
    get_all_agencies,
    verify_agency_status,
    serialize_agency,
    save_staff,
    get_staff_by_id,
    get_staff_by_email,
    get_staff_for_agency,
    update_staff_role,
    update_staff_status,
    change_staff_password,
    verify_staff_password,
    delete_staff,
    serialize_staff,
    get_reports_for_agency,
    get_report_by_id,
    get_report_counts_for_agency,
    update_report_status,
    assign_report_staff,
    update_report_analysis,
    get_dashboard_overview_stats,
    get_alert_counts_for_agency,
)
from modelApi import call_gpt_model
from socket_instance import socketio

agency_bp = Blueprint("agency", __name__)


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def serialize_report_for_agency(doc):
    if not doc:
        return None
    created = doc.get("createdAt")
    if isinstance(created, datetime):
        created = created.isoformat()
    updated = doc.get("updatedAt")
    if isinstance(updated, datetime):
        updated = updated.isoformat()
    assigned_at = doc.get("assigned_at")
    if isinstance(assigned_at, datetime):
        assigned_at = assigned_at.isoformat()
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
        "assigned_staff_id": doc.get("assigned_staff_id"),
        "assigned_staff_name": doc.get("assigned_staff_name"),
        "assigned_at": assigned_at,
        "attachments": doc.get("attachments", []),
        "ai_Analysis": doc.get("ai_Analysis"),
        "createdAt": created,
        "updatedAt": updated,
    }


# ─────────────────────────────────────────────────────────────
#  1. AUTHENTICATION (Station Admins & Dispatchers)
# ─────────────────────────────────────────────────────────────

@agency_bp.route("/auth/register", methods=["POST"])
def register():
    data = request.json or {}
    required_fields = ["name", "phone_number", "email", "password", "region"]
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    location = data.get("location") or {}
    if "lat" not in location or "lng" not in location:
        return jsonify({"error": "Location object with 'lat' and 'lng' is required"}), 400

    if get_agency_by_email(data["email"]):
        return jsonify({"error": "An agency with this email already exists"}), 409
    if get_agency_by_phone(data["phone_number"]):
        return jsonify({"error": "An agency with this phone number already exists"}), 409

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
        "success": True,
        "message": "Agency registered successfully",
        "id": new_id
    }), 201


@agency_bp.route("/agency/auth/login", methods=["POST"])
@agency_bp.route("/auth/login", methods=["POST"])
def login():
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    # 1. Check Agency Account (Station Admin / Creator)
    agency = get_agency_by_email(email)
    if agency and verify_agency_password(agency=agency, password=password):
        token = create_access_token(identity=str(agency["_id"]))
        agency_data = serialize_agency(agency)
        return jsonify({
            "token": token,
            "must_change_password": False,
            "agency": agency_data,
            "user": {
                "id": str(agency["_id"]),
                "name": agency["name"],
                "email": agency["email"],
                "role": agency.get("role", "AGENCY_ADMIN"),
                "agency_id": str(agency["_id"]),
                "must_change_password": False,
            }
        })

    # 2. Check Agency Staff Account (Dispatchers)
    staff = get_staff_by_email(email)
    if staff and verify_staff_password(staff, password):
        if not staff.get("is_active", True):
            return jsonify({"error": "Your staff account has been deactivated by the agency administrator."}), 403

        assigned_agency = get_agency_by_id(staff["agency_id"])
        token = create_access_token(identity=str(staff["agency_id"]))
        must_change = staff.get("must_change_password", False)
        return jsonify({
            "token": token,
            "must_change_password": must_change,
            "agency": serialize_agency(assigned_agency) if assigned_agency else None,
            "user": {
                "id": str(staff["_id"]),
                "name": staff["name"],
                "email": staff["email"],
                "role": staff.get("role", "DISPATCHER"),
                "agency_id": str(staff["agency_id"]),
                "must_change_password": must_change,
            }
        })

    return jsonify({"error": "Invalid email or password"}), 401


@agency_bp.route("/agency/auth/me", methods=["GET"])
@agency_bp.route("/auth/me", methods=["GET"])
@jwt_required()
def me():
    agency = get_agency_by_id(get_jwt_identity())
    if not agency:
        return jsonify({"error": "Agency not found"}), 404
    return jsonify(serialize_agency(agency))


@agency_bp.route("/agency/auth/change-initial-password", methods=["PATCH"])
@agency_bp.route("/auth/change-initial-password", methods=["PATCH"])
@jwt_required()
def change_initial_password_route():
    data = request.json or {}
    new_password = data.get("new_password")
    staff_id = data.get("staff_id")
    email = (data.get("email") or "").strip().lower()

    if not new_password or len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    staff = None
    if staff_id:
        staff = get_staff_by_id(staff_id)
    elif email:
        staff = get_staff_by_email(email)

    if not staff:
        return jsonify({"error": "Staff account not found"}), 404

    success = change_staff_password(str(staff["_id"]), new_password)
    if not success:
        return jsonify({"error": "Failed to update password"}), 500

    return jsonify({"success": True, "message": "Permanent password successfully set!"})


# ─────────────────────────────────────────────────────────────
#  2. AGENCY SETTINGS (Identity, HQ Geolocation, Password)
# ─────────────────────────────────────────────────────────────

@agency_bp.route("/agency/details", methods=["PATCH"])
@jwt_required()
def update_agency_details():
    agency_id = get_jwt_identity()
    new_details = request.json or {}
    updated = update_agency(agency_id, new_details)
    if not updated:
        return jsonify({"error": "Update failed"}), 500
    return jsonify({"success": True, "message": "Details updated successfully!"})


@agency_bp.route("/agency/location", methods=["PATCH"])
@jwt_required()
def set_agency_location():
    agency_id = get_jwt_identity()
    data = request.json or {}
    lat = data.get("lat")
    lng = data.get("lng")
    if lat is None or lng is None:
        return jsonify({"error": "lat and lng are required"}), 400
    update_agency_location(agency_id, lat, lng)
    return jsonify({"success": True, "message": "Location Updated Successfully!"})


@agency_bp.route("/agency/password", methods=["PATCH"])
@jwt_required()
def update_agency_password_route():
    agency_id = get_jwt_identity()
    data = request.json or {}
    current = data.get("current_password", "")
    new_pw = data.get("new_password", "")

    agency = get_agency_by_id(agency_id)
    if not agency or not verify_agency_password(agency, current):
        return jsonify({"error": "Current password is incorrect"}), 401
    try:
        update_agency_password(agency_id, new_pw)
        return jsonify({"success": True, "message": "Password updated"})
    except Exception:
        return jsonify({"error": "Password update failed"}), 500


# ─────────────────────────────────────────────────────────────
#  3. STATION TEAM MANAGEMENT & RBAC
# ─────────────────────────────────────────────────────────────

@agency_bp.route("/agency/team", methods=["GET"])
@jwt_required()
def list_agency_team():
    agency_id = get_jwt_identity()
    staff_members = get_staff_for_agency(agency_id)
    return jsonify([serialize_staff(s) for s in staff_members])


@agency_bp.route("/agency/team", methods=["POST"])
@jwt_required()
def add_agency_staff():
    agency_id = get_jwt_identity()
    data = request.json or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone_number") or "").strip()
    password = data.get("password") or "Besafe123!"

    if not name or not email:
        return jsonify({"error": "Name and official email are required."}), 400

    result = save_staff(
        agency_id=agency_id,
        name=name,
        email=email,
        phone=phone,
        password=password,
        role="DISPATCHER",
        created_by=agency_id
    )

    if not result.get("success"):
        return jsonify({"error": result.get("message", "Failed to add dispatcher.")}), 400

    staff_doc = get_staff_by_id(result["staff_id"])
    return jsonify({"success": True, "member": serialize_staff(staff_doc)}), 201


@agency_bp.route("/agency/team/<staff_id>/status", methods=["PATCH"])
@jwt_required()
def set_staff_status(staff_id):
    data = request.json or {}
    is_active = data.get("is_active")
    if is_active is None:
        return jsonify({"error": "is_active boolean field is required."}), 400

    updated = update_staff_status(staff_id, bool(is_active))
    if not updated:
        return jsonify({"error": "Staff member not found or update failed."}), 404

    return jsonify({"success": True, "is_active": bool(is_active)})


@agency_bp.route("/agency/team/<staff_id>/role", methods=["PATCH"])
@jwt_required()
def set_staff_role(staff_id):
    data = request.json or {}
    new_role = data.get("role")
    if new_role not in ["DISPATCHER", "AGENCY_ADMIN"]:
        return jsonify({"error": "Role must be DISPATCHER or AGENCY_ADMIN."}), 400

    updated = update_staff_role(staff_id, new_role)
    if not updated:
        return jsonify({"error": "Staff member not found or update failed."}), 404

    return jsonify({"success": True, "role": new_role})


@agency_bp.route("/agency/team/<staff_id>", methods=["DELETE"])
@jwt_required()
def remove_staff(staff_id):
    deleted = delete_staff(staff_id)
    if not deleted:
        return jsonify({"error": "Staff member not found."}), 404
    return jsonify({"success": True, "message": "Staff member removed."})


# ─────────────────────────────────────────────────────────────
#  4. SAFCHAT INTELLIGENCE (Agency Dossiers, Assignment, XAI)
# ─────────────────────────────────────────────────────────────

@agency_bp.route("/agency/reports", methods=["GET"])
@jwt_required()
def agency_list_reports():
    agency_id = get_jwt_identity()
    status = request.args.get("status")
    reports = get_reports_for_agency(agency_id, status=status)
    return jsonify([serialize_report_for_agency(r) for r in reports])


@agency_bp.route("/agency/reports/<report_id>", methods=["GET"])
@jwt_required()
def agency_get_report(report_id):
    agency_id = get_jwt_identity()
    report = get_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    if str(report.get("assignedAgencyId")) != agency_id:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(serialize_report_for_agency(report))


@agency_bp.route("/agency/reports/<report_id>/status", methods=["PATCH"])
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


@agency_bp.route("/agency/reports/<report_id>/assign", methods=["PATCH"])
@jwt_required()
def assign_report_route(report_id):
    data = request.json or {}
    staff_id = data.get("staff_id")
    staff_name = data.get("staff_name")

    if staff_id and not staff_name:
        staff = get_staff_by_id(staff_id)
        if staff:
            staff_name = staff.get("name", "Dispatcher")

    success = assign_report_staff(report_id, staff_id, staff_name)
    if not success:
        return jsonify({"error": "Report not found or assignment failed"}), 404

    agency_id = get_jwt_identity()
    socketio.emit("report_assigned", {
        "report_id": report_id,
        "staff_id": staff_id,
        "staff_name": staff_name,
    }, to=f"agency_{agency_id}")

    return jsonify({
        "success": True,
        "message": f"Report assigned to {staff_name}" if staff_id else "Report unassigned",
        "assigned_staff_id": staff_id,
        "assigned_staff_name": staff_name,
    })


@agency_bp.route("/agency/reports/<report_id>/analyze", methods=["POST"])
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
        return jsonify({"error": "AI analysis pipeline failed", "details": analysis}), 502

    update_report_analysis(report_id, analysis)

    return jsonify({
        "success": True,
        "analysis": analysis,
        "status": "triaged"
    })


@agency_bp.route("/agency/reports/stats", methods=["GET"])
@jwt_required()
def agency_report_stats():
    agency_id = get_jwt_identity()
    return jsonify(get_report_counts_for_agency(agency_id))


# ─────────────────────────────────────────────────────────────
#  5. DASHBOARD STATS & KPI METRICS
# ─────────────────────────────────────────────────────────────

@agency_bp.route("/agency/dashboard/stats", methods=["GET"])
@agency_bp.route("/stats", methods=["GET"])
@jwt_required()
def dashboard_stats_route():
    agency_id = get_jwt_identity()
    return jsonify(get_dashboard_overview_stats(agency_id))


# ─────────────────────────────────────────────────────────────
#  6. SUPER ADMIN PLATFORM MATRIX
# ─────────────────────────────────────────────────────────────

@agency_bp.route("/admin/agencies", methods=["GET"])
@jwt_required()
def list_agencies_for_super_admin():
    agencies = get_all_agencies()
    return jsonify([serialize_agency(a) for a in agencies])


@agency_bp.route("/admin/agencies/<agency_id>/verify", methods=["PATCH"])
@jwt_required()
def set_agency_verification(agency_id):
    data = request.json or {}
    is_verified = data.get("is_verified", True)
    updated = verify_agency_status(agency_id, bool(is_verified))
    if not updated:
        return jsonify({"error": "Agency not found or update failed."}), 404

    return jsonify({"success": True, "is_verified": bool(is_verified)})
