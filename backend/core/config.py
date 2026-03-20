from pathlib import Path
from pydantic_settings import BaseSettings

# Resolve .env relative to backend/ (one level up from core/)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    GITHUB_TOKEN: str = ""
    TRUST_THRESHOLD: float = 0.5
    
    class Config:
        env_file = str(_ENV_PATH)

settings = Settings()
