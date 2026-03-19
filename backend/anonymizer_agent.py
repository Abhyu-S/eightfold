"""
anonymizer_agent.py
--------------------
Uses an LLM (via LangChain) to:
  1. Strip all PII (name, age, gender, location, contact details) from raw resume text.
  2. Parse the cleaned text into a structured JSON candidate profile.

Supports both OpenAI (GPT-4o) and Google Gemini backends via the LLM_PROVIDER env var.

Output JSON schema:
{
    "skills": ["Python", "FastAPI", ...],
    "years_of_experience": 4,
    "education": [{"degree": "B.Tech CS", "institution": "Redacted", "year": 2020}],
    "work_history": [
        {
            "role": "Software Engineer",
            "company": "Tech Company A",
            "duration_months": 24,
            "key_achievements": ["Built X", "Led Y"]
        }
    ],
    "certifications": ["AWS Solutions Architect"],
    "projects": [
        {
            "name": "Project Name",
            "description": "What it does",
            "tech_stack": ["Python", "React"]
        }
    ],
    "pii_removed": true
}
"""

import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()
logger = logging.getLogger(__name__)

# ── Feature Flag ──────────────────────────────────────────────────────────────
USE_MOCK_DATA: bool = os.getenv("USE_MOCK_DATA", "False").lower() == "true"


# ============================================================
# MOCK OUTPUT
# ============================================================
MOCK_ANONYMIZED_PROFILE = {
    "skills": [
        "Python", "FastAPI", "React", "TypeScript", "Docker",
        "PostgreSQL", "Redis", "AWS", "Machine Learning", "scikit-learn",
    ],
    "years_of_experience": 5,
    "education": [
        {
            "degree": "B.Tech Computer Science",
            "institution": "[University Redacted]",
            "year": 2019,
        }
    ],
    "work_history": [
        {
            "role": "Senior Software Engineer",
            "company": "[Company A Redacted]",
            "duration_months": 30,
            "key_achievements": [
                "Reduced API response time by 40% via caching layer",
                "Led migration from monolith to microservices",
            ],
        },
        {
            "role": "Software Engineer",
            "company": "[Company B Redacted]",
            "duration_months": 24,
            "key_achievements": [
                "Built real-time data pipeline processing 1M events/day",
                "Mentored 3 junior engineers",
            ],
        },
    ],
    "certifications": ["AWS Certified Developer – Associate"],
    "projects": [
        {
            "name": "ML Pipeline Automation",
            "description": "End-to-end ML pipeline with automated retraining and drift detection",
            "tech_stack": ["Python", "scikit-learn", "Apache Airflow", "Docker"],
        }
    ],
    "pii_removed": True,
}


# ============================================================
# LLM FACTORY
# ============================================================

def _build_llm():
    """
    Instantiate the correct LLM based on the LLM_PROVIDER env var.
    Raises a clear error if the required API key is missing.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    model = os.getenv("LLM_MODEL", "gpt-4o")

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY is not set in .env")
        return ChatOpenAI(model=model, temperature=0, openai_api_key=api_key)

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GOOGLE_API_KEY is not set in .env")
        return ChatGoogleGenerativeAI(model=model, temperature=0, google_api_key=api_key)

    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: '{provider}'. Use 'openai' or 'gemini'.")


# ============================================================
# PROMPTS
# ============================================================

ANONYMIZER_SYSTEM_PROMPT = """\
You are a Privacy & Talent Assessment AI. Your task is to process raw resume text and return a STRICT JSON object.

RULES:
1. Remove ALL personally identifiable information (PII):
   - Full name, nicknames, initials
   - Email addresses, phone numbers, URLs/social media handles
   - Home city, state, country, ZIP codes
   - Age, date of birth, gender, nationality, ethnicity, religion
   - LinkedIn, GitHub, Twitter URLs (the URLs themselves — keep content/skills)
   - University/company names may be replaced with "[University Redacted]" or "[Company Redacted]"
2. Preserve all technical content: skills, tech stacks, achievements, project descriptions.
3. Estimate `years_of_experience` as an integer from work history dates.
4. Output ONLY valid JSON — no markdown, no extra text, no code fences.
5. Follow the exact schema provided below.

OUTPUT SCHEMA:
{
  "skills": ["string"],
  "years_of_experience": integer,
  "education": [
    {
      "degree": "string",
      "institution": "string (redact if identifiable)",
      "year": integer or null
    }
  ],
  "work_history": [
    {
      "role": "string",
      "company": "string (use [Company Redacted] or generic descriptor)",
      "duration_months": integer,
      "key_achievements": ["string"]
    }
  ],
  "certifications": ["string"],
  "projects": [
    {
      "name": "string",
      "description": "string",
      "tech_stack": ["string"]
    }
  ],
  "pii_removed": true
}
"""

ANONYMIZER_HUMAN_PROMPT = """\
Here is the raw resume text to process:

---
{resume_text}
---

Return the anonymized JSON profile now.
"""


# ============================================================
# MAIN PUBLIC FUNCTION
# ============================================================

def anonymize_and_parse_resume(
    resume_text: str,
    llm=None,
) -> dict:
    """
    Strip PII from resume text and parse it into a structured JSON profile.

    Parameters
    ----------
    resume_text : str
        Raw text extracted from a PDF resume.
    llm : optional
        Pre-built LangChain LLM instance. If None, one is created from env vars.

    Returns
    -------
    dict
        Structured anonymized candidate profile.

    Raises
    ------
    ValueError
        If the LLM returns output that cannot be parsed as valid JSON.
    """
    if USE_MOCK_DATA:
        logger.info("USE_MOCK_DATA=True — returning mock anonymized profile")
        return dict(MOCK_ANONYMIZED_PROFILE)

    if not resume_text or not resume_text.strip():
        raise ValueError("resume_text is empty — cannot anonymize.")

    # Build LLM if not provided
    if llm is None:
        llm = _build_llm()

    # ── LangChain LCEL Chain ─────────────────────────────────────────────
    prompt = ChatPromptTemplate.from_messages([
        ("system", ANONYMIZER_SYSTEM_PROMPT),
        ("human", ANONYMIZER_HUMAN_PROMPT),
    ])
    chain = prompt | llm | StrOutputParser()

    logger.info("Invoking anonymization LLM chain (%d chars input)...", len(resume_text))

    raw_output = chain.invoke({"resume_text": resume_text})

    # ── Parse JSON robustly ───────────────────────────────────────────────
    parsed = _parse_json_robustly(raw_output)
    logger.info(
        "Anonymization complete. Skills found: %d, Experience: %s yrs",
        len(parsed.get("skills", [])),
        parsed.get("years_of_experience", "?"),
    )
    return parsed


def _parse_json_robustly(raw: str) -> dict:
    """
    Attempt to extract and parse JSON from LLM output.
    Handles cases where the model adds extra prose or markdown fences.
    """
    raw = raw.strip()

    # Remove common markdown code fences
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        )

    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try finding the first { ... } block
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM output could not be parsed as JSON.\n"
                f"Raw output:\n{raw}\n\nError: {exc}"
            ) from exc

    raise ValueError(f"No JSON object found in LLM output:\n{raw}")


# ── CLI quick-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import pprint
    from backend.pdf_parser import extract_text_from_pdf

    if len(sys.argv) < 2:
        print("Usage: python -m backend.anonymizer_agent <path-to-resume.pdf>")
        sys.exit(1)

    text = extract_text_from_pdf(sys.argv[1])
    profile = anonymize_and_parse_resume(text)
    pprint.pprint(profile)
