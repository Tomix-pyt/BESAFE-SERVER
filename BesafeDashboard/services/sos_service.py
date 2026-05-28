import re

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

    return {
        "emailsSent": emails_sent,
        "smsSent": sms_sent,
        "pushDispatched": push_dispatched,
        "failures": failures,
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
