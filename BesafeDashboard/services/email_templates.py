from datetime import datetime


def _escape_html(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


APP_DOWNLOAD_URL = "https://besafe.app/download"
APP_NAME = "BeSafe"


def render_otp_code(user_name, otp_code):
    safe_name = _escape_html(user_name or "there")
    safe_code = _escape_html(str(otp_code))
    return f"""<!DOCTYPE html>
<html>
<body style="font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 0; background-color: #f4f4f4;">
  <div style="max-width: 400px; margin: 40px auto; background: #ffffff; padding: 32px 24px; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
    <h2 style="text-align: center; color: #333; margin-bottom: 24px;">{APP_NAME}</h2>
    <h3 style="color: #444;">Hello {safe_name}!</h3>
    <h2 style="color: #333;">Your login code</h2>
    <p style="color: #666; line-height: 1.5;">Enter this temporary code to log in to your account.</p>
    <div style="text-align: center; margin: 24px 0;">
      <span style="display: inline-block; font-size: 36px; font-weight: 700; letter-spacing: 8px; color: #7c3aed; background: #f5f3ff; padding: 12px 24px; border-radius: 10px;">{safe_code}</span>
    </div>
    <p style="color: #999; font-size: 13px; margin-top: 24px;">If you did not make this login request, you can safely ignore this email.</p>
  </div>
</body>
</html>"""


def render_sos_alert(user_name, location=None, message=None):
    safe_name = _escape_html(user_name or "A BeSafe user")
    note = ""
    msg = (message or "").strip()
    if msg:
        note = f"<p><strong>Note:</strong> {_escape_html(msg)}</p>"
    map_html = ""
    if location and _is_finite(location.get("latitude")) and _is_finite(location.get("longitude")):
        lat = location["latitude"]
        lng = location["longitude"]
        url = f"https://maps.google.com/?q={lat},{lng}"
        map_html = (
            f'<p><strong>Last reported location:</strong> {lat:.5f}, {lng:.5f}<br/>'
            f'<a href="{url}" style="color: #2563eb;">Open in Google Maps</a></p>'
        )
    return f"""<!DOCTYPE html>
<html>
<body style="font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 0; background-color: #f4f4f4;">
  <div style="max-width: 520px; margin: 40px auto; background: #ffffff; padding: 32px 24px; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
    <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-bottom: 24px; text-align: center;">
      <h2 style="color: #b91c1c; margin: 0;">Emergency SOS — {APP_NAME}</h2>
    </div>
    <p style="color: #333; font-size: 16px; line-height: 1.5;"><strong>{safe_name}</strong> has triggered an SOS and may need <strong>immediate help</strong>.</p>
    {note}
    {map_html}
    <div style="margin-top: 24px; padding: 16px; background: #f0fdf4; border-radius: 8px; border: 1px solid #bbf7d0;">
      <p style="color: #166534; margin: 0; font-size: 14px;">
        <strong>Don&rsquo;t have {APP_NAME}?</strong><br/>
        Download the app to receive real-time updates: <a href="{APP_DOWNLOAD_URL}" style="color: #16a34a;">{APP_DOWNLOAD_URL}</a>
      </p>
    </div>
    <p style="color: #64748b; font-size: 12px; margin-top: 24px;">Sent at {datetime.now().isoformat()}</p>
  </div>
</body>
</html>"""


def render_sos_sms_body(user_name, location=None, message=None):
    lines = [
        f"SOS — {user_name or 'A BeSafe user'} needs immediate help.",
    ]
    msg = (message or "").strip()
    if msg:
        lines.append(f"Note: {msg}")
    if location and _is_finite(location.get("latitude")) and _is_finite(location.get("longitude")):
        lines.append(
            f"Location: https://maps.google.com/?q={location['latitude']},{location['longitude']}"
        )
    lines.append(f"Download {APP_NAME}: {APP_DOWNLOAD_URL}")
    return "\n".join(lines)


def render_contact_invite(inviter_name):
    safe_name = _escape_html(inviter_name or "Someone")
    return f"""<!DOCTYPE html>
<html>
<body style="font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 0; background-color: #f4f4f4;">
  <div style="max-width: 480px; margin: 40px auto; background: #ffffff; padding: 32px 24px; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
    <div style="text-align: center; margin-bottom: 24px;">
      <div style="width: 64px; height: 64px; background: #7c3aed; border-radius: 16px; margin: 0 auto; display: flex; align-items: center; justify-content: center;">
        <span style="color: #fff; font-size: 28px; font-weight: 700;">B</span>
      </div>
    </div>
    <h2 style="color: #333; text-align: center;">You&rsquo;ve been added as an emergency contact</h2>
    <p style="color: #555; line-height: 1.6; font-size: 15px;">
      <strong>{safe_name}</strong> has added you as their emergency contact on {APP_NAME}.
    </p>
    <p style="color: #555; line-height: 1.6; font-size: 15px;">
      If they trigger an SOS alert, you will be notified immediately with their location and any message they include.
    </p>
    <div style="text-align: center; margin: 28px 0;">
      <a href="{APP_DOWNLOAD_URL}"
         style="display: inline-block; background: #7c3aed; color: #ffffff; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 15px;">
        Download {APP_NAME}
      </a>
    </div>
    <p style="color: #999; font-size: 13px; text-align: center;">
      You can also respond to SOS alerts via SMS without the app.
    </p>
  </div>
</body>
</html>"""


def render_contact_invite_sms(inviter_name):
    safe_name = inviter_name or "Someone"
    return (
        f"{safe_name} added you as their emergency contact on {APP_NAME}. "
        f"You'll be notified if they trigger an SOS. "
        f"Download: {APP_DOWNLOAD_URL}"
    )


def _is_finite(v):
    return isinstance(v, (int, float)) and v == v and v != float("inf") and v != float("-inf")
