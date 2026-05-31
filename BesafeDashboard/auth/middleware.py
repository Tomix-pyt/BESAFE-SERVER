from functools import wraps

from flask import g, request

from auth.helpers import verify_jwt
from db import get_user_by_id
from exceptions import (
    AuthenticationTokenException,
    UnauthorizedAccessException,
    ForbiddenAccessException,
)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise AuthenticationTokenException("Missing or invalid Authorization header")

        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token, "access")
        if not payload:
            raise AuthenticationTokenException("Invalid or expired access token")

        user = get_user_by_id(payload.get("id"))
        if not user:
            raise AuthenticationTokenException("User not found")

        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def require_onboarded(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if not user:
            raise UnauthorizedAccessException("Not authenticated")
        if not user.get("isOnboarded"):
            raise ForbiddenAccessException("Please complete onboarding first")
        return f(*args, **kwargs)
    return decorated


def require_role(role: str):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if not user:
                raise UnauthorizedAccessException("Not authenticated")
            if user.get("role") != role:
                raise ForbiddenAccessException("Access denied")
            return f(*args, **kwargs)
        return decorated
    return decorator
