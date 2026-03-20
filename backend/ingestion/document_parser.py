from backend.core.logger import logger
from backend.core.config import settings
import google.generativeai as genai

def parse_document(file_bytes: bytes, mime_type: str) -> str:
    """Uses Gemini Multimodal to extract text from PDFs or Images."""
    logger.info(f"Parsing document of type {mime_type} using Gemini Vision.")
    
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set. Returning dummy text.")
        return "GEMINI_API_KEY not configured."
        
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = "Extract all text from this document as accurately as possible. Preserve the original structure."
    try:
        response = model.generate_content(
            [
                {"mime_type": mime_type, "data": file_bytes},
                prompt
            ]
        )
        return response.text
    except Exception as e:
        logger.error(f"Error parsing document with Gemini: {e}")
        return ""
