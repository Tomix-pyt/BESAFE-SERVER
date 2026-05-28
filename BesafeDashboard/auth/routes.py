from datetime import datetime, timedelta

from flask import Blueprint, request

from auth.helpers import (
    generate_numeric_otp,
    generate_token_pair,
    hash_otp,
    verify_jwt,
)
from auth.middleware import require_auth
from config import Config
from db import (
    delete_otp_session,
    delete_refresh_token,
    find_otp_session,
    find_refresh_token,
    get_user_by_id,
    get_user_by_phone,
    save_user,
    update_otp_session,
    update_user_last_seen,
    upsert_otp_session,
)
from exceptions import (
    BadRequestException,
    TooManyAttemptsException,
    NotFoundException,
    UnauthorizedAccessException,
    AuthenticationTokenException,
)
from helpers.response import ok_response

auth_bp = Blueprint("auth", __name__)

OTP_EXPIRY_MINUTES = 8
MAX_SEND_PER_HOUR = 3
MAX_VERIFY_ATTEMPTS = 5
BLOCK_DURATION_HOURS = 1
RESEND_COOLDOWN_BASE = 30
MAX_COOLDOWN_SECONDS = 120


def _format_time(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


def _progressive_cooldown(send_count: int) -> int:
    return min(RESEND_COOLDOWN_BASE * send_count, MAX_COOLDOWN_SECONDS)


# ── POST /send-otp
@auth_bp.route("/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "").strip()
    if not phone:
        raise BadRequestException("Phone number is required")

    now = datetime.now()
    session = find_otp_session(phone)

    # Block check
    if session and session.get("blocked_until") and session["blocked_until"] > now:
        raise TooManyAttemptsException("Too many attempts. Try again later.")

    if not session:
        otp = generate_numeric_otp()
        otp_hash = hash_otp(otp)
        expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
        upsert_otp_session(
            phone=phone,
            otp_hash=otp_hash,
            expires_at=expires_at,
            send_count=1,
            last_sent_at=now,
            first_sent_at=now,
        )
        cooldown = _progressive_cooldown(1)
        print(f"[OTP] {phone}: {otp}")
        return ok_response("OTP sent", {"cooldown": cooldown})

    one_hour_ago = now - timedelta(hours=1)
    first_sent = session.get("first_sent_at")

    if not first_sent or first_sent < one_hour_ago:
        send_count = 1
        first_sent = now
    else:
        send_count = session.get("send_count", 0)
        cooldown_seconds = _progressive_cooldown(send_count)
        diff = (now - session.get("last_sent_at", now)).total_seconds()
        if diff < cooldown_seconds:
            wait = int(cooldown_seconds - diff) + 1
            raise TooManyAttemptsException(
                f"Please wait {_format_time(wait)} before requesting another code"
            )

        if send_count >= MAX_SEND_PER_HOUR:
            blocked_until = now + timedelta(hours=BLOCK_DURATION_HOURS)
            update_otp_session(phone, {"blocked_until": blocked_until})
            raise TooManyAttemptsException("Too many attempts. Try again later.")

        send_count += 1

    otp = generate_numeric_otp()
    otp_hash = hash_otp(otp)
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    upsert_otp_session(
        phone=phone,
        otp_hash=otp_hash,
        expires_at=expires_at,
        send_count=send_count,
        last_sent_at=now,
        verify_attempts=0,
        first_sent_at=first_sent,
    )

    cooldown = _progressive_cooldown(send_count)
    print(f"[OTP] {phone}: {otp}")
    return ok_response("OTP sent", {"cooldown": cooldown})


# ── POST /verify-otp
@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "").strip()
    otp = data.get("otp", "").strip()

    if not phone or not otp:
        raise BadRequestException("Phone and OTP are required")

    now = datetime.now()
    session = find_otp_session(phone)
    if not session:
        raise BadRequestException("No OTP session found. Request a code first.")

    if session.get("blocked_until") and session["blocked_until"] > now:
        raise TooManyAttemptsException("Too many attempts. Try again later.")

    if session.get("expires_at", now) < now:
        delete_otp_session(phone)
        raise BadRequestException("OTP expired. Request a new code.")

    attempts = session.get("verify_attempts", 0)
    if attempts >= MAX_VERIFY_ATTEMPTS:
        blocked_until = now + timedelta(hours=BLOCK_DURATION_HOURS)
        update_otp_session(phone, {"blocked_until": blocked_until})
        raise TooManyAttemptsException("Too many failed attempts. Try again later.")

    if hash_otp(otp) != session.get("otp_hash", ""):
        update_otp_session(phone, {"verify_attempts": attempts + 1})
        remaining = MAX_VERIFY_ATTEMPTS - (attempts + 1)
        raise BadRequestException(f"Invalid OTP. {remaining} attempts remaining.")

    user = get_user_by_phone(phone)
    is_new_user = not user

    if is_new_user:
        user = save_user(phone)
    else:
        update_user_last_seen(user["_id"])
        user = get_user_by_phone(phone)

    tokens = generate_token_pair(user)
    delete_otp_session(phone)

    return ok_response("OTP verified successfully", {
        "tokens": tokens,
        "isNewUser": is_new_user,
        "isOnboarded": user.get("isOnboarded", False),
        "user": {
            "id": str(user["_id"]),
            "phone": user["phone"],
            "name": user.get("name"),
        },
    })


# ── POST /resend-otp
@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "").strip()
    if not phone:
        raise BadRequestException("Phone number is required")

    now = datetime.now()
    session = find_otp_session(phone)
    if not session:
        raise BadRequestException("No OTP session found. Request a new code.")

    if session.get("blocked_until") and session["blocked_until"] > now:
        raise TooManyAttemptsException("Too many attempts. Try again later.")

    send_count = session.get("send_count", 0)
    cooldown_seconds = _progressive_cooldown(send_count)
    diff = (now - session.get("last_sent_at", now)).total_seconds()
    if diff < cooldown_seconds:
        wait = int(cooldown_seconds - diff) + 1
        raise TooManyAttemptsException(
            f"Please wait {_format_time(wait)} before requesting another code"
        )

    if send_count >= MAX_SEND_PER_HOUR:
        blocked_until = now + timedelta(hours=BLOCK_DURATION_HOURS)
        update_otp_session(phone, {"blocked_until": blocked_until})
        raise TooManyAttemptsException("Too many attempts. Try again later.")

    send_count += 1
    otp = generate_numeric_otp()
    otp_hash = hash_otp(otp)
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    upsert_otp_session(
        phone=phone,
        otp_hash=otp_hash,
        expires_at=expires_at,
        send_count=send_count,
        last_sent_at=now,
        verify_attempts=0,
        first_sent_at=session.get("first_sent_at"),
    )

    cooldown = _progressive_cooldown(send_count)
    print(f"[OTP] {phone}: {otp}")
    return ok_response("OTP resent", {"cooldown": cooldown})


# ── GET /otp-cooldown?phone=...
@auth_bp.route("/otp-cooldown", methods=["GET"])
def otp_cooldown():
    phone = request.args.get("phone", "").strip()
    if phone and not phone.startswith("+"):
        phone = "+" + phone
    if not phone:
        raise BadRequestException("Phone number is required")

    session = find_otp_session(phone)
    if not session:
        return ok_response(data={"cooldown": 0})

    now = datetime.now()
    send_count = session.get("send_count", 0)
    cooldown_seconds = _progressive_cooldown(send_count)
    diff = (now - session.get("last_sent_at", now)).total_seconds()
    remaining = max(0, int(cooldown_seconds - diff))
    return ok_response(data={"cooldown": remaining})


# ── POST /refresh
@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token", "").strip()
    if not refresh_token:
        raise BadRequestException("Refresh token is required")

    payload = verify_jwt(refresh_token, "refresh")
    if not payload:
        raise AuthenticationTokenException("Invalid or expired refresh token")

    stored = find_refresh_token(refresh_token)
    if not stored:
        raise AuthenticationTokenException("Refresh token not found. Please log in again.")

    user = get_user_by_id(payload.get("id"))
    if not user:
        raise NotFoundException("User not found")

    delete_refresh_token(refresh_token)
    tokens = generate_token_pair(user)

    return ok_response("Session refreshed", {"tokens": tokens})


# ── POST /logout
@auth_bp.route("/logout", methods=["POST"])
def logout():
    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token", "").strip()
    if refresh_token:
        delete_refresh_token(refresh_token)
    return ok_response("Logged out successfully")
