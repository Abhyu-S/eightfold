import re
from backend.core.logger import logger

def extract_urls(text: str) -> list[str]:
    """Uses regex and NLP to pull all external URLs from resume text."""
    logger.info("Extracting URLs from text.")
    url_pattern = re.compile(r'https?://[^\s]+')
    urls = url_pattern.findall(text)
    return urls
