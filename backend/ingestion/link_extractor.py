import re
import json
import google.generativeai as genai
from backend.core.logger import logger
from backend.core.config import settings

def extract_urls(text: str) -> list[str]:
    """Uses regex to pull all external URLs from resume text."""
    logger.info("Extracting URLs from text.")
    # Exclude trailing punctuation often caught by greedy matches
    url_pattern = re.compile(r'https?://[^\s<>"\'{}|\\^\[\]`]+(?<![.,;:)!])')
    urls = url_pattern.findall(text)
    return urls


def extract_project_links(text: str) -> list[dict]:
    """
    Uses Gemini to intelligently extract projects from the resume text and
    associate each URL with its parent project.
    
    Returns a list of dicts:
    [
        {
            "project_name": "EightFold AI Platform",
            "description": "Brief project description from the resume",
            "urls": ["https://github.com/user/repo"],
            "claimed_tech": ["Python", "FastAPI", "React"]
        },
        ...
    ]
    """
    logger.info("Extracting project-link associations from resume text.")
    
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set. Falling back to regex-only extraction.")
        urls = extract_urls(text)
        if urls:
            return [{"project_name": "Unknown Project", "description": "", "urls": urls, "claimed_tech": []}]
        return []
    
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
    Analyze this resume text and extract EVERY project mentioned, along with any URLs 
    (GitHub, portfolio, deployed app, etc.) that appear near or adjacent to each project.
    Also extract the technologies claimed for each project.
    
    If a URL doesn't belong to any specific project (e.g., a LinkedIn or portfolio link), 
    group it under a project named "Profile Links".
    
    Return ONLY a valid JSON array with this schema:
    [
        {{
            "project_name": "Name of the project",
            "description": "One-line description from the resume",
            "urls": ["https://..."],
            "claimed_tech": ["Python", "React", ...]
        }}
    ]
    
    Resume text:
    {text}
    """
    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
        if raw.startswith("```json"): raw = raw[7:]
        elif raw.startswith("```"): raw = raw[3:]
        if raw.endswith("```"): raw = raw[:-3]
        projects = json.loads(raw.strip())
        
        # Validate structure
        if not isinstance(projects, list):
            projects = [projects]
        
        logger.info(f"Extracted {len(projects)} projects with linked URLs.")
        return projects
    except Exception as e:
        logger.error(f"Error extracting project links with Gemini: {e}")
        # Fallback to regex
        urls = extract_urls(text)
        if urls:
            return [{"project_name": "Unknown Project", "description": "", "urls": urls, "claimed_tech": []}]
        return []
