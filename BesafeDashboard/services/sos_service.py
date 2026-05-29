import re
from datetime import datetime

from services.email_service import send_sos_emergency_email
from services.email_templates import render_sos_alert, render_sos_sms_body
from services.notification_service import send_to_emergency_contacts
from services.sms_service import is_sms_configured, send_sms

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _is_valid_email(value):
    v = (value or "").strip()
    return bool(v and _EMAIL_RE.match(v))


def _normalize_phone_e164(phone):
    raw = (phone or "").strip().replace(" ", "").replace("-", "")
    if not raw:
        return None
    if raw.startswith("+"):
        digits = "+" + re.sub(r"\D", "", raw[1:])
        return digits if len(digits) > 8 else None
    digits_only = re.sub(r"\D", "", raw)
    return f"+{digits_only}" if len(digits_only) >= 8 else None


def send_sos(user, payload):
    user_display_name = (user.get("name") or "").strip() or "BeSafe user"
    failures = []
    emails_sent = 0
    sms_sent = 0

    for contact in (user.get("emergencyContacts") or []):
        has_email = _is_valid_email(contact.get("email"))
        phone_e164 = _normalize_phone_e164(contact.get("phone"))
        has_phone = bool(phone_e164)

        if has_email and has_phone:
            if _try_email(contact, user_display_name, payload, failures):
                emails_sent += 1
            if _try_sms(phone_e164, contact, user_display_name, payload, failures):
                sms_sent += 1
        elif has_email and not has_phone:
            if _try_email(contact, user_display_name, payload, failures):
                emails_sent += 1
        elif not has_email and has_phone:
            if _try_sms(phone_e164, contact, user_display_name, payload, failures):
                sms_sent += 1
        else:
            failures.append({
                "channel": "email",
                "target": contact.get("name", "contact"),
                "reason": "No valid email or phone",
            })

    push_dispatched = False
    try:
        send_to_emergency_contacts(str(user["_id"]), "SOS_ALERT", {"name": user_display_name})
        push_dispatched = True
    except Exception as e:
        print(f"[SOS] Push to emergency contacts failed: {e}")

    any_channel_ok = emails_sent > 0 or sms_sent > 0 or push_dispatched
    if not any_channel_ok:
        detail = "; ".join(f'{f["channel"]} ({f["target"]}): {f["reason"]}' for f in failures) if failures else "No SOS messages could be delivered."
        raise Exception(detail)

    alerted_agencies = _route_to_agency(user, payload)

    return {
        "emailsSent": emails_sent,
        "smsSent": sms_sent,
        "pushDispatched": push_dispatched,
        "failures": failures,
        "agenciesAlerted": alerted_agencies,
    }


def _try_email(contact, user_display_name, payload, failures):
    to = (contact.get("email") or "").strip()
    try:
        html = render_sos_alert(user_display_name, payload.get("location"), payload.get("message"))
        sms_text = render_sos_sms_body(user_display_name, payload.get("location"), payload.get("message"))
        send_sos_emergency_email(
            to_email=to,
            to_name=contact.get("name", ""),
            subject=f"SOS — {user_display_name} needs help",
            text_body=sms_text,
            html_body=html,
        )
        return True
    except Exception as e:
        failures.append({"channel": "email", "target": to, "reason": str(e)})
        print(f"[SOS] Email failed: {to} - {e}")
        return False


def _try_sms(phone_e164, contact, user_display_name, payload, failures):
    if not is_sms_configured():
        failures.append({
            "channel": "sms",
            "target": phone_e164,
            "reason": "SMS not configured (Twilio env vars)",
        })
        return False
    try:
        body = render_sos_sms_body(user_display_name, payload.get("location"), payload.get("message"))
        send_sms(phone_e164, body)
        return True
    except Exception as e:
        failures.append({"channel": "sms", "target": phone_e164, "reason": str(e)})
        print(f"[SOS] SMS failed: {phone_e164} - {e}")
        return False


# ─────────────────────────────────────────────────────────────
#  AGENCY ALERT ROUTING  —  every SOS also creates a dashboard alert
# ─────────────────────────────────────────────────────────────

def _serialize_alert_simple(doc: dict) -> dict:
    created = doc.get("created_at")
    if isinstance(created, datetime):
        created = created.isoformat()
    return {
        "id": str(doc["_id"]),
        "user_id": doc.get("user_id", ""),
        "user_name": doc.get("user_name", "Unknown"),
        "user_phone": doc.get("user_phone", ""),
        "user_photo": doc.get("user_photo", ""),
        "transcribed_text": doc.get("transcribed_text", ""),
        "confidence": round(float(doc.get("confidence", 0)), 4),
        "gps_lat": doc.get("gps_lat"),
        "gps_lng": doc.get("gps_lng"),
        "status": doc.get("status", "active"),
        "agency_id": doc.get("agency_id", ""),
        "created_at": created,
    }


def _enrich(alert: dict) -> dict:
    from utils import calculate_priority, priority_label
    p = calculate_priority(alert)
    alert["priority"] = p
    alert["priority_label"] = priority_label(p)
    return alert


def _route_to_agency(user, payload):
    from models.agency import get_agency_by_phone
    from models.alert import save_alert, get_alert_by_id
    from socket_instance import socketio

    user_id = str(user["_id"])
    user_name = (user.get("name") or "").strip() or "BeSafe user"
    user_phone = user.get("phone", "")
    user_photo = user.get("profilePicture") or ""
    location = payload.get("location") or {}

    alerted = []

    for contact in (user.get("emergencyContacts") or []):
        phone = (contact.get("phone") or "").strip()
        if not phone:
            continue
        agency = get_agency_by_phone(phone)
        if not agency:
            continue

        alert_id = save_alert(
            user_id=user_id,
            user_name=user_name,
            user_phone=user_phone,
            user_photo=user_photo,
            transcribed_text="Manual SOS — User initiated emergency",
            confidence=1.0,
            gps_lat=location.get("latitude"),
            gps_lng=location.get("longitude"),
            sos_contacts=[c.get("phone", "") for c in (user.get("emergencyContacts") or [])],
            agency_id=str(agency["_id"]),
        )

        saved_doc = get_alert_by_id(alert_id)
        if saved_doc:
            payload_enriched = _enrich(_serialize_alert_simple(saved_doc))
            socketio.emit(
                "new_alert", payload_enriched,
                room=f"agency_{str(agency['_id'])}"
            )

        alerted.append({
            "agency_id": str(agency["_id"]),
            "agency_name": agency.get("name"),
            "alert_id": alert_id,
        })

    return alerted
