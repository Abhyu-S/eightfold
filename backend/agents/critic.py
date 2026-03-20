"""
critic.py
---------
The Critic agent argues AGAINST hiring the candidate.
Identifies risks, skill gaps, and unverified claims.
Uses Gemini Flash via google-generativeai.
"""

import json
import logging

import google.generativeai as genai

from backend.config import settings
from backend.evidence_bundle import format_evidence_for_prompt

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GOOGLE_API_KEY)

CRITIC_PROMPT = """\
You are the CRITIC agent in a multi-agent hiring debate system.

YOUR ROLE: Argue AGAINST hiring this candidate. You must identify risks, gaps, and weaknesses.
However, you MUST base every argument on the evidence bundle below.
Do NOT fabricate issues — criticize only what the data shows.

RULES:
1. Highlight missing skills the JD requires but candidate lacks
2. Flag unverified skills (claimed on resume but not found in GitHub)
3. Point out weak matches (similarity < 0.50)
4. Question experience gaps or inconsistencies
5. Assess risk: what could go wrong if this person is hired?
6. Be specific and quantitative — no vague concerns
7. If the candidate is actually strong, acknowledge it but still find areas of concern

EVIDENCE BUNDLE:
{evidence}

PREVIOUS DEBATE CONTEXT (if any):
{context}

Respond as JSON with this schema:
{{
  "key_concerns": ["string"],
  "skill_gaps": ["string"],
  "verification_issues": ["string"],
  "risk_assessment": "string",
  "rebuttal_to_advocate": "string or null",
  "overall_assessment": "string"
}}
"""

CRITIC_SCHEMA = {
    "type": "object",
    "properties": {
        "key_concerns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Main concerns about hiring this candidate",
        },
        "skill_gaps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific skill gaps with evidence",
        },
        "verification_issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Skills claimed but not verified",
        },
        "risk_assessment": {
            "type": "string",
            "description": "Overall risk assessment if hired",
        },
        "rebuttal_to_advocate": {
            "type": "string",
            "description": "Counter to advocate's arguments (null if round 1)",
        },
        "overall_assessment": {
            "type": "string",
            "description": "1-2 sentence critical assessment",
        },
    },
    "required": ["key_concerns", "skill_gaps", "overall_assessment"],
}


def run_critic(
    evidence_bundle: dict,
    previous_context: str = "",
    round_num: int = 1,
) -> dict:
    """
    Run the critic agent.

    Parameters
    ----------
    evidence_bundle : the shared evidence bundle
    previous_context : debate context from previous rounds
    round_num : current debate round

    Returns
    -------
    dict with critic's structured concerns
    """
    evidence_text = format_evidence_for_prompt(evidence_bundle)

    prompt = CRITIC_PROMPT.format(
        evidence=evidence_text,
        context=previous_context or "This is the first round — no previous context.",
    )

    model = genai.GenerativeModel(
        settings.GEMINI_MODEL_FLASH,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            response_schema=CRITIC_SCHEMA,
            temperature=0.1,
        ),
    )

    response = model.generate_content(prompt)
    result = json.loads(response.text)

    logger.info(
        "Critic (round %d): %d concerns, %d skill gaps",
        round_num,
        len(result.get("key_concerns", [])),
        len(result.get("skill_gaps", [])),
    )
    return result
