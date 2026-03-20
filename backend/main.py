from fastapi import FastAPI
from backend.core.logger import logger

app = FastAPI(
    title="V1 Agentic Deep Auditor",
    description="Multi-Agent system that acts as a Senior Hiring Manager to deeply investigate a candidate's digital footprint.",
    version="1.0.0"
)

@app.get("/health")
def health_check():
    """Health check endpoint to ensure API is running."""
    logger.info("Health check pinged")
    return {"status": "ok", "message": "V1 Agentic Deep Auditor API is operational."}
