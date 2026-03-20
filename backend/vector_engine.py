"""
vector_engine.py
----------------
FAISS-backed vector similarity engine for per-skill matching.
Wraps the existing embeddings.py models with a FAISS IndexFlatIP index.

Computes:
  - Per-skill cosine similarities between JD and candidate skills
  - Overall JD ↔ resume text similarity
  - Skill-level evidence for the debate agents
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from backend.embeddings import embed_text, embed_texts
from backend.skill_taxonomy import normalize_skill

logger = logging.getLogger(__name__)

# Try importing FAISS; fall back to brute-force numpy if unavailable
try:
    import faiss
    HAS_FAISS = True
except ImportError:
    logger.warning("faiss-cpu not installed — falling back to numpy cosine similarity")
    HAS_FAISS = False


@dataclass
class SkillMatch:
    """A single JD skill ↔ candidate skill match."""
    jd_skill: str
    candidate_skill: str
    similarity: float


@dataclass
class VectorMatchResult:
    """Complete vector matching result."""
    overall_similarity: float
    skill_matches: list[SkillMatch] = field(default_factory=list)
    jd_skills_embedded: int = 0
    candidate_skills_embedded: int = 0


def _cosine_sim_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute cosine similarity matrix between two sets of vectors."""
    # Normalize
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    return a_norm @ b_norm.T


def _faiss_search(jd_embeddings: np.ndarray, candidate_embeddings: np.ndarray) -> np.ndarray:
    """
    Use FAISS IndexFlatIP to find cosine similarities.
    Assumes embeddings are already normalized.
    Returns a similarity matrix of shape (n_jd, n_candidate).
    """
    d = candidate_embeddings.shape[1]
    index = faiss.IndexFlatIP(d)

    # Normalize for cosine similarity via inner product
    faiss.normalize_L2(candidate_embeddings)
    index.add(candidate_embeddings)

    faiss.normalize_L2(jd_embeddings)
    n_candidate = candidate_embeddings.shape[0]
    distances, indices = index.search(jd_embeddings, n_candidate)

    # Reconstruct full similarity matrix
    sim_matrix = np.zeros((jd_embeddings.shape[0], n_candidate), dtype=np.float32)
    for i in range(jd_embeddings.shape[0]):
        for j in range(n_candidate):
            sim_matrix[i, indices[i, j]] = distances[i, j]

    return sim_matrix


def compute_skill_similarities(
    jd_skills: list[str],
    candidate_skills: list[str],
    similarity_threshold: float = 0.3,
) -> list[SkillMatch]:
    """
    Compute per-skill cosine similarities between JD and candidate skills.
    Uses FAISS if available, otherwise falls back to numpy.

    Returns a list of SkillMatch objects, one per JD skill,
    matched to the most similar candidate skill.
    """
    if not jd_skills or not candidate_skills:
        return []

    # Embed all skills
    jd_embs = embed_texts(jd_skills).astype(np.float32)
    cand_embs = embed_texts(candidate_skills).astype(np.float32)

    if jd_embs.size == 0 or cand_embs.size == 0:
        return []

    # Compute similarity matrix
    if HAS_FAISS:
        sim_matrix = _faiss_search(jd_embs.copy(), cand_embs.copy())
    else:
        sim_matrix = _cosine_sim_matrix(jd_embs, cand_embs)

    # For each JD skill, find the best candidate skill match
    matches = []
    for i, jd_skill in enumerate(jd_skills):
        best_j = int(np.argmax(sim_matrix[i]))
        best_sim = float(sim_matrix[i, best_j])

        if best_sim >= similarity_threshold:
            matches.append(SkillMatch(
                jd_skill=jd_skill,
                candidate_skill=candidate_skills[best_j],
                similarity=round(best_sim, 4),
            ))
        else:
            # Still record it but with the best match (even below threshold)
            matches.append(SkillMatch(
                jd_skill=jd_skill,
                candidate_skill=candidate_skills[best_j] if best_sim > 0 else "",
                similarity=round(max(best_sim, 0.0), 4),
            ))

    logger.info(
        "Skill similarities computed: %d JD skills × %d candidate skills → %d matches above threshold",
        len(jd_skills), len(candidate_skills),
        sum(1 for m in matches if m.similarity >= similarity_threshold),
    )
    return matches


def compute_overall_similarity(jd_text: str, resume_text: str) -> float:
    """
    Compute overall cosine similarity between JD and resume text.
    Uses the existing embed_text function.
    """
    if not jd_text.strip() or not resume_text.strip():
        return 0.0

    jd_emb = embed_text(jd_text)
    resume_emb = embed_text(resume_text)

    # Cosine similarity
    dot = float(np.dot(jd_emb, resume_emb))
    norm_a = float(np.linalg.norm(jd_emb))
    norm_b = float(np.linalg.norm(resume_emb))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    sim = dot / (norm_a * norm_b)
    return round(max(0.0, min(1.0, sim)), 4)


def compute_vector_match(
    jd_text: str,
    resume_text: str,
    jd_skills: list[str],
    candidate_skills: list[str],
) -> VectorMatchResult:
    """
    Full vector matching: overall text similarity + per-skill matches.
    """
    overall = compute_overall_similarity(jd_text, resume_text)
    skill_matches = compute_skill_similarities(jd_skills, candidate_skills)

    return VectorMatchResult(
        overall_similarity=overall,
        skill_matches=skill_matches,
        jd_skills_embedded=len(jd_skills),
        candidate_skills_embedded=len(candidate_skills),
    )


# ── CLI quick-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    result = compute_vector_match(
        jd_text="Looking for a Python backend engineer with FastAPI and ML experience.",
        resume_text="Experienced Python developer with FastAPI, scikit-learn, Docker, PostgreSQL.",
        jd_skills=["python", "fastapi", "machine-learning", "kubernetes", "aws"],
        candidate_skills=["python", "fastapi", "scikit-learn", "docker", "postgresql", "redis"],
    )
    print(f"Overall similarity: {result.overall_similarity}")
    for m in result.skill_matches:
        print(f"  {m.jd_skill} ↔ {m.candidate_skill}: {m.similarity}")
