import requests
from config import Config


def is_sms_configured():
    return bool(Config.TWILIO_ACCOUNT_SID and Config.TWILIO_AUTH_TOKEN and Config.TWILIO_PHONE_NUMBER)


def send_sms(to_e164, body):
    sid = Config.TWILIO_ACCOUNT_SID
    token = Config.TWILIO_AUTH_TOKEN
    from_ = Config.TWILIO_PHONE_NUMBER

    print(f"[SMS] ─────────────────────────────────────────")
    print(f"[SMS] TO:  {to_e164}")
    print(f"[SMS] FROM: {from_}")
    print(f"[SMS] BODY:")
    for line in body.split("\n"):
        print(f"[SMS]   {line}")
    print(f"[SMS] ─────────────────────────────────────────")

    if not sid or not token or not from_:
        print(f"[SMS] SKIPPED — Twilio not configured")
        return

    try:
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data={"From": from_, "To": to_e164, "Body": body},
            auth=(sid, token),
            timeout=15,
        )
        if resp.ok:
            print(f"[SMS] SENT via Twilio (sid={resp.json().get('sid', '?')})")
        else:
            print(f"[SMS] TWILIO ERROR {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[SMS] TWILIO EXCEPTION: {e}")
