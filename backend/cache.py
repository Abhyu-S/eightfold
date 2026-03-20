"""
cache.py
--------
Centralized SQLite caching layer.
MD5-hashes any key (URL, LLM prompt, etc.) and stores the response.
Eliminates redundant API calls during demo/evaluation.
"""

import hashlib
import json
import logging
import sqlite3
import time
from typing import Optional

from backend.config import settings

logger = logging.getLogger(__name__)

_DB_PATH = settings.SQLITE_CACHE_PATH


def _get_conn() -> sqlite3.Connection:
    """Get a connection to the cache database, creating the table if needed."""
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key_hash TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def _make_key(raw_key: str) -> str:
    """MD5 hash of the input key."""
    return hashlib.md5(raw_key.encode("utf-8")).hexdigest()


def cache_get(raw_key: str) -> Optional[str]:
    """
    Look up a cached value by its raw key string.
    Returns the stored JSON string, or None on miss.
    """
    key_hash = _make_key(raw_key)
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM cache WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        if row:
            logger.debug("Cache HIT for key hash %s", key_hash[:8])
            return row[0]
        return None
    finally:
        conn.close()


def cache_set(raw_key: str, value: str) -> None:
    """Store a value in the cache, keyed by the MD5 hash of raw_key."""
    key_hash = _make_key(raw_key)
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO cache (key_hash, value, created_at) VALUES (?, ?, ?)",
            (key_hash, value, time.time()),
        )
        conn.commit()
        logger.debug("Cache SET for key hash %s", key_hash[:8])
    finally:
        conn.close()


def cache_get_json(raw_key: str) -> Optional[dict]:
    """Get cached value and parse as JSON dict. Returns None on miss."""
    val = cache_get(raw_key)
    if val is not None:
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return None
    return None


def cache_set_json(raw_key: str, value: dict) -> None:
    """JSON-serialize a dict and store it in the cache."""
    cache_set(raw_key, json.dumps(value, ensure_ascii=False))


def get_or_fetch_json(key: str, fetch_fn, *args, **kwargs) -> dict:
    """
    Check cache first. If miss, call fetch_fn(*args, **kwargs),
    cache the result, and return it.
    fetch_fn must return a dict.
    """
    cached = cache_get_json(key)
    if cached is not None:
        return cached
    result = fetch_fn(*args, **kwargs)
    if result is not None:
        cache_set_json(key, result)
    return result
