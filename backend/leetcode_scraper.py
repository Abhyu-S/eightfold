"""
leetcode_scraper.py
--------------------
Fetches public LeetCode statistics for a given username via LeetCode's
GraphQL API. All API calls cached via SQLite.

Collects:
  - Solved problem counts by difficulty (easy/medium/hard/total)
  - Contest rating, global rank, contests attended
  - Recent accepted submissions with topic tags (DP, graphs, greedy, etc.)
  - Aggregated topic frequency across recent solves
"""

import logging
from collections import Counter
from typing import Optional

import requests
from dotenv import load_dotenv

from backend.cache import cache_get_json, cache_set_json
from backend.config import settings

load_dotenv()

logger = logging.getLogger(__name__)

USE_MOCK_DATA: bool = settings.USE_MOCK_DATA
GRAPHQL_URL = "https://leetcode.com/graphql"
REQUEST_TIMEOUT = 15
MAX_RECENT_TO_INSPECT = 15  # cap N+1 topic-tag lookups


# ============================================================
# MOCK DATA
# ============================================================
MOCK_LEETCODE_DATA = {
    "username": "leetcoder123",
    "solved": {"total": 412, "easy": 180, "medium": 190, "hard": 42},
    "contest": {
        "rating": 1847.3,
        "global_rank": 45210,
        "attended": 23,
        "top_percentage": 12.4,
    },
    "recent_questions": [
        {"title": "Longest Palindromic Substring", "difficulty": "Medium", "topics": ["String", "Dynamic Programming"]},
        {"title": "Course Schedule", "difficulty": "Medium", "topics": ["Graph", "Topological Sort"]},
    ],
    "recent_topics_frequency": {"Dynamic Programming": 4, "Graph": 3, "Array": 6, "String": 2},
    "error": None,
}


# ============================================================
# GRAPHQL QUERIES
# ============================================================
PROFILE_QUERY = """
query userProfile($username: String!) {
  matchedUser(username: $username) {
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
      }
    }
    profile {
      ranking
    }
  }
  userContestRanking(username: $username) {
    attendedContestsCount
    rating
    globalRanking
    topPercentage
  }
}
"""

RECENT_QUERY = """
query recentAc($username: String!, $limit: Int) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    title
    titleSlug
    timestamp
  }
}
"""

QUESTION_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    difficulty
    topicTags {
      name
      slug
    }
  }
}
"""


# ============================================================
# HELPERS
# ============================================================
def _graphql(query: str, variables: Optional[dict] = None) -> Optional[dict]:
    """
    Executes a GraphQL query against LeetCode. Cached by query+variables.
    Returns None (rather than raising) on any failure, so callers can
    degrade gracefully instead of crashing the whole profile fetch.
    """
    cache_key = f"leetcode:gql:{query}:{variables}"
    cached = cache_get_json(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://leetcode.com",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()

        if "errors" in payload and payload["errors"]:
            logger.warning("LeetCode GraphQL errors: %s", payload["errors"])
            return None

        data = payload.get("data")
        if data is None:
            logger.warning("LeetCode GraphQL returned no data for query")
            return None

        cache_set_json(cache_key, data)
        return data

    except requests.RequestException as exc:
        logger.error("LeetCode API request failed: %s", exc)
        return None
    except (KeyError, ValueError) as exc:
        logger.error("LeetCode API response malformed: %s", exc)
        return None


# ============================================================
# MAIN PUBLIC FUNCTION
# ============================================================
def fetch_leetcode_profile(username: str) -> dict:
    """
    Fetch a user's LeetCode profile: solved counts, contest stats, and
    topic tags from recent accepted submissions.
    """
    if USE_MOCK_DATA:
        logger.info("USE_MOCK_DATA=True — returning mock LeetCode data for '%s'", username)
        mock = dict(MOCK_LEETCODE_DATA)
        mock["username"] = username
        return mock

    # top-level cache for the fully assembled result
    cache_key = f"leetcode:full_profile:{username}"
    cached = cache_get_json(cache_key)
    if cached is not None:
        return cached

    result = {
        "username": username,
        "solved": {"total": 0, "easy": 0, "medium": 0, "hard": 0},
        "contest": {"rating": None, "global_rank": None, "attended": 0, "top_percentage": None},
        "recent_questions": [],
        "recent_topics_frequency": {},
        "error": None,
    }

    profile_data = _graphql(PROFILE_QUERY, {"username": username})
    if profile_data is None:
        result["error"] = f"LeetCode profile fetch failed for '{username}' (API error or rate limited)."
        return result

    user = profile_data.get("matchedUser")
    if user is None:
        result["error"] = f"LeetCode user '{username}' not found."
        return result

    # Solved counts
    solved = {}
    for item in user.get("submitStatsGlobal", {}).get("acSubmissionNum", []):
        solved[item["difficulty"]] = item["count"]
    result["solved"] = {
        "total": solved.get("All", 0),
        "easy": solved.get("Easy", 0),
        "medium": solved.get("Medium", 0),
        "hard": solved.get("Hard", 0),
    }

    # Contest stats
    contest = profile_data.get("userContestRanking")
    if contest:
        result["contest"] = {
            "rating": contest.get("rating"),
            "global_rank": contest.get("globalRanking"),
            "attended": contest.get("attendedContestsCount", 0),
            "top_percentage": contest.get("topPercentage"),
        }

    # Recent submissions + topic tags (capped to avoid N+1 explosion)
    recent_data = _graphql(RECENT_QUERY, {"username": username, "limit": MAX_RECENT_TO_INSPECT})
    recent_list = (recent_data or {}).get("recentAcSubmissionList", [])

    topic_counter: Counter = Counter()
    recent_questions = []
    for problem in recent_list:
        q_data = _graphql(QUESTION_QUERY, {"titleSlug": problem["titleSlug"]})
        question = (q_data or {}).get("question")
        if question is None:
            continue
        topics = [t["name"] for t in question.get("topicTags", [])]
        topic_counter.update(topics)
        recent_questions.append({
            "title": problem["title"],
            "difficulty": question.get("difficulty"),
            "topics": topics,
        })

    result["recent_questions"] = recent_questions
    result["recent_topics_frequency"] = dict(topic_counter)

    logger.info(
        "LeetCode for '%s': solved=%d (E:%d/M:%d/H:%d), contests=%d, recent_inspected=%d",
        username, result["solved"]["total"], result["solved"]["easy"],
        result["solved"]["medium"], result["solved"]["hard"],
        result["contest"]["attended"], len(recent_questions),
    )
    cache_set_json(cache_key, result)
    return result


# ── Utility: extract username from LeetCode URL ──────────────────────────────
def extract_leetcode_username(url: str) -> Optional[str]:
    """Extract a LeetCode username from a profile URL."""
    import re
    match = re.search(r"leetcode\.com/(?:u/)?([a-zA-Z0-9_\-]+)/?", url)
    if match:
        username = match.group(1)
        if username.lower() not in {"problems", "contest", "discuss", "explore"}:
            return username
    return None


# ── CLI quick-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import json
    import pprint

    uname = sys.argv[1] if len(sys.argv) > 1 else "leetcoder123"
    data = fetch_leetcode_profile(uname)
    pprint.pprint(data)