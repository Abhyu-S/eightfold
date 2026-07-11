# backend/llm.py
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from backend.config import settings


def get_llm(temperature: float = 0.0):
    if settings.LLM_PROVIDER == "groq":
        return ChatGroq(
            model=settings.GROQ_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=temperature,
        )
    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL_FLASH,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
    )