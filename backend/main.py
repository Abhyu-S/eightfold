"""
main.py
-------
FastAPI backend for the AI Resume Screener (Next.js version).
Endpoints:
- /api/upload-candidate: Parse PDF, scrape, chunk, embed, store in memory.
- /api/add-jd: Embed JD and store.
- /api/match: Compare JD embeddings with all candidate chunks, score, and rank.
- /api/reset: Clear in-memory DB.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import settings
from backend.logger import get_logger
from backend.pdf_parser import extract_text_from_pdf_bytes, extract_links_from_pdf_bytes
from backend.anonymizer_agent import redact_pii, extract_structured_profile
from backend.github_scraper import fetch_github_profile, extract_github_username
from backend.codeforces_scraper import fetch_codeforces_profile, extract_codeforces_handle
from backend.leetcode_scraper import fetch_leetcode_profile, extract_leetcode_username
from backend.scorer import compute_final_score
from backend.explainer import generate_explanation
from backend.chunking import chunk_profile
from backend.embeddings import embed_texts, embed_text

logger = get_logger(__name__)

app = FastAPI(
    title="AI Resume Screener",
    description="Bias-free, deterministic candidate evaluation.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── IN-MEMORY VECTOR DB ───────────────────────────────────────────────────────
class CandidateData:
    def __init__(self, candidate_id: str, profile: dict, github_data: dict, codeforces_data: dict, leetcode_data: dict, chunks: list, chunk_embeddings: Any):
        self.candidate_id = candidate_id
        self.profile = profile
        self.github_data = github_data
        self.codeforces_data = codeforces_data
        self.leetcode_data = leetcode_data
        self.chunks = chunks
        self.chunk_embeddings = chunk_embeddings  # Numpy array of shape (N, D)

VECTOR_DB = {
    "candidates": {}, # candidate_id -> CandidateData
    "jd_embs": {}     # jd_id -> (text, embedding)
}

# ── SCHEMAS ──────────────────────────────────────────────────────────────────
class AddJDRequest(BaseModel):
    jd_text: str
    jd_id: str

class MatchRequest(BaseModel):
    jd_text: str
    top_k: int = 10

class MatchResult(BaseModel):
    candidate_id: str
    rank: int
    match_score: float
    final_score: float
    verified_skills: List[str]
    unverified_claims: List[str]
    verification_rate: float
    trajectory_score: float
    explanation: str
    top_language: Optional[str]
    cf_rank: Optional[str]
    cf_max_rating: Optional[int]


# ── HELPER FUNCTIONS ──────────────────────────────────────────────────────────
def _find_username(profile: dict, field_name: str, url_domain: str, extract_func) -> Optional[str]:
    if profile.get(field_name):
        return profile[field_name]
    for url_info in profile.get("external_urls", []):
        url = url_info.get("url", "")
        if url_domain in url:
            username = extract_func(url)
            if username:
                return username
    return None

def _detect_cp_requirement(jd_text: str) -> bool:
    cp_keywords = ["competitive programming", "codeforces", "leetcode", "hackerrank", "algorithmic", "dsa"]
    return any(kw in jd_text.lower() for kw in cp_keywords)

def _collect_code_contents(github_data: dict) -> list[str]:
    contents = []
    if not github_data or github_data.get("error"):
        return contents
    for repo_name, signals in github_data.get("code_signals", {}).items():
        for f in signals.get("code_files", []):
            content = f.get("content", "")
            if content.strip():
                contents.append(content)
        readme = signals.get("readme")
        if readme:
            contents.append(readme)
    return contents


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "AI Resume Screener is operational."}


@app.post("/api/upload-candidate")
async def upload_candidate(
    resume: UploadFile = File(...),
    github_username: str = Form(default=""),
    codeforces_handle: str = Form(default=""),
    leetcode_username: str = Form(default="")
):
    candidate_id = str(uuid.uuid4())[:8]
    logger.info("=== Uploading candidate %s ===", candidate_id)

    pdf_bytes = await resume.read()
    if not pdf_bytes:
        raise HTTPException(400, "Empty PDF file.")

    raw_text = extract_text_from_pdf_bytes(pdf_bytes)
    pdf_links = extract_links_from_pdf_bytes(pdf_bytes)

    # Extract & Redact
    redacted_text = redact_pii(raw_text)
    redacted_profile = extract_structured_profile(redacted_text, pdf_links=pdf_links)

    # Resolve Usernames
    gh_user = github_username or _find_username(redacted_profile, "github_username", "github.com", extract_github_username)
    cf_user = codeforces_handle or _find_username(redacted_profile, "codeforces_handle", "codeforces.com", extract_codeforces_handle)
    lc_user = leetcode_username or _find_username(redacted_profile, "leetcode_username", "leetcode.com", extract_leetcode_username)

    # Scrape
    github_data = fetch_github_profile(gh_user) if gh_user else None
    codeforces_data = fetch_codeforces_profile(cf_user) if cf_user else None
    leetcode_data = fetch_leetcode_profile(lc_user) if lc_user else None

    # Chunking
    chunks = chunk_profile(
        candidate_id=candidate_id,
        profile_dict=redacted_profile,
        github_data=github_data,
        codeforces_data=codeforces_data,
        leetcode_data=leetcode_data
    )

    # Embed Chunks
    chunk_texts = [c.text for c in chunks]
    chunk_embeddings = embed_texts(chunk_texts) if chunk_texts else None

    # Store in Memory DB
    VECTOR_DB["candidates"][candidate_id] = CandidateData(
        candidate_id=candidate_id,
        profile=redacted_profile,
        github_data=github_data or {},
        codeforces_data=codeforces_data or {},
        leetcode_data=leetcode_data or {},
        chunks=chunks,
        chunk_embeddings=chunk_embeddings
    )

    return {
        "candidate_id": candidate_id,
        "skills_found": len(redacted_profile.get("skills", []))
    }


@app.post("/api/add-jd")
async def add_jd(req: AddJDRequest):
    jd_emb = embed_text(req.jd_text)
    VECTOR_DB["jd_embs"][req.jd_id] = (req.jd_text, jd_emb)
    return {"status": "success", "jd_id": req.jd_id}


@app.post("/api/match", response_model=List[MatchResult])
async def match_candidates(req: MatchRequest):
    jd_text = req.jd_text
    top_k = req.top_k

    if not VECTOR_DB["candidates"]:
        return []

    jd_emb = embed_text(jd_text)
    jd_requires_cp = _detect_cp_requirement(jd_text)

    results = []
    
    for c_id, c_data in VECTOR_DB["candidates"].items():
        # Match Score (Semantic Match using the best chunk vs JD)
        # We can also compute evidence match here, but scorer.py expects the raw codes
        code_contents = _collect_code_contents(c_data.github_data)
        
        # We'll use the existing deterministic scorer which does its own code embedding / text embedding comparison
        # But wait, scorer.py embeds `resume_text`. We don't have a single `resume_text` anymore, we have chunks!
        # To adapt `scorer.py` without rewriting it entirely, we can pass the concatenated chunks text as `resume_text`.
        # Since `scorer.py` computes cosine sim on text, chunking is more for RAG retrieval but here we use it to construct the text.
        combined_text = "\n\n".join([c.text for c in c_data.chunks])
        
        claimed_skills = [s.get('name') if isinstance(s, dict) else s for s in c_data.profile.get("skills", [])]
        verified_deps = c_data.github_data.get("verified_dependencies", [])
        work_history = c_data.profile.get("work_history", [])
        has_github = not c_data.github_data.get("error", True) if c_data.github_data else False

        scoring_result = compute_final_score(
            jd_text=jd_text,
            resume_text=combined_text,
            code_contents=code_contents,
            claimed_skills=claimed_skills,
            verified_deps=verified_deps,
            work_history=work_history,
            has_github_evidence=has_github,
            codeforces_data=c_data.codeforces_data,
            jd_requires_cp=jd_requires_cp
        )

        explanation = generate_explanation(
            scoring_result=scoring_result,
            jd_text=jd_text,
            github_data=c_data.github_data,
            codeforces_data=c_data.codeforces_data,
            work_history=work_history
        )

        # Map to Frontend Schema
        total_claims = len(claimed_skills)
        verified_count = len(scoring_result.verified_skills)
        verification_rate = (verified_count / total_claims) if total_claims > 0 else 1.0
        
        # trajectory_score is just a synthetic metric derived from experience signal for the UI
        trajectory_score = min(5, max(1, round(scoring_result.experience_signal * 5)))

        top_lang = None
        if c_data.github_data and c_data.github_data.get("language_distribution"):
            langs = c_data.github_data.get("language_distribution")
            if langs:
                top_lang = list(langs.keys())[0]

        results.append(MatchResult(
            candidate_id=c_id,
            rank=0, # assigned after sorting
            match_score=scoring_result.semantic_match,
            final_score=scoring_result.final_score,
            verified_skills=scoring_result.verified_skills,
            unverified_claims=scoring_result.unverified_skills,
            verification_rate=verification_rate,
            trajectory_score=trajectory_score,
            explanation=explanation.get("summary", "Analysis completed."),
            top_language=top_lang,
            cf_rank=c_data.codeforces_data.get("rank") if c_data.codeforces_data else None,
            cf_max_rating=c_data.codeforces_data.get("max_rating") if c_data.codeforces_data else None
        ))

    # Sort and rank
    results.sort(key=lambda x: x.final_score, reverse=True)
    results = results[:top_k]
    
    for i, r in enumerate(results):
        r.rank = i + 1

    return results


@app.delete("/api/reset")
async def reset_db():
    VECTOR_DB["candidates"].clear()
    VECTOR_DB["jd_embs"].clear()
    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.APP_PORT, reload=True)
