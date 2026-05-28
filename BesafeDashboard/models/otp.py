from datetime import datetime
from models.base import besafe_client

otp_sessions_collection = besafe_client.get_collection('OtpSessions')

try:
    otp_sessions_collection.create_index("phone", unique=True)
    otp_sessions_collection.create_index("expires_at")
except Exception as e:
    print(f"Index warning: {e}")


def save_otp_session(phone, otp_hash, expires_at, cooldown_until=None,
                     blocked_until=None):
    now = datetime.now()
    doc = {
        "phone": phone,
        "otp_hash": otp_hash,
        "expires_at": expires_at,
        "verify_attempts": 0,
        "send_count": 1,
        "first_sent_at": now,
        "last_sent_at": now,
        "cooldown_until": cooldown_until,
        "blocked_until": blocked_until,
        "created_at": now,
        "updated_at": now,
    }
    result = otp_sessions_collection.insert_one(doc)
    return result


def find_otp_session(phone):
    return otp_sessions_collection.find_one({"phone": phone})


def update_otp_session(phone, updates):
    updates["updated_at"] = datetime.now()
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
            "otp_hash": otp_hash,
            "expires_at": expires_at,
            "verify_attempts": verify_attempts,
            "send_count": send_count,
            "first_sent_at": first_sent_at or now,
            "last_sent_at": last_sent_at,
            "cooldown_until": cooldown_until,
            "blocked_until": blocked_until,
            "updated_at": now,
        }},
        upsert=True
    )
