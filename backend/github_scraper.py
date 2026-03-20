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
            "readme": "# ML Pipeline\nEnd-to-end machine learning pipeline...",
            "code_files": [
                {"path": "src/train.py", "content": "import sklearn\ndef train_model(): ..."},
            ],
            "recent_commits": [
                "feat: add hyperparameter tuning",
                "fix: resolve data leakage in validation split",
                "refactor: modularize feature engineering pipeline",
            ],
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
            return None # Expected file, got dir
        if file_content.size > MAX_FILE_SIZE_BYTES:
            return None
        if file_content.encoding == "base64":
            return base64.b64decode(file_content.content).decode("utf-8", errors="replace")
        return None
    except UnknownObjectException:
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
    except Exception as exc:
        logger.warning(f"Failed to fetch tree: {exc}")
        return []


def _fetch_recent_commits_pygithub(repo, count: int = 20) -> list[str]:
    try:
        commits = repo.get_commits()[:count]
        return [c.commit.message.split("\n")[0] for c in commits if c.commit.message]
    except Exception:
        return []


# ============================================================
# PUBLIC: Fetch code signals for a specific repo
# ============================================================

def fetch_repo_code_signals(owner: str, repo_name: str) -> dict:
    """
    For a single repo, fetch signals via PyGithub.
    Added explicit caching since we generate expensive sub-requests.
    """
    # Using the whole function cache
    cache_key = f"github:repo_signals:{owner}:{repo_name}"
    cached = cache_get_json(cache_key)
    if cached is not None:
        return cached

    signals = {
        "readme": None,
        "code_files": [],
        "recent_commits": [],
    }

    try:
        g = _get_github_client()
        repo = g.get_repo(f"{owner}/{repo_name}")
        
        # README
        readme = _fetch_file_content_pygithub(repo, "README.md")
        if not readme:
            readme = _fetch_file_content_pygithub(repo, "readme.md")
        signals["readme"] = readme

        # Core source files
        core_paths = _select_core_files_pygithub(repo)
        for path in core_paths:
            content = _fetch_file_content_pygithub(repo, path)
            if content:
                signals["code_files"].append({"path": path, "content": content})

        # Recent commits
        signals["recent_commits"] = _fetch_recent_commits_pygithub(repo)

        logger.info(
            "Code signals for %s/%s: readme=%s, files=%d, commits=%d",
            owner, repo_name,
            "yes" if signals["readme"] else "no",
            len(signals["code_files"]),
            len(signals["recent_commits"]),
        )
        cache_set_json(cache_key, signals)
        return signals
    except Exception as exc:
        logger.warning("Failed to fetch repo %s/%s: %s", owner, repo_name, exc)
        return signals

# ============================================================
# PUBLIC: Full GitHub profile fetch
# ============================================================

def fetch_github_profile(username: str) -> dict:
    """
    Fetch a GitHub user's public profile and repos via PyGithub.
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
        "error": None,
    }

    g = _get_github_client()
    try:
        user = g.get_user(username)
        result["public_repos"] = user.public_repos
        result["followers"] = user.followers
        result["following"] = user.following

        # Top Repos
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
            
            req_text = _fetch_file_content_pygithub(repo, "requirements.txt")
            if req_text:
                result["raw_dependency_files"][f"{repo_name}/requirements.txt"] = req_text
                all_deps.update(_extract_deps_from_requirements(req_text))

            pkg_text = _fetch_file_content_pygithub(repo, "package.json")
            if pkg_text:
                result["raw_dependency_files"][f"{repo_name}/package.json"] = pkg_text
                all_deps.update(_extract_deps_from_package_json(pkg_text))

        result["verified_dependencies"] = sorted(all_deps)

        # Code signals for top repos
        for repo in repos[:3]:
            repo_name = repo.name
            try:
                signals = fetch_repo_code_signals(username, repo_name)
                result["code_signals"][repo_name] = signals
            except Exception as exc:
                logger.warning("Failed to fetch code signals for %s/%s: %s", username, repo_name, exc)

        logger.info(
            "GitHub profile fetched for '%s': %d repos, %d deps, %d repos with code signals",
            username, len(result["top_repos"]), len(result["verified_dependencies"]),
            len(result["code_signals"]),
        )
        cache_set_json(cache_key, result)
        return result

    except UnknownObjectException:
        result["error"] = f"GitHub user '{username}' not found or API unavailable."
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
