import json
from flask import jsonify
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List
from config import Config

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
    "Acute Safety Crisis Shock"
]
# pydentic return shema
class ReportAnalysisResponse(BaseModel):
    identified_pattern_type: str = Field(description=f"Behavioral pattern categories of {IDENTIFIED_PATTERN_TYPES}")
    severity_rating: float = Field(description="Calculated severity from 0.0 to 1.0")
    pattern_tags: List[str] = Field(description="Strict Strategic risk tags like  [DIGITIAL EXPLOITATION, GROOMING,SEXTORTION, or COERSION]")
    escalation_risk: str = Field(description="HIGH, MEDIUM, or LOW tracking indicator")
    timeline_urgency: str = Field(description="IMMEDIATE, DELAYED, or ROUTINE action indicator")
    isolation_risk_detected: bool
    investigative_priority: str = Field(description="CRITICAL, HIGH, MEDIUM, or LOW")
    explainable_ai_report: str = Field(description="Strategic summary mapping out the systemic risk vectors for the analyst, NOT TOO LONG")

# system prompt
SYSTEM_PROMT = "You are an expert investigative data analyst specializing in human safety, trafficking prevention, " \
        "and survivor advocacy. You are evaluating a structured case report submitted through a mobile intake pipeline. Your task " \
        "is to identify behavioral patterns, assess escalating risk profiles, and generate an objective, auditable report synthesis " \
        "that supports organizational resource management and caseworker decisions. Focus on identifying long-term patterns of coercion," \
        " grooming, digital explotation or sextortion. Do not suggest autonomous intervention paths; your data output must serve strictly as " \
        "human decision-support evidence. YOUR OUPUT SHOULD STRICLY FOLLOW OUTPUT GUARDRAILS"

def call_gpt_model(category,description,timing,frequency,system_prompt=SYSTEM_PROMT):
    user_content = (
            f"Incident Category: {category}\n"
            f"User Narrative: {description}\n"
            f"Reported Timing: {timing}\n"
            f"Reported Frequency: {frequency}")

    if not all([category, description, timing, frequency]):
            return jsonify({"error": "Incomplete intake parameters"}), 400

    try :
        response = client.chat.completions.create(
                model="gpt-4o",
                response_format={ "type": "json_schema"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format=ReportAnalysisResponse,
            )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        # this is a fall back mechanism
        return{
            "identified_pattern_type": "Pipeline_Error",
            "severity_rating": 0.0,
            "pattern_tags": ["error"],
            "escalation_risk": "LOW",
            "timeline_urgency": "ROUTINE",
            "isolation_risk_detected": False,
            "investigative_priority": "LOW",
            "explainable_ai_report": f"Error running asynchronous evaluation processing pipeline. Logs: {str(e)}"
            }
