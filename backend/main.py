"""
main.py
-------
FastAPI orchestrator for the AI Resume Screener.
Single endpoint that runs the full pipeline:
  PDF → Redact PII → Extract Profile → Scrape GitHub/Codeforces →
  Embed → Score (deterministic) → Bias Check → Explain
"""

import logging
import re
import uuid

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.logger import get_logger
from backend.pdf_parser import extract_text_from_pdf_bytes, extract_links_from_pdf_bytes
from backend.anonymizer_agent import redact_pii, extract_structured_profile
from backend.github_scraper import (
    fetch_github_profile,
    fetch_repo_code_signals,
    extract_github_username,
)
from backend.codeforces_scraper import fetch_codeforces_profile, extract_codeforces_handle
from backend.scorer import compute_final_score
from backend.explainer import generate_explanation

logger = get_logger(__name__)

app = FastAPI(
    title="AI Resume Screener",
    description="Bias-free, deterministic candidate evaluation with glass-box explainability.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "AI Resume Screener is operational."}


def _detect_cp_requirement(jd_text: str) -> bool:
    """Check if job description mentions competitive programming."""
    cp_keywords = [
        "competitive programming", "codeforces", "leetcode", "hackerrank",
        "algorithmic", "data structures and algorithms", "dsa",
        "problem solving", "competitive coder",
    ]
    jd_lower = jd_text.lower()
    return any(kw in jd_lower for kw in cp_keywords)


def _extract_all_urls(profile: dict) -> list[dict]:
    """Collect all URLs from the extracted profile."""
    urls = profile.get("external_urls", [])
    for project in profile.get("projects", []):
        url = project.get("url")
        if url and not any(u["url"] == url for u in urls):
            urls.append({"url": url, "type": "github_repo"})
    return urls


def _find_github_username(profile: dict) -> str | None:
    """Find GitHub username from profile data."""
    # Direct field
    if profile.get("github_username"):
        return profile["github_username"]
    # From URLs
    for url_info in profile.get("external_urls", []):
        url = url_info.get("url", "")
        if "github.com" in url:
            username = extract_github_username(url)
            if username:
                return username
    return None


def _find_codeforces_handle(profile: dict) -> str | None:
    """Find Codeforces handle from profile data."""
    if profile.get("codeforces_handle"):
        return profile["codeforces_handle"]
    for url_info in profile.get("external_urls", []):
        url = url_info.get("url", "")
        if "codeforces.com" in url:
            handle = extract_codeforces_handle(url)
            if handle:
                return handle
    return None


def _collect_code_contents(github_data: dict) -> list[str]:
    """Gather all fetched code file contents from GitHub data."""
    contents = []
    for repo_name, signals in github_data.get("code_signals", {}).items():
        for f in signals.get("code_files", []):
            content = f.get("content", "")
            if content.strip():
                contents.append(content)
        # Also include README as a signal
        readme = signals.get("readme")
        if readme:
            contents.append(readme)
    return contents


@app.post("/api/evaluate")
async def evaluate_candidate(
    resume_pdf: UploadFile = File(...),
    job_description: str = Form(...),
):
    """
    Full pipeline evaluation of a candidate resume against a job description.

    Returns deterministic scores, bias check results, and glass-box explanations.
    """
    candidate_id = str(uuid.uuid4())[:8]
    logger.info("=== Evaluating candidate %s ===", candidate_id)

    # ── Step 1: Extract PDF text ─────────────────────────────────────────
    pdf_bytes = await resume_pdf.read()
    if not pdf_bytes:
        raise HTTPException(400, "Empty PDF file.")

    raw_text = extract_text_from_pdf_bytes(pdf_bytes)
    if not raw_text.strip():
        raise HTTPException(400, "Could not extract text from PDF.")

    logger.info("Step 1: Extracted %d chars from PDF", len(raw_text))

    # ── Step 1b: Extract hyperlinks from PDF annotations ─────────────────
    pdf_links = extract_links_from_pdf_bytes(pdf_bytes)
    logger.info("Step 1b: Extracted %d hyperlinks from PDF: %s", len(pdf_links), pdf_links)

    # ── Step 2: Extract structured profile from ORIGINAL text ────────────
    original_profile = extract_structured_profile(raw_text, pdf_links=pdf_links)
    logger.info("Step 2: Extracted profile with %d skills", len(original_profile.get("skills", [])))

    # ── Step 3: Redact PII and extract from REDACTED text ────────────────
    redacted_text = redact_pii(raw_text)
    redacted_profile = extract_structured_profile(redacted_text, pdf_links=pdf_links)
    logger.info("Step 3: PII redacted, re-extracted profile")

    # ── Step 4: Find external profiles ───────────────────────────────────
    github_username = _find_github_username(original_profile)
    codeforces_handle = _find_codeforces_handle(original_profile)
    logger.info("Step 4: GitHub=%s, CF=%s", github_username, codeforces_handle)

    # ── Step 5: Scrape GitHub ────────────────────────────────────────────
    github_data = {"code_signals": {}, "verified_dependencies": [], "top_repos": []}
    has_github = False
    if github_username:
        try:
            github_data = fetch_github_profile(github_username)
            has_github = not github_data.get("error")
            logger.info("Step 5: GitHub fetched — %d repos, %d deps",
                       len(github_data.get("top_repos", [])),
                       len(github_data.get("verified_dependencies", [])))
        except Exception as exc:
            logger.warning("GitHub scraping failed: %s", exc)
    else:
        logger.info("Step 5: No GitHub username found, skipping")

    # ── Step 6: Scrape Codeforces ────────────────────────────────────────
    codeforces_data = None
    if codeforces_handle:
        try:
            codeforces_data = fetch_codeforces_profile(codeforces_handle)
            logger.info("Step 6: Codeforces fetched — rating=%s",
                       codeforces_data.get("max_rating"))
        except Exception as exc:
            logger.warning("Codeforces scraping failed: %s", exc)
    else:
        logger.info("Step 6: No Codeforces handle found, skipping")

    # ── Step 7: Collect code contents for embedding ──────────────────────
    code_contents = _collect_code_contents(github_data)
    logger.info("Step 7: Collected %d code content pieces for embedding", len(code_contents))

    # ── Step 8: Compute deterministic score (on REDACTED profile) ────────
    jd_requires_cp = _detect_cp_requirement(job_description)
    claimed_skills = redacted_profile.get("skills", [])
    verified_deps = github_data.get("verified_dependencies", [])
    work_history = redacted_profile.get("work_history", [])

    scoring_result = compute_final_score(
        jd_text=job_description,
        resume_text=redacted_text,
        code_contents=code_contents,
        claimed_skills=claimed_skills,
        verified_deps=verified_deps,
        work_history=work_history,
        has_github_evidence=has_github,
        codeforces_data=codeforces_data,
        jd_requires_cp=jd_requires_cp,
    )
    logger.info("Step 8: Score computed — final=%.4f", scoring_result.final_score)

    # ── Step 9: Bias check — score on original vs redacted ───────────────
    # Since we always score on redacted text, the score is already bias-free.
    # For the demo: re-score on the original text (which has PII) and verify delta ≈ 0.
    # The delta should be non-zero ONLY because embedding of PII text differs slightly.
    original_scoring = compute_final_score(
        jd_text=job_description,
        resume_text=raw_text,  # Original text WITH PII
        code_contents=code_contents,
        claimed_skills=original_profile.get("skills", []),
        verified_deps=verified_deps,
        work_history=original_profile.get("work_history", []),
        has_github_evidence=has_github,
        codeforces_data=codeforces_data,
        jd_requires_cp=jd_requires_cp,
    )

    bias_delta = abs(scoring_result.final_score - original_scoring.final_score)
    logger.info("Step 9: Bias check — redacted=%.4f, original=%.4f, delta=%.6f",
               scoring_result.final_score, original_scoring.final_score, bias_delta)

    # ── Step 10: Generate explanation ────────────────────────────────────
    explanation = {}
    try:
        explanation = generate_explanation(
            scoring_result=scoring_result,
            jd_text=job_description,
            github_data=github_data,
            codeforces_data=codeforces_data,
            work_history=work_history,
        )
        logger.info("Step 10: Explanation generated")
    except Exception as exc:
        logger.error("Explanation generation failed: %s", exc)
        explanation = {
            "pros": ["Score computed successfully"],
            "cons": ["Detailed explanation unavailable"],
            "summary": f"Candidate scored {scoring_result.final_score:.2f}/1.0 based on mathematical analysis.",
            "skill_evidence": [],
        }

    # ── Build response ───────────────────────────────────────────────────
    response = {
        "candidate_id": candidate_id,
        "final_score": scoring_result.final_score,
        "final_score_pct": round(scoring_result.final_score * 100, 2),
        "score_breakdown": scoring_result.component_breakdown,
        "bias_check": {
            "redacted_score": scoring_result.final_score,
            "original_score": original_scoring.final_score,
            "delta": round(bias_delta, 6),
            "is_bias_free": bias_delta < 0.01,
        },
        "explanation": explanation,
        "skills": {
            "verified": scoring_result.verified_skills,
            "unverified": scoring_result.unverified_skills,
            "claimed_count": len(claimed_skills),
            "verified_count": len(scoring_result.verified_skills),
        },
        "github_summary": {
            "username": github_username,
            "repos_analyzed": len(github_data.get("top_repos", [])),
            "languages": github_data.get("language_distribution", {}),
            "verified_deps": verified_deps[:20],
            "top_repos": [
                {"name": r["name"], "stars": r["stars"], "language": r["language"]}
                for r in github_data.get("top_repos", [])[:5]
            ],
        },
        "codeforces_summary": {
            "handle": codeforces_handle,
            "max_rating": codeforces_data.get("max_rating") if codeforces_data else None,
            "rank": codeforces_data.get("rank") if codeforces_data else None,
            "contests": codeforces_data.get("contests_participated", 0) if codeforces_data else 0,
            "solved_approx": codeforces_data.get("solved_problems_approx", 0) if codeforces_data else 0,
            "problem_distribution": codeforces_data.get("problem_rating_distribution", {}) if codeforces_data else {},
        },
        "profile": {
            "skills": redacted_profile.get("skills", []),
            "years_of_experience": redacted_profile.get("years_of_experience"),
            "work_history": work_history,
            "projects": redacted_profile.get("projects", []),
            "certifications": redacted_profile.get("certifications", []),
        },
    }

    logger.info("=== Evaluation complete for %s: %.2f%% ===", candidate_id, response["final_score_pct"])
    return response


# ── Run with uvicorn ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.APP_PORT, reload=True)
