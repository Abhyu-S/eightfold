"""
main.py
-------
FastAPI backend for the Agentic Talent Intelligence Platform.

Endpoints:
  POST /api/upload-candidate   → Upload PDF + GitHub/CF handles → run full pipeline
  POST /api/add-jd             → Store a Job Description in the vector DB
  GET  /api/match              → Get top-k candidate matches for a JD
  GET  /api/health             → Health check
  GET  /api/candidates         → List all candidate IDs in the vector store
"""

import json
import logging
import os
import uuid
from typing import Optional

import chromadb
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.anonymizer_agent import anonymize_and_parse_resume
from backend.codeforces_scraper import fetch_codeforces_profile
from backend.evaluation_agents import evaluate_candidate
from backend.github_scraper import fetch_github_profile
from backend.pdf_parser import extract_text_from_pdf_bytes
from backend.vector_db import (
    add_candidate,
    add_job_description,
    clear_all,
    delete_candidate,
    get_top_matches,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Agentic Talent Intelligence Platform",
    description="AI-powered, bias-free candidate matching for modern recruiters.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store: candidate_id → full review (cached to avoid re-running agents)
_candidate_store: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class AddJDRequest(BaseModel):
    jd_text: str
    jd_id: Optional[str] = "default_jd"


class MatchRequest(BaseModel):
    jd_text: str
    top_k: Optional[int] = 5


class MatchResult(BaseModel):
    candidate_id: str
    rank: int
    match_score: float
    final_score: float
    verified_skills: list[str]
    unverified_claims: list[str]
    verification_rate: float
    trajectory_score: int
    explanation: str
    top_language: str
    cf_rank: Optional[str]
    cf_max_rating: Optional[int]


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/add-jd")
async def add_jd(request: AddJDRequest):
    """Store a Job Description in the vector database."""
    if not request.jd_text.strip():
        raise HTTPException(status_code=400, detail="jd_text cannot be empty.")
    try:
        add_job_description(request.jd_text, jd_id=request.jd_id)
        return {"message": f"JD '{request.jd_id}' stored successfully."}
    except Exception as exc:
        logger.error("Failed to add JD: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/upload-candidate")
async def upload_candidate(
    resume: UploadFile = File(...),
    github_username: str = Form(default=""),
    codeforces_handle: str = Form(default=""),
    candidate_label: Optional[str] = Form(default=None),
):
    """
    Full pipeline for a single candidate:
      1. Extract text from uploaded PDF
      2. Anonymize & parse with LLM
      3. Scrape GitHub + Codeforces
      4. Store unified profile in ChromaDB
      5. Return the full profile for the frontend
    """
    # Validate file type
    if not resume.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported.")

    # Generate unique candidate ID
    candidate_id = candidate_label or f"candidate_{uuid.uuid4().hex[:8]}"

    try:
        # ── Step 1: Parse PDF ──────────────────────────────────────────
        pdf_bytes = await resume.read()
        raw_text = extract_text_from_pdf_bytes(pdf_bytes)
        if not raw_text.strip():
            raise HTTPException(
                status_code=422,
                detail="Could not extract text from the PDF. Please use a text-based PDF."
            )

        # ── Step 2: Anonymize ─────────────────────────────────────────
        profile = anonymize_and_parse_resume(raw_text)

        # ── Step 3: Scrape GitHub ─────────────────────────────────────
        github_data: dict = {}
        if github_username.strip():
            github_data = fetch_github_profile(github_username.strip())
            # Merge verified dependencies into profile for embedding
            profile["github_verified_deps"] = github_data.get("verified_dependencies", [])
        else:
            github_data = {"verified_dependencies": [], "top_repos": [], "language_distribution": {}, "error": None}

        # ── Step 4: Scrape Codeforces ──────────────────────────────────
        cf_data: dict = {}
        if codeforces_handle.strip():
            cf_data = fetch_codeforces_profile(codeforces_handle.strip())
            profile["cf_max_rating"] = cf_data.get("max_rating")
        else:
            cf_data = {
                "max_rating": None, "current_rating": None, "rank": None,
                "max_rank": None, "contests_participated": 0,
                "recent_contests": [], "solved_problems_approx": 0,
                "contribution": 0, "error": None,
            }

        # ── Step 5: Store in ChromaDB ─────────────────────────────────
        add_candidate(
            profile=profile,
            candidate_id=candidate_id,
            metadata={
                "github_username": github_username,
                "codeforces_handle": codeforces_handle,
            },
        )

        # Cache raw data for later evaluation
        _candidate_store[candidate_id] = {
            "profile": profile,
            "github_data": github_data,
            "cf_data": cf_data,
        }

        return {
            "candidate_id": candidate_id,
            "message": "Candidate ingested successfully.",
            "skills_found": len(profile.get("skills", [])),
            "github_deps_verified": len(github_data.get("verified_dependencies", [])),
            "cf_rating": cf_data.get("current_rating"),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Pipeline error for candidate '%s': %s", candidate_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(exc)}")


@app.post("/api/match", response_model=list[MatchResult])
async def match_candidates(request: MatchRequest):
    """
    Find and evaluate the top-k candidates matching the provided JD.
    Runs the full Agentic Reasoning Panel on each matched candidate.
    """
    if not request.jd_text.strip():
        raise HTTPException(status_code=400, detail="jd_text cannot be empty.")

    try:
        raw_matches = get_top_matches(request.jd_text, k=request.top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {str(exc)}")

    if not raw_matches:
        return []

    results: list[MatchResult] = []
    for match in raw_matches:
        cid = match["candidate_id"]
        stored = _candidate_store.get(cid, {})

        profile   = stored.get("profile")   or match.get("profile") or {}
        gh_data   = stored.get("github_data") or {}
        cf_data   = stored.get("cf_data")     or {}

        try:
            review = evaluate_candidate(
                candidate_profile=profile,
                github_data=gh_data,
                codeforces_data=cf_data,
                jd_text=request.jd_text,
                match_score=match["similarity_score"],
                candidate_id=cid,
            )
        except Exception as exc:
            logger.error("Agent evaluation failed for '%s': %s", cid, exc, exc_info=True)
            # Return partial result rather than failing the whole endpoint
            review = {
                "tech_lead": {"verified_skills": [], "unverified_claims": [], "verification_rate": 0, "verdict": "Evaluation error."},
                "trajectory": {"score": 1, "reasoning": "Could not evaluate."},
                "explainability": {"summary": "Evaluation error occurred."},
                "final_score": match["similarity_score"],
                "github_summary": {},
                "codeforces_summary": {},
            }

        results.append(MatchResult(
            candidate_id=cid,
            rank=match["rank"],
            match_score=match["similarity_score"],
            final_score=review.get("final_score", match["similarity_score"]),
            verified_skills=review["tech_lead"].get("verified_skills", []),
            unverified_claims=review["tech_lead"].get("unverified_claims", []),
            verification_rate=review["tech_lead"].get("verification_rate", 0),
            trajectory_score=review["trajectory"].get("score", 1),
            explanation=review["explainability"].get("summary", ""),
            top_language=review.get("github_summary", {}).get("top_language", "Unknown"),
            cf_rank=review.get("codeforces_summary", {}).get("rank"),
            cf_max_rating=review.get("codeforces_summary", {}).get("max_rating"),
        ))

    # Re-sort by final_score descending
    results.sort(key=lambda r: r.final_score, reverse=True)
    for i, r in enumerate(results, start=1):
        r.rank = i

    return results


@app.get("/api/candidates")
async def list_candidates():
    """List all currently stored candidate IDs."""
    return {"candidates": list(_candidate_store.keys()), "count": len(_candidate_store)}


@app.delete("/api/candidates/{candidate_id}")
async def remove_candidate(candidate_id: str):
    """Remove a candidate from both the vector store and in-memory cache."""
    try:
        delete_candidate(candidate_id)
        _candidate_store.pop(candidate_id, None)
        return {"message": f"Candidate '{candidate_id}' removed."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/api/reset")
async def reset_all():
    """⚠️ Wipe ALL candidates from the vector store (for testing/demo reset)."""
    clear_all()
    _candidate_store.clear()
    return {"message": "All data cleared."}


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
