from functools import wraps

from flask import g, jsonify, request

from auth.helpers import verify_jwt
from db import get_user_by_id


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"message": "Missing or invalid Authorization header"}), 401

        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token, "access")
        if not payload:
            return jsonify({"message": "Invalid or expired access token"}), 401

        user = get_user_by_id(payload.get("id"))
        if not user:
            return jsonify({"message": "User not found"}), 401

        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def require_onboarded(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if not user:
            return jsonify({"message": "Not authenticated"}), 401
        if not user.get("isOnboarded"):
            return jsonify({"message": "Please complete onboarding first"}), 403
        return f(*args, **kwargs)
    return decorated


def require_role(role: str):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if not user:
                return jsonify({"message": "Not authenticated"}), 401
            if user.get("role") != role:
                return jsonify({"message": "Access denied"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
