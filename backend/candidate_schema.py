from pydantic import BaseModel, Field
from typing import Optional, Any

class ChunkMetadata(BaseModel):
    candidate_id: str
    chunk_type: str  # e.g., "Work Experience", "Technical Skills", "Competitive Programming Stats", "GitHub Project", "Code File"
    source: str      # e.g., "resume", "github", "codeforces", "leetcode"
    additional_metadata: Optional[dict[str, Any]] = Field(default_factory=dict)

class SemanticChunk(BaseModel):
    text: str
    metadata: ChunkMetadata

    def to_dict(self):
        return {
            "text": self.text,
            "metadata": self.metadata.model_dump()
        }
