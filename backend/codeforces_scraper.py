"""
codeforces_scraper.py
---------------------
Fetches public Codeforces statistics for a given handle.
All API calls cached via SQLite.

Collects:
  - Max rating, current rank
  - Contest participation count and recent performances
  - Solved problem count (approximate)
  - Problem rating distribution (800, 900, ..., 3500+)
"""

import logging
import re
from collections import Counter
from typing import Optional

import requests
from dotenv import load_dotenv

from backend.cache import cache_get_json, cache_set_json
from backend.config import settings

load_dotenv()

logger = logging.getLogger(__name__)

USE_MOCK_DATA: bool = settings.USE_MOCK_DATA
CF_API_BASE = "https://codeforces.com/api"


# ============================================================
# MOCK DATA
# ============================================================
MOCK_CF_DATA = {
    "handle": "tourist",
    "max_rating": 3979,
    "current_rating": 3858,
    "rank": "Legendary Grandmaster",
    "max_rank": "Legendary Grandmaster",
    "contests_participated": 247,
    "recent_contests": [
        {"contest": "Codeforces Round 950", "rank": 1, "rating_change": +82},
        {"contest": "Codeforces Round 940", "rank": 2, "rating_change": +53},
        {"contest": "Codeforces Round 935", "rank": 1, "rating_change": +67},
    ],
    "solved_problems_approx": 3500,
    "contribution": 147,
    "problem_rating_distribution": {
        "800": 120, "900": 115, "1000": 200, "1100": 180,
        "1200": 250, "1300": 220, "1400": 300, "1500": 280,
        "1600": 260, "1700": 240, "1800": 200, "1900": 180,
        "2000": 150, "2100": 120, "2200": 80, "2300": 60,
        "2400": 40, "2500": 25, "2600": 15, "2700": 10,
        "2800": 5, "2900": 3, "3000+": 2,
    },
    "error": None,
}


# ============================================================
# HELPERS
# ============================================================

def _safe_cf_get(endpoint: str, params: dict = None) -> Optional[dict]:
    """Cached Codeforces API call."""
    cache_key = f"codeforces:{endpoint}:{params}"
    cached = cache_get_json(cache_key)
    if cached is not None:
        return cached

    url = f"{CF_API_BASE}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            logger.warning("Codeforces API %s → HTTP %d", url, resp.status_code)
            return None
        data = resp.json()
        if data.get("status") != "OK":
            logger.warning("Codeforces API non-OK: %s", data.get("comment", ""))
            return None
        result = data.get("result")
        cache_set_json(cache_key, result)
        return result
    except requests.RequestException as exc:
        logger.error("Codeforces API failed: %s", exc)
        return None


def _rating_to_rank(rating: Optional[int]) -> str:
    if rating is None:
        return "Unrated"
    if rating < 1200: return "Newbie"
    if rating < 1400: return "Pupil"
    if rating < 1600: return "Specialist"
    if rating < 1900: return "Expert"
    if rating < 2100: return "Candidate Master"
    if rating < 2300: return "Master"
    if rating < 2400: return "International Master"
    if rating < 2600: return "Grandmaster"
    if rating < 3000: return "International Grandmaster"
    return "Legendary Grandmaster"


def _compute_problem_rating_distribution(submissions: list) -> dict:
    """
    From a list of submissions, count solved problems bucketed by their rating.
    Returns a dict like {"800": 15, "900": 22, ...}
    """
    solved = set()
    solved_with_rating = []

    for sub in submissions:
        if sub.get("verdict") != "OK":
            continue
        problem = sub.get("problem", {})
        key = (problem.get("contestId"), problem.get("index"))
        if key in solved:
            continue
        solved.add(key)
        rating = problem.get("rating")
        if rating is not None:
            solved_with_rating.append(rating)

    # Bucket by rating
    counter = Counter()
    for r in solved_with_rating:
        if r >= 3000:
            counter["3000+"] += 1
        else:
            bucket = str((r // 100) * 100)
            counter[bucket] += 1

    # Sort by rating bucket
    sorted_dist = {}
    for bucket in sorted(counter.keys(), key=lambda x: int(x.replace("+", "9"))):
        sorted_dist[bucket] = counter[bucket]

    return sorted_dist


# ============================================================
# MAIN PUBLIC FUNCTION
# ============================================================

def fetch_codeforces_profile(handle: str) -> dict:
    """
    Fetch a user's Codeforces profile with problem rating distribution.
    """
    if USE_MOCK_DATA:
        logger.info("USE_MOCK_DATA=True — returning mock Codeforces data for '%s'", handle)
        mock = dict(MOCK_CF_DATA)
        mock["handle"] = handle
        return mock

    # top-level cache — avoids re-running bucketing/aggregation even when
    # the underlying API calls are already cached
    cache_key = f"codeforces:full_profile:{handle}"
    cached = cache_get_json(cache_key)
    if cached is not None:
        return cached

    result = {
        "handle": handle,
        "max_rating": None,
        "current_rating": None,
        "rank": None,
        "max_rank": None,
        "contests_participated": 0,
        "recent_contests": [],
        "solved_problems_approx": 0,
        "contribution": 0,
        "problem_rating_distribution": {},
        "error": None,
    }

    # 1. User info
    user_info = _safe_cf_get("user.info", params={"handles": handle})
    if not user_info or not isinstance(user_info, list) or len(user_info) == 0:
        result["error"] = f"Codeforces handle '{handle}' not found or API unavailable."
        logger.warning(result["error"])
        return result  # don't cache errors — handle might get corrected/created later

    user = user_info[0]
    result["current_rating"] = user.get("rating")
    result["max_rating"] = user.get("maxRating")
    result["rank"] = user.get("rank") or _rating_to_rank(result["current_rating"])
    result["max_rank"] = user.get("maxRank") or _rating_to_rank(result["max_rating"])
    result["contribution"] = user.get("contribution", 0)

    # 2. Contest history
    rating_history = _safe_cf_get("user.rating", params={"handle": handle})
    if rating_history and isinstance(rating_history, list):
        result["contests_participated"] = len(rating_history)
        recent = rating_history[-5:]
        result["recent_contests"] = [
            {
                "contest": entry.get("contestName", "Unknown"),
                "rank": entry.get("rank"),
                "rating_change": entry.get("newRating", 0) - entry.get("oldRating", 0),
            }
            for entry in reversed(recent)
        ]

    # 3. Submissions → solved count + rating distribution
    submissions = _safe_cf_get(
        "user.status", params={"handle": handle, "from": 1, "count": 10000}
    )
    if submissions and isinstance(submissions, list):
        solved = {
            (sub["problem"].get("contestId"), sub["problem"]["index"])
            for sub in submissions
            if sub.get("verdict") == "OK"
        }
        result["solved_problems_approx"] = len(solved)
        result["problem_rating_distribution"] = _compute_problem_rating_distribution(submissions)

    logger.info(
        "Codeforces for '%s': rating=%s, contests=%d, solved≈%d, distribution_buckets=%d",
        handle, result["current_rating"], result["contests_participated"],
        result["solved_problems_approx"], len(result["problem_rating_distribution"]),
    )
    cache_set_json(cache_key, result)
    return result


# ── Utility: extract handle from Codeforces URL ─────────────────────────────
def extract_codeforces_handle(url: str) -> Optional[str]:
    """Extract Codeforces handle from a URL."""
    patterns = [
        r"codeforces\.com/profile/([a-zA-Z0-9_\-]+)",
        r"codeforces\.com/submissions/([a-zA-Z0-9_\-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


# ── CLI quick-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import pprint

    h = sys.argv[1] if len(sys.argv) > 1 else "tourist"
    data = fetch_codeforces_profile(h)
    pprint.pprint(data)
