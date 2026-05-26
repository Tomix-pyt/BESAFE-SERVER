from mailjet_rest import Client

from config import Config


def send_sos_emergency_email(to_email, to_name, subject, text_body, html_body):
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
        print(f"[Email] SOS send failed: {e}")
        raise Exception("Could not send SOS email")
