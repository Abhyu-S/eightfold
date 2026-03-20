import json
import google.generativeai as genai
from backend.core.logger import logger
from backend.core.config import settings

def evaluate_candidate(candidate_data: dict, rubric: dict) -> dict:
    """The final brain: cross-references verified data with the rubric to output Pros/Cons."""
    logger.info("Running final nuanced evaluation.")
    if not settings.GEMINI_API_KEY:
        return {"final_pros": [], "final_cons": [], "recommendation": "Reject"}
        
    genai.configure(api_key=settings.GEMINI_API_KEY)
    # Using pro for comprehensive synthesis and decision making
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
    You are the final Hiring Manager. Evaluate the following candidate data against the rubric.
    Apply the "Benefit of the Doubt >50%" rule: if there is >50% positive signal, recommend Hire.
    Provide your final assessment.
    
    Rubric:
    {json.dumps(rubric)}
    
    Candidate Data:
    {json.dumps(candidate_data)}
    
    Return ONLY a valid JSON object with the following schema:
    {{
        "final_pros": ["List of overall strengths"],
        "final_cons": ["List of overall weaknesses or risks"],
        "recommendation": "Hire" or "Reject"
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
        logger.error(f"Error evaluating candidate with Gemini: {e}")
        return {"final_pros": [], "final_cons": [], "recommendation": "Reject"}
