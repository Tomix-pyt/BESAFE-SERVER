from mailjet_rest import Client

from config import Config
from services.email_templates import (
    render_contact_invite,
    render_otp_code,
    render_sos_alert,
    render_sos_sms_body,
)

_TEMPLATES = {
    "otp_code": {
        "subject": "Your BeSafe login code",
        "html": lambda ctx: render_otp_code(ctx["user_name"], ctx["otp_code"]),
    },
    "sos_alert": {
        "subject": lambda ctx: f"SOS — {ctx.get('user_name', 'Someone')} needs help",
        "html": lambda ctx: render_sos_alert(
            ctx.get("user_name"), ctx.get("location"), ctx.get("message")
        ),
    },
    "contact_invite": {
        "subject": lambda ctx: f"{ctx.get('inviter_name', 'Someone')} added you as an emergency contact on BeSafe",
        "html": lambda ctx: render_contact_invite(ctx.get("inviter_name", "Someone")),
    },
}


def _send(to_email, to_name, subject, text_body, html_body):
    from_email = Config.EMAIL_FROM
    if not from_email:
        raise Exception("Email delivery is not configured (EMAIL_FROM)")

    client = Client(auth=(Config.MAILJET_API_KEY, Config.MAILJET_API_SECRET), version="v3.1")

    try:
        result = client.send.create(data={
            "Messages": [
                {
                    "From": {"Email": from_email, "Name": "BeSafe"},
                    "To": [{"Email": to_email, "Name": to_name}],
                    "Subject": subject,
                    "TextPart": text_body,
                    "HTMLPart": html_body,
                }
            ]
        })
        if result.status_code != 200:
            raise Exception(f"Mailjet returned {result.status_code}")
    except Exception as e:
        print(f"[Email] Send failed: {e}")
        raise Exception("Could not send email")


def send_typed_email(template_name, to_email, to_name, **context):
    template = _TEMPLATES.get(template_name)
    if not template:
        raise ValueError(f"Unknown email template: {template_name}")

    subject = template["subject"](context) if callable(template["subject"]) else template["subject"]
    html = template["html"](context)

    _send(to_email, to_name, subject, "See the HTML version of this email.", html)


def send_sos_emergency_email(to_email, to_name, subject, text_body, html_body):
    _send(to_email, to_name, subject, text_body, html_body)
