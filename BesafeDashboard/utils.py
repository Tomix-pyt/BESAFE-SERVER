import requests
from datetime import datetime
from config import Config


# ─────────────────────────────────────────────────────────────
# NLP MODEL CALLER
# ─────────────────────────────────────────────────────────────

def call_nlp_api(text: str) -> dict | None:
    """
    POST transcribed text to the hosted NLP model.
    Returns: { "label": "threat"|"non-threat", "confidence": float }
    """
    try:
        resp = requests.post(
            Config.NLP_API_URL,
            json={"text": text},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"[NLP API ERROR] {e}")
        return None


# ─────────────────────────────────────────────────────────────
# PRIORITY SCORING
# ─────────────────────────────────────────────────────────────

def calculate_priority(alert: dict) -> float:
    """
    Dynamic priority score so the dashboard always shows
    the most urgent alert at the top.

    Formula:
        priority = (confidence × 0.6)
                 + (time_decay  × 0.3)   ← caps at 30 min ignored
                 + (unacked     × 0.1)   ← 1.0 if still 'active'

    Result: 0.0 → 1.0  (higher = more urgent)
    """
    confidence = float(alert.get("confidence", 0))

    created_at = alert.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except ValueError:
            created_at = datetime.now()
    elif not isinstance(created_at, datetime):
        created_at = datetime.now()

    minutes_old = (datetime.now() - created_at).total_seconds() / 60
    time_weight = min(minutes_old / 30.0, 1.0)

    unacked = 1.0 if alert.get("status") == "active" else 0.0

    priority = (confidence * 0.6) + (time_weight * 0.3) + (unacked * 0.1)
    return round(priority, 4)


def priority_label(score: float) -> str:
    if score >= 0.75:
        return "CRITICAL"
    elif score >= 0.50:
        return "HIGH"
    elif score >= 0.25:
        return "MEDIUM"
    return "LOW"


# ─────────────────────────────────────────────────────────────
# SMS  (Africa's Talking — swap for any provider)
# ─────────────────────────────────────────────────────────────

def send_sms(phone: str, message: str) -> bool:
    """
    Sends an SMS to non-agency contacts (family members).
    Requires africastalking package and credentials in .env
    """
    if not Config.SMS_API_KEY or not Config.SMS_USERNAME:
        print(f"[SMS SKIP] No credentials — would send to {phone}: {message}")
        return False
    try:
        import africastalking
        africastalking.initialize(
            username=Config.SMS_USERNAME,
            api_key=Config.SMS_API_KEY
        )
        sms      = africastalking.SMS
        response = sms.send(message, [phone])
        print(f"[SMS OK] → {phone}: {response}")
        return True
    except Exception as e:
        print(f"[SMS ERROR] {phone}: {e}")
        return False
