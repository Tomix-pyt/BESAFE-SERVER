import base64
import io
import json
import logging

import requests
from flask import jsonify
from openai import OpenAI
from PIL import Image
from pydantic import BaseModel, Field
from typing import List, Optional
from config import Config

logger = logging.getLogger(__name__)

IDENTIFIED_PATTERN_TYPES = [
    "Digital Isolate & Command Pattern",
    "Velocity-Based Digital Stalking",
    "Surveillance-Backed Intimidation",
    "Grooming-Induced Compliance",
    "Debt-Bondage Escalation Risk",
    "Document-Withholding Control",
    "Asymmetric Power Coercion",
    "Persistent Behavioral Escalation",
    "Cyclical Intimidation Wave",
    "Acute Safety Crisis Shock",
]


class ReportAnalysisResponse(BaseModel):
    identified_pattern_type: str = Field(description=f"Behavioral pattern category, one of {IDENTIFIED_PATTERN_TYPES}")
    severity_rating: float = Field(description="Calculated severity from 0.0 to 1.0")
    pattern_tags: List[str] = Field(description="Strategic risk tags, one of DIGITAL_EXPLOITATION, GROOMING, SEXTORTION, COERCION")
    escalation_risk: str = Field(description="HIGH, MEDIUM, or LOW")
    timeline_urgency: str = Field(description="IMMEDIATE, DELAYED, or ROUTINE")
    isolation_risk_detected: bool
    investigative_priority: str = Field(description="CRITICAL, HIGH, MEDIUM, or LOW")
    explainable_ai_report: str = Field(description="Short strategic summary mapping the systemic risk vectors for the analyst")


SYSTEM_PROMPT = (
    "You are an expert investigative data analyst specializing in human safety, trafficking prevention, "
    "and survivor advocacy. You are evaluating a structured case report submitted through a mobile intake "
    "pipeline. Your task is to identify behavioral patterns, assess escalating risk profiles, and generate "
    "an objective, auditable report synthesis that supports organizational resource management and "
    "caseworker decisions. Focus on identifying long-term patterns of coercion, grooming, digital "
    "exploitation, or sextortion. Do not suggest autonomous intervention paths; your data output must "
    "serve strictly as human decision-support evidence."
)


# ── OpenAI client (lazy) ────────────────────────────────────────
_openai_client = None

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=Config.GPT_API)
    return _openai_client


# ── Gemini client (lazy) ───────────────────────────────────────
_gemini_client = None

def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(api_key=Config.GEMINI_API_KEY)
    return _gemini_client


MAX_IMAGES = 4
MAX_IMAGE_DIM = 1024


def _process_image_from_url(url):
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        logger.warning("Failed to process image %s: %s", url, e)
        return None


def _process_document_text(url):
    if url.endswith(".txt"):
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return resp.text[:2000]
        except Exception as e:
            logger.warning("Failed to fetch document %s: %s", url, e)
    return None


def _process_attachments(attachments):
    if not attachments:
        return {"evidence_notes": "", "image_data_urls": []}

    evidence_notes = []
    image_data_urls = []
    image_count = 0

    for att in attachments:
        name = att.get("name", "file")
        url = att.get("url") or att.get("uri", "")
        file_type = att.get("type", "document")

        if file_type == "photo" and image_count < MAX_IMAGES:
            data_url = _process_image_from_url(url)
            if data_url:
                image_data_urls.append(data_url)
                image_count += 1
                evidence_notes.append(f"[Image evidence: {name}]")
            else:
                evidence_notes.append(f"[Image unavailable: {name}]")
        elif file_type == "photo":
            evidence_notes.append(f"[Image omitted (limit): {name}]")
        elif file_type == "document":
            text = _process_document_text(url)
            if text:
                evidence_notes.append(f"[Document evidence: {name}]\n{text}")
            else:
                evidence_notes.append(f"[Document attached: {name}]")
        elif file_type == "audio":
            evidence_notes.append(f"[Audio recording: {name}]")
        elif file_type == "video":
            evidence_notes.append(f"[Video evidence: {name}]")
        else:
            evidence_notes.append(f"[Attachment: {name}]")

    return {
        "evidence_notes": "\n\n".join(evidence_notes),
        "image_data_urls": image_data_urls,
    }


# ── OpenAI implementation ──────────────────────────────────────

def _build_user_content(category, description, timing, frequency, attachments=None):
    base = (
        f"Incident Category: {category}\n"
        f"User Narrative: {description}\n"
        f"Reported Timing: {timing}\n"
        f"Reported Frequency: {frequency}"
    )

    if not attachments:
        return base

    evidence = _process_attachments(attachments)
    if not evidence["image_data_urls"]:
        if evidence["evidence_notes"]:
            return base + "\n\n---\n" + evidence["evidence_notes"]
        return base

    text_content = base
    if evidence["evidence_notes"]:
        text_content += "\n\n---\n" + evidence["evidence_notes"]

    parts = [{"type": "text", "text": text_content}]
    for data_url in evidence["image_data_urls"]:
        parts.append({"type": "image_url", "image_url": {"url": data_url}})
    return parts


def _call_openai(category, description, timing, frequency, system_prompt=SYSTEM_PROMPT, attachments=None):
    if not all([category, description, timing, frequency]):
        return jsonify({"error": "Incomplete intake parameters"}), 400

    client = _get_openai_client()
    user_content = _build_user_content(category, description, timing, frequency, attachments=attachments)

    try:
        completion = client.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format=ReportAnalysisResponse,
        )

        choice = completion.choices[0]

        if choice.finish_reason == "length":
            raise ValueError("Model response was truncated before completion (max_tokens reached)")

        message = choice.message

        if message.refusal:
            raise ValueError(f"Model declined to process this report: {message.refusal}")

        result = message.parsed.model_dump()
        result["provider"] = "openai"
        return result

    except Exception as e:
        logger.exception("[provider=openai] analysis failed")
        return {
            "identified_pattern_type": "Pipeline_Error",
            "severity_rating": 0.0,
            "pattern_tags": ["error"],
            "escalation_risk": "LOW",
            "timeline_urgency": "ROUTINE",
            "isolation_risk_detected": False,
            "investigative_priority": "LOW",
            "explainable_ai_report": "Error running the evaluation pipeline. See server logs for details.",
            "error_message": f"[provider=openai] {e}",
        }


# ── Gemini implementation ──────────────────────────────────────

# Schema description embedded in the prompt so Gemini knows the expected JSON shape
_GEMINI_SCHEMA_HINT = """Respond with a JSON object matching this exact schema:
{
  "identified_pattern_type": "<one of the pattern types>",
  "severity_rating": <0.0 to 1.0>,
  "pattern_tags": ["<tag1>", "<tag2>"],
  "escalation_risk": "HIGH" | "MEDIUM" | "LOW",
  "timeline_urgency": "IMMEDIATE" | "DELAYED" | "ROUTINE",
  "isolation_risk_detected": true | false,
  "investigative_priority": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
  "explainable_ai_report": "<short strategic summary>"
}"""


def _call_gemini(category, description, timing, frequency, system_prompt=SYSTEM_PROMPT, attachments=None):
    if not all([category, description, timing, frequency]):
        return jsonify({"error": "Incomplete intake parameters"}), 400

    if not Config.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not configured")
        return {
            "identified_pattern_type": "Pipeline_Error",
            "severity_rating": 0.0,
            "pattern_tags": ["error"],
            "escalation_risk": "LOW",
            "timeline_urgency": "ROUTINE",
            "isolation_risk_detected": False,
            "investigative_priority": "LOW",
            "explainable_ai_report": "Gemini API key not configured.",
            "error_message": "Gemini API key is missing in server configuration.",
        }

    try:
        from google import genai
        client = _get_gemini_client()
        user_content = (
            _build_user_content(category, description, timing, frequency, attachments=attachments)
            + "\n\n"
            + _GEMINI_SCHEMA_HINT
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_content,
            config=genai.types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                system_instruction=system_prompt,
            ),
        )

        text = response.text.strip()

        # Remove potential markdown fence if the model wraps JSON in ```json ... ```
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()

        raw = json.loads(text)
        parsed = ReportAnalysisResponse.model_validate(raw)
        result = parsed.model_dump()
        result["provider"] = "gemini"
        return result

    except Exception as e:
        logger.exception("[provider=gemini] analysis failed")
        return {
            "identified_pattern_type": "Pipeline_Error",
            "severity_rating": 0.0,
            "pattern_tags": ["error"],
            "escalation_risk": "LOW",
            "timeline_urgency": "ROUTINE",
            "isolation_risk_detected": False,
            "investigative_priority": "LOW",
            "explainable_ai_report": "Error running the evaluation pipeline. See server logs for details.",
            "error_message": f"[provider=gemini] {e}",
        }


# ── FreeModel client (lazy) ────────────────────────────────────
_freemodel_client = None

def _get_freemodel_client():
    global _freemodel_client
    if _freemodel_client is None:
        _freemodel_client = OpenAI(
            api_key=Config.FREEMODEL_API_KEY,
            base_url=Config.FREEMODEL_BASE_URL,
        )
    return _freemodel_client


# ── FreeModel implementation ──────────────────────────────────

def _call_freemodel(category, description, timing, frequency, system_prompt=SYSTEM_PROMPT, attachments=None):
    if not all([category, description, timing, frequency]):
        return jsonify({"error": "Incomplete intake parameters"}), 400

    if not Config.FREEMODEL_API_KEY:
        logger.error("FREEMODEL_API_KEY not configured")
        return {
            "identified_pattern_type": "Pipeline_Error",
            "severity_rating": 0.0,
            "pattern_tags": ["error"],
            "escalation_risk": "LOW",
            "timeline_urgency": "ROUTINE",
            "isolation_risk_detected": False,
            "investigative_priority": "LOW",
            "explainable_ai_report": "FreeModel API key not configured.",
            "error_message": "FreeModel API key is missing in server configuration.",
        }

    client = _get_freemodel_client()
    user_content = _build_user_content(category, description, timing, frequency, attachments=attachments)

    try:
        # FreeModel supports json_object but not json_schema — validate with Pydantic after parse
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt + "\n\nRespond with JSON matching the schema provided in the user message."},
                {"role": "user", "content": user_content + "\n\n" + _GEMINI_SCHEMA_HINT},
            ],
            response_format={"type": "json_object"},
        )

        choice = completion.choices[0]

        if choice.finish_reason == "length":
            raise ValueError("Model response was truncated before completion (max_tokens reached)")

        message = choice.message

        if message.refusal:
            raise ValueError(f"Model declined to process this report: {message.refusal}")

        raw = json.loads(message.content)
        parsed = ReportAnalysisResponse.model_validate(raw)
        result = parsed.model_dump()
        result["provider"] = "freemodel"
        return result

    except Exception as e:
        logger.exception("[provider=freemodel] analysis failed")
        return {
            "identified_pattern_type": "Pipeline_Error",
            "severity_rating": 0.0,
            "pattern_tags": ["error"],
            "escalation_risk": "LOW",
            "timeline_urgency": "ROUTINE",
            "isolation_risk_detected": False,
            "investigative_priority": "LOW",
            "explainable_ai_report": "Error running the evaluation pipeline. See server logs for details.",
            "error_message": f"[provider=freemodel] {e}",
        }


# ── Public dispatcher ──────────────────────────────────────────

def call_gpt_model(category, description, timing, frequency, system_prompt=SYSTEM_PROMPT, attachments=None):
    provider = (Config.AI_PROVIDER or "gemini").strip().lower()
    logger.info("AI_PROVIDER=%s dispatching analysis", provider)

    if provider == "openai":
        return _call_openai(category, description, timing, frequency, system_prompt, attachments=attachments)

    if provider == "freemodel":
        return _call_freemodel(category, description, timing, frequency, system_prompt, attachments=attachments)

    # default: gemini
    return _call_gemini(category, description, timing, frequency, system_prompt, attachments=attachments)
