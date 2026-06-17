import logging
from flask import jsonify
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List
from config import Config

logger = logging.getLogger(__name__)

client = OpenAI(api_key=Config.GPT_API)

IDENTIFIED_PATTERN_TYPES = [
    # 1. Digital Coercion & Stalking Patterns
    "Digital Isolate & Command Pattern",
    "Velocity-Based Digital Stalking",
    "Surveillance-Backed Intimidation",
    "Grooming-Induced Compliance",

    # 2. Exploitation & Human Safety Patterns
    "Debt-Bondage Escalation Risk",
    "Document-Withholding Control",
    "Asymmetric Power Coercion",

    # 3. Longitudinal & Behavioral Lifecycle Patterns
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


def call_gpt_model(category, description, timing, frequency, system_prompt=SYSTEM_PROMPT):
    if not all([category, description, timing, frequency]):
        return jsonify({"error": "Incomplete intake parameters"}), 400

    user_content = (
        f"Incident Category: {category}\n"
        f"User Narrative: {description}\n"
        f"Reported Timing: {timing}\n"
        f"Reported Frequency: {frequency}"
    )

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

        # message.parsed is already a validated ReportAnalysisResponse instance
        return message.parsed.model_dump()

    except Exception as e:
        # Log full detail server-side; keep the analyst-facing report generic.
        logger.exception("GPT structured analysis pipeline failed")
        return {
            "identified_pattern_type": "Pipeline_Error",
            "severity_rating": 0.0,
            "pattern_tags": ["error"],
            "escalation_risk": "LOW",
            "timeline_urgency": "ROUTINE",
            "isolation_risk_detected": False,
            "investigative_priority": "LOW",
            "explainable_ai_report": "Error running the evaluation pipeline. See server logs for details.",
        }