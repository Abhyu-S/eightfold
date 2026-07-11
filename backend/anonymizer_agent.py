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

from pydantic import BaseModel, Field
from typing import List
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate

from backend.llm import get_llm
from backend.config import settings
from backend.cache import cache_get, cache_set, _make_key

load_dotenv()
logger = logging.getLogger(__name__)

# ── Feature Flag ──────────────────────────────────────────────────────────────
USE_MOCK_DATA: bool = settings.USE_MOCK_DATA


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

REDACTION_PROMPT = """REDACTION_PROMPT = ""\
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

PRESERVE EXACTLY — DO NOT MODIFY ANY CHARACTER WITHIN THESE, EVEN IF THEY \
CONTAIN THE PERSON'S NAME OR A USERNAME THAT LOOKS LIKE THEIR NAME:
- All technical skills, frameworks, languages
- Project descriptions and tech stacks
- Role titles and job achievements
- GitHub repository URLs and Codeforces handles — copy them character-for-character, \
including the username portion (e.g. github.com/johnsmith123 must stay EXACTLY \
as github.com/johnsmith123, never github.com/[Name Redacted])
- Certifications and their names
- Duration of employment (months/years)

CRITICAL RULE: Redaction only applies to standalone mentions of a person's real name \
in running text (e.g. "John Smith is a software engineer..."). It NEVER applies to \
substrings inside a URL, even if that substring resembles or matches the person's name. \
A username in a URL is not the same thing as the person's name — leave every URL untouched.

Return ONLY the redacted text. No extra commentary.
"""


def redact_pii(raw_text: str) -> str:
    if USE_MOCK_DATA:
        return "[Name Redacted] is a software engineer with 5 years of experience..."

    if not raw_text or not raw_text.strip():
        return ""

    cache_key = f"redact_pii:{_make_key(raw_text)}"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.info("PII redaction loaded from cache")
        return cached

    llm = get_llm(temperature=0.0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", REDACTION_PROMPT),
        ("human", "Resume text:\n---\n{text}\n---"),
    ])
    response = (prompt | llm).invoke({"text": raw_text})
    redacted = response.content.strip()

    cache_set(cache_key, redacted)
    logger.info("PII redacted: %d → %d chars", len(raw_text), len(redacted))
    return redacted

# ============================================================
# STRUCTURED EXTRACTION
# ============================================================

class EducationEntry(BaseModel):
    degree: str
    institution: Optional[str] = None
    year: Optional[int] = None

class WorkEntry(BaseModel):
    role: str
    company: Optional[str] = None
    duration_months: Optional[int] = None
    key_achievements: List[str] = Field(default_factory=list)

class ProjectEntry(BaseModel):
    name: str
    description: Optional[str] = None
    tech_stack: List[str] = Field(default_factory=list)
    url: Optional[str] = None

class ExternalUrl(BaseModel):
    url: str
    type: str  # github_profile | github_repo | codeforces | leetcode | portfolio | other

class CandidateProfile(BaseModel):
    skills: List[str]
    years_of_experience: Optional[int] = None
    education: List[EducationEntry] = Field(default_factory=list)
    work_history: List[WorkEntry] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[ProjectEntry]
    external_urls: List[ExternalUrl]
    github_username: Optional[str] = None
    codeforces_handle: Optional[str] = None
    leetcode_username: Optional[str] = None   

EXTRACTION_PROMPT = """\
You are a Talent Data Extraction AI. Parse the following resume text into a \
structured JSON profile.

RULES:
1. Extract ALL technical skills, frameworks, languages, and tools mentioned.
2. Extract ALL external URLs that are EXPLICITLY written in the resume text.
3. For GitHub profile URLs like github.com/username, extract the username.
4. For Codeforces URLs like codeforces.com/profile/handle, extract the handle.
5. For LeetCode URLs like leetcode.com/u/username, extract the username as leetcode_username.
6. Estimate years_of_experience from work history dates.
7. List all projects with their tech stacks and URLs.
8. If information is missing, use null or empty arrays.

CRITICAL: Do NOT invent, guess, or hallucinate any URLs, usernames, or handles.
Only extract information that is EXPLICITLY present in the text.
If there is no Codeforces URL in the text, set codeforces_handle to null.
If there is no GitHub URL in the text, set github_username to null.
If there is no LeetCode URL in the text, set leetcode_username to null.
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

    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(CandidateProfile)

    result: CandidateProfile = structured_llm.invoke(
        f"{EXTRACTION_PROMPT}\n\nResume text:\n---\n{text}\n---{links_section}"
    )
    parsed = result.model_dump()
    parsed["pii_removed"] = "redacted" in text.lower()

    # Merge PDF-extracted links that the LLM might have missed
    if pdf_links:
        existing_urls = {u.get("url", "") for u in parsed.get("external_urls", [])}
        for link in pdf_links:
            link_type = _classify_url(link)

            if link not in existing_urls:
                parsed.setdefault("external_urls", []).append(
                    {"url": link, "type": link_type}
                )
                existing_urls.add(link)

            # Backfill username/handle fields independently of whether the
            # URL was already present — the LLM sometimes lists the URL but
            # misses the corresponding field.
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
            elif link_type == "leetcode" and not parsed.get("leetcode_username"):
                from backend.leetcode_scraper import extract_leetcode_username
                username = extract_leetcode_username(link)
                if username:
                 parsed["leetcode_username"] = username

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
