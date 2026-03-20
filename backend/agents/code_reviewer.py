import json
import google.generativeai as genai
from backend.core.logger import logger
from backend.core.config import settings

def review_code_quality(code_content: dict, rubric: dict) -> dict:
    """LLM agent that reviews the fetched GitHub files for quality/maintainability."""
    logger.info("Reviewing code quality against the rubric.")
    if not settings.GEMINI_API_KEY or not code_content:
        return {"pros": [], "cons": []}
        
    genai.configure(api_key=settings.GEMINI_API_KEY)
    # Using pro for complex code analysis
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    code_str = "\\n\\n".join([f"--- File: {k} ---\\n{v}" for k, v in code_content.items()])
    prompt = f"""
    You are an expert Code Reviewer. Review the following code files against the provided requirements rubric.
    Analyze the code for quality, maintainability, and architectural decisions.
    
    Requirements Rubric:
    {json.dumps(rubric)}
    
    Code Files:
    {code_str}
    
    Return ONLY a valid JSON object with the following schema:
    {{
        "pros": ["A list of specific architectural/quality pros"],
        "cons": ["A list of specific architectural/quality cons"]
    }}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"): text = text[7:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"Error reviewing code with Gemini: {e}")
        return {"pros": [], "cons": []}
