"""
github_scraper.py
-----------------
Fetches public GitHub profile data, repository code signals, and commit history.
All API calls are cached via SQLite for demo reliability.

Collects:
  - Top repositories (name, stars, language, description)
  - Aggregated language usage across all public repos
  - Dependencies verified from requirements.txt / package.json
  - Selective code file contents (README + up to 3 core files)
  - Recent commit messages

USAGE NOTE:
  fetch_github_profile() is for GENERAL profile signal (activity, breadth,
  overall language mix). Its top_repos list is star-ranked and is NOT
  guaranteed to include the specific repos a candidate lists on their resume.

  fetch_repo_code_signals(owner, repo_name) is for CLAIM VERIFICATION —
  call it directly with the owner/repo parsed from a resume-provided URL
  to check whether a specific claimed project actually contains what the
  candidate says it does.
"""

import base64
import json
import logging
import os
import re
from typing import Optional

from github import Github, Auth
from github.GithubException import UnknownObjectException, GithubException
from dotenv import load_dotenv

from backend.cache import cache_get_json, cache_set_json
from backend.config import settings

load_dotenv()

logger = logging.getLogger(__name__)

USE_MOCK_DATA: bool = settings.USE_MOCK_DATA
GITHUB_TOKEN: Optional[str] = settings.GITHUB_TOKEN

MAX_REPOS_TO_INSPECT = 5
CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".cpp", ".c", ".java", ".go", ".rs"}
MAX_CODE_FILES_PER_REPO = 3
MAX_FILE_SIZE_BYTES = 50_000  # Skip files larger than ~50KB


# ============================================================
# MOCK DATA
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
    ],
    "language_distribution": {"Python": 65, "JavaScript": 20, "TypeScript": 10, "Shell": 5},
    "verified_dependencies": ["fastapi", "uvicorn", "scikit-learn", "pandas", "numpy", "react"],
    "raw_dependency_files": {
        "ml-pipeline/requirements.txt": "scikit-learn\npandas\nnumpy\nmatplotlib\n",
    },
    "code_signals": {
        "ml-pipeline": {
            "language": "Python",
            "readme": "# ML Pipeline\nEnd-to-end machine learning pipeline...",
            "code_files": [
                {"path": "src/train.py", "content": "import sklearn\ndef train_model(): ..."},
            ],
            "recent_commits": [
                "feat: add hyperparameter tuning",
                "fix: resolve data leakage in validation split",
                "refactor: modularize feature engineering pipeline",
            ],
            "rate_limited": False,
        }
    },
    "error": None,
}


# ============================================================
# HELPERS
# ============================================================

def _get_github_client() -> Github:
    if GITHUB_TOKEN:
        auth = Auth.Token(GITHUB_TOKEN)
        return Github(auth=auth)
    return Github()


def _extract_deps_from_requirements(text: str) -> list[str]:
    deps = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("!=")[0]
        pkg = pkg.split("[")[0].strip().lower()
        if pkg:
            deps.append(pkg)
    return deps


def _extract_deps_from_package_json(text: str) -> list[str]:
    try:
        data = json.loads(text)
        deps = list(data.get("dependencies", {}).keys())
        deps += list(data.get("devDependencies", {}).keys())
        return [d.lower() for d in deps]
    except json.JSONDecodeError:
        return []


def _fetch_file_content_pygithub(repo, filepath: str) -> Optional[str]:
    try:
        file_content = repo.get_contents(filepath)
        if isinstance(file_content, list):
            return None  # Expected file, got dir
        if file_content.size > MAX_FILE_SIZE_BYTES:
            return None
        if file_content.encoding == "base64":
            return base64.b64decode(file_content.content).decode("utf-8", errors="replace")
        return None
    except UnknownObjectException:
        return None
    except GithubException as exc:
        if exc.status == 403:
            logger.warning(f"GitHub rate limit hit fetching {filepath}")
            raise  # let caller handle rate limiting explicitly
        logger.warning(f"Could not load {filepath}: {exc}")
        return None
    except Exception as exc:
        logger.warning(f"Could not load {filepath}: {exc}")
        return None


def _select_core_files_pygithub(repo) -> list[str]:
    """
    Fetch the file tree recursively using PyGithub and select core files.
    """
    candidates = []
    skip_patterns = {"test", "spec", "__pycache__", "node_modules", ".git", "dist", "build", "venv"}

    try:
        default_branch = repo.default_branch
        tree = repo.get_git_tree(default_branch, recursive=True)
        for element in tree.tree:
            if element.type != "blob":
                continue
            path = element.path or ""
            ext = os.path.splitext(path)[1].lower()
            if ext not in CODE_EXTENSIONS:
                continue

            parts = path.lower().split("/")
            if any(skip in parts for skip in skip_patterns):
                continue

            size = element.size
            if size is None or size > MAX_FILE_SIZE_BYTES or size < 50:
                continue

            priority = 0
            if any(d in parts for d in ["src", "lib", "app", "core", "main"]):
                priority = 2
            elif len(parts) == 1:
                priority = 1

            candidates.append((priority, size, path))

        candidates.sort(key=lambda x: (-x[0], -x[1]))
        return [c[2] for c in candidates[:MAX_CODE_FILES_PER_REPO]]
    except GithubException as exc:
        if exc.status == 403:
            logger.warning("GitHub rate limit hit fetching file tree")
            raise
        logger.warning(f"Failed to fetch tree: {exc}")
        return []
    except Exception as exc:
        logger.warning(f"Failed to fetch tree: {exc}")
        return []


def _fetch_recent_commits_pygithub(repo, count: int = 20) -> list[str]:
    try:
        commits = repo.get_commits()[:count]
        return [c.commit.message.split("\n")[0] for c in commits if c.commit.message]
    except GithubException as exc:
        if exc.status == 403:
            logger.warning("GitHub rate limit hit fetching commits")
            raise
        return []
    except Exception:
        return []


# ============================================================
# PUBLIC: Fetch code signals for a specific repo
# ============================================================

def fetch_repo_code_signals(owner: str, repo_name: str) -> dict:
    """
    For a single repo, fetch signals via PyGithub. This is the function to
    call for verifying a resume-claimed project — pass the owner/repo parsed
    directly from the claimed URL, not from fetch_github_profile()'s top_repos.

    Returns a dict with an explicit `rate_limited` flag so callers (e.g. the
    verification agent) can distinguish "genuinely empty repo" from
    "we couldn't check because the API was rate-limited" — these should NOT
    be treated the same when judging a claim.
    """
    cache_key = f"github:repo_signals:{owner}:{repo_name}"
    cached = cache_get_json(cache_key)
    if cached is not None:
        return cached

    signals = {
        "language": None,
        "readme": None,
        "code_files": [],
        "recent_commits": [],
        "rate_limited": False,
    }

    try:
        g = _get_github_client()
        repo = g.get_repo(f"{owner}/{repo_name}")
        signals["language"] = repo.language

        # README
        try:
            readme = _fetch_file_content_pygithub(repo, "README.md")
            if not readme:
                readme = _fetch_file_content_pygithub(repo, "readme.md")
            signals["readme"] = readme
        except GithubException:
            signals["rate_limited"] = True

        # Core source files
        if not signals["rate_limited"]:
            try:
                core_paths = _select_core_files_pygithub(repo)
                for path in core_paths:
                    content = _fetch_file_content_pygithub(repo, path)
                    if content:
                        signals["code_files"].append({"path": path, "content": content})
            except GithubException:
                signals["rate_limited"] = True

        # Recent commits
        if not signals["rate_limited"]:
            try:
                signals["recent_commits"] = _fetch_recent_commits_pygithub(repo)
            except GithubException:
                signals["rate_limited"] = True

        logger.info(
            "Code signals for %s/%s: language=%s, readme=%s, files=%d, commits=%d, rate_limited=%s",
            owner, repo_name,
            signals["language"],
            "yes" if signals["readme"] else "no",
            len(signals["code_files"]),
            len(signals["recent_commits"]),
            signals["rate_limited"],
        )

        # Don't cache rate-limited results — we want to retry later, not
        # freeze a false-negative "empty repo" verdict in the cache.
        if not signals["rate_limited"]:
            cache_set_json(cache_key, signals)
        return signals

    except UnknownObjectException:
        logger.warning(f"Repo not found: {owner}/{repo_name}")
        signals["error"] = "repo_not_found"
        return signals
    except GithubException as exc:
        if exc.status == 403:
            logger.warning(f"GitHub rate limit hit fetching repo {owner}/{repo_name}")
            signals["rate_limited"] = True
        else:
            logger.warning(f"GitHub error for {owner}/{repo_name}: {exc}")
        return signals
    except Exception as exc:
        logger.warning("Failed to fetch repo %s/%s: %s", owner, repo_name, exc)
        return signals


# ============================================================
# PUBLIC: Full GitHub profile fetch
# ============================================================

def fetch_github_profile(username: str) -> dict:
    """
    Fetch a GitHub user's public profile and general repo activity via PyGithub.

    NOTE: top_repos is star-ranked and reflects general activity only — it is
    NOT guaranteed to include the specific repos a candidate lists on their
    resume (many candidates' real project repos have 0 stars). For per-project
    claim verification, use fetch_repo_code_signals(owner, repo) directly with
    the URL parsed from the resume, not this function's top_repos.
    """
    if USE_MOCK_DATA:
        logger.info("USE_MOCK_DATA=True — returning mock GitHub data for '%s'", username)
        mock = dict(MOCK_GITHUB_DATA)
        mock["username"] = username
        return mock

    cache_key = f"github:profile_full:{username}"
    cached = cache_get_json(cache_key)
    if cached is not None:
        return cached

    result = {
        "username": username,
        "public_repos": 0,
        "followers": 0,
        "following": 0,
        "top_repos": [],
        "language_distribution": {},
        "verified_dependencies": [],
        "raw_dependency_files": {},
        "code_signals": {},
        "rate_limited": False,
        "error": None,
    }

    g = _get_github_client()
    try:
        user = g.get_user(username)
        result["public_repos"] = user.public_repos
        result["followers"] = user.followers
        result["following"] = user.following

        # Top Repos (star-ranked; see docstring caveat above)
        repos = sorted(user.get_repos(), key=lambda r: r.stargazers_count, reverse=True)[:MAX_REPOS_TO_INSPECT]

        language_counts: dict[str, int] = {}
        for repo in repos:
            lang = repo.language or "Unknown"
            result["top_repos"].append({
                "name": repo.name,
                "stars": repo.stargazers_count,
                "forks": repo.forks_count,
                "language": lang,
                "description": repo.description or "",
                "topics": repo.get_topics() if hasattr(repo, "get_topics") else [],
            })
            if lang != "Unknown":
                language_counts[lang] = language_counts.get(lang, 0) + 1

        total = sum(language_counts.values()) or 1
        result["language_distribution"] = {
            lang: round((count / total) * 100)
            for lang, count in sorted(language_counts.items(), key=lambda x: -x[1])
        }

        # Dependencies
        all_deps: set[str] = set()
        for repo in repos[:MAX_REPOS_TO_INSPECT]:
            repo_name = repo.name
            try:
                req_text = _fetch_file_content_pygithub(repo, "requirements.txt")
                if req_text:
                    result["raw_dependency_files"][f"{repo_name}/requirements.txt"] = req_text
                    all_deps.update(_extract_deps_from_requirements(req_text))

                pkg_text = _fetch_file_content_pygithub(repo, "package.json")
                if pkg_text:
                    result["raw_dependency_files"][f"{repo_name}/package.json"] = pkg_text
                    all_deps.update(_extract_deps_from_package_json(pkg_text))
            except GithubException as exc:
                if exc.status == 403:
                    logger.warning("Rate limit hit while scanning dependencies")
                    result["rate_limited"] = True
                    break
                raise

        result["verified_dependencies"] = sorted(all_deps)

        # Code signals for top repos
        if not result["rate_limited"]:
            for repo in repos[:3]:
                repo_name = repo.name
                signals = fetch_repo_code_signals(username, repo_name)
                result["code_signals"][repo_name] = signals
                if signals.get("rate_limited"):
                    result["rate_limited"] = True
                    break

        logger.info(
            "GitHub profile fetched for '%s': %d repos, %d deps, %d repos with code signals, rate_limited=%s",
            username, len(result["top_repos"]), len(result["verified_dependencies"]),
            len(result["code_signals"]), result["rate_limited"],
        )

        if not result["rate_limited"]:
            cache_set_json(cache_key, result)
        return result

    except UnknownObjectException:
        result["error"] = f"GitHub user '{username}' not found or API unavailable."
        return result
    except GithubException as exc:
        if exc.status == 403:
            result["rate_limited"] = True
            result["error"] = "GitHub API rate limit exceeded."
            logger.warning(f"Rate limit hit fetching profile for {username}")
        else:
            result["error"] = f"GitHub API error: {exc}"
            logger.error(f"GitHub API error for {username}: {exc}")
        return result
    except Exception as exc:
        result["error"] = f"Error fetching github data: {exc}"
        logger.error(f"Error fetching github data for {username}: {exc}")
        return result


# ── Utility: extract username from GitHub URL ────────────────────────────────
def extract_github_username(url: str) -> Optional[str]:
    """Extract a GitHub username from various URL formats."""
    patterns = [
        r"github\.com/([a-zA-Z0-9\-]+)/?$",
        r"github\.com/([a-zA-Z0-9\-]+)/[a-zA-Z0-9\-]+",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            username = match.group(1)
            if username.lower() not in {"settings", "explore", "marketplace", "topics"}:
                return username
    return None


# ── CLI quick-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import pprint

    uname = sys.argv[1] if len(sys.argv) > 1 else "octocat"
    data = fetch_github_profile(uname)
    pprint.pprint(data)