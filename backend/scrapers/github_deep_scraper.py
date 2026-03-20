import requests
import re
from backend.core.logger import logger
from backend.core.config import settings

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    """Build headers with optional auth token."""
    h = {"Accept": "application/vnd.github.v3+json"}
    if settings.GITHUB_TOKEN:
        h["Authorization"] = f"token {settings.GITHUB_TOKEN}"
    return h


def _safe_get(url: str, params: dict = None) -> dict | list | None:
    """GET with error handling. Returns parsed JSON or None."""
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        print(f"    ⚠️  {url} → HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    except requests.RequestException as e:
        print(f"    ❌ Exception fetching {url}: {e}")
        return None


# ── URL Classification ─────────────────────────────────────────────────────

def is_profile_url(url: str) -> bool:
    """Returns True if URL points to a GitHub profile (not a specific repo)."""
    # github.com/user  (exactly one path segment after github.com)
    match = re.search(r"github\.com/([^/\s?#]+)/?$", url)
    return match is not None


def extract_owner_repo(url: str) -> tuple[str, str]:
    """Extracts owner and repo from https://github.com/owner/repo"""
    pattern = r"github\.com/([^/]+)/([^/\s?#]+)"
    match = re.search(pattern, url)
    if match:
        repo_name = match.group(2)
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]
        return match.group(1), repo_name
    return "", ""


def extract_username(url: str) -> str:
    """Extracts GitHub username from a profile URL."""
    match = re.search(r"github\.com/([^/\s?#]+)/?$", url)
    return match.group(1) if match else ""


# ── Repo-Level Scraping (existing, enhanced) ───────────────────────────────

def scrape_github_repo(repo_url: str) -> dict:
    """Fetches file trees, selects top 3 files heuristically, fetches raw code."""
    logger.info(f"Scraping GitHub repo: {repo_url}")
    owner, repo = extract_owner_repo(repo_url)
    if not owner or not repo:
        print(f"  ⚠️  Could not extract owner/repo from URL: {repo_url}")
        return {"files_scraped": 0, "content": {}, "readme": ""}

    print(f"  📦 Parsed: owner={owner}, repo={repo}")

    # Step 1: Get default branch
    repo_info = _safe_get(f"{GITHUB_API}/repos/{owner}/{repo}")
    if not repo_info:
        return {"files_scraped": 0, "content": {}, "readme": ""}
    default_branch = repo_info.get("default_branch", "main")
    print(f"    Default branch: {default_branch}")

    # Step 2: Fetch README
    readme = ""
    readme_resp = _safe_get(f"{GITHUB_API}/repos/{owner}/{repo}/readme")
    if readme_resp and readme_resp.get("encoding") == "base64":
        import base64
        try:
            readme = base64.b64decode(readme_resp["content"]).decode("utf-8", errors="replace")[:3000]
            print(f"    📖 README fetched ({len(readme)} chars)")
        except Exception:
            pass

    # Step 3: Get file tree
    tree_data = _safe_get(f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1")
    if not tree_data:
        return {"files_scraped": 0, "content": {}, "readme": readme}
    tree = tree_data.get("tree", [])
    print(f"    Total tree items: {len(tree)}")

    # Step 4: Heuristically select key files
    selected_files = []
    valid_extensions = {".py", ".js", ".ts", ".java", ".go", ".cpp", ".c", ".rs", ".rb", ".php"}
    # Priority keywords for key files
    priority_keywords = ["model", "main", "app", "index", "server", "train", "pipeline", "agent"]

    for item in tree:
        if item.get("type") == "blob":
            path = item.get("path", "")
            if any(path.endswith(ext) for ext in valid_extensions):
                if "test_" not in path and "node_modules" not in path and "__pycache__" not in path:
                    selected_files.append(path)

    # Sort by priority: files matching key words come first
    def priority_score(p):
        basename = p.lower().split("/")[-1]
        for i, kw in enumerate(priority_keywords):
            if kw in basename:
                return i
        return len(priority_keywords) + 1

    selected_files.sort(key=priority_score)
    selected_files = selected_files[:3]
    print(f"    Selected files: {selected_files}")

    # Step 5: Fetch raw content
    content = {}
    for path in selected_files:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{path}"
        try:
            raw_resp = requests.get(raw_url, headers=_headers(), timeout=10)
            if raw_resp.status_code == 200:
                content[path] = raw_resp.text[:5000]
                print(f"    ✅ Fetched {path} ({len(raw_resp.text)} chars)")
            else:
                print(f"    ❌ Failed to fetch {path}: {raw_resp.status_code}")
        except Exception as e:
            print(f"    ❌ Exception fetching {path}: {e}")

    return {"files_scraped": len(content), "content": content, "readme": readme}


# ── Profile-Level Scraping (NEW) ──────────────────────────────────────────

def _fetch_recent_commits(owner: str, repo: str, max_commits: int = 10) -> list[dict]:
    """Fetch recent commit messages for a repo."""
    commits_data = _safe_get(
        f"{GITHUB_API}/repos/{owner}/{repo}/commits",
        params={"per_page": max_commits}
    )
    if not commits_data or not isinstance(commits_data, list):
        return []

    commits = []
    for c in commits_data:
        commit_info = c.get("commit", {})
        commits.append({
            "message": commit_info.get("message", "")[:200],
            "date": commit_info.get("author", {}).get("date", ""),
            "author": commit_info.get("author", {}).get("name", ""),
        })
    return commits


def scrape_github_profile(profile_url: str, max_repos: int = 5) -> dict:
    """
    Discovers repos from a GitHub profile, then deeply scrapes the top ones.

    Returns:
    {
        "username": str,
        "followers": int,
        "public_repos": int,
        "repos": [
            {
                "name": str,
                "description": str,
                "stars": int,
                "language": str,
                "topics": [str],
                "readme": str,
                "recent_commits": [{"message", "date", "author"}],
                "key_files": {"path": "content"},
            }
        ]
    }
    """
    username = extract_username(profile_url)
    if not username:
        print(f"  ⚠️  Could not extract username from: {profile_url}")
        return {"username": "", "repos": []}

    print(f"\n  👤 Scraping GitHub profile: {username}")
    if settings.GITHUB_TOKEN:
        print(f"  🔑 Token loaded (first 8 chars): {settings.GITHUB_TOKEN[:8]}...")
    else:
        print(f"  ⚠️  No GITHUB_TOKEN — rate limit is 60 req/hr")

    # Step 1: Get user profile
    user_data = _safe_get(f"{GITHUB_API}/users/{username}")
    if not user_data:
        return {"username": username, "repos": []}

    result = {
        "username": username,
        "followers": user_data.get("followers", 0),
        "public_repos": user_data.get("public_repos", 0),
        "bio": user_data.get("bio", ""),
        "repos": [],
    }
    print(f"    Followers: {result['followers']}, Public repos: {result['public_repos']}")

    # Step 2: Get top repos by stars
    repos_data = _safe_get(
        f"{GITHUB_API}/users/{username}/repos",
        params={"sort": "stars", "direction": "desc", "per_page": max_repos}
    )
    if not repos_data or not isinstance(repos_data, list):
        print(f"    ❌ Could not fetch repos for {username}")
        return result

    print(f"    📂 Found {len(repos_data)} repos, scraping top {min(len(repos_data), max_repos)}...\n")

    for repo in repos_data[:max_repos]:
        repo_name = repo.get("name", "")
        print(f"    ── Repo: {repo_name} ({'⭐' * min(repo.get('stargazers_count', 0), 5)}) ──")

        repo_entry = {
            "name": repo_name,
            "description": repo.get("description") or "",
            "stars": repo.get("stargazers_count", 0),
            "language": repo.get("language") or "Unknown",
            "topics": repo.get("topics", []),
            "readme": "",
            "recent_commits": [],
            "key_files": {},
        }

        # Fetch README
        readme_data = _safe_get(f"{GITHUB_API}/repos/{username}/{repo_name}/readme")
        if readme_data and readme_data.get("encoding") == "base64":
            import base64
            try:
                repo_entry["readme"] = base64.b64decode(readme_data["content"]).decode("utf-8", errors="replace")[:3000]
                print(f"       📖 README: {len(repo_entry['readme'])} chars")
            except Exception:
                pass

        # Fetch recent commits
        repo_entry["recent_commits"] = _fetch_recent_commits(username, repo_name)
        print(f"       📝 Commits: {len(repo_entry['recent_commits'])} recent")

        # Fetch key files (model.py, main.py, app.py, etc.)
        default_branch = repo.get("default_branch", "main")
        tree_data = _safe_get(f"{GITHUB_API}/repos/{username}/{repo_name}/git/trees/{default_branch}?recursive=1")

        if tree_data and tree_data.get("tree"):
            tree = tree_data["tree"]
            valid_extensions = {".py", ".js", ".ts", ".java", ".go"}
            priority_keywords = ["model", "main", "app", "index", "server", "train", "pipeline", "agent"]

            candidates = []
            for item in tree:
                if item.get("type") == "blob":
                    path = item.get("path", "")
                    if any(path.endswith(ext) for ext in valid_extensions):
                        if "test_" not in path and "node_modules" not in path and "__pycache__" not in path:
                            candidates.append(path)

            # Sort by priority
            def priority_score(p):
                basename = p.lower().split("/")[-1]
                for i, kw in enumerate(priority_keywords):
                    if kw in basename:
                        return i
                return len(priority_keywords) + 1

            candidates.sort(key=priority_score)
            top_files = candidates[:3]

            for fpath in top_files:
                raw_url = f"https://raw.githubusercontent.com/{username}/{repo_name}/{default_branch}/{fpath}"
                try:
                    raw_resp = requests.get(raw_url, headers=_headers(), timeout=10)
                    if raw_resp.status_code == 200:
                        repo_entry["key_files"][fpath] = raw_resp.text[:5000]
                        print(f"       ✅ {fpath} ({len(raw_resp.text)} chars)")
                except Exception:
                    pass

            print(f"       🔑 Key files: {list(repo_entry['key_files'].keys())}")

        result["repos"].append(repo_entry)

    return result
