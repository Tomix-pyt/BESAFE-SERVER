from exponent_server_sdk import PushClient, PushMessage, PushServerError
from db import add_push_token, get_user_by_id, remove_push_token
from models.base import besafe_client


NOTIFICATION_TYPES = {
    "SAFETY_CHECK_STARTED",
    "SAFETY_CHECK_TICK",
    "SAFETY_CHECK_DUE",
    "SAFETY_CHECK_DUE_TICK",
    "SAFETY_CHECK_OVERDUE",
    "SAFETY_CHECK_ENDED",
    "SOS_ALERT",
    "SOS_RESOLVED",
    "CONTACT_ADDED",
}


def _format_mm_ss(total_seconds):
    safe = max(0, int(total_seconds))
    m = safe // 60
    s = safe % 60
    return f"{m:02d}:{s:02d}"


def _template(type_, data=None):
    data = data or {}
    if type_ in ("SAFETY_CHECK_STARTED", "SAFETY_CHECK_TICK"):
        return {
            "title": "Safety check active",
            "body": f'{data.get("activity", "Safety check")} · check-in in {_format_mm_ss(data.get("secondsLeft", 0))}',
            "sound": None,
            "priority": "normal",
            "channelId": "safety-check-ongoing",
        }
    if type_ == "SAFETY_CHECK_DUE":
        return {
            "title": "Are you safe?",
            "body": f'Contacts notified in {_format_mm_ss(data.get("secondsLeft", 120))} if no response',
            "sound": None,
            "priority": "high",
            "channelId": "alerts",
        }
    if type_ == "SAFETY_CHECK_DUE_TICK":
        return {
            "title": "Are you safe?",
            "body": f'Contacts notified in {_format_mm_ss(data.get("secondsLeft", 120))} if no response',
            "sound": None,
            "priority": "normal",
            "channelId": "safety-check-ongoing",
        }
    if type_ == "SAFETY_CHECK_OVERDUE":
        return {
            "title": "Alerting your emergency contacts",
            "body": data.get("contactsSummary", "Your emergency contacts are being notified"),
            "sound": None,
            "priority": "high",
            "channelId": "alerts",
        }
    if type_ == "SAFETY_CHECK_ENDED":
        reason = data.get("reason", "")
        body = "You confirmed you're safe. Timer reset." if reason == "confirmed" else "Safety check stopped."
        return {
            "title": "Safety check ended",
            "body": body,
            "sound": None,
            "priority": "normal",
            "channelId": "safety-check-ongoing",
        }
    if type_ == "SOS_ALERT":
        return {
            "title": "Emergency Alert",
            "body": f'{data.get("name", "Someone")} has triggered an SOS. They may need help.',
            "sound": None,
            "priority": "high",
            "channelId": "alerts",
        }
    if type_ == "SOS_RESOLVED":
        return {
            "title": "All Clear",
            "body": f'{data.get("name", "Your contact")} has confirmed they are safe.',
            "sound": None,
            "priority": "high",
            "channelId": "alerts",
        }
    if type_ == "CONTACT_ADDED":
        return {
            "title": "Added as Emergency Contact",
            "body": f'{data.get("name", "Someone")} added you as their BeSafe emergency contact.',
            "sound": None,
            "priority": "normal",
            "channelId": "alerts",
        }
    return {"title": "", "body": ""}


def send_to_user(user_id, type_, data=None):
    user = get_user_by_id(user_id)
    if not user or not user.get("pushTokens"):
        return
    _dispatch(user["pushTokens"], type_, data)


def send_to_users(user_ids, type_, data=None):
    users_collection = besafe_client.get_collection("Users")
    cursor = users_collection.find(
        {"_id": {"$in": [__import__("bson").ObjectId(uid) for uid in user_ids]},
         "pushTokens": {"$exists": True, "$not": {"$size": 0}}},
        {"pushTokens": 1}
    )
    all_tokens = []
    for u in cursor:
        all_tokens.extend(u.get("pushTokens", []))
    if all_tokens:
        _dispatch(all_tokens, type_, data)


def send_to_emergency_contacts(user_id, type_, data=None, contact_ids=None):
    user = get_user_by_id(user_id)
    if not user or not user.get("emergencyContacts"):
        return

    contacts = user["emergencyContacts"]
    if contact_ids:
        contacts = [c for c in contacts if str(c.get("_id", "")) in contact_ids]

    phones = [c["phone"] for c in contacts if c.get("phone")]
    if not phones:
        return

    users_collection = besafe_client.get_collection("Users")
    cursor = users_collection.find(
        {"phone": {"$in": phones},
         "pushTokens": {"$exists": True, "$not": {"$size": 0}}},
        {"pushTokens": 1}
    )
    tokens = []
    for u in cursor:
        tokens.extend(u.get("pushTokens", []))

    if not tokens:
        return

    dispatch_data = {"name": user.get("name", ""), "count": len(phones), **(data or {})}
    _dispatch(tokens, type_, dispatch_data)


def save_token(user_id, token):
    if not token.startswith("ExponentPushToken["):
        raise Exception(f"Invalid Expo push token: {token}")
    add_push_token(user_id, token)


def remove_token(user_id, token):
    remove_push_token(user_id, token)


def _dispatch(tokens, type_, data=None):
    tpl = _template(type_, data)
    valid = [t for t in tokens if t.startswith("ExponentPushToken[")]
    if not valid:
        return

    messages = [
        PushMessage(
            to=t,
            title=tpl["title"],
            body=tpl["body"],
            data={"type": type_, **(data or {})},
            sound=tpl.get("sound"),
            priority=tpl.get("priority", "high"),
            channel_id=tpl.get("channelId", "alerts"),
        )
        for t in valid
    ]

    client = PushClient()
    for msg in messages:
        try:
            client.publish(msg)
        except PushServerError as e:
            print(f"[Push] Error sending to {msg.to}: {e}")
