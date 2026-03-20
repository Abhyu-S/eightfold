from backend.core.logger import logger
from backend.core.config import settings

def calculate_trust_score(total_projects: int, verified_projects: int) -> bool:
    """Implements the >50% mathematical rule and flags unverified projects."""
    if total_projects == 0:
        return False
        
    ratio = verified_projects / total_projects
    logger.info(f"Trust ratio calculated: {ratio:.2f}")
    return ratio > settings.TRUST_THRESHOLD
