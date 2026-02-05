## IMPLEMENTATION GUIDE: AI Essay Grader for UPSC Aspirants

### Overview

This implementation provides a complete two-module system for intelligent essay grading:
1. **Data Ingestion Pipeline**: Store NCERT textbook content using Parent-Child RAG
2. **Essay Evaluation Engine**: Multi-agent system for comprehensive essay grading

---

## Module 1: Data Ingestion Pipeline

### Purpose
Extract and organize NCERT PDFs (Grades 6-12) into a retrieval-augmented generation (RAG) system with Pinecone and MongoDB.

### Architecture

```
NCERT PDF
    ↓
[Text Extraction] → PyMuPDF
    ↓
[Parent Chunking] → ~1000 tokens → MongoDB (Text Storage)
    ↓
[Child Chunking]  → ~200 tokens → OpenAI Embedding → Pinecone (Vector + Metadata)
    ↓
[Linkage] → metadata.parent_id points to MongoDB ObjectId
```

### Key Components

#### `NCERTIngestionPipeline` Class (`app/services/ingestion.py`)

**Methods:**

1. **`ingest_textbook(file_path, subject, grade)`**
   - Main ingestion function
   - Args:
     - `file_path`: Path to NCERT PDF
     - `subject`: Subject name (e.g., 'History', 'Geography')
     - `grade`: Grade level (6-12)
   - Returns: Dictionary with statistics

2. **`_extract_text_from_pdf(file_path)`**
   - Uses PyMuPDF to extract text from PDF
   - Preserves formatting and structure

3. **`_create_parent_chunks(text)`**
   - Creates large chunks (~1000 tokens)
   - Preserves context and full meaning
   - Stored in MongoDB collection: `parent_docs`

4. **`_create_child_chunks(parent_chunk)`**
   - Creates small chunks (~200 tokens) from each parent
   - Optimized for semantic search
   - Each child references parent via metadata

5. **`_get_embedding(text)`**
   - Calls OpenAI API to get text embeddings
   - Uses `text-embedding-3-small` model (1536-dim vectors)

6. **`ingest_batch(files)`**
   - Process multiple files in parallel
   - Args: List of tuples (file_path, subject, grade)

### MongoDB Storage

**Collection: `parent_docs`**
```python
{
    "_id": ObjectId,
    "subject": "history",
    "grade": 10,
    "text": "Full parent chunk text (up to ~1000 tokens)",
    "token_count": 1024,
    "parent_index": 0,
    "created_at": timestamp
}
```

### Pinecone Storage

**Index Name Pattern:** `{subject}-index` (e.g., `history-index`)

**Vector Format:**
```python
{
    "id": "{parent_id}_{child_idx}",
    "values": [0.123, -0.456, ...],  # 1536-dim embedding
    "metadata": {
        "parent_id": "ObjectId string",
        "grade": 10,
        "subject": "history",
        "child_index": 0,
        "text_preview": "First 100 chars of child chunk"
    }
}
```

### API Endpoint

**POST `/ingest/textbook`**
```bash
curl -X POST http://localhost:8000/ingest/textbook \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "History",
    "grade": 10,
    "file_path": "/path/to/ncert_history_10.pdf"
  }'
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

---

## Module 2: Essay Evaluation Engine

### Purpose
Grade student essays using a sophisticated 3-phase multi-agent system.

### Architecture

```
Student Essay + Question
    ↓
[Phase 0: Shadow Rubric]
    ├─ Query RAG system with question
    ├─ Extract 15 must-have concepts from NCERT
    └─ Create answer key (Shadow Rubric)
    ↓
[Phase 1: Extraction & Parsing]
    ├─ Extract atomic claims from essay
    ├─ Extract discourse markers (logical flow indicators)
    └─ Split into paragraphs
    ↓
[Phase 2: Parallel Agent Execution]
    ├─ Agent 1: Fact Checker (verify claims)
    ├─ Agent 2: Content Coverage (check concept coverage)
    └─ Agent 3: Linguistic (grammar, vocabulary, tone)
    ↓
[Phase 3: Holistic Scoring]
    ├─ Calculate raw score
    ├─ Apply penalties for contradictions
    ├─ Calculate logical flow (paragraph-to-paragraph similarity)
    └─ Normalize to 0-1600 range and assign grade
```

### Key Components

#### `EssayEvaluationEngine` Class (`app/services/essay_evaluator.py`)

### Phase 0: Shadow Rubric

**`create_shadow_rubric(question, subject)`**
- Query Pinecone with the essay question
- Fetch parent documents from MongoDB
- Extract top 15 concepts using LLM
- Returns: List of must-have concepts (answer key)

### Phase 1: Extraction & Parsing

**`extract_atomic_claims(essay_text)`**
- Uses LLM to identify factual claims
- Returns: List of 5-10 atomic claims
- Example: "The Battle of Plassey was in 1757"

**`extract_discourse_markers(essay_text)`**
- Identifies logical connectives:
  - Causative: "because", "due to", "caused"
  - Contrastive: "however", "but", "although"
  - Additive: "moreover", "furthermore", "also"
  - Conclusive: "therefore", "thus", "hence"
  - Sequential: "then", "next", "finally"
- Returns: Dictionary with marker counts

### Phase 2: Parallel Agents

#### Agent 1: Fact Checker

**`fact_checker_agent(claims, subject)`**
- For each claim:
  1. Query Pinecone (Child chunks) for relevant content
  2. Fetch parent documents from MongoDB
  3. Use LLM to verify if claim is SUPPORTED/CONTRADICTED/NEUTRAL
- Returns:
  - List of verified claims with status
  - Accuracy Score (0-100)
  - Contradiction count

**Example Output:**
```python
{
    "agent": "fact_checker",
    "verified_claims": [
        {
            "claim": "The Battle of Plassey was in 1757",
            "status": "supported",
            "confidence": 0.9
        },
        {
            "claim": "It resulted in British rule",
            "status": "supported",
            "confidence": 0.85
        }
    ],
    "accuracy_score": 85.0,
    "contradiction_count": 0,
    "supported_count": 2,
    "total_claims": 2
}
```

#### Agent 2: Content Coverage

**`content_coverage_agent(essay_text, shadow_concepts)`**
- Check which must-have concepts appear in essay (case-insensitive)
- Returns:
  - List of covered/uncovered concepts
  - Coverage Score (0-100) = (covered / total) * 100

**Example Output:**
```python
{
    "agent": "content_coverage",
    "covered_concepts": [
        {"concept": "British East India Company", "covered": True},
        {"concept": "Robert Clive", "covered": True},
        {"concept": "Bengal", "covered": True},
        {"concept": "French competition", "covered": False}
    ],
    "coverage_score": 75.0,
    "concepts_covered": 3,
    "total_concepts": 4
}
```

#### Agent 3: Linguistic Analysis

**`linguistic_agent(essay_text)`**
- Uses LLM to analyze:
  - Grammar quality (0-100)
  - Vocabulary level (0-100)
  - Tone appropriateness for UPSC (0-100)
- Returns:
  - Individual scores for each dimension
  - Weighted language score = (Grammar × 0.3) + (Vocabulary × 0.4) + (Tone × 0.3)

**Example Output:**
```python
{
    "agent": "linguistic",
    "grammar_score": 85,
    "vocabulary_score": 78,
    "tone_score": 82,
    "language_score": 81.3,
    "overall_score": 82
}
```

### Phase 3: Holistic Scoring

**Scoring Formula:**

```
Content_Score = (Fact_Accuracy_Score + Coverage_Score) / 2

Logical_Flow = Average cosine similarity between consecutive paragraph embeddings

Raw_Score = (0.5 × Content_Score) + (0.3 × Logical_Flow) + (0.2 × Language_Score)

Contradiction_Penalty = 15 × number_of_contradictions

Final_Score = max(0, Raw_Score - Contradiction_Penalty)

Normalized_Score (0-1600) = (Final_Score / 100) × 1600

Grade = A+ (≥1440), A (≥1280), B+ (≥1120), B (≥960), C+ (≥800), C (≥640), D (≥480), F (<480)
```

**Example Calculation:**
```
Fact Accuracy: 85
Coverage: 80
Content Score: (85 + 80) / 2 = 82.5

Logical Flow: 78 (paragraph-to-paragraph similarity)
Language Score: 81

Raw Score = (0.5 × 82.5) + (0.3 × 78) + (0.2 × 81)
          = 41.25 + 23.4 + 16.2
          = 80.85

Contradictions: 1
Penalty: 1 × 15 = 15

Final Score = 80.85 - 15 = 65.85

Normalized Score = (65.85 / 100) × 1600 = 1053.6

Grade: B
```

### Logical Flow Calculation

- Split essay into paragraphs
- Get embeddings for each paragraph using OpenAI API
- Calculate cosine similarity between consecutive paragraphs
- Average similarity score × 100 = Logical Flow (0-100)
- High similarity = essay flows well between ideas

### API Endpoint

**POST `/grade_essay`**
```bash
curl -X POST http://localhost:8000/grade_essay \
  -H "Content-Type: application/json" \
  -d '{
    "essay_text": "The Battle of Plassey (1757) was a crucial event...",
    "question": "Discuss the significance of the Battle of Plassey",
    "subject": "history"
  }'
```

**Response Structure:**
```json
{
    "evaluation_id": "1234567890.123",
    "question": "Discuss the significance of the Battle of Plassey",
    "subject": "history",
    "essay_preview": "The Battle of Plassey (1757)...",
    
    "phase_0_shadow_rubric": {
        "concepts": ["Battle of Plassey", "British East India Company", ...],
        "concept_count": 15
    },
    
    "phase_1_extraction": {
        "claims": ["The Battle was in 1757", ...],
        "claim_count": 5,
        "discourse_markers": {
            "causative": 3,
            "contrastive": 2,
            "additive": 4,
            "conclusive": 2,
            "sequential": 1
        }
    },
    
    "phase_2_agents": {
        "fact_checker": { ... },
        "content_coverage": { ... },
        "linguistic": { ... }
    },
    
    "scoring": {
        "fact_accuracy_score": 85.0,
        "coverage_score": 80.0,
        "content_score": 82.5,
        "logical_flow": 78.0,
        "language_score": 81.3,
        "raw_score": 80.85,
        "contradiction_penalty": 15.0,
        "final_score": 65.85,
        "normalized_score_0_1600": 1053.6
    },
    
    "grade": "B",
    "feedback": "✓ Good factual accuracy. ✓ Good coverage... ⚠️ Improve grammar..."
}
```

---

## Configuration

### Environment Variables (`.env`)

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Pinecone
PINECONE_API_KEY=...
PINECONE_ENVIRONMENT=us-east-1-aws

# MongoDB
MONGO_URL=mongodb://localhost:27017

# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/essay_eval_db

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Groq (Legacy)
GROQ_API_KEY=...
```

### Settings Configuration (`app/core/config.py`)

```python
class Settings:
    # Embedding
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSION = 1536
    
    # Chunking
    PARENT_CHUNK_SIZE = 1000    # tokens
    CHILD_CHUNK_SIZE = 200      # tokens
    CHUNK_OVERLAP = 50          # tokens
    
    # Pinecone indices (subject-based, not grade-based)
    PINECONE_INDICES = {
        "history": "history-index",
        "geography": "geography-index",
        "political-science": "political-science-index",
        "economics": "economics-index",
        "general-studies": "general-studies-index"
    }
    
    # MongoDB collections
    MONGO_PARENT_DOCS_COLLECTION = "parent_docs"
    MONGO_SHADOW_GRAPHS_COLLECTION = "shadow_graphs"
    MONGO_ESSAY_EVALUATIONS_COLLECTION = "essay_evaluations"
```

---

## Database Schema

### MongoDB Collections

#### 1. `parent_docs` - Parent Chunks Storage
```javascript
{
    "_id": ObjectId,
    "subject": String,           // "history", "geography", etc.
    "grade": Integer,            // 6-12
    "text": String,              // Full parent chunk (~1000 tokens)
    "token_count": Integer,
    "parent_index": Integer,     // Index within document
    "created_at": Number         // Unix timestamp
}
```

#### 2. `shadow_graphs` - Shadow Rubrics (Answer Keys)
```javascript
{
    "_id": ObjectId,
    "question": String,          // Essay question
    "subject": String,
    "concepts": [String],        // 15 must-have concepts
    "retrieved_docs": [{...}],   // Retrieved parent documents
    "created_at": Number
}
```

#### 3. `essay_evaluations` - Evaluation Reports
```javascript
{
    "_id": ObjectId,
    "evaluation_id": String,
    "question": String,
    "subject": String,
    "essay_preview": String,
    "phase_0_shadow_rubric": {...},
    "phase_1_extraction": {...},
    "phase_2_agents": {...},
    "scoring": {...},
    "grade": String,
    "feedback": String,
    "created_at": Number
}
```

### Pinecone Index Schema

**Index Name:** `{subject}-index`

**Vector Metadata:**
```python
{
    "parent_id": String,        # MongoDB ObjectId
    "grade": Integer,           # 6-12
    "subject": String,          # normalized to lowercase
    "child_index": Integer,     # Index within parent
    "text_preview": String      # First 100 chars
}
```

---

## Usage Examples

### Example 1: Ingest NCERT History Textbook

```python
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.services.ingestion import NCERTIngestionPipeline
from app.core.config import settings

async def main():
    # Initialize MongoDB
    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client.get_database("essayEval")
    
    # Initialize pipeline
    pipeline = NCERTIngestionPipeline(db)
    
    # Ingest textbook
    result = await pipeline.ingest_textbook(
        file_path="/path/to/ncert_history_10.pdf",
        subject="History",
        grade=10
    )
    
    print(f"✓ Ingestion complete: {result}")

asyncio.run(main())
```

### Example 2: Grade an Essay

```python
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.services.essay_evaluator import EssayEvaluationEngine
from app.core.config import settings

async def main():
    # Initialize MongoDB
    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client.get_database("essayEval")
    
    # Initialize engine
    engine = EssayEvaluationEngine(db)
    
    # Grade essay
    essay = """
    The Battle of Plassey (1757) was a crucial turning point in Indian history.
    Robert Clive's victory over Siraj-ud-Daulah led to British dominance in Bengal.
    This battle marked the beginning of British imperial rule in India...
    """
    
    result = await engine.grade_essay(
        essay_text=essay,
        question="Discuss the significance of the Battle of Plassey",
        subject="history"
    )
    
    print(f"Grade: {result['grade']}")
    print(f"Score (0-1600): {result['scoring']['normalized_score_0_1600']}")
    print(f"Feedback: {result['feedback']}")

asyncio.run(main())
```

---

## Performance Considerations

### Optimization Tips

1. **Chunking Strategy**
   - Larger parent chunks preserve context but require more storage
   - Smaller child chunks improve retrieval precision
   - 1000/200 token ratio provides good balance

2. **Parallel Processing**
   - All 3 agents in Phase 2 run concurrently via `asyncio.gather()`
   - RAG queries parallelized across multiple claims
   - Embeddings fetched in batch where possible

3. **Rate Limiting**
   - OpenAI API: Implement token bucket rate limiter
   - Pinecone: Default rate limits are generous
   - MongoDB: No rate limiting needed (local or Atlas)

4. **Caching**
   - Cache embeddings of frequently used concepts
   - Cache shadow rubrics for similar questions
   - Store evaluation results in MongoDB for reference

---

## Error Handling

The system includes comprehensive error handling:

1. **PDF Extraction Errors**: Caught and logged, returns error response
2. **OpenAI API Errors**: Retry with exponential backoff (built into langchain)
3. **Pinecone Errors**: Fallback to less detailed search
4. **MongoDB Errors**: Transient retries, eventual error if persistent
5. **LLM Parsing Errors**: Graceful fallback to default values

---

## Testing the Implementation

### 1. Test Ingestion

```bash
curl -X POST http://localhost:8000/ingest/textbook \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "History",
    "grade": 10,
    "file_path": "/path/to/sample.pdf"
  }'
```

### 2. Test Essay Grading

```bash
curl -X POST http://localhost:8000/grade_essay \
  -H "Content-Type: application/json" \
  -d '{
    "essay_text": "Sample essay text here...",
    "question": "Sample question here...",
    "subject": "history"
  }'
```

### 3. View API Documentation

Visit `http://localhost:8000/docs` for interactive Swagger UI

---

## File Structure

```
backend/
├── app/
│   ├── core/
│   │   └── config.py           # Updated with Pinecone/OpenAI settings
│   ├── db/
│   │   ├── models.py
│   │   ├── mongo.py
│   │   └── postgres.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # NEW: Pydantic models
│   ├── services/
│   │   ├── ingestion.py        # NEW: Data ingestion pipeline
│   │   ├── essay_evaluator.py  # NEW: Essay evaluation engine
│   │   ├── ai_agents.py
│   │   └── ocr.py
│   ├── utils/
│   │   ├── ai_orchestrator.py
│   │   └── rate_limiter.py
│   └── main.py                 # Updated with new endpoints
├── requirements.txt            # Updated dependencies
└── Dockerfile
```

---

## Next Steps

1. **Set up environment variables** in `.env` file
2. **Install dependencies**: `pip install -r requirements.txt`
3. **Initialize Pinecone indices** with appropriate settings
4. **Test ingestion** with sample NCERT PDFs
5. **Test essay grading** with sample essays
6. **Monitor logs** for performance metrics
7. **Fine-tune parameters** based on test results

---

## Key Features Summary

| Feature | Details |
|---------|---------|
| **Ingestion** | Parent-Child RAG with Pinecone + MongoDB |
| **Retrieval** | Semantic search with OpenAI embeddings |
| **Evaluation** | 3-Phase multi-agent system |
| **Fact-Checking** | LLM-based verification against NCERT |
| **Content Coverage** | Concept matching from shadow rubric |
| **Language Analysis** | Grammar, vocabulary, tone assessment |
| **Logical Flow** | Vector similarity between paragraphs |
| **Scoring** | Weighted formula (0-100) normalized to 0-1600 |
| **Grading** | A+ through F letter grades |
| **Feedback** | Personalized improvement suggestions |

---

**Version:** 3.0.0  
**Last Updated:** January 2026  
**Status:** Implementation Complete
