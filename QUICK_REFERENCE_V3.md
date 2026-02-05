# QUICK REFERENCE: API Endpoints & Code Examples

## 1. Data Ingestion Module

### Endpoint: POST /ingest/textbook

Ingest NCERT PDFs using Parent-Child RAG strategy.

**Request:**
```json
{
  "subject": "History",
  "grade": 10,
  "file_path": "/path/to/ncert_history_10.pdf"
}
```

**Response:**
```json
{
  "status": "success",
  "subject": "History",
  "grade": 10,
  "parent_chunks_created": 25,
  "child_vectors_created": 150,
  "parent_ids": ["507f1f77bcf86cd799439011", ...],
  "pinecone_index": "history-index"
}
```

**Code Example:**
```python
from app.services.ingestion import NCERTIngestionPipeline
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def ingest_ncert():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.get_database("essayEval")
    
    pipeline = NCERTIngestionPipeline(db)
    result = await pipeline.ingest_textbook(
        file_path="/path/to/ncert.pdf",
        subject="History",
        grade=10
    )
    return result

# Run
result = asyncio.run(ingest_ncert())
```

---

## 2. Essay Evaluation Module

### Endpoint: POST /grade_essay

Grade an essay using 3-Phase multi-agent evaluation.

**Request:**
```json
{
  "essay_text": "The Battle of Plassey (1757) was...",
  "question": "Discuss the significance of the Battle of Plassey",
  "subject": "history"
}
```

**Response (Key Fields):**
```json
{
  "evaluation_id": "1234567890.123",
  "grade": "A",
  "scoring": {
    "fact_accuracy_score": 85.0,
    "coverage_score": 80.0,
    "content_score": 82.5,
    "logical_flow": 78.0,
    "language_score": 81.3,
    "normalized_score_0_1600": 1320.0
  },
  "feedback": "✓ Good factual accuracy. ✓ Good coverage..."
}
```

**Code Example:**
```python
from app.services.essay_evaluator import EssayEvaluationEngine
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def grade_essay():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.get_database("essayEval")
    
    engine = EssayEvaluationEngine(db)
    result = await engine.grade_essay(
        essay_text="The Battle of Plassey...",
        question="Discuss the significance...",
        subject="history"
    )
    return result

# Run
result = asyncio.run(grade_essay())
print(f"Grade: {result['grade']}")
print(f"Score: {result['scoring']['normalized_score_0_1600']}")
```

---

## 3. Phase Breakdown

### Phase 0: Shadow Rubric Creation
**What it does:** Generates the answer key by querying NCERT content

```python
shadow_result = await engine.create_shadow_rubric(
    question="Discuss British colonial rule in India",
    subject="history"
)
# Returns: {
#     "status": "success",
#     "concepts": ["British East India Company", "Robert Clive", ...],
#     "concept_count": 15,
#     "retrieved_docs": [...]
# }
```

### Phase 1: Extraction & Parsing
**What it does:** Extracts claims and discourse markers from essay

```python
claims = await engine.extract_atomic_claims(essay_text)
# Returns: ["The Battle of Plassey was in 1757", ...]

discourse = await engine.extract_discourse_markers(essay_text)
# Returns: {
#     "causative": 3,
#     "contrastive": 2,
#     "additive": 4,
#     "conclusive": 2,
#     "sequential": 1
# }
```

### Phase 2: Parallel Agents

#### Agent 1: Fact Checker
```python
fact_result = await engine.fact_checker_agent(
    claims=["Battle of Plassey was in 1757", ...],
    subject="history"
)
# Returns: {
#     "accuracy_score": 85.0,
#     "contradiction_count": 0,
#     "verified_claims": [
#         {"claim": "...", "status": "supported", "confidence": 0.9},
#         ...
#     ]
# }
```

#### Agent 2: Content Coverage
```python
coverage_result = await engine.content_coverage_agent(
    essay_text=essay_text,
    shadow_concepts=["British East India Company", ...]
)
# Returns: {
#     "coverage_score": 80.0,
#     "concepts_covered": 12,
#     "total_concepts": 15,
#     "covered_concepts": [
#         {"concept": "...", "covered": True},
#         ...
#     ]
# }
```

#### Agent 3: Linguistic Analysis
```python
linguistic_result = await engine.linguistic_agent(essay_text)
# Returns: {
#     "grammar_score": 85,
#     "vocabulary_score": 78,
#     "tone_score": 82,
#     "language_score": 81.3,
#     "overall_score": 82
# }
```

### Phase 3: Holistic Scoring
**Scoring Formula:**
```
Content_Score = (Fact_Accuracy + Coverage) / 2
Logical_Flow = Average cosine similarity between consecutive paragraphs
Raw_Score = (0.5 × Content) + (0.3 × Logical_Flow) + (0.2 × Language)
Final_Score = Raw_Score - (15 × contradictions)
Normalized = (Final_Score / 100) × 1600
```

---

## 4. Database Queries

### MongoDB - Find Parent Document
```python
from bson import ObjectId

parent_doc = await db.parent_docs.find_one(
    {"_id": ObjectId(parent_id)}
)
print(parent_doc["text"])  # Get full context
```

### MongoDB - Find Shadow Rubric
```python
shadow = await db.shadow_graphs.find_one(
    {"question": "Discuss the significance..."}
)
print(shadow["concepts"])  # Get must-have concepts
```

### MongoDB - Find Evaluation Report
```python
evaluation = await db.essay_evaluations.find_one(
    {"evaluation_id": "1234567890.123"}
)
print(evaluation["grade"])  # Get final grade
```

### Pinecone - Query for Similar Content
```python
from pinecone import Pinecone
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key="sk-...")
pc = Pinecone(api_key="...")

# Get embedding for query
response = await client.embeddings.create(
    model="text-embedding-3-small",
    input="Battle of Plassey significance"
)
query_embedding = response.data[0].embedding

# Query Pinecone
index = pc.Index("history-index")
results = index.query(
    vector=query_embedding,
    top_k=5,
    include_metadata=True
)

# Get parent documents
for match in results["matches"]:
    parent_id = match["metadata"]["parent_id"]
    parent_doc = await db.parent_docs.find_one({"_id": ObjectId(parent_id)})
    print(parent_doc["text"])
```

---

## 5. Configuration

### Environment Variables
```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Pinecone
PINECONE_API_KEY=...
PINECONE_ENVIRONMENT=us-east-1-aws

# MongoDB
MONGO_URL=mongodb://localhost:27017

# Other services
DATABASE_URL=postgresql://...
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
GROQ_API_KEY=...
```

### Settings in Code
```python
from app.core.config import settings

# Embedding config
print(settings.EMBEDDING_MODEL)        # "text-embedding-3-small"
print(settings.EMBEDDING_DIMENSION)    # 1536

# Chunking config
print(settings.PARENT_CHUNK_SIZE)      # 1000 tokens
print(settings.CHILD_CHUNK_SIZE)       # 200 tokens

# Index names
print(settings.PINECONE_INDICES)       # {"history": "history-index", ...}

# Collection names
print(settings.MONGO_PARENT_DOCS_COLLECTION)         # "parent_docs"
print(settings.MONGO_SHADOW_GRAPHS_COLLECTION)       # "shadow_graphs"
print(settings.MONGO_ESSAY_EVALUATIONS_COLLECTION)   # "essay_evaluations"
```

---

## 6. Error Handling

### Ingestion Errors
```python
result = await pipeline.ingest_textbook(...)
if result["status"] == "error":
    print(f"Ingestion failed: {result['message']}")
else:
    print(f"Successfully created {result['child_vectors_created']} vectors")
```

### Grading Errors
```python
result = await engine.grade_essay(...)
if result.get("status") == "error":
    print(f"Grading failed: {result['message']}")
else:
    print(f"Essay graded: {result['grade']}")
```

---

## 7. Scaling Tips

### Batch Ingestion
```python
# Ingest multiple textbooks in parallel
files = [
    ("/path/to/history_10.pdf", "History", 10),
    ("/path/to/geography_10.pdf", "Geography", 10),
    ("/path/to/political_11.pdf", "Political-Science", 11)
]

result = await pipeline.ingest_batch(files)
print(f"Successful: {result['successful']}")
print(f"Failed: {result['failed']}")
```

### Rate Limiting
```python
from app.utils.rate_limiter import TokenBucketRateLimiter

# Create rate limiter: 100 requests per 60 seconds
limiter = TokenBucketRateLimiter(rate=100, per=60)

# Use in request
await limiter.acquire()
# Make request here
```

---

## 8. Monitoring & Logging

### Enable Detailed Logging
```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug("Debug information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred")
```

### Key Log Points
```
Ingestion:
  ✓ "Extracted X characters from PDF"
  ✓ "Created X parent chunks"
  ✓ "Stored parent chunk X with ID: Y"
  ✓ "Upserted batch X to Pinecone"

Evaluation:
  ✓ "Starting essay evaluation"
  ✓ "Creating shadow rubric"
  ✓ "Fact Checker Agent: Processing X claims"
  ✓ "Content Coverage Agent: Checking X concepts"
  ✓ "Linguistic Agent: Analyzing essay"
  ✓ "Essay evaluation completed"
```

---

## 9. Testing Checklist

- [ ] Test ingestion with 1-2 NCERT PDFs
- [ ] Verify parent chunks stored in MongoDB
- [ ] Verify child vectors stored in Pinecone with metadata
- [ ] Test essay grading with sample essays
- [ ] Verify all agents run in parallel
- [ ] Check shadow rubric creation
- [ ] Validate scoring calculations
- [ ] Test error handling for invalid inputs
- [ ] Test batch operations
- [ ] Monitor API response times

---

## 10. API Response Examples

### Successful Ingestion
```json
{
  "status": "success",
  "subject": "History",
  "grade": 10,
  "parent_chunks_created": 25,
  "child_vectors_created": 150,
  "parent_ids": ["507f1f77bcf86cd799439011"],
  "pinecone_index": "history-index"
}
```

### Successful Grading
```json
{
  "evaluation_id": "1704067200.123",
  "question": "Discuss the significance of the Battle of Plassey",
  "subject": "history",
  "phase_0_shadow_rubric": {
    "concepts": ["Battle of Plassey", "Robert Clive", ...],
    "concept_count": 15
  },
  "phase_2_agents": {
    "fact_checker": {"accuracy_score": 85, ...},
    "content_coverage": {"coverage_score": 80, ...},
    "linguistic": {"language_score": 81.3, ...}
  },
  "scoring": {
    "fact_accuracy_score": 85.0,
    "coverage_score": 80.0,
    "content_score": 82.5,
    "logical_flow": 78.0,
    "language_score": 81.3,
    "raw_score": 80.85,
    "contradiction_penalty": 0.0,
    "final_score": 80.85,
    "normalized_score_0_1600": 1293.6
  },
  "grade": "A",
  "feedback": "✓ Good factual accuracy. ✓ Good coverage of required concepts."
}
```

---

**Last Updated:** January 2026  
**Version:** 3.0.0
