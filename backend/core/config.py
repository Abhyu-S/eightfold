from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    GITHUB_TOKEN: str = ""
    TRUST_THRESHOLD: float = 0.5
    
    class Config:
        env_file = ".env"

settings = Settings()
