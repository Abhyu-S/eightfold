"""
codeforces_scraper.py
---------------------
Fetches public Codeforces statistics for a given handle.

Collects:
  - Max rating ever achieved
  - Current rank title (e.g. "Expert", "Specialist")
  - Number of contests participated in
  - Recent 10 contest performance (rating delta)
  - Solved problem count (approximated from submissions)

Mock fallback: Set USE_MOCK_DATA=True in .env (or toggle the flag below)
to return pre-canned data without hitting the Codeforces API.
"""

import os
import logging
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Feature Flag ─────────────────────────────────────────────────────────────
USE_MOCK_DATA: bool = os.getenv("USE_MOCK_DATA", "False").lower() == "true"

CF_API_BASE = "https://codeforces.com/api"


# ============================================================
# MOCK DATA  (toggle USE_MOCK_DATA = True to use this)
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
        {"contest": "Codeforces Round 921", "rank": 5, "rating_change": +28},
        {"contest": "Codeforces Round 915", "rank": 3, "rating_change": +44},
    ],
    "solved_problems_approx": 3500,
    "contribution": 147,
    "error": None,
}

MOCK_CF_DATA_NOT_FOUND = {
    "handle": "unknown_user",
    "max_rating": None,
    "current_rating": None,
    "rank": None,
    "max_rank": None,
    "contests_participated": 0,
    "recent_contests": [],
    "solved_problems_approx": 0,
    "contribution": 0,
    "error": "Codeforces handle not found (mock).",
}


# ============================================================
# HELPERS
# ============================================================

def _safe_cf_get(endpoint: str, params: dict = None) -> Optional[dict]:
    """
    Call a Codeforces API endpoint and return the result dict,
    or None on error / non-OK status.
    """
    url = f"{CF_API_BASE}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            logger.warning("Codeforces API %s → HTTP %d", url, resp.status_code)
            return None
        data = resp.json()
        if data.get("status") != "OK":
            logger.warning("Codeforces API returned non-OK: %s", data.get("comment", ""))
            return None
        return data.get("result")
    except requests.RequestException as exc:
        logger.error("Codeforces API request failed: %s", exc)
        return None


def _rating_to_rank(rating: Optional[int]) -> str:
    """Map a numeric rating to a Codeforces rank title."""
    if rating is None:
        return "Unrated"
    if rating < 1200:
        return "Newbie"
    if rating < 1400:
        return "Pupil"
    if rating < 1600:
        return "Specialist"
    if rating < 1900:
        return "Expert"
    if rating < 2100:
        return "Candidate Master"
    if rating < 2300:
        return "Master"
    if rating < 2400:
        return "International Master"
    if rating < 2600:
        return "Grandmaster"
    if rating < 3000:
        return "International Grandmaster"
    return "Legendary Grandmaster"


# ============================================================
# MAIN PUBLIC FUNCTION
# ============================================================

def fetch_codeforces_profile(handle: str) -> dict:
    """
    Fetch a user's Codeforces profile statistics.

    Parameters
    ----------
    handle : str
        Codeforces username handle (e.g. "tourist")

    Returns
    -------
    dict with keys:
        handle, max_rating, current_rating, rank, max_rank,
        contests_participated, recent_contests,
        solved_problems_approx, contribution, error

    Notes
    -----
    - If the handle doesn't exist on Codeforces, returns a safe dict
      with None values and a descriptive error message (no crash).
    - `solved_problems_approx` counts distinct accepted problems from
      the last 10,000 submissions (Codeforces API limit per call).
    """
    if USE_MOCK_DATA:
        logger.info("USE_MOCK_DATA=True — returning mock Codeforces data for '%s'", handle)
        mock = dict(MOCK_CF_DATA)
        mock["handle"] = handle
        return mock

    # ── Default safe result ───────────────────────────────────────────────
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
        "error": None,
    }

    # ── 1. User info ──────────────────────────────────────────────────────
    user_info = _safe_cf_get("user.info", params={"handles": handle})
    if not user_info or not isinstance(user_info, list) or len(user_info) == 0:
        result["error"] = f"Codeforces handle '{handle}' not found or API unavailable."
        logger.warning(result["error"])
        return result  # Safe return — no crash

    user = user_info[0]
    result["current_rating"] = user.get("rating")
    result["max_rating"] = user.get("maxRating")
    result["rank"] = user.get("rank") or _rating_to_rank(result["current_rating"])
    result["max_rank"] = user.get("maxRank") or _rating_to_rank(result["max_rating"])
    result["contribution"] = user.get("contribution", 0)

    # ── 2. Contest history ────────────────────────────────────────────────
    rating_history = _safe_cf_get("user.rating", params={"handle": handle})
    if rating_history and isinstance(rating_history, list):
        result["contests_participated"] = len(rating_history)
        # Grab the 5 most recent contests
        recent = rating_history[-5:]
        result["recent_contests"] = [
            {
                "contest": entry.get("contestName", "Unknown"),
                "rank": entry.get("rank"),
                "rating_change": entry.get("newRating", 0) - entry.get("oldRating", 0),
            }
            for entry in reversed(recent)  # newest first
        ]
    else:
        logger.warning("Could not fetch rating history for '%s'", handle)

    # ── 3. Approximate solved count ───────────────────────────────────────
    # Codeforces doesn't expose a direct "problems solved" counter —
    # we approximate it by counting distinct (contestId, index) from submissions.
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

    logger.info(
        "Codeforces profile fetched for '%s': rating=%s, contests=%d, solved≈%d",
        handle,
        result["current_rating"],
        result["contests_participated"],
        result["solved_problems_approx"],
    )
    return result


# ── CLI quick-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import pprint

    h = sys.argv[1] if len(sys.argv) > 1 else "tourist"
    data = fetch_codeforces_profile(h)
    pprint.pprint(data)
