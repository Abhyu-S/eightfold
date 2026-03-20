"""
anonymizer_agent.py
--------------------
Uses Gemini (native structured output) to:
  1. Strip all PII from raw resume text (name, gender, location, university, etc.)
  2. Parse the cleaned text into a structured JSON candidate profile.
  3. Extract external URLs (GitHub, Codeforces, project links) separately.

No LangChain. Direct google-generativeai SDK with response_schema.
"""

import json
import logging
import os
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv

from backend.config import settings
from backend.cache import cache_get, cache_set, _make_key

load_dotenv()
logger = logging.getLogger(__name__)

# ── Feature Flag ──────────────────────────────────────────────────────────────
USE_MOCK_DATA: bool = settings.USE_MOCK_DATA

# ── Configure Gemini ──────────────────────────────────────────────────────────
genai.configure(api_key=settings.GOOGLE_API_KEY)


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
            "url": "https://github.com/octocat/ml-pipeline",
        }
    ],
    "external_urls": [
        {"url": "https://github.com/octocat", "type": "github_profile"},
        {"url": "https://codeforces.com/profile/tourist", "type": "codeforces"},
    ],
    "github_username": "octocat",
    "codeforces_handle": "tourist",
    "pii_removed": True,
}


# ============================================================
# PII REDACTION
# ============================================================

REDACTION_PROMPT = """\
You are a Privacy AI. Your ONLY job is to take raw resume text and return a \
redacted version where ALL personally identifiable information is replaced.

REMOVE / REPLACE:
- Full name, nicknames, initials → "[Name Redacted]"
- Email addresses → "[Email Redacted]"
- Phone numbers → "[Phone Redacted]"
- Home city, state, country, ZIP → "[Location Redacted]"
- Age, date of birth, gender, nationality, ethnicity, religion → remove entirely
- University/college names → "[University Redacted]"
- Company names → "[Company Redacted]"  (but keep the role/title/achievements)
- LinkedIn/social URLs → remove (but keep GitHub/Codeforces URLs)
- Profile photos or physical descriptions → remove

PRESERVE EXACTLY:
- All technical skills, frameworks, languages
- Project descriptions and tech stacks
- Role titles and job achievements
- GitHub repository URLs and Codeforces handles
- Certifications and their names
- Duration of employment (months/years)

Return ONLY the redacted text. No extra commentary.
"""


def redact_pii(raw_text: str) -> str:
    """
    Strip all PII from raw resume text using Gemini Flash.
    Returns the redacted text string.
    Results are cached by content hash.
    """
    if USE_MOCK_DATA:
        return "[Name Redacted] is a software engineer with 5 years of experience..."

    if not raw_text or not raw_text.strip():
        return ""

    # Check cache
    cache_key = f"redact_pii:{_make_key(raw_text)}"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.info("PII redaction loaded from cache")
        return cached

    model = genai.GenerativeModel(settings.GEMINI_MODEL_FLASH)
    response = model.generate_content(
        [REDACTION_PROMPT, f"Resume text:\n---\n{raw_text}\n---"],
        generation_config=genai.types.GenerationConfig(
            temperature=0.0,
        ),
    )
    redacted = response.text.strip()

    cache_set(cache_key, redacted)
    logger.info("PII redacted: %d → %d chars", len(raw_text), len(redacted))
    return redacted


# ============================================================
# STRUCTURED EXTRACTION
# ============================================================

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "All technical skills, programming languages, frameworks, tools mentioned"
        },
        "years_of_experience": {
            "type": "integer",
            "description": "Total estimated years of professional experience"
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "degree": {"type": "string"},
                    "institution": {"type": "string", "description": "Use [University Redacted] if in redacted text"},
                    "year": {"type": "integer"}
                },
                "required": ["degree"]
            }
        },
        "work_history": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "company": {"type": "string"},
                    "duration_months": {"type": "integer"},
                    "key_achievements": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["role"]
            }
        },
        "certifications": {
            "type": "array",
            "items": {"type": "string"}
        },
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "tech_stack": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "url": {"type": "string", "description": "Project URL if listed (GitHub, etc.)"}
                },
                "required": ["name"]
            }
        },
        "external_urls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "type": {
                        "type": "string",
                        "description": "One of: github_profile, github_repo, codeforces, leetcode, portfolio, other"
                    }
                },
                "required": ["url", "type"]
            },
            "description": "All external URLs found in the resume"
        },
        "github_username": {
            "type": "string",
            "description": "GitHub username extracted from profile URL. null if not found."
        },
        "codeforces_handle": {
            "type": "string",
            "description": "Codeforces handle extracted from profile URL. null if not found."
        }
    },
    "required": ["skills", "projects", "external_urls"]
}

EXTRACTION_PROMPT = """\
You are a Talent Data Extraction AI. Parse the following resume text into a \
structured JSON profile.

RULES:
1. Extract ALL technical skills, frameworks, languages, and tools mentioned.
2. Extract ALL external URLs that are EXPLICITLY written in the resume text.
3. For GitHub profile URLs like github.com/username, extract the username.
4. For Codeforces URLs like codeforces.com/profile/handle, extract the handle.
5. Estimate years_of_experience from work history dates.
6. List all projects with their tech stacks and URLs.
7. If information is missing, use null or empty arrays.

CRITICAL: Do NOT invent, guess, or hallucinate any URLs, usernames, or handles.
Only extract information that is EXPLICITLY present in the text.
If there is no Codeforces URL in the text, set codeforces_handle to null.
If there is no GitHub URL in the text, set github_username to null.
Do NOT make up URLs that are not in the text.

Return ONLY the JSON object matching the schema.
"""


def extract_structured_profile(text: str, pdf_links: list[str] = None) -> dict:
    """
    Parse resume text (original or redacted) into a structured JSON profile
    using Gemini Flash with native structured output.

    Parameters
    ----------
    text : str
        Resume text (from PDF extraction).
    pdf_links : list[str], optional
        Pre-extracted hyperlinks from PDF annotations.
        These are merged into the profile to ensure no links are missed.

    Returns a dict matching the EXTRACTION_SCHEMA.
    """
    if USE_MOCK_DATA:
        logger.info("USE_MOCK_DATA=True — returning mock anonymized profile")
        return dict(MOCK_ANONYMIZED_PROFILE)

    if not text or not text.strip():
        raise ValueError("Input text is empty — cannot extract profile.")

    # Check cache (include pdf_links in cache key)
    links_key = ",".join(sorted(pdf_links or []))
    cache_key = f"extract_profile:{_make_key(text + links_key)}"
    cached = cache_get(cache_key)
    if cached is not None:
        try:
            logger.info("Structured profile loaded from cache")
            return json.loads(cached)
        except json.JSONDecodeError:
            pass

    # Include PDF-extracted links in the prompt so the LLM knows about them
    links_section = ""
    if pdf_links:
        links_section = "\n\nThe following hyperlinks were extracted from the PDF document:\n"
        for link in pdf_links:
            links_section += f"- {link}\n"
        links_section += "\nUse these actual URLs in your extraction. Do NOT invent additional URLs."

    model = genai.GenerativeModel(
        settings.GEMINI_MODEL_FLASH,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            response_schema=EXTRACTION_SCHEMA,
            temperature=0.0,
        ),
    )

    response = model.generate_content(
        [EXTRACTION_PROMPT, f"Resume text:\n---\n{text}\n---{links_section}"]
    )

    parsed = json.loads(response.text)
    parsed["pii_removed"] = "[Redacted]" in text or "[redacted]" in text.lower()

    # Merge PDF-extracted links that the LLM might have missed
    if pdf_links:
        existing_urls = {u.get("url", "") for u in parsed.get("external_urls", [])}
        for link in pdf_links:
            if link not in existing_urls:
                link_type = _classify_url(link)
                parsed.setdefault("external_urls", []).append(
                    {"url": link, "type": link_type}
                )
                # Also set github_username / codeforces_handle if found
                if link_type == "github_profile" and not parsed.get("github_username"):
                    from backend.github_scraper import extract_github_username
                    username = extract_github_username(link)
                    if username:
                        parsed["github_username"] = username
                elif link_type == "codeforces" and not parsed.get("codeforces_handle"):
                    from backend.codeforces_scraper import extract_codeforces_handle
                    handle = extract_codeforces_handle(link)
                    if handle:
                        parsed["codeforces_handle"] = handle

    # Cache the result
    cache_set(cache_key, json.dumps(parsed, ensure_ascii=False))

    logger.info(
        "Extraction complete. Skills: %d, URLs: %d, Projects: %d",
        len(parsed.get("skills", [])),
        len(parsed.get("external_urls", [])),
        len(parsed.get("projects", [])),
    )
    return parsed


def _classify_url(url: str) -> str:
    """Classify a URL into a type."""
    url_lower = url.lower()
    if "github.com" in url_lower:
        # Check if it's a repo URL or a profile URL
        parts = url_lower.rstrip("/").split("github.com/")[-1].split("/")
        if len(parts) >= 2:
            return "github_repo"
        return "github_profile"
    if "codeforces.com" in url_lower:
        return "codeforces"
    if "leetcode.com" in url_lower:
        return "leetcode"
    if "linkedin.com" in url_lower:
        return "linkedin"
    if "kaggle.com" in url_lower:
        return "kaggle"
    return "other"


def anonymize_and_parse_resume(resume_text: str, pdf_links: list[str] = None) -> dict:
    """
    Full pipeline: redact PII then extract structured profile.
    Convenience wrapper that returns the profile from redacted text.
    Also returns the redacted text itself for bias checking.
    """
    redacted_text = redact_pii(resume_text)
    profile = extract_structured_profile(redacted_text, pdf_links=pdf_links)
    profile["_redacted_text"] = redacted_text
    return profile


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
