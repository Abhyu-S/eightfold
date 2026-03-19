"""
github_scraper.py
-----------------
Fetches public GitHub profile data for a given username.

Collects:
  - Top repositories (name, stars, language, description)
  - Aggregated language usage across all public repos
  - Dependencies verified from requirements.txt / package.json in top repos

Mock fallback: Set USE_MOCK_DATA=True in .env (or toggle the flag below)
to return pre-canned data without hitting the GitHub API.
"""

import os
import json
import logging
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Feature Flag ────────────────────────────────────────────────────────────
USE_MOCK_DATA: bool = os.getenv("USE_MOCK_DATA", "False").lower() == "true"

GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")
GITHUB_API_BASE = "https://api.github.com"

# Max repos to inspect for dependency files
MAX_REPOS_TO_INSPECT = 5


# ============================================================
# MOCK DATA  (toggle USE_MOCK_DATA = True to use this)
# ============================================================
MOCK_GITHUB_DATA = {
    "username": "octocat",
    "public_repos": 8,
    "followers": 1200,
    "following": 45,
    "top_repos": [
        {
            "name": "ml-pipeline",
            "stars": 412,
            "forks": 88,
            "language": "Python",
            "description": "End-to-end ML pipeline with feature engineering",
            "topics": ["machine-learning", "python", "scikit-learn"],
        },
        {
            "name": "react-dashboard",
            "stars": 230,
            "forks": 41,
            "language": "JavaScript",
            "description": "Admin dashboard built with React and TypeScript",
            "topics": ["react", "typescript", "dashboard"],
        },
        {
            "name": "fastapi-boilerplate",
            "stars": 178,
            "forks": 29,
            "language": "Python",
            "description": "Production-ready FastAPI starter template",
            "topics": ["fastapi", "python", "rest-api"],
        },
    ],
    "language_distribution": {
        "Python": 65,
        "JavaScript": 20,
        "TypeScript": 10,
        "Shell": 5,
    },
    "verified_dependencies": [
        "fastapi",
        "uvicorn",
        "scikit-learn",
        "pandas",
        "numpy",
        "react",
        "typescript",
        "langchain",
    ],
    "raw_dependency_files": {
        "ml-pipeline/requirements.txt": "scikit-learn\npandas\nnumpy\nmatplotlib\n",
        "fastapi-boilerplate/requirements.txt": "fastapi\nuvicorn\npython-dotenv\npydantic\n",
    },
    "error": None,
}


# ============================================================
# HELPERS
# ============================================================

def _get_headers() -> dict:
    """Build request headers, including GitHub PAT if available."""
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _safe_get(url: str, params: dict = None) -> Optional[dict | list]:
    """
    Perform a GET request and return parsed JSON, or None on error.
    Logs a warning for non-200 responses (rate limit, 404, etc.).
    """
    try:
        resp = requests.get(url, headers=_get_headers(), params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("GitHub API %s → HTTP %d: %s", url, resp.status_code, resp.text[:200])
        return None
    except requests.RequestException as exc:
        logger.error("GitHub API request failed: %s", exc)
        return None


def _fetch_file_content(owner: str, repo: str, filepath: str) -> Optional[str]:
    """
    Try to fetch a raw file from a repo via the GitHub Contents API.
    Returns the decoded text, or None if not found.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{filepath}"
    data = _safe_get(url)
    if data and isinstance(data, dict) and data.get("encoding") == "base64":
        import base64
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Could not decode %s/%s/%s: %s", owner, repo, filepath, exc)
    return None


def _extract_deps_from_requirements(text: str) -> list[str]:
    """Parse a requirements.txt string and return a list of package names (lowercase)."""
    deps = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip version specifiers: package>=1.0  →  package
        pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("!=")[0]
        pkg = pkg.split("[")[0].strip().lower()  # strip extras
        if pkg:
            deps.append(pkg)
    return deps


def _extract_deps_from_package_json(text: str) -> list[str]:
    """Parse a package.json string and return a list of dependency names (lowercase)."""
    try:
        data = json.loads(text)
        deps = list(data.get("dependencies", {}).keys())
        deps += list(data.get("devDependencies", {}).keys())
        return [d.lower() for d in deps]
    except json.JSONDecodeError:
        logger.warning("Could not parse package.json")
        return []


# ============================================================
# MAIN PUBLIC FUNCTION
# ============================================================

def fetch_github_profile(username: str) -> dict:
    """
    Fetch a GitHub user's public profile, top repos, language breakdown,
    and verified dependencies from manifest files.

    Parameters
    ----------
    username : str
        GitHub username (e.g. "torvalds")

    Returns
    -------
    dict with keys:
        username, public_repos, followers, following,
        top_repos, language_distribution, verified_dependencies,
        raw_dependency_files, error
    """
    if USE_MOCK_DATA:
        logger.info("USE_MOCK_DATA=True — returning mock GitHub data for '%s'", username)
        mock = dict(MOCK_GITHUB_DATA)
        mock["username"] = username
        return mock

    result = {
        "username": username,
        "public_repos": 0,
        "followers": 0,
        "following": 0,
        "top_repos": [],
        "language_distribution": {},
        "verified_dependencies": [],
        "raw_dependency_files": {},
        "error": None,
    }

    # ── 1. User profile ───────────────────────────────────────────────────
    profile = _safe_get(f"{GITHUB_API_BASE}/users/{username}")
    if not profile:
        result["error"] = f"GitHub user '{username}' not found or API unavailable."
        return result

    result["public_repos"] = profile.get("public_repos", 0)
    result["followers"] = profile.get("followers", 0)
    result["following"] = profile.get("following", 0)

    # ── 2. Top repositories (sorted by stars) ────────────────────────────
    repos_data = _safe_get(
        f"{GITHUB_API_BASE}/users/{username}/repos",
        params={"sort": "stars", "direction": "desc", "per_page": MAX_REPOS_TO_INSPECT},
    )
    if not repos_data or not isinstance(repos_data, list):
        result["error"] = "Could not fetch repositories."
        return result

    language_counts: dict[str, int] = {}

    for repo in repos_data:
        name = repo.get("name", "")
        lang = repo.get("language") or "Unknown"

        result["top_repos"].append(
            {
                "name": name,
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "language": lang,
                "description": repo.get("description") or "",
                "topics": repo.get("topics", []),
            }
        )

        # Accumulate language stats
        if lang != "Unknown":
            language_counts[lang] = language_counts.get(lang, 0) + 1

    # Convert counts to percentages
    total = sum(language_counts.values()) or 1
    result["language_distribution"] = {
        lang: round((count / total) * 100)
        for lang, count in sorted(language_counts.items(), key=lambda x: -x[1])
    }

    # ── 3. Verify dependencies from manifest files ───────────────────────
    all_deps: set[str] = set()

    for repo in repos_data[:MAX_REPOS_TO_INSPECT]:
        repo_name = repo.get("name", "")

        # Try requirements.txt
        req_text = _fetch_file_content(username, repo_name, "requirements.txt")
        if req_text:
            key = f"{repo_name}/requirements.txt"
            result["raw_dependency_files"][key] = req_text
            all_deps.update(_extract_deps_from_requirements(req_text))

        # Try package.json
        pkg_text = _fetch_file_content(username, repo_name, "package.json")
        if pkg_text:
            key = f"{repo_name}/package.json"
            result["raw_dependency_files"][key] = pkg_text
            all_deps.update(_extract_deps_from_package_json(pkg_text))

    result["verified_dependencies"] = sorted(all_deps)

    logger.info(
        "GitHub profile fetched for '%s': %d repos, %d verified deps",
        username,
        len(result["top_repos"]),
        len(result["verified_dependencies"]),
    )
    return result


# ── CLI quick-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import pprint

    uname = sys.argv[1] if len(sys.argv) > 1 else "octocat"
    data = fetch_github_profile(uname)
    pprint.pprint(data)
