"""
embeddings.py
-------------
Dual embedding engine for text and code.
Local HuggingFace models by default, Gemini API as fallback.

Text:  BAAI/bge-small-en-v1.5  (~130MB VRAM, fast, great for semantic matching)
Code:  all-MiniLM-L6-v2  (~90MB VRAM, universal, works for code similarity)

Both models fit comfortably on a 6GB GPU (RTX 3060).
"""

import logging
from typing import Optional

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Singleton model holders ──────────────────────────────────────────────────
_text_model = None
_code_model = None


def _load_text_model():
    """Load the text embedding model (sentence-transformers)."""
    global _text_model
    if _text_model is not None:
        return _text_model

    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "local":
        from sentence_transformers import SentenceTransformer
        model_name = settings.TEXT_EMBED_MODEL
        logger.info("Loading local text embedding model: %s", model_name)
        _text_model = SentenceTransformer(model_name, trust_remote_code=True)
        logger.info("Text embedding model loaded successfully")
    else:
        _text_model = _GeminiEmbedder()

    return _text_model


def _load_code_model():
    """Load the code embedding model."""
    global _code_model
    if _code_model is not None:
        return _code_model

    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "local":
        from sentence_transformers import SentenceTransformer
        model_name = settings.CODE_EMBED_MODEL
        logger.info("Loading local code embedding model: %s", model_name)
        # No trust_remote_code needed for standard models
        _code_model = SentenceTransformer(model_name)
        logger.info("Code embedding model loaded successfully")
    else:
        _code_model = _GeminiEmbedder()

    return _code_model


class _GeminiEmbedder:
    """Wrapper around Gemini embedding API."""

    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self._genai = genai

    def encode(self, texts, **kwargs) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        results = []
        for text in texts:
            # Truncate to avoid token limits
            truncated = text[:8000]
            resp = self._genai.embed_content(
                model="models/text-embedding-004",
                content=truncated,
                task_type="retrieval_document",
            )
            results.append(resp["embedding"])
        return np.array(results, dtype=np.float32)


# ============================================================
# PUBLIC API
# ============================================================

def embed_text(text: str) -> np.ndarray:
    """
    Embed a text string using the text embedding model.
    Returns a 1D numpy array (the embedding vector).
    Deterministic: same input → same output.
    """
    model = _load_text_model()
    embedding = model.encode([text], normalize_embeddings=True)
    return np.array(embedding[0], dtype=np.float32)


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Batch embed multiple text strings.
    Returns a 2D numpy array of shape (N, D).
    """
    if not texts:
        return np.array([], dtype=np.float32)
    model = _load_text_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return np.array(embeddings, dtype=np.float32)


def embed_code(code: str) -> np.ndarray:
    """
    Embed a code string using the code embedding model.
    Returns a 1D numpy array.
    Deterministic: same input → same output.
    """
    model = _load_code_model()
    embedding = model.encode([code], normalize_embeddings=True)
    return np.array(embedding[0], dtype=np.float32)


def embed_codes(codes: list[str]) -> np.ndarray:
    """
    Batch embed multiple code strings.
    Returns a 2D numpy array of shape (N, D).
    """
    if not codes:
        return np.array([], dtype=np.float32)
    model = _load_code_model()
    embeddings = model.encode(codes, normalize_embeddings=True)
    return np.array(embeddings, dtype=np.float32)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.
    Returns a float in [-1, 1]. Deterministic.
    """
    a = vec_a.reshape(1, -1)
    b = vec_b.reshape(1, -1)
    sim = sklearn_cosine_similarity(a, b)[0][0]
    return float(sim)


def max_cosine_similarity(query_vec: np.ndarray, candidate_vecs: np.ndarray) -> float:
    """
    Compute the maximum cosine similarity between a query vector and
    a batch of candidate vectors.
    Returns the highest similarity score.
    If candidate_vecs is empty, returns 0.0.
    """
    if candidate_vecs.size == 0:
        return 0.0
    query = query_vec.reshape(1, -1)
    if candidate_vecs.ndim == 1:
        candidate_vecs = candidate_vecs.reshape(1, -1)
    sims = sklearn_cosine_similarity(query, candidate_vecs)[0]
    return float(np.max(sims))


def mean_cosine_similarity(query_vec: np.ndarray, candidate_vecs: np.ndarray) -> float:
    """
    Compute the mean cosine similarity between a query vector and
    a batch of candidate vectors.
    """
    if candidate_vecs.size == 0:
        return 0.0
    query = query_vec.reshape(1, -1)
    if candidate_vecs.ndim == 1:
        candidate_vecs = candidate_vecs.reshape(1, -1)
    sims = sklearn_cosine_similarity(query, candidate_vecs)[0]
    return float(np.mean(sims))
