from datetime import datetime, timedelta

from db import (
    cancel_user_checks,
    create_safety_check,
    get_active_check,
    get_user_by_id,
    update_safety_check,
)
from services.notification_service import send_to_emergency_contacts, send_to_user


def _seconds_until(dt):
    return max(0, int((dt - datetime.now()).total_seconds()))


def start(user_id, activity, interval_minutes, contact_ids=None, start_location=None):
    cancel_user_checks(user_id)

    now = datetime.now()
    next_check_at = now + timedelta(minutes=interval_minutes)
    expires_at = now + timedelta(hours=24)

    check = create_safety_check({
        "userId": user_id,
        "activity": activity,
        "intervalMinutes": interval_minutes,
        "contactIds": contact_ids or [],
        "nextCheckAt": next_check_at,
        "expiresAt": expires_at,
        "startLocation": start_location,
    })

    send_to_user(user_id, "SAFETY_CHECK_STARTED", {
        "activity": activity,
        "checkId": str(check["_id"]),
        "minutesLeft": interval_minutes,
        "secondsLeft": _seconds_until(next_check_at),
    })

    print(f"[SafetyCheck] started for user={user_id}, next check at {next_check_at}")
    return check


def extend(user_id, additional_minutes):
    check = get_active_check(user_id)
    if not check:
        raise Exception("No active safety check found")

    new_next = check["nextCheckAt"] + timedelta(minutes=additional_minutes)
    return update_safety_check(check["_id"], {"nextCheckAt": new_next})


def update_location(user_id, location):
    check = get_active_check(user_id)
    if not check:
        return None
    return update_safety_check(check["_id"], {"lastLocation": location})


def stop(user_id, end_location=None):
    check = get_active_check(user_id)
    if not check:
        raise Exception("No active safety check")

    updates = {"status": "cancelled"}
    if end_location:
        updates["lastLocation"] = end_location
    check = update_safety_check(check["_id"], updates)

    send_to_user(user_id, "SAFETY_CHECK_ENDED", {
        "reason": "stopped",
        "checkId": str(check["_id"]),
    })

    return check


def confirm(user_id):
    check = get_active_check(user_id)
    if not check:
        raise Exception("No active safety check found")

    was_triggered = check["status"] == "triggered"
    check = update_safety_check(check["_id"], {"status": "confirmed"})

    send_to_user(user_id, "SAFETY_CHECK_ENDED", {
        "reason": "confirmed",
        "checkId": str(check["_id"]),
    })

    if was_triggered:
        send_to_emergency_contacts(user_id, "SOS_RESOLVED", {}, check.get("contactIds", []))

    return check


def cancel(user_id):
    cancel_user_checks(user_id)
    return {"cancelled": 1}


def get_active(user_id):
    return get_active_check(user_id)


def format_contact_summary(user_id, contact_ids):
    user = get_user_by_id(user_id)
    if not user:
        return "Your emergency contacts are being notified"

    contacts = user.get("emergencyContacts", [])
    selected = [c for c in contacts if str(c.get("_id", "")) in contact_ids] if contact_ids else contacts
    names = [c["name"] for c in selected if c.get("name")]

    if not names:
        return "Your emergency contacts are being notified"
    if len(names) == 1:
        return f"{names[0]} is being notified"
    if len(names) == 2:
        return f"{names[0]} and {names[1]} are being notified"
    return f"{names[0]}, {names[1]} and {len(names) - 2} others are being notified"
