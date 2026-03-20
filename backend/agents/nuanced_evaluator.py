from backend.core.logger import logger

def evaluate_candidate(candidate_data: dict, rubric: dict) -> dict:
    """The final brain: cross-references verified data with the rubric to output Pros/Cons."""
    logger.info("Running final nuanced evaluation.")
    # TODO: Final LLM synthesis
    return {"final_pros": [], "final_cons": [], "recommendation": "Reject"}
