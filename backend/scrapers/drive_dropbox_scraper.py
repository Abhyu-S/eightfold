import re
from backend.core.logger import logger

def get_direct_download_link(share_url: str) -> str:
    """Formats public share links into direct download links for processing."""
    logger.info(f"Formatting drive/dropbox link: {share_url}")
    
    # Dropbox: replace dl=0 with dl=1
    if "dropbox.com" in share_url:
        if "dl=0" in share_url:
            return share_url.replace("dl=0", "dl=1")
        elif "?" not in share_url:
            return share_url + "?dl=1"
        else:
            return share_url + "&dl=1"
            
    # Google Drive: convert /file/d/ID/view to /uc?id=ID&export=download
    if "drive.google.com" in share_url:
        match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', share_url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?export=download&id={file_id}"
            
    return share_url
