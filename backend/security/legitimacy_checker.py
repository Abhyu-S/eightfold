import requests
from backend.core.logger import logger

def check_link_legitimacy(url: str) -> bool:
    """Sends HEAD requests to links; checks headers, sizes, and login redirects."""
    logger.info(f"Checking legitimacy for URL: {url}")
    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code != 200:
            logger.warning(f"URL {url} returned status code {response.status_code}")
            return False
            
        content_length_str = response.headers.get('Content-Length')
        if content_length_str and content_length_str.isdigit():
            size_mb = int(content_length_str) / (1024 * 1024)
            if size_mb > 50:
                logger.warning(f"URL {url} points to a file over 50MB ({size_mb:.2f}MB). Rejecting.")
                return False
                
        # Simple heuristic to catch login redirects
        if "login" in response.url.lower() or "signin" in response.url.lower():
            logger.warning(f"URL {url} redirects to a login page. Rejecting.")
            return False
            
        return True
    except requests.RequestException as e:
        logger.error(f"Error checking legitimacy for URL {url}: {e}")
        return False
