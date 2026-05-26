from config import Config
from utils import call_nlp_api

THREAT_THRESHOLD = 0.75


def analyze_text(text, user_id):
    result = call_nlp_api(text)
    if not result:
        raise Exception("AI analysis service unavailable")

    prediction = result.get("prediction", "")
    confidence = float(result.get("confidence", 0))
    model_version = result.get("model_version", "unknown")

    should_trigger_sos = prediction.lower() == "threat" and confidence >= THREAT_THRESHOLD

    if should_trigger_sos:
        print(f"[THREAT] user={user_id}: text='{text}', confidence={confidence}")

    return {
        "prediction": prediction,
        "confidence": confidence,
        "model_version": model_version,
        "shouldTriggerSOS": should_trigger_sos,
    }
