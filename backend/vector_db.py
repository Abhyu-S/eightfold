"""
vector_db.py
------------
Manages the ChromaDB vector store for candidate-JD matching.

Functions:
  - add_job_description(jd_text, jd_id)          → embed & store a JD
  - add_candidate(profile_json, candidate_id)     → embed & store a candidate profile
  - get_top_matches(jd_text, k)                   → retrieve top-k candidate matches
  - delete_candidate(candidate_id)                → remove a candidate
  - clear_all()                                   → wipe the collection (testing)

Embedding: Uses LangChain's OpenAI or Google embeddings based on LLM_PROVIDER.
Persistence: ChromaDB stores data on disk at CHROMA_PERSIST_DIR.
"""

import json
import logging
import os
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
CANDIDATE_COLLECTION = "candidates"
JD_COLLECTION = "job_descriptions"

# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDING MODEL FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def _build_embedding_fn():
    """
    Returns a ChromaDB-compatible embedding function based on provider.
    Supports OpenAI and Google Gemini.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY is not set.")
        return OpenAIEmbeddingFunction(api_key=api_key, model_name="text-embedding-3-small")

    elif provider == "gemini":
        from chromadb.utils.embedding_functions import GoogleGenerativeAiEmbeddingFunction
        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            raise EnvironmentError("GOOGLE_API_KEY is not set.")
        return GoogleGenerativeAiEmbeddingFunction(api_key=api_key)

    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: '{provider}'")


# ─────────────────────────────────────────────────────────────────────────────
# CHROMADB CLIENT SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_client: Optional[chromadb.PersistentClient] = None
_embedding_fn = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info("ChromaDB initialized at '%s'", CHROMA_PERSIST_DIR)
    return _client


def _get_embedding_fn():
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = _build_embedding_fn()
    return _embedding_fn


def _get_collection(name: str):
    """Get or create a named ChromaDB collection with the configured embedding function."""
    client = _get_client()
    return client.get_or_create_collection(
        name=name,
        embedding_function=_get_embedding_fn(),
        metadata={"hnsw:space": "cosine"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE → TEXT SERIALIZER
# ─────────────────────────────────────────────────────────────────────────────

def _profile_to_text(profile: dict) -> str:
    """
    Convert a structured candidate profile JSON to a rich text document
    suitable for embedding. Optimised for semantic similarity with JD text.
    """
    parts = []

    skills = profile.get("skills", [])
    if skills:
        parts.append("Technical Skills: " + ", ".join(skills))

    yoe = profile.get("years_of_experience")
    if yoe is not None:
        parts.append(f"Years of Experience: {yoe}")

    for job in profile.get("work_history", []):
        role = job.get("role", "")
        company = job.get("company", "")
        months = job.get("duration_months", 0)
        achievements = ". ".join(job.get("key_achievements", []))
        parts.append(
            f"Role: {role} at {company} ({months} months). {achievements}"
        )

    for proj in profile.get("projects", []):
        name = proj.get("name", "")
        desc = proj.get("description", "")
        tech = ", ".join(proj.get("tech_stack", []))
        parts.append(f"Project '{name}': {desc}. Tech: {tech}")

    certs = profile.get("certifications", [])
    if certs:
        parts.append("Certifications: " + ", ".join(certs))

    # GitHub-verified fields (added by orchestrator later)
    gh_deps = profile.get("github_verified_deps", [])
    if gh_deps:
        parts.append("GitHub Verified Libraries: " + ", ".join(gh_deps))

    # Codeforces
    cf_rating = profile.get("cf_max_rating")
    if cf_rating:
        parts.append(f"Competitive Programming — Max Rating: {cf_rating}")

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def add_job_description(jd_text: str, jd_id: str = "default_jd") -> None:
    """
    Embed and store a Job Description in ChromaDB.

    Parameters
    ----------
    jd_text : str   The full job description text.
    jd_id   : str   A unique identifier for this JD (default: "default_jd").
    """
    if not jd_text.strip():
        raise ValueError("jd_text cannot be empty.")

    collection = _get_collection(JD_COLLECTION)
    collection.upsert(
        ids=[jd_id],
        documents=[jd_text],
        metadatas=[{"type": "job_description", "jd_id": jd_id}],
    )
    logger.info("JD '%s' added to vector store (%d chars)", jd_id, len(jd_text))


def add_candidate(
    profile: dict,
    candidate_id: str,
    metadata: Optional[dict] = None,
) -> None:
    """
    Embed and store a candidate profile in ChromaDB.

    Parameters
    ----------
    profile      : dict   Structured candidate profile (from anonymizer + scrapers).
    candidate_id : str    Unique identifier for this candidate (e.g. "candidate_001").
    metadata     : dict   Optional extra metadata to store alongside the vector.
    """
    if not profile:
        raise ValueError("profile cannot be empty.")

    doc_text = _profile_to_text(profile)

    meta = {"type": "candidate", "candidate_id": candidate_id}
    if metadata:
        meta.update(metadata)

    # Store the profile JSON so we can retrieve it later
    meta["profile_json"] = json.dumps(profile)

    collection = _get_collection(CANDIDATE_COLLECTION)
    collection.upsert(
        ids=[candidate_id],
        documents=[doc_text],
        metadatas=[meta],
    )
    logger.info(
        "Candidate '%s' added to vector store (%d chars embedded)",
        candidate_id,
        len(doc_text),
    )


def get_top_matches(jd_text: str, k: int = 5) -> list[dict]:
    """
    Find the top-k candidates whose profiles best match the given JD text.

    Parameters
    ----------
    jd_text : str   The job description to match against.
    k       : int   Number of top candidates to return (default: 5).

    Returns
    -------
    list[dict]  Ranked list of candidates, each containing:
        {
            "candidate_id": str,
            "similarity_score": float,   # 0–1, higher is better
            "profile": dict,             # reconstructed candidate profile
            "rank": int,                 # 1-indexed ranking
        }
    """
    if not jd_text.strip():
        raise ValueError("jd_text cannot be empty.")

    collection = _get_collection(CANDIDATE_COLLECTION)

    # Check if collection has any candidates
    count = collection.count()
    if count == 0:
        logger.warning("No candidates in vector store — returning empty results.")
        return []

    actual_k = min(k, count)
    results = collection.query(
        query_texts=[jd_text],
        n_results=actual_k,
        include=["metadatas", "distances", "documents"],
    )

    matches = []
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    for rank, (cid, dist, meta) in enumerate(zip(ids, distances, metadatas), start=1):
        # ChromaDB cosine distance: 0 = identical, 2 = opposite
        # Convert to similarity score [0, 1]
        similarity = round(1 - (dist / 2), 4)

        # Reconstruct the profile from stored JSON
        profile_json_str = meta.get("profile_json", "{}")
        try:
            profile = json.loads(profile_json_str)
        except json.JSONDecodeError:
            profile = {}

        matches.append(
            {
                "candidate_id": cid,
                "similarity_score": similarity,
                "profile": profile,
                "rank": rank,
            }
        )

    logger.info("Top-%d matches retrieved for JD query.", actual_k)
    return matches


def delete_candidate(candidate_id: str) -> None:
    """Remove a candidate from the vector store."""
    collection = _get_collection(CANDIDATE_COLLECTION)
    collection.delete(ids=[candidate_id])
    logger.info("Candidate '%s' deleted from vector store.", candidate_id)


def clear_all() -> None:
    """
    ⚠️ Delete ALL candidates and JDs from the vector store.
    Primarily for testing/reset purposes.
    """
    client = _get_client()
    for name in [CANDIDATE_COLLECTION, JD_COLLECTION]:
        try:
            client.delete_collection(name)
            logger.warning("Collection '%s' deleted from ChromaDB.", name)
        except Exception:
            pass


# ── CLI quick-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import pprint

    # Add a dummy JD
    jd = """
    We are looking for a Senior Python Backend Engineer with strong experience in
    FastAPI, PostgreSQL, Redis, and Docker. Experience with machine learning pipelines
    (scikit-learn, pandas) is a plus. Competitive programming background welcome.
    """
    add_job_description(jd, jd_id="test_jd_001")

    # Add a dummy candidate
    sample_profile = {
        "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "scikit-learn"],
        "years_of_experience": 5,
        "work_history": [
            {
                "role": "Backend Engineer",
                "company": "[Company Redacted]",
                "duration_months": 36,
                "key_achievements": ["Built high-throughput API serving 10M requests/day"],
            }
        ],
        "projects": [],
        "certifications": ["AWS Developer Associate"],
        "pii_removed": True,
    }
    add_candidate(sample_profile, candidate_id="test_candidate_001")

    # Query
    results = get_top_matches(jd, k=5)
    pprint.pprint(results)
