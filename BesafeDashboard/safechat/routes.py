from flask import Blueprint, g, request

from auth.middleware import require_auth
from db import (
    get_user_by_id,
    save_report,
    get_reports_for_user,
    get_report_by_id,
    get_nearest_agencies,
    get_all_agencies,
    agencies_have_location,
)
from exceptions import (
    BadRequestException,
    NotFoundException,
    InternalServerErrorException,
)
from helpers.response import created_response, ok_response
from socket_instance import socketio

safechat_bp = Blueprint("safechat", __name__)


@safechat_bp.route("/reports", methods=["POST"])
@require_auth
def submit_report():
    data = request.get_json(silent=True) or {}

    category = (data.get("category") or "").strip()
    description = (data.get("description") or "").strip()
    timing = (data.get("timing") or "").strip()
    frequency = (data.get("frequency") or "").strip()
    submit_for_help = bool(data.get("submitForHelp", False))
    location = data.get("location")

    valid_categories = {"abuse-home", "harassment", "unsafe-ride", "threats", "other"}
    if category not in valid_categories:
        raise BadRequestException(f"category must be one of {valid_categories}")
    if not description:
        raise BadRequestException("description is required")
    if timing not in ("just-now", "today", "this-week", "longer-ago"):
        raise BadRequestException("timing must be one of: just-now, today, this-week, longer-ago")
    if frequency not in ("first", "few", "many"):
        raise BadRequestException("frequency must be one of: first, few, many")

    user_id = str(g.current_user["_id"])
    agency_id = None

    if submit_for_help:
        user_location = None
        if location and isinstance(location, dict):
            user_location = location
        else:
            user = get_user_by_id(user_id)
            if user and user.get("location"):
                user_location = user["location"]

        target_agencies = []
        if user_location and user_location.get("lat") and user_location.get("lng"):
            if agencies_have_location():
                target_agencies = get_nearest_agencies(
                    user_location["lat"], user_location["lng"], limit=1
                )
        if not target_agencies:
            target_agencies = get_all_agencies()

        if target_agencies:
            agency_id = str(target_agencies[0]["_id"])

    try:
        report_id = save_report(
            user_id=user_id,
            category=category,
            description=description,
            timing=timing,
            frequency=frequency,
            location=location,
            submit_for_help=submit_for_help,
            agency_id=agency_id,
        )

        if submit_for_help and agency_id:
            saved = get_report_by_id(report_id)
            if saved:
                payload = serialize_report(saved)
                socketio.emit("new_report", payload, room=f"agency_{agency_id}")

        return created_response("Report saved", {"reportId": report_id})

    except Exception as e:
        raise InternalServerErrorException(str(e))


@safechat_bp.route("/reports", methods=["GET"])
@require_auth
def list_reports():
    user_id = str(g.current_user["_id"])
    try:
        reports = get_reports_for_user(user_id)
        return ok_response(data={"reports": [serialize_report(r) for r in reports]})
    except Exception as e:
        raise InternalServerErrorException(str(e))


@safechat_bp.route("/reports/<report_id>", methods=["GET"])
@require_auth
def get_report(report_id):
    report = get_report_by_id(report_id)
    if not report:
        raise NotFoundException("Report not found")

    user_id = str(g.current_user["_id"])
    if str(report.get("userId")) != user_id:
        raise NotFoundException("Report not found")

    return ok_response(data={"report": serialize_report(report)})


def serialize_report(doc):
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
        "status": doc.get("status", "private"),
        "priority": doc.get("priority", "low"),
        "submittedToAgency": doc.get("submittedToAgency", False),
        "assignedAgencyId": doc.get("assignedAgencyId"),
        "createdAt": created,
        "updatedAt": updated,
    }
