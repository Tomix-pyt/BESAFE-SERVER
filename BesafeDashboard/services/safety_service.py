from config import Config
from utils import call_nlp_model

THREAT_THRESHOLD = 0.75


def analyze_text(text, user_id):
    label,confidence,version = call_nlp_model(text)
    if not label:
        raise Exception("AI analysis service unavailable")
    should_trigger_sos = label.lower() == "threat" and confidence >= THREAT_THRESHOLD

    if should_trigger_sos:
        print(f"[THREAT] user={user_id}: text='{text}', confidence={confidence}")

    return {
        "prediction": label,
        "confidence": confidence,
        "model_version": version,
        "shouldTriggerSOS": should_trigger_sos,
    }
