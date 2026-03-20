from backend.core.logger import logger

def get_direct_download_link(share_url: str) -> str:
    """Formats public share links into direct download links for processing."""
    logger.info(f"Formatting drive/dropbox link: {share_url}")
    # TODO: Implement logic to rewrite sharing URLs
    return share_url
