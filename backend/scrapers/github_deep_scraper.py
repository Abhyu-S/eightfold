from backend.core.logger import logger

def scrape_github_repo(repo_url: str) -> dict:
    """Fetches file trees, selects top 3 files heuristically, fetches raw code."""
    logger.info(f"Scraping GitHub repo: {repo_url}")
    # TODO: Implement GitHub API fetching
    return {"files_scraped": 0, "content": {}}
