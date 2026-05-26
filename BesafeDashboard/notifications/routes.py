from flask import Blueprint, g, jsonify, request

from auth.middleware import require_auth
from services.notification_service import remove_token, save_token

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/token", methods=["PATCH"])
@require_auth
def save_push_token():
    data = request.get_json(silent=True) or {}
    push_token = data.get("pushToken", "").strip()
    if not push_token:
        return jsonify({"message": "Push token is required"}), 400

    try:
        save_token(str(g.current_user["_id"]), push_token)
        return jsonify({"message": "Push token saved", "data": {}}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 400


@notifications_bp.route("/token", methods=["DELETE"])
@require_auth
def delete_push_token():
    data = request.get_json(silent=True) or {}
    push_token = data.get("pushToken", "").strip()
    if not push_token:
        return jsonify({"message": "Push token is required"}), 400

    remove_token(str(g.current_user["_id"]), push_token)
    return jsonify({"message": "Push token removed", "data": {}}), 200
