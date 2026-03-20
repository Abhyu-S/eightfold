import json
import google.generativeai as genai
from backend.core.logger import logger
from backend.core.config import settings

def analyze_role_requirements(jd_text: str) -> dict:
    """Transforms the recruiter's JD text into a structured JSON rubric."""
    logger.info("Analyzing role requirements from JD.")
    if not settings.GEMINI_API_KEY:
        return {"seniority": "Fresher", "core_stack": []}
        
    genai.configure(api_key=settings.GEMINI_API_KEY)
    # Using flash for simple structured extraction
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
    Analyze the following Job Description and extract the required seniority level and core technology stack.
    Return ONLY a valid JSON object with the following schema:
    {{
        "seniority": "string (e.g., Junior, Mid, Senior, Lead)",
        "core_stack": ["string element 1", "string element 2"]
    }}
    
    Job Description:
    {jd_text}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"): text = text[7:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
            
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"Error parsing JD with Gemini: {e}")
        return {"seniority": "Unknown", "core_stack": []}
