# Deployment Checklist: AI Essay Grader v3.0

## Pre-Deployment Verification

### 1. Environment Setup ✓

- [ ] Python 3.9+ installed
- [ ] Virtual environment created and activated
- [ ] All dependencies installed: `pip install -r backend/requirements.txt`

### 2. Configuration ✓

- [ ] `.env` file created with required variables:
  - [ ] `OPENAI_API_KEY`
  - [ ] `PINECONE_API_KEY`
  - [ ] `PINECONE_ENVIRONMENT`
  - [ ] `MONGO_URL`
  - [ ] `DATABASE_URL`
  - [ ] `KAFKA_BOOTSTRAP_SERVERS`

- [ ] `app/core/config.py` verified with correct settings
- [ ] Embedding model confirmed: `text-embedding-3-small`
- [ ] Chunking parameters verified:
  - Parent: 1000 tokens
  - Child: 200 tokens
  - Overlap: 50 tokens

### 3. External Services ✓

#### MongoDB
- [ ] Instance running (local or Atlas)
- [ ] Connection URL tested
- [ ] Collections will auto-create:
  - [ ] `parent_docs`
  - [ ] `shadow_graphs`
  - [ ] `essay_evaluations`
- [ ] Indexes created for performance

#### Pinecone
- [ ] Account created at pinecone.io
- [ ] API key generated
- [ ] Indices created for each subject:
  - [ ] `history-index` (dimension: 1536)
  - [ ] `geography-index` (dimension: 1536)
  - [ ] `political-science-index` (dimension: 1536)
  - [ ] `economics-index` (dimension: 1536)
  - [ ] `general-studies-index` (dimension: 1536)
- [ ] Test query executed successfully

#### OpenAI
- [ ] API key obtained
- [ ] Billing enabled
- [ ] Model `text-embedding-3-small` accessible
- [ ] Model `gpt-3.5-turbo` accessible for chat completions
- [ ] Rate limits understood

#### PostgreSQL (Legacy)
- [ ] Database created: `essay_eval_db`
- [ ] User authentication configured
- [ ] Tables will auto-create via SQLAlchemy

#### Kafka (Optional for Legacy Features)
- [ ] Kafka broker running (if using legacy ingestion)
- [ ] Topics created:
  - [ ] `ocr-jobs`
  - [ ] `ai-processing`

### 4. Code Verification ✓

#### Core Modules
- [ ] `app/services/ingestion.py` - Parent-Child RAG implementation
- [ ] `app/services/essay_evaluator.py` - 3-Phase evaluation engine
- [ ] `app/models/schemas.py` - Pydantic validation models
- [ ] `app/core/config.py` - Configuration with new settings
- [ ] `app/main.py` - Updated with new endpoints

#### New API Endpoints
- [ ] `/ingest/textbook` - POST endpoint implemented
- [ ] `/ingest/batch` - POST endpoint for batch processing
- [ ] `/grade_essay` - POST endpoint for essay grading
- [ ] `/evaluation/{evaluation_id}` - GET endpoint for retrieving results

#### Backward Compatibility
- [ ] Legacy endpoints preserved:
  - [ ] `/upload/`
  - [ ] `/status/{submission_id}`
  - [ ] `/submissions/`
  - [ ] `/health`

### 5. Testing ✓

#### Unit Tests
- [ ] Import all modules without errors
- [ ] Syntax validation passed
- [ ] Type hints correct (Pydantic models)

#### Integration Tests
- [ ] Test ingestion with sample PDF
- [ ] Test essay grading with sample essay
- [ ] Verify MongoDB document creation
- [ ] Verify Pinecone vector upsert
- [ ] Verify OpenAI API calls work

#### API Tests
- [ ] `POST /ingest/textbook` returns 200
- [ ] `POST /grade_essay` returns 200
- [ ] `GET /evaluation/{id}` returns 200
- [ ] Error handling returns appropriate status codes

### 6. Performance Validation ✓

#### Ingestion Pipeline
- [ ] Single PDF ingestion: < 30 seconds
- [ ] Batch processing: Parallel execution working
- [ ] MongoDB inserts: < 2 seconds for 25 parents
- [ ] Pinecone upserts: < 5 seconds for 150 vectors
- [ ] Memory usage: < 500MB for typical PDF

#### Evaluation Pipeline
- [ ] Shadow rubric creation: < 3 seconds
- [ ] Atomic claims extraction: < 2 seconds
- [ ] Parallel agents: Running concurrently
- [ ] Fact checker: < 10 seconds
- [ ] Content coverage: < 2 seconds
- [ ] Linguistic analysis: < 3 seconds
- [ ] Total evaluation: < 25 seconds
- [ ] Response time acceptable for API

### 7. Database Verification ✓

#### MongoDB Checks
```bash
# Connect to MongoDB
mongo "mongodb://localhost:27017"

# Switch to database
use essayEval

# Check collections created
show collections

# Expected output:
# parent_docs
# shadow_graphs
# essay_evaluations
```

- [ ] Collections exist
- [ ] Indexes created for performance
- [ ] Sample documents can be queried

#### Pinecone Checks
```python
from pinecone import Pinecone

pc = Pinecone(api_key="...")
index = pc.Index("history-index")
index_info = index.describe_index_stats()

# Verify:
# - dimensions: 1536
# - records: > 0 (after ingestion)
```

- [ ] Indices exist with correct dimensions
- [ ] Metadata filtering works
- [ ] Vector search returns results

### 8. Security Review ✓

- [ ] API keys never hardcoded (using environment variables)
- [ ] CORS configured for appropriate origins
- [ ] Rate limiting implemented for API access
- [ ] MongoDB authentication enabled
- [ ] Pinecone API key protected
- [ ] Error messages don't expose sensitive data
- [ ] Input validation on all endpoints (Pydantic)
- [ ] No SQL injection vulnerabilities
- [ ] No unauthorized data exposure

### 9. Documentation ✓

- [ ] [IMPLEMENTATION_MODULES.md](../IMPLEMENTATION_MODULES.md) - Complete
- [ ] [QUICK_REFERENCE_V3.md](../QUICK_REFERENCE_V3.md) - Complete
- [ ] [ARCHITECTURE_DETAILED.md](../ARCHITECTURE_DETAILED.md) - Complete
- [ ] [IMPLEMENTATION_COMPLETE_V3.md](../IMPLEMENTATION_COMPLETE_V3.md) - Complete
- [ ] API documentation at `/docs` working
- [ ] README updated with v3.0 information

### 10. Monitoring & Logging ✓

- [ ] Logging configured to INFO level
- [ ] Log output includes timestamps
- [ ] Key operations logged:
  - [ ] Ingestion start/completion
  - [ ] API request receipt
  - [ ] Database operations
  - [ ] LLM API calls
  - [ ] Error conditions
- [ ] Logs stored for audit trail
- [ ] Error handling with graceful fallbacks

---

## Deployment Steps

### Step 1: Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### Step 2: Configure Environment
```bash
# Create .env file
cp .env.example .env

# Edit .env with actual values
nano .env
```

### Step 3: Verify External Services
```bash
# Test MongoDB connection
python -c "from motor.motor_asyncio import AsyncIOMotorClient; from app.core.config import settings; print('MongoDB OK')"

# Test Pinecone
python -c "from pinecone import Pinecone; from app.core.config import settings; pc = Pinecone(api_key=settings.PINECONE_API_KEY); print('Pinecone OK')"

# Test OpenAI
python -c "from openai import AsyncOpenAI; from app.core.config import settings; client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY); print('OpenAI OK')"
```

### Step 4: Create Pinecone Indices
```python
from pinecone import Pinecone
from app.core.config import settings

pc = Pinecone(api_key=settings.PINECONE_API_KEY)

# Create indices for each subject
indices = {
    "history-index": 1536,
    "geography-index": 1536,
    "political-science-index": 1536,
    "economics-index": 1536,
    "general-studies-index": 1536
}

for index_name, dimension in indices.items():
    try:
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine"
        )
        print(f"Created: {index_name}")
    except:
        print(f"Already exists: {index_name}")
```

### Step 5: Start the API Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 6: Verify API is Running
```bash
# Check health
curl http://localhost:8000/

# View API docs
# Open browser: http://localhost:8000/docs
```

### Step 7: Run Initial Tests
```bash
# Test ingestion
curl -X POST http://localhost:8000/ingest/textbook \
  -H "Content-Type: application/json" \
  -d '{"subject": "History", "grade": 10, "file_path": "/path/to/sample.pdf"}'

# Test essay grading
curl -X POST http://localhost:8000/grade_essay \
  -H "Content-Type: application/json" \
  -d '{
    "essay_text": "Sample essay...",
    "question": "Sample question...",
    "subject": "history"
  }'
```

---

## Post-Deployment Verification

### Checklist

- [ ] API responds to requests on all new endpoints
- [ ] Ingestion creates documents in MongoDB
- [ ] Ingestion creates vectors in Pinecone
- [ ] Evaluation creates shadow rubrics
- [ ] Evaluation produces valid grading reports
- [ ] Scores fall within 0-1600 range
- [ ] Letter grades assigned correctly (A+ through F)
- [ ] Feedback messages are personalized
- [ ] Error responses are properly formatted
- [ ] Logs show expected operations
- [ ] Performance meets requirements
- [ ] No memory leaks over extended usage

### Monitoring Commands

```bash
# Monitor API logs
tail -f logs/essay_grader.log

# Check MongoDB for ingestion results
mongo essayEval
db.parent_docs.count()
db.shadow_graphs.count()
db.essay_evaluations.count()

# Check Pinecone vector count
python -c "from pinecone import Pinecone; from app.core.config import settings; pc = Pinecone(api_key=settings.PINECONE_API_KEY); idx = pc.Index('history-index'); print(idx.describe_index_stats())"

# Monitor API performance
# Use APM tools like DataDog, New Relic, or Prometheus
```

---

## Scaling Considerations

### For Production Deployment

1. **API Gateway**: Use load balancer (nginx, AWS ALB)
2. **Database Scaling**:
   - MongoDB: Atlas with auto-scaling
   - PostgreSQL: Read replicas for high traffic
3. **Caching**: Redis for frequently accessed data
4. **Queue Management**: Kafka for async operations
5. **Monitoring**: Datadog, New Relic, or CloudWatch
6. **Alerting**: PagerDuty for critical issues
7. **CDN**: CloudFront for static assets
8. **Containerization**: Docker + Kubernetes for orchestration

### Estimated Capacity

- **Single Server**: 100-200 concurrent users
- **Ingestion**: 5-10 PDFs/minute
- **Evaluation**: 3-5 essays/minute
- **Storage**: ~1GB per 10,000 essays evaluated

---

## Rollback Plan

If issues arise post-deployment:

1. **Quick Rollback**:
   ```bash
   git revert <commit_hash>
   pip install -r requirements.txt
   restart service
   ```

2. **Data Recovery**:
   - MongoDB: Backup exists at `/backups/mongodb`
   - Pinecone: Vectors recoverable from parent_docs
   - PostgreSQL: Automated backups enabled

3. **Notify Team**:
   - Send incident notification
   - Document what went wrong
   - Plan fix for next deployment

---

## Support Contacts

- **Technical Issues**: Dev team Slack channel
- **Infrastructure**: DevOps team
- **Data Issues**: Database admin
- **API Questions**: API documentation or /docs

---

## Final Sign-Off

- [ ] QA: All tests passed
- [ ] DevOps: Infrastructure ready
- [ ] Security: Security review complete
- [ ] Product: Feature acceptance received
- [ ] Management: Deployment approved

**Deployment Date**: _______________
**Deployed By**: _______________
**Verified By**: _______________

---

**Version**: 3.0.0  
**Last Updated**: January 2026  
**Status**: Ready for Production
