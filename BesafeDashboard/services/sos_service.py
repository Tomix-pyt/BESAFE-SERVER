import re
from datetime import datetime

from db import get_user_by_phone
from services.email_service import send_sos_emergency_email
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


def _escape_html(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _build_sos_body(user_name, payload):
    lines = [
        "BeSafe SOS alert",
        f"{user_name or 'A BeSafe user'} may need immediate help.",
    ]
    msg = (payload.get("message") or "").strip()
    if msg:
        lines.append(f"Note: {msg}")
    loc = payload.get("location")
    if loc and _is_finite(loc.get("latitude")) and _is_finite(loc.get("longitude")):
        lat = loc["latitude"]
        lng = loc["longitude"]
        lines.append(
            f"Last reported location: {lat:.5f}, {lng:.5f} "
            f"(maps: https://maps.google.com/?q={lat},{lng})"
        )
    lines.append(f"Time (server): {datetime.now().isoformat()}")
    return "\n".join(lines)


def _build_sos_html(user_name, payload):
    safe_name = _escape_html(user_name or "A BeSafe user")
    note = ""
    msg = (payload.get("message") or "").strip()
    if msg:
        note = f"<p><strong>Note:</strong> {_escape_html(msg)}</p>"
    map_html = ""
    loc = payload.get("location")
    if loc and _is_finite(loc.get("latitude")) and _is_finite(loc.get("longitude")):
        lat = loc["latitude"]
        lng = loc["longitude"]
        url = f"https://maps.google.com/?q={lat},{lng}"
        map_html = (
            f"<p><strong>Last reported location:</strong> {lat:.5f}, {lng:.5f}<br/>"
            f'<a href="{url}">Open in Google Maps</a></p>'
        )
    return f"""<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;line-height:1.5">
  <h2 style="color:#b91c1c">Emergency SOS — BeSafe</h2>
  <p><strong>{safe_name}</strong> has triggered an SOS and may need immediate help.</p>
  {note}
  {map_html}
  <p style="color:#64748b;font-size:12px">Sent at {datetime.now().isoformat()}</p>
</body></html>"""


def _is_finite(v):
    return isinstance(v, (int, float)) and v == v and v != float("inf") and v != float("-inf")


def send_sos(user, payload):
    user_display_name = (user.get("name") or "").strip() or "BeSafe user"
    text_body = _build_sos_body(user_display_name, payload)
    failures = []
    emails_sent = 0
    sms_sent = 0

    for contact in (user.get("emergencyContacts") or []):
        has_email = _is_valid_email(contact.get("email"))
        phone_e164 = _normalize_phone_e164(contact.get("phone"))
        has_phone = bool(phone_e164)

        if has_email and has_phone:
            if _try_email(contact, user_display_name, text_body, payload, failures):
                emails_sent += 1
            if _try_sms(phone_e164, contact, text_body, failures):
                sms_sent += 1
        elif has_email and not has_phone:
            if _try_email(contact, user_display_name, text_body, payload, failures):
                emails_sent += 1
        elif not has_email and has_phone:
            if _try_sms(phone_e164, contact, text_body, failures):
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


def _try_email(contact, user_display_name, text_body, payload, failures):
    to = (contact.get("email") or "").strip()
    try:
        send_sos_emergency_email(
            to_email=to,
            to_name=contact.get("name", ""),
            subject=f"SOS — {user_display_name} needs help",
            text_body=text_body,
            html_body=_build_sos_html(user_display_name, payload),
        )
        return True
    except Exception as e:
        failures.append({"channel": "email", "target": to, "reason": str(e)})
        print(f"[SOS] Email failed: {to} - {e}")
        return False


def _try_sms(phone_e164, contact, text_body, failures):
    if not is_sms_configured():
        failures.append({
            "channel": "sms",
            "target": phone_e164,
            "reason": "SMS not configured (Twilio env vars)",
        })
        return False
    try:
        send_sms(phone_e164, text_body)
        return True
    except Exception as e:
        failures.append({"channel": "sms", "target": phone_e164, "reason": str(e)})
        print(f"[SOS] SMS failed: {phone_e164} - {e}")
        return False
