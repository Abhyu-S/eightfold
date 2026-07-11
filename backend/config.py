"""
config.py
---------
Central configuration loader. All settings from environment variables (via .env).
"""

# backend/config.py additions



import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ── LLM Provider ───────────────────────────────────────────────────────
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")  # "gemini" | "groq"
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    # ── Gemini LLM ───────────────────────────────────────────────────────
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GEMINI_MODEL_FLASH: str = os.getenv("GEMINI_MODEL_FLASH", "gemini-2.0-flash")
    GEMINI_MODEL_PRO: str = os.getenv("GEMINI_MODEL_PRO", "gemini-2.0-flash-thinking-exp-01-21")

    # ── GitHub ───────────────────────────────────────────────────────────
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

    # ── Embeddings ───────────────────────────────────────────────────────
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "local")  # "local" or "gemini"
    TEXT_EMBED_MODEL: str = os.getenv("TEXT_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    CODE_EMBED_MODEL: str = os.getenv("CODE_EMBED_MODEL", "all-MiniLM-L6-v2")

    # ── Caching ──────────────────────────────────────────────────────────
    SQLITE_CACHE_PATH: str = os.getenv("SQLITE_CACHE_PATH", "./cache.db")

    # ── Feature flags ────────────────────────────────────────────────────
    USE_MOCK_DATA: bool = os.getenv("USE_MOCK_DATA", "False").lower() == "true"

    # ── Server ───────────────────────────────────────────────────────────
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))


settings = Settings()
