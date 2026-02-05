"""
Pydantic models for Essay Grading API
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

# ============================================================================
# INGESTION ENDPOINT MODELS
# ============================================================================

class IngestionRequest(BaseModel):
    """Request model for NCERT textbook ingestion."""
    subject: str = Field(..., description="Subject (e.g., 'History', 'Geography')")
    grade: int = Field(..., ge=6, le=12, description="Grade level (6-12)")
    file_path: str = Field(..., description="Local path to NCERT PDF file")
    
    class Config:
        json_schema_extra = {
            "example": {
                "subject": "History",
                "grade": 10,
                "file_path": "/path/to/ncert_history_10.pdf"
            }
        }

class IngestionResponse(BaseModel):
    """Response model for ingestion endpoint."""
    status: str = Field(..., description="'success' or 'error'")
    subject: Optional[str] = None
    grade: Optional[int] = None
    parent_chunks_created: Optional[int] = None
    child_vectors_created: Optional[int] = None
    pinecone_index: Optional[str] = None
    message: Optional[str] = None

# ============================================================================
# ESSAY EVALUATION ENDPOINT MODELS
# ============================================================================

class GradeEssayRequest(BaseModel):
    """Request model for essay grading endpoint."""
    essay_text: str = Field(..., description="Student's essay text")
    question: str = Field(..., description="Essay question/prompt")
    subject: str = Field(
        default="general-studies",
        description="Subject domain (history, geography, political-science, economics)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "essay_text": "The Battle of Plassey in 1757...",
                "question": "Discuss the significance of the Battle of Plassey",
                "subject": "history"
            }
        }

# Sub-models for detailed responses

class AtomicClaim(BaseModel):
    """Verified atomic claim."""
    claim: str
    status: str = Field(..., description="'supported', 'contradicted', 'neutral', 'unverified'")
    confidence: float = Field(..., ge=0, le=1)

class FactCheckerResult(BaseModel):
    """Result from Fact Checker Agent."""
    agent: str = "fact_checker"
    verified_claims: List[AtomicClaim]
    accuracy_score: float = Field(..., ge=0, le=100)
    contradiction_count: int
    supported_count: int
    total_claims: int

class ConceptCoverage(BaseModel):
    """Covered concept detail."""
    concept: str
    covered: bool

class ContentCoverageResult(BaseModel):
    """Result from Content Coverage Agent."""
    agent: str = "content_coverage"
    covered_concepts: List[ConceptCoverage]
    coverage_score: float = Field(..., ge=0, le=100)
    concepts_covered: int
    total_concepts: int

class LinguisticResult(BaseModel):
    """Result from Linguistic Agent."""
    agent: str = "linguistic"
    grammar_score: float = Field(..., ge=0, le=100)
    vocabulary_score: float = Field(..., ge=0, le=100)
    tone_score: float = Field(..., ge=0, le=100)
    language_score: float = Field(..., ge=0, le=100)
    overall_score: float = Field(..., ge=0, le=100)

class DiscourseMarkers(BaseModel):
    """Discourse marker counts."""
    causative: int
    contrastive: int
    additive: int
    conclusive: int
    sequential: int

class Phase0Result(BaseModel):
    """Shadow Rubric result."""
    concepts: List[str]
    concept_count: int

class Phase1Result(BaseModel):
    """Extraction & Parsing result."""
    claims: List[str]
    claim_count: int
    discourse_markers: DiscourseMarkers

class Phase2Agents(BaseModel):
    """All three agents' results."""
    fact_checker: FactCheckerResult
    content_coverage: ContentCoverageResult
    linguistic: LinguisticResult

class ScoringBreakdown(BaseModel):
    """Detailed scoring breakdown."""
    fact_accuracy_score: float = Field(..., ge=0, le=100)
    coverage_score: float = Field(..., ge=0, le=100)
    content_score: float = Field(..., ge=0, le=100)
    logical_flow: float = Field(..., ge=0, le=100)
    language_score: float = Field(..., ge=0, le=100)
    raw_score: float = Field(..., ge=0, le=100)
    contradiction_penalty: float = Field(..., ge=0)
    final_score: float = Field(..., ge=0)
    normalized_score_0_1600: float = Field(..., ge=0, le=1600)

class GradeEssayResponse(BaseModel):
    """Complete essay grading response."""
    evaluation_id: str
    question: str
    subject: str
    essay_preview: str
    
    # Phase results
    phase_0_shadow_rubric: Phase0Result
    phase_1_extraction: Phase1Result
    phase_2_agents: Phase2Agents
    
    # Scoring
    scoring: ScoringBreakdown
    
    # Final grade
    grade: str = Field(..., description="Letter grade (A+, A, B+, B, C+, C, D, F)")
    feedback: str = Field(..., description="Personalized feedback for student")
    
    class Config:
        json_schema_extra = {
            "example": {
                "evaluation_id": "1234567890.123",
                "question": "Discuss the significance of the Battle of Plassey",
                "subject": "history",
                "essay_preview": "The Battle of Plassey was a significant...",
                "grade": "A",
                "feedback": "✓ Good factual accuracy. ✓ Good coverage..."
            }
        }

class ErrorResponse(BaseModel):
    """Error response model."""
    status: str = "error"
    evaluation_id: Optional[str] = None
    message: str
    
class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    service: str = "Essay Grader API"
    version: str
    modules: Dict[str, str] = Field(..., description="Status of each module")
