from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

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
        return jsonify({"message": "Phone number is required"}), 400

    now = datetime.now()
    session = find_otp_session(phone)

    # Block check
    if session and session.get("blockedUntil") and session["blockedUntil"] > now:
        return jsonify({"message": "Too many attempts. Try again later."}), 429

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
        return jsonify({"data": {"cooldown": cooldown}, "message": "OTP sent"}), 200

    one_hour_ago = now - timedelta(hours=1)
    first_sent = session.get("firstSentAt")

    if not first_sent or first_sent < one_hour_ago:
        send_count = 1
        first_sent = now
    else:
        send_count = session.get("sendCount", 0)
        cooldown_seconds = _progressive_cooldown(send_count)
        diff = (now - session.get("lastSentAt", now)).total_seconds()
        if diff < cooldown_seconds:
            wait = int(cooldown_seconds - diff) + 1
            return jsonify({
                "message": f"Please wait {_format_time(wait)} before requesting another code"
            }), 429

        if send_count >= MAX_SEND_PER_HOUR:
            blocked_until = now + timedelta(hours=BLOCK_DURATION_HOURS)
            update_otp_session(phone, {"blockedUntil": blocked_until})
            return jsonify({"message": "Too many attempts. Try again later."}), 429

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
    return jsonify({"data": {"cooldown": cooldown}, "message": "OTP sent"}), 200


# ── POST /verify-otp
@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "").strip()
    otp = data.get("otp", "").strip()

    if not phone or not otp:
        return jsonify({"message": "Phone and OTP are required"}), 400

    now = datetime.now()
    session = find_otp_session(phone)
    if not session:
        return jsonify({"message": "No OTP session found. Request a code first."}), 400

    if session.get("blockedUntil") and session["blockedUntil"] > now:
        return jsonify({"message": "Too many attempts. Try again later."}), 429

    if session.get("expiresAt", now) < now:
        delete_otp_session(phone)
        return jsonify({"message": "OTP expired. Request a new code."}), 400

    attempts = session.get("verifyAttempts", 0)
    if attempts >= MAX_VERIFY_ATTEMPTS:
        blocked_until = now + timedelta(hours=BLOCK_DURATION_HOURS)
        update_otp_session(phone, {"blockedUntil": blocked_until})
        return jsonify({"message": "Too many failed attempts. Try again later."}), 429

    if hash_otp(otp) != session.get("otpHash", ""):
        update_otp_session(phone, {"verifyAttempts": attempts + 1})
        remaining = MAX_VERIFY_ATTEMPTS - (attempts + 1)
        return jsonify({"message": f"Invalid OTP. {remaining} attempts remaining."}), 400

    user = get_user_by_phone(phone)
    is_new_user = not user

    if is_new_user:
        user = save_user(phone)
    else:
        update_user_last_seen(user["_id"])
        user = get_user_by_phone(phone)

    tokens = generate_token_pair(user)
    delete_otp_session(phone)

    return jsonify({
        "message": "OTP verified successfully",
        "data": {
            "tokens": tokens,
            "isNewUser": is_new_user,
            "isOnboarded": user.get("isOnboarded", False),
            "user": {
                "id": str(user["_id"]),
                "phone": user["phone"],
                "name": user.get("name"),
            },
        },
    }), 200


# ── POST /resend-otp
@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    data = request.get_json(silent=True) or {}
    phone = data.get("phone", "").strip()
    if not phone:
        return jsonify({"message": "Phone number is required"}), 400

    now = datetime.now()
    session = find_otp_session(phone)
    if not session:
        return jsonify({"message": "No OTP session found. Request a new code."}), 400

    if session.get("blockedUntil") and session["blockedUntil"] > now:
        return jsonify({"message": "Too many attempts. Try again later."}), 429

    send_count = session.get("sendCount", 0)
    cooldown_seconds = _progressive_cooldown(send_count)
    diff = (now - session.get("lastSentAt", now)).total_seconds()
    if diff < cooldown_seconds:
        wait = int(cooldown_seconds - diff) + 1
        return jsonify({
            "message": f"Please wait {_format_time(wait)} before requesting another code"
        }), 429

    if send_count >= MAX_SEND_PER_HOUR:
        blocked_until = now + timedelta(hours=BLOCK_DURATION_HOURS)
        update_otp_session(phone, {"blockedUntil": blocked_until})
        return jsonify({"message": "Too many attempts. Try again later."}), 429

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
        first_sent_at=session.get("firstSentAt"),
    )

    cooldown = _progressive_cooldown(send_count)
    print(f"[OTP] {phone}: {otp}")
    return jsonify({"data": {"cooldown": cooldown}, "message": "OTP resent"}), 200


# ── GET /otp-cooldown?phone=...
@auth_bp.route("/otp-cooldown", methods=["GET"])
def otp_cooldown():
    phone = request.args.get("phone", "").strip()
    if not phone:
        return jsonify({"message": "Phone number is required"}), 400

    session = find_otp_session(phone)
    if not session:
        return jsonify({"data": {"cooldown": 0}}), 200

    now = datetime.now()
    send_count = session.get("sendCount", 0)
    cooldown_seconds = _progressive_cooldown(send_count)
    diff = (now - session.get("lastSentAt", now)).total_seconds()
    remaining = max(0, int(cooldown_seconds - diff))
    return jsonify({"data": {"cooldown": remaining}}), 200


# ── POST /refresh
@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token", "").strip()
    if not refresh_token:
        return jsonify({"message": "Refresh token is required"}), 400

    payload = verify_jwt(refresh_token, "refresh")
    if not payload:
        return jsonify({"message": "Invalid or expired refresh token"}), 401

    stored = find_refresh_token(refresh_token)
    if not stored:
        return jsonify({"message": "Refresh token not found. Please log in again."}), 401

    user = get_user_by_id(payload.get("id"))
    if not user:
        return jsonify({"message": "User not found"}), 404

    delete_refresh_token(refresh_token)
    tokens = generate_token_pair(user)

    return jsonify({"data": {"tokens": tokens}, "message": "Session refreshed"}), 200


# ── POST /logout
@auth_bp.route("/logout", methods=["POST"])
def logout():
    data = request.get_json(silent=True) or {}
    refresh_token = data.get("refresh_token", "").strip()
    if refresh_token:
        delete_refresh_token(refresh_token)
    return jsonify({"message": "Logged out successfully"}), 200
