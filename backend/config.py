"""
config.py
---------
Central configuration loader for the platform.
All settings are read from environment variables (via .env).
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower()
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

    # GitHub
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

    # Vector DB
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")

    # Feature flags
    USE_MOCK_DATA: bool = os.getenv("USE_MOCK_DATA", "False").lower() == "true"

    # Server
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))


settings = Settings()
