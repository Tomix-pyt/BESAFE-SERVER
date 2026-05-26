import requests
from config import Config


def is_sms_configured():
    return bool(Config.TWILIO_ACCOUNT_SID and Config.TWILIO_AUTH_TOKEN and Config.TWILIO_PHONE_NUMBER)


def send_sms(to_e164, body):
    sid = Config.TWILIO_ACCOUNT_SID
    token = Config.TWILIO_AUTH_TOKEN
    from_ = Config.TWILIO_PHONE_NUMBER

    if not sid or not token or not from_:
        raise Exception("SMS is not configured (Twilio env vars missing)")

    resp = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data={"From": from_, "To": to_e164, "Body": body},
        auth=(sid, token),
        timeout=15,
    )
    if not resp.ok:
        raise Exception(f"Twilio error {resp.status_code}: {resp.text}")
