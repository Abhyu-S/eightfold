"""
fairness.py
-----------
The Fairness agent fact-checks both Advocate and Critic.
Cross-references their claims against the evidence bundle.
Ensures balanced debate and flags bias or factual errors.
"""

import json
import logging

import google.generativeai as genai

from backend.config import settings
from backend.evidence_bundle import format_evidence_for_prompt

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GOOGLE_API_KEY)

FAIRNESS_PROMPT = """\
You are the FAIRNESS agent in a multi-agent hiring debate system.

YOUR ROLE: Fact-check BOTH the Advocate and Critic. You are the impartial referee.
Cross-reference every claim they make against the evidence bundle.
Flag any factual errors, exaggerations, or biased reasoning.

RULES:
1. For each major claim by Advocate or Critic, verify it against the evidence
2. Flag if Advocate overstates a weak match (sim < 0.5) as strong
3. Flag if Critic ignores a strong match (sim ≥ 0.75)
4. Check if either agent makes claims not supported by the data
5. Ensure no bias based on non-skill factors
6. Produce a balanced, fact-based review
7. Indicate which agent's arguments are more data-supported

EVIDENCE BUNDLE:
{evidence}

ADVOCATE'S ARGUMENTS:
{advocate_args}

CRITIC'S ARGUMENTS:
{critic_args}

Respond as JSON with this schema:
{{
  "fact_checks": [
    {{
      "claim": "string",
      "claimed_by": "advocate or critic",
      "verdict": "accurate, exaggerated, inaccurate, or unsupported",
      "correction": "string or null"
    }}
  ],
  "advocate_accuracy": "high, medium, or low",
  "critic_accuracy": "high, medium, or low",
  "bias_flags": ["string"],
  "balanced_summary": "string"
}}
"""

FAIRNESS_SCHEMA = {
    "type": "object",
    "properties": {
        "fact_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "claimed_by": {"type": "string"},
                    "verdict": {"type": "string"},
                    "correction": {"type": "string"},
                },
                "required": ["claim", "claimed_by", "verdict"],
            },
            "description": "Individual fact checks on claims made by agents",
        },
        "advocate_accuracy": {
            "type": "string",
            "description": "Overall accuracy of advocate's arguments: high, medium, or low",
        },
        "critic_accuracy": {
            "type": "string",
            "description": "Overall accuracy of critic's arguments: high, medium, or low",
        },
        "bias_flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Any detected bias in either agent's arguments",
        },
        "balanced_summary": {
            "type": "string",
            "description": "Fair, balanced summary of the debate so far",
        },
    },
    "required": ["fact_checks", "advocate_accuracy", "critic_accuracy", "balanced_summary"],
}


def run_fairness(
    evidence_bundle: dict,
    advocate_result: dict,
    critic_result: dict,
    round_num: int = 1,
) -> dict:
    """
    Run the fairness agent to fact-check both sides.

    Parameters
    ----------
    evidence_bundle : the shared evidence bundle
    advocate_result : advocate's arguments (dict)
    critic_result : critic's concerns (dict)
    round_num : current debate round

    Returns
    -------
    dict with fairness review
    """
    evidence_text = format_evidence_for_prompt(evidence_bundle)

    prompt = FAIRNESS_PROMPT.format(
        evidence=evidence_text,
        advocate_args=json.dumps(advocate_result, indent=2),
        critic_args=json.dumps(critic_result, indent=2),
    )

    model = genai.GenerativeModel(
        settings.GEMINI_MODEL_FLASH,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            response_schema=FAIRNESS_SCHEMA,
            temperature=0.0,
        ),
    )

    response = model.generate_content(prompt)
    result = json.loads(response.text)

    logger.info(
        "Fairness (round %d): %d fact checks, advocate=%s, critic=%s, %d bias flags",
        round_num,
        len(result.get("fact_checks", [])),
        result.get("advocate_accuracy", "?"),
        result.get("critic_accuracy", "?"),
        len(result.get("bias_flags", [])),
    )
    return result
