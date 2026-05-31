from flask import Blueprint, g, request

from auth.middleware import require_auth
from exceptions import BadRequestException
from helpers.response import ok_response
from services.notification_service import remove_token, save_token


notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/token", methods=["PATCH"])
@require_auth
def save_push_token():
    data = request.get_json(silent=True) or {}
    push_token = data.get("pushToken", "").strip()
    if not push_token:
        raise BadRequestException("Push token is required")

    try:
        save_token(str(g.current_user["_id"]), push_token)
        return ok_response("Push token saved", {})
    except Exception as e:
        raise BadRequestException(str(e))


@notifications_bp.route("/token", methods=["DELETE"])
@require_auth
def delete_push_token():
    data = request.get_json(silent=True) or {}
    push_token = data.get("pushToken", "").strip()
    if not push_token:
        raise BadRequestException("Push token is required")

    remove_token(str(g.current_user["_id"]), push_token)
    return ok_response("Push token removed", {})
