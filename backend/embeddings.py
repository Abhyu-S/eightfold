"""
embeddings.py
-------------
Unified embedding engine using Gemini embeddings exclusively.
Local HuggingFace embeddings have been fully deprecated to avoid version collision
and cache issues, providing a seamless uniform API interface.
"""

import logging
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity
from google import genai
from google.genai import types

from backend.config import settings

logger = logging.getLogger(__name__)

# Singleton client holder
_client = None

def _get_client():
    """Lazy initialize the Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _client

def _embed_batch(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> np.ndarray:
    """
    Internal batched embedder making a single bulk API request to Gemini.
    """
    if not texts:
        return np.array([], dtype=np.float32)
    
    # Truncate texts to avoid payload caps on extreme length strings
    truncated_texts = [text[:8000] for text in texts]
    
    client = _get_client()
    
    # Generate bulk embeddings
    resp = client.models.embed_content(
        model="gemini-embedding-2-preview",  # Primary embedding model for generic usage
        contents=truncated_texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
        ),
    )
    
    # Extract values directly
    embeddings = [e.values for e in resp.embeddings]
    return np.array(embeddings, dtype=np.float32)


# ============================================================
# PUBLIC API
# ============================================================

def embed_text(text: str) -> np.ndarray:
    """
    Embed a text string using the text embedding model.
    Returns a 1D numpy array (the embedding vector).
    Deterministic: same input → same output.
    """
    return _embed_batch([text], task_type="RETRIEVAL_DOCUMENT")[0]


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Batch embed multiple text strings.
    Returns a 2D numpy array of shape (N, D).
    """
    return _embed_batch(texts, task_type="RETRIEVAL_DOCUMENT")


def embed_code(code: str) -> np.ndarray:
    """
    Embed a code string using the code embedding model.
    Returns a 1D numpy array.
    Deterministic: same input → same output.
    """
    return _embed_batch([code], task_type="RETRIEVAL_DOCUMENT")[0]


def embed_codes(codes: list[str]) -> np.ndarray:
    """
    Batch embed multiple code strings.
    Returns a 2D numpy array of shape (N, D).
    """
    return _embed_batch(codes, task_type="RETRIEVAL_DOCUMENT")


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
