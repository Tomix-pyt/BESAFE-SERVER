from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt

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
#  HELPERS & TOKEN CONTEXT
# ─────────────────────────────────────────────────────────────

def get_session_context():
    """
    Extracts the authenticated operator identity and agency_id from JWT.
    Supports both staff_{id} and agency_{id} prefixes as well as legacy raw IDs.
    """
    identity = str(get_jwt_identity() or "")
    claims = get_jwt() or {}

    agency_id = claims.get("agency_id")
    user_id = claims.get("user_id")
    role = claims.get("role")
    user_type = claims.get("user_type")

    if not agency_id:
        if identity.startswith("staff_"):
            staff_id = identity.replace("staff_", "")
            staff = get_staff_by_id(staff_id)
            if staff:
                agency_id = str(staff.get("agency_id", ""))
                user_id = staff_id
                role = staff.get("role", "DISPATCHER")
                user_type = "staff"
        elif identity.startswith("agency_"):
            agency_id = identity.replace("agency_", "")
            user_id = agency_id
            role = "AGENCY_ADMIN"
            user_type = "agency"
        else:
            # Legacy raw agency id
            agency_id = identity
            user_id = identity
            role = "AGENCY_ADMIN"
            user_type = "agency"

    return {
        "user_id": str(user_id or identity),
        "agency_id": str(agency_id or identity),
        "role": role or "DISPATCHER",
        "user_type": user_type or "agency",
    }


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
        agency_id = str(agency["_id"])
        additional_claims = {
            "user_id": agency_id,
            "agency_id": agency_id,
            "role": agency.get("role", "AGENCY_ADMIN"),
            "user_type": "agency",
        }
        token = create_access_token(
            identity=f"agency_{agency_id}",
            additional_claims=additional_claims
        )
        agency_data = serialize_agency(agency)
        return jsonify({
            "token": token,
            "must_change_password": False,
            "agency": agency_data,
            "user": {
                "id": agency_id,
                "name": agency["name"],
                "email": agency["email"],
                "role": agency.get("role", "AGENCY_ADMIN"),
                "agency_id": agency_id,
                "must_change_password": False,
            }
        })

    # 2. Check Agency Staff Account (Dispatchers)
    staff = get_staff_by_email(email)
    if staff and verify_staff_password(staff, password):
        if not staff.get("is_active", True):
            return jsonify({"error": "Your staff account has been deactivated by the agency administrator."}), 403

        staff_id = str(staff["_id"])
        agency_id = str(staff["agency_id"])
        assigned_agency = get_agency_by_id(agency_id)

        additional_claims = {
            "user_id": staff_id,
            "agency_id": agency_id,
            "role": staff.get("role", "DISPATCHER"),
            "user_type": "staff",
        }
        token = create_access_token(
            identity=f"staff_{staff_id}",
            additional_claims=additional_claims
        )
        must_change = staff.get("must_change_password", False)
        return jsonify({
            "token": token,
            "must_change_password": must_change,
            "agency": serialize_agency(assigned_agency) if assigned_agency else None,
            "user": {
                "id": staff_id,
                "name": staff["name"],
                "email": staff["email"],
                "role": staff.get("role", "DISPATCHER"),
                "agency_id": agency_id,
                "must_change_password": must_change,
            }
        })

    return jsonify({"error": "Invalid email or password"}), 401


@agency_bp.route("/agency/auth/me", methods=["GET"])
@agency_bp.route("/auth/me", methods=["GET"])
@jwt_required()
def me():
    ctx = get_session_context()
    user_id = ctx["user_id"]
    agency_id = ctx["agency_id"]
    user_type = ctx["user_type"]

    agency_doc = get_agency_by_id(agency_id)
    serialized_agency = serialize_agency(agency_doc) if agency_doc else None

    if user_type == "staff":
        staff_doc = get_staff_by_id(user_id)
        if not staff_doc:
            return jsonify({"error": "Staff account not found"}), 404

        return jsonify({
            "id": str(staff_doc["_id"]),
            "name": staff_doc["name"],
            "email": staff_doc["email"],
            "phone_number": staff_doc.get("phone", ""),
            "role": staff_doc.get("role", "DISPATCHER"),
            "agency_id": str(staff_doc["agency_id"]),
            "must_change_password": staff_doc.get("must_change_password", False),
            "agency": serialized_agency,
        })
    else:
        if not agency_doc:
            return jsonify({"error": "Agency not found"}), 404

        agency_profile = serialize_agency(agency_doc)
        agency_profile["agency"] = serialized_agency
        return jsonify(agency_profile)


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

    ctx = get_session_context()
    target_id = staff_id or (ctx["user_id"] if ctx["user_type"] == "staff" else None)

    staff = None
    if target_id:
        staff = get_staff_by_id(target_id)
    elif email:
        staff = get_staff_by_email(email)

    if not staff:
        return jsonify({"error": "Staff account not found"}), 404

    success = change_staff_password(str(staff["_id"]), new_password)
    if not success:
        return jsonify({"error": "Failed to update password"}), 500

    return jsonify({"success": True, "message": "Permanent password successfully set!"})


# ─────────────────────────────────────────────────────────────
#  2. AGENCY SETTINGS (Restricted to Station Admin)
# ─────────────────────────────────────────────────────────────

@agency_bp.route("/agency/details", methods=["PATCH"])
@jwt_required()
def update_agency_details():
    ctx = get_session_context()
    if ctx["role"] not in ["AGENCY_ADMIN", "SUPER_ADMIN"]:
        return jsonify({"error": "Only agency administrators can modify station details."}), 403

    agency_id = ctx["agency_id"]
    new_details = request.json or {}
    updated = update_agency(agency_id, new_details)
    if not updated:
        return jsonify({"error": "Update failed"}), 500
    return jsonify({"success": True, "message": "Details updated successfully!"})


@agency_bp.route("/agency/location", methods=["PATCH"])
@jwt_required()
def set_agency_location():
    ctx = get_session_context()
    if ctx["role"] not in ["AGENCY_ADMIN", "SUPER_ADMIN"]:
        return jsonify({"error": "Only agency administrators can change headquarters location."}), 403

    agency_id = ctx["agency_id"]
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
    ctx = get_session_context()
    if ctx["role"] not in ["AGENCY_ADMIN", "SUPER_ADMIN"]:
        return jsonify({"error": "Only agency administrators can change station master password."}), 403

    agency_id = ctx["agency_id"]
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
#  3. STATION TEAM MANAGEMENT & RBAC (Admin only)
# ─────────────────────────────────────────────────────────────

@agency_bp.route("/agency/team", methods=["GET"])
@jwt_required()
def list_agency_team():
    ctx = get_session_context()
    agency_id = ctx["agency_id"]
    staff_members = get_staff_for_agency(agency_id)
    return jsonify([serialize_staff(s) for s in staff_members])


@agency_bp.route("/agency/team", methods=["POST"])
@jwt_required()
def add_agency_staff():
    ctx = get_session_context()
    if ctx["role"] not in ["AGENCY_ADMIN", "SUPER_ADMIN"]:
        return jsonify({"error": "Only agency administrators can invite dispatchers."}), 403

    agency_id = ctx["agency_id"]
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
        created_by=ctx["user_id"]
    )

    if not result.get("success"):
        return jsonify({"error": result.get("message", "Failed to add dispatcher.")}), 400

    staff_doc = get_staff_by_id(result["staff_id"])
    return jsonify({"success": True, "member": serialize_staff(staff_doc)}), 201


@agency_bp.route("/agency/team/<staff_id>/status", methods=["PATCH"])
@jwt_required()
def set_staff_status(staff_id):
    ctx = get_session_context()
    if ctx["role"] not in ["AGENCY_ADMIN", "SUPER_ADMIN"]:
        return jsonify({"error": "Only agency administrators can change dispatcher status."}), 403

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
    ctx = get_session_context()
    if ctx["role"] not in ["AGENCY_ADMIN", "SUPER_ADMIN"]:
        return jsonify({"error": "Only agency administrators can update roles."}), 403

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
    ctx = get_session_context()
    if ctx["role"] not in ["AGENCY_ADMIN", "SUPER_ADMIN"]:
        return jsonify({"error": "Only agency administrators can remove dispatchers."}), 403

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
    ctx = get_session_context()
    agency_id = ctx["agency_id"]
    status = request.args.get("status")
    reports = get_reports_for_agency(agency_id, status=status)
    return jsonify([serialize_report_for_agency(r) for r in reports])


@agency_bp.route("/agency/reports/<report_id>", methods=["GET"])
@jwt_required()
def agency_get_report(report_id):
    ctx = get_session_context()
    agency_id = ctx["agency_id"]
    report = get_report_by_id(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    if str(report.get("assignedAgencyId")) != agency_id:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(serialize_report_for_agency(report))


@agency_bp.route("/agency/reports/<report_id>/status", methods=["PATCH"])
@jwt_required()
def agency_update_report_status(report_id):
    ctx = get_session_context()
    agency_id = ctx["agency_id"]
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

    ctx = get_session_context()
    agency_id = ctx["agency_id"]
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
    ctx = get_session_context()
    agency_id = ctx["agency_id"]
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
    ctx = get_session_context()
    agency_id = ctx["agency_id"]
    return jsonify(get_report_counts_for_agency(agency_id))


# ─────────────────────────────────────────────────────────────
#  5. DASHBOARD STATS & KPI METRICS
# ─────────────────────────────────────────────────────────────

@agency_bp.route("/agency/dashboard/stats", methods=["GET"])
@agency_bp.route("/stats", methods=["GET"])
@jwt_required()
def dashboard_stats_route():
    ctx = get_session_context()
    agency_id = ctx["agency_id"]
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
    ctx = get_session_context()
    if ctx["role"] != "SUPER_ADMIN":
        return jsonify({"error": "Super Admin access required."}), 403

    data = request.json or {}
    is_verified = data.get("is_verified", True)
    updated = verify_agency_status(agency_id, bool(is_verified))
    if not updated:
        return jsonify({"error": "Agency not found or update failed."}), 404

    return jsonify({"success": True, "is_verified": bool(is_verified)})
