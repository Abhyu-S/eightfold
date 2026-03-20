import requests
from backend.core.logger import logger

def fetch_codeforces_stats(handle: str) -> dict:
    """Uses public REST API to pull algorithmic stats."""
    logger.info(f"Fetching Codeforces stats for: {handle}")
    try:
        response = requests.get(f"https://codeforces.com/api/user.info?handles={handle}", timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "OK" and data.get("result"):
            user_info = data["result"][0]
            return {
                "rating": user_info.get("rating", 0),
                "maxRating": user_info.get("maxRating", 0),
                "rank": user_info.get("rank", "unrated"),
                "maxRank": user_info.get("maxRank", "unrated")
            }
    except Exception as e:
        logger.error(f"Error fetching Codeforces stats for {handle}: {e}")
        
    return {"rating": 0, "rank": "unrated"}
