"""
advocate.py
-----------
The Advocate agent argues FOR hiring the candidate.
Uses Gemini Flash via langchain-google-genai.
Receives the evidence bundle and produces structured arguments.
"""

import json
import logging

import google.generativeai as genai

from backend.config import settings
from backend.evidence_bundle import format_evidence_for_prompt

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GOOGLE_API_KEY)

ADVOCATE_PROMPT = """\
You are the ADVOCATE agent in a multi-agent hiring debate system.

YOUR ROLE: Argue FOR hiring this candidate. You are their champion.
However, you MUST base every argument on the evidence bundle below.
Do NOT fabricate or exaggerate — argue only from observed data.

RULES:
1. Highlight strong skill matches (similarity ≥ 0.75)
2. Emphasize GitHub-verified skills over unverified claims
3. Point out extra skills the candidate brings beyond requirements
4. Cite specific evidence: repo names, similarity scores, experience years
5. Acknowledge gaps honestly but reframe them constructively
6. Be specific and quantitative — no generic praise

EVIDENCE BUNDLE:
{evidence}

PREVIOUS DEBATE CONTEXT (if any):
{context}

Respond as JSON with this schema:
{{
  "key_arguments": ["string"],
  "skill_highlights": ["string"],
  "experience_strengths": ["string"],
  "rebuttal_to_critic": "string or null",
  "overall_assessment": "string"
}}
"""

ADVOCATE_SCHEMA = {
    "type": "object",
    "properties": {
        "key_arguments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Main arguments for hiring this candidate",
        },
        "skill_highlights": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific skill strengths with evidence",
        },
        "experience_strengths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Experience-based arguments",
        },
        "rebuttal_to_critic": {
            "type": "string",
            "description": "Counter-arguments to critic's points (null if round 1)",
        },
        "overall_assessment": {
            "type": "string",
            "description": "1-2 sentence strong recommendation",
        },
    },
    "required": ["key_arguments", "skill_highlights", "overall_assessment"],
}


def run_advocate(
    evidence_bundle: dict,
    previous_context: str = "",
    round_num: int = 1,
) -> dict:
    """
    Run the advocate agent.

    Parameters
    ----------
    evidence_bundle : the shared evidence bundle
    previous_context : debate context from previous rounds
    round_num : current debate round

    Returns
    -------
    dict with advocate's structured arguments
    """
    evidence_text = format_evidence_for_prompt(evidence_bundle)

    prompt = ADVOCATE_PROMPT.format(
        evidence=evidence_text,
        context=previous_context or "This is the first round — no previous context.",
    )

    model = genai.GenerativeModel(
        settings.GEMINI_MODEL_FLASH,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            response_schema=ADVOCATE_SCHEMA,
            temperature=0.1,
        ),
    )

    response = model.generate_content(prompt)
    result = json.loads(response.text)

    logger.info(
        "Advocate (round %d): %d arguments, %d skill highlights",
        round_num,
        len(result.get("key_arguments", [])),
        len(result.get("skill_highlights", [])),
    )
    return result
