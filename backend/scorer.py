"""
scorer.py
---------
Deterministic mathematical scoring engine.
NO LLM calls. Pure Python + numpy.

Score Components:
  1. semantic_match (0.30)  — cosine_sim(JD text embedding, resume text embedding)
  2. evidence_match (0.30)  — mean cosine_sim(JD text embedding, code file embeddings)
  3. verification_ratio (0.25) — |verified ∩ claimed| / |claimed|
  4. experience_signal (0.15) — work experience relevance factor

Final score = Σ(component × weight), bounded [0, 1].

Guarantees:
  - Deterministic: same inputs → same outputs (no randomness, no temperature)
  - Bias-free: operates on anonymized text (names/locations stripped before embedding)
  - Transparent: every component is individually accessible
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

from backend.embeddings import (
    embed_text,
    embed_code,
    embed_codes,
    cosine_similarity,
    mean_cosine_similarity,
)

logger = logging.getLogger(__name__)


# ── Score weights (must sum to 1.0) ──────────────────────────────────────────
W_SEMANTIC = 0.30
W_EVIDENCE = 0.30
W_VERIFICATION = 0.25
W_EXPERIENCE = 0.15


@dataclass
class ScoringResult:
    """Immutable result of the deterministic scoring pipeline."""
    final_score: float
    semantic_match: float
    evidence_match: float
    verification_ratio: float
    experience_signal: float
    verified_skills: list[str] = field(default_factory=list)
    unverified_skills: list[str] = field(default_factory=list)
    component_breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize_skill(skill: str) -> str:
    """Normalize a skill name for comparison."""
    return skill.lower().strip().replace("-", "").replace("_", "").replace(".", "").replace(" ", "")


def _compute_verification_ratio(
    claimed_skills: list[str],
    verified_skills_sources: list[str],
) -> tuple[float, list[str], list[str]]:
    """
    Compute skill verification ratio.

    Parameters
    ----------
    claimed_skills : skills listed on the resume
    verified_skills_sources : skills found in GitHub deps / code files

    Returns
    -------
    (ratio, verified_list, unverified_list)
    """
    if not claimed_skills:
        return 0.0, [], []

    claimed_normalized = {_normalize_skill(s): s for s in claimed_skills}
    verified_normalized = {_normalize_skill(s) for s in verified_skills_sources}

    verified = []
    unverified = []

    for norm, original in claimed_normalized.items():
        if norm in verified_normalized:
            verified.append(original)
        else:
            # Fuzzy: check if the core of the skill name is in any verified dep
            found = False
            for vn in verified_normalized:
                if norm in vn or vn in norm:
                    verified.append(original)
                    found = True
                    break
            if not found:
                unverified.append(original)

    ratio = len(verified) / len(claimed_normalized) if claimed_normalized else 0.0
    return ratio, sorted(verified), sorted(unverified)


def _compute_experience_signal(
    work_history: list[dict],
    has_github_evidence: bool,
) -> float:
    """
    Compute experience relevance signal.

    - If work history exists AND there's GitHub evidence supporting it: 1.0
    - If work history exists but no GitHub evidence: 0.7 (take at face value, slight skepticism)
    - If no work history: 0.3
    - Scale by duration: more months = higher confidence

    Returns a float in [0, 1].
    """
    if not work_history:
        return 0.3

    total_months = sum(job.get("duration_months", 0) for job in work_history)

    # Duration factor: cap at 60 months (5 years) for full credit
    duration_factor = min(total_months / 60.0, 1.0)

    if has_github_evidence:
        # Strong signal: work experience + code to back it up
        base = 0.8 + (0.2 * duration_factor)
    else:
        # Moderate signal: take at face value with slight skepticism
        base = 0.5 + (0.2 * duration_factor)

    return min(base, 1.0)


def compute_final_score(
    jd_text: str,
    resume_text: str,
    code_contents: list[str],
    claimed_skills: list[str],
    verified_deps: list[str],
    work_history: list[dict],
    has_github_evidence: bool = True,
    codeforces_data: Optional[dict] = None,
    jd_requires_cp: bool = False,
) -> ScoringResult:
    """
    Compute the deterministic final candidate score.

    Parameters
    ----------
    jd_text : str
        The job description text.
    resume_text : str
        The ANONYMIZED resume text (PII already stripped).
    code_contents : list[str]
        Contents of fetched GitHub code files.
    claimed_skills : list[str]
        Skills listed on the resume.
    verified_deps : list[str]
        Skills/libraries found in GitHub repos.
    work_history : list[dict]
        Work experience entries from the structured profile.
    has_github_evidence : bool
        Whether any GitHub data was successfully fetched.
    codeforces_data : dict, optional
        Codeforces profile data (used only if JD requires CP).
    jd_requires_cp : bool
        Whether the JD mentions competitive programming.

    Returns
    -------
    ScoringResult
        Deterministic, fully transparent scoring result.
    """
    # 1. Semantic Match: JD text ↔ resume text
    jd_emb = embed_text(jd_text)
    resume_emb = embed_text(resume_text)
    semantic_match = cosine_similarity(jd_emb, resume_emb)
    # Clamp to [0, 1] (cosine sim can be slightly negative for unrelated texts)
    semantic_match = max(0.0, min(1.0, semantic_match))

    # 2. Evidence Match: JD text ↔ code files
    if code_contents:
        code_embs = embed_codes(code_contents)
        evidence_match = mean_cosine_similarity(jd_emb, code_embs)
        evidence_match = max(0.0, min(1.0, evidence_match))
    else:
        evidence_match = 0.0

    # 3. Verification Ratio: claimed skills ↔ GitHub-verified skills
    verification_ratio, verified_list, unverified_list = _compute_verification_ratio(
        claimed_skills, verified_deps
    )

    # 4. Experience Signal
    experience_signal = _compute_experience_signal(work_history, has_github_evidence)

    # ── Composite final score ────────────────────────────────────────────
    final_score = (
        semantic_match * W_SEMANTIC
        + evidence_match * W_EVIDENCE
        + verification_ratio * W_VERIFICATION
        + experience_signal * W_EXPERIENCE
    )
    final_score = round(final_score, 6)  # Round to avoid floating point noise

    # Optional CP bonus (only if JD requires it)
    cp_bonus = 0.0
    if jd_requires_cp and codeforces_data:
        max_rating = codeforces_data.get("max_rating")
        if max_rating and max_rating > 0:
            # Normalize rating: 3000+ = full bonus of 0.05
            cp_factor = min(max_rating / 3000.0, 1.0)
            cp_bonus = round(cp_factor * 0.05, 6)
            final_score = min(1.0, final_score + cp_bonus)

    result = ScoringResult(
        final_score=round(final_score, 6),
        semantic_match=round(semantic_match, 6),
        evidence_match=round(evidence_match, 6),
        verification_ratio=round(verification_ratio, 6),
        experience_signal=round(experience_signal, 6),
        verified_skills=verified_list,
        unverified_skills=unverified_list,
        component_breakdown={
            "semantic_match": {"value": round(semantic_match, 6), "weight": W_SEMANTIC, "weighted": round(semantic_match * W_SEMANTIC, 6)},
            "evidence_match": {"value": round(evidence_match, 6), "weight": W_EVIDENCE, "weighted": round(evidence_match * W_EVIDENCE, 6)},
            "verification_ratio": {"value": round(verification_ratio, 6), "weight": W_VERIFICATION, "weighted": round(verification_ratio * W_VERIFICATION, 6)},
            "experience_signal": {"value": round(experience_signal, 6), "weight": W_EXPERIENCE, "weighted": round(experience_signal * W_EXPERIENCE, 6)},
            "cp_bonus": cp_bonus,
        },
    )

    logger.info(
        "Score computed: final=%.4f (semantic=%.3f, evidence=%.3f, verification=%.3f, experience=%.3f, cp_bonus=%.3f)",
        result.final_score,
        result.semantic_match,
        result.evidence_match,
        result.verification_ratio,
        result.experience_signal,
        cp_bonus,
    )
    return result


# ── CLI quick-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Quick smoke test with dummy data
    result = compute_final_score(
        jd_text="Looking for a Python backend engineer with FastAPI and ML experience.",
        resume_text="Experienced Python developer with FastAPI, scikit-learn, Docker, PostgreSQL.",
        code_contents=["import fastapi\nfrom sklearn import pipeline\ndef train(): pass"],
        claimed_skills=["Python", "FastAPI", "scikit-learn", "Docker", "PostgreSQL"],
        verified_deps=["fastapi", "scikit-learn", "docker"],
        work_history=[{"role": "Backend Engineer", "duration_months": 36}],
        has_github_evidence=True,
    )
    print(f"Final Score: {result.final_score}")
    print(f"Breakdown: {result.component_breakdown}")
    print(f"Verified: {result.verified_skills}")
    print(f"Unverified: {result.unverified_skills}")
