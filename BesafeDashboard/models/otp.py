from datetime import datetime
from models.base import besafe_client

otp_sessions_collection = besafe_client.get_collection('OtpSessions')

try:
    otp_sessions_collection.create_index("phone", unique=True)
    otp_sessions_collection.create_index("expiresAt")
except Exception as e:
    print(f"Index warning: {e}")


def save_otp_session(phone, otp_hash, expires_at, cooldown_until=None,
                     blocked_until=None):
    now = datetime.now()
    doc = {
        "phone": phone,
        "otpHash": otp_hash,
        "expiresAt": expires_at,
        "verifyAttempts": 0,
        "sendCount": 1,
        "firstSentAt": now,
        "lastSentAt": now,
        "cooldownUntil": cooldown_until,
        "blockedUntil": blocked_until,
        "createdAt": now,
        "updatedAt": now,
    }
    result = otp_sessions_collection.insert_one(doc)
    return result


def find_otp_session(phone):
    return otp_sessions_collection.find_one({"phone": phone})


def update_otp_session(phone, updates):
    updates["updatedAt"] = datetime.now()
    otp_sessions_collection.update_one(
        {"phone": phone},
        {"$set": updates}
    )


def delete_otp_session(phone):
    otp_sessions_collection.delete_one({"phone": phone})


def upsert_otp_session(phone, otp_hash, expires_at, send_count,
                       last_sent_at, verify_attempts=0, cooldown_until=None,
                       blocked_until=None, first_sent_at=None):
    now = datetime.now()
    otp_sessions_collection.update_one(
        {"phone": phone},
        {"$set": {
            "otpHash": otp_hash,
            "expiresAt": expires_at,
            "verifyAttempts": verify_attempts,
            "sendCount": send_count,
            "firstSentAt": first_sent_at or now,
            "lastSentAt": last_sent_at,
            "cooldownUntil": cooldown_until,
            "blockedUntil": blocked_until,
            "updatedAt": now,
        }},
        upsert=True
    )
