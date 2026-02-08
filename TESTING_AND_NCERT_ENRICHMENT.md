# Testing & NCERT Enrichment Strategy

## Overview
- **LLM**: Groq API (Mixtral-8x7b-32768) for all chat completions
- **Embeddings**: OpenAI (text-embedding-3-small) - Groq doesn't support embeddings
- **Vector DB**: Pinecone (subject-indexed, 5 main indices)
- **Metadata DB**: MongoDB (parent docs, shadow graphs, evaluations)
- **Queue System**: Kafka (OCR → AI pipeline)

---

## PART 1: TESTING STRATEGY

### 1.1 Setup & Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Set environment variables
export GROQ_API_KEY="your_groq_key"
export OPENAI_API_KEY="your_openai_key"
export PINECONE_API_KEY="your_pinecone_key"
export MONGO_URL="mongodb://localhost:27017"
export KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
```

### 1.2 Unit Testing

#### Test 1: Groq LLM Integration (Mock Test)

**File**: `backend/tests/test_groq_integration.py`

```python
import pytest
import asyncio
from app.services.essay_evaluator import EssayEvaluationEngine
from app.db.mongo import db

@pytest.mark.asyncio
async def test_extract_concepts_with_groq():
    """Test Groq concept extraction"""
    engine = EssayEvaluationEngine(db)
    
    sample_text = """
    Democracy is a system of government where power is vested in the people.
    Citizens participate in decision-making through voting and representation.
    Key concepts include separation of powers, rule of law, and individual rights.
    """
    
    concepts = await engine._extract_concepts(sample_text)
    
    assert isinstance(concepts, list)
    assert len(concepts) > 0
    assert len(concepts) <= 15
    print(f"✓ Extracted concepts: {concepts}")

@pytest.mark.asyncio
async def test_extract_atomic_claims_with_groq():
    """Test Groq claim extraction"""
    engine = EssayEvaluationEngine(db)
    
    essay = """
    The Indian Constitution was adopted in 1950. It guarantees fundamental rights to all citizens.
    Dr. Ambedkar chaired the drafting committee. The Preamble outlines the nation's objectives.
    """
    
    claims = await engine.extract_atomic_claims(essay)
    
    assert isinstance(claims, list)
    assert len(claims) > 0
    assert all(isinstance(c, str) for c in claims)
    print(f"✓ Extracted claims: {claims}")

@pytest.mark.asyncio
async def test_linguistic_agent_with_groq():
    """Test Groq linguistic analysis"""
    engine = EssayEvaluationEngine(db)
    
    essay = "The Constitution of India is the supreme law of the land."
    
    result = await engine.linguistic_agent(essay)
    
    assert result["agent"] == "linguistic"
    assert "language_score" in result
    assert 0 <= result["language_score"] <= 100
    print(f"✓ Linguistic analysis: {result['language_score']}")

# Run tests
# pytest backend/tests/test_groq_integration.py -v
```

#### Test 2: Pinecone Embedding Integration

**File**: `backend/tests/test_pinecone_embeddings.py`

```python
import pytest
from app.services.ingestion import NCERTIngestionPipeline
from app.db.mongo import db

@pytest.mark.asyncio
async def test_pinecone_query():
    """Test Pinecone vector search"""
    engine = EssayEvaluationEngine(db)
    
    query = "What are fundamental rights in India?"
    subject = "political-science"
    
    results = await engine._query_pinecone(query, subject, top_k=3)
    
    assert isinstance(results, list)
    assert all("score" in r for r in results)
    print(f"✓ Top {len(results)} results for '{query}'")

# Run: pytest backend/tests/test_pinecone_embeddings.py -v
```

### 1.3 Integration Testing

#### Test 3: Full Essay Evaluation Pipeline

**File**: `backend/tests/test_essay_evaluation_pipeline.py`

```python
import pytest
from app.services.essay_evaluator import EssayEvaluationEngine
from app.db.mongo import db

@pytest.mark.asyncio
async def test_full_grading_pipeline():
    """End-to-end essay grading"""
    engine = EssayEvaluationEngine(db)
    
    essay = """
    Indian democracy is built on the principles of liberty, equality, and fraternity.
    The Constitution guarantees fundamental rights including freedom of speech.
    Separation of powers between executive, legislative, and judicial branches ensures checks and balances.
    The Parliament is bicameral with the Lok Sabha and Rajya Sabha working for national interest.
    """
    
    question = "Explain the key principles and structure of Indian democracy"
    subject = "political-science"
    
    # Run full evaluation
    result = await engine.grade_essay(
        essay_text=essay,
        question=question,
        subject=subject
    )
    
    # Validate output structure
    assert "grade" in result
    assert "scoring" in result
    assert "overall_score" in result["scoring"]
    assert "feedback" in result
    
    print(f"✓ Essay Score: {result['scoring']['final_score']}")
    print(f"✓ Grade: {result['grade']}")
    print(f"✓ Feedback: {result['feedback']}")

# Run: pytest backend/tests/test_essay_evaluation_pipeline.py -v -s
```

### 1.4 Queue Integration Testing

#### Test 4: Kafka End-to-End

**File**: `backend/tests/test_kafka_pipeline.py`

```python
import asyncio
import json
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from app.core.config import settings

async def test_kafka_ocr_to_ai_pipeline():
    """Test OCR worker → AI worker message flow"""
    
    # Simulate OCR producer
    producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    await producer.start()
    
    message = {
        "submission_id": 123,
        "mongo_id": "507f1f77bcf86cd799439011",
        "filename": "essay.pdf",
        "question": "Analyze the rise of nationalism in 19th century India",
        "subject": "history"
    }
    
    await producer.send_and_wait(
        settings.OCR_TOPIC,
        json.dumps(message).encode('utf-8')
    )
    await producer.stop()
    
    # Consume from AI topic (should be produced by OCR worker)
    consumer = AIOKafkaConsumer(
        settings.AI_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="test-group",
        auto_offset_reset='earliest',
        consumer_timeout_ms=5000
    )
    
    await consumer.start()
    
    received_messages = []
    async for msg in consumer:
        data = json.loads(msg.value.decode('utf-8'))
        received_messages.append(data)
        if len(received_messages) >= 1:
            break
    
    await consumer.stop()
    
    assert len(received_messages) >= 1
    assert "mongo_id" in received_messages[0]
    print(f"✓ Message flow: OCR → AI Topic successful")

# Run: pytest backend/tests/test_kafka_pipeline.py -v -s
```

### 1.5 Quick Manual Testing

**Test the API directly:**

```bash
# 1. Start backend, OCR worker, AI worker, Kafka
docker-compose up -d

# 2. Upload an essay (generates Submission ID)
curl -X POST "http://localhost:8000/upload_essay" \
  -F "file=@sample_essay.pdf" \
  -F "question=Explain Indian federalism" \
  -F "subject=political-science"

# Response: {"submission_id": 123, "status": "uploaded"}

# 3. Check evaluation status
curl "http://localhost:8000/evaluation/123"

# 4. View raw evaluation report
curl "http://localhost:8000/evaluation/123/report"
```

---

## PART 2: NCERT BOOK ENRICHMENT STRATEGY

### 2.1 Data Collection

#### Option A: Use NCERT PDF Directory

```bash
# Create NCERT books directory
mkdir -p data/ncert_books
# Download NCERT PDFs from: https://ncert.nic.in/ncertpublications/
# Place in: data/ncert_books/
```

**Expected structure**:
```
data/ncert_books/
├── history/
│   ├── class-9-ancient-india.pdf
│   ├── class-10-medieval-india.pdf
│   └── class-11-modern-india.pdf
├── geography/
│   ├── class-9-physical-geography.pdf
│   └── class-10-human-geography.pdf
├── political-science/
│   ├── class-9-constitution.pdf
│   └── class-10-governance.pdf
└── economics/
    ├── class-10-development.pdf
    └── class-11-macroeconomics.pdf
```

#### Option B: Use Public APIs

```python
# Example: NCERT Book API (if available)
import httpx

async def fetch_ncert_from_api():
    """Fetch NCERT content from public APIs"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.ncert.nic.in/books",
            params={"subject": "history", "class": "11"}
        )
        return response.json()
```

### 2.2 Ingestion Pipeline (Direct Integration)

**File**: `backend/scripts/enrich_ncert_books.py`

```python
import asyncio
from app.services.ingestion import NCERTIngestionPipeline
from app.db.mongo import db
from app.core.config import settings
import os

async def enrich_vector_db_with_ncert():
    """Batch ingest all NCERT books into Pinecone + MongoDB"""
    
    ingestion = NCERTIngestionPipeline(db)
    
    subject_mapping = {
        "history": "data/ncert_books/history",
        "geography": "data/ncert_books/geography",
        "political-science": "data/ncert_books/political-science",
        "economics": "data/ncert_books/economics",
        "general-studies": "data/ncert_books/general-studies"
    }
    
    for subject, directory in subject_mapping.items():
        if not os.path.exists(directory):
            print(f"⚠️  Skipping {subject}: directory not found")
            continue
        
        pdf_files = [f for f in os.listdir(directory) if f.endswith('.pdf')]
        
        for pdf_file in pdf_files:
            pdf_path = os.path.join(directory, pdf_file)
            
            print(f"📖 Ingesting: {subject}/{pdf_file}")
            
            with open(pdf_path, 'rb') as f:
                file_bytes = f.read()
            
            result = await ingestion.ingest_textbook(
                file_bytes=file_bytes,
                filename=pdf_file,
                subject=subject,
                grade=pdf_file.split("-")[1] if "-" in pdf_file else "general"
            )
            
            print(f"✓ {subject}/{pdf_file}: {result.get('status')}")

# Run the ingestion
if __name__ == "__main__":
    asyncio.run(enrich_vector_db_with_ncert())
```

**Execute**:
```bash
cd backend
python scripts/enrich_ncert_books.py
```

### 2.3 Efficient Batch Ingestion

**File**: `backend/scripts/bulk_ingest_ncert.py`

```python
import asyncio
import os
from app.services.ingestion import NCERTIngestionPipeline
from app.db.mongo import db

async def bulk_ingest():
    """Ingest all NCERT books with progress tracking"""
    ingestion = NCERTIngestionPipeline(db)
    
    base_dir = "data/ncert_books"
    
    total_files = sum([len(files) for _, _, files in os.walk(base_dir) if any(f.endswith('.pdf') for f in files)])
    processed = 0
    
    for subject in os.listdir(base_dir):
        subject_path = os.path.join(base_dir, subject)
        
        if not os.path.isdir(subject_path):
            continue
        
        for pdf_file in os.listdir(subject_path):
            if not pdf_file.endswith('.pdf'):
                continue
            
            pdf_path = os.path.join(subject_path, pdf_file)
            processed += 1
            
            try:
                with open(pdf_path, 'rb') as f:
                    bytes_data = f.read()
                
                # Ingest with subject classification
                await ingestion.ingest_textbook(
                    file_bytes=bytes_data,
                    filename=pdf_file,
                    subject=subject,
                    grade="NCERT"
                )
                
                print(f"[{processed}/{total_files}] ✓ {pdf_file}")
                
            except Exception as e:
                print(f"[{processed}/{total_files}] ✗ {pdf_file}: {str(e)}")
            
            # Small delay to avoid API rate limits
            await asyncio.sleep(1)
    
    print(f"\n✓ Bulk ingestion complete: {processed}/{total_files} files")

if __name__ == "__main__":
    asyncio.run(bulk_ingest())
```

---

## PART 3: TESTING AFTER ENRICHMENT

### 3.1 Verify Pinecone Indices

```python
# backend/scripts/verify_pinecone_indices.py
import asyncio
from app.services.essay_evaluator import EssayEvaluationEngine
from app.db.mongo import db

async def verify_indices():
    """Check Pinecone indices are populated"""
    engine = EssayEvaluationEngine(db)
    
    subjects = ["history", "geography", "political-science", "economics", "general-studies"]
    
    for subject in subjects:
        # Query a general term
        results = await engine._query_pinecone(
            query_text="important concepts and facts",
            subject=subject,
            top_k=3
        )
        
        if results:
            print(f"✓ {subject}: {len(results)} documents found")
            for doc in results:
                print(f"  - Topic: {doc.get('topic', 'N/A')}, Score: {doc['score']:.3f}")
        else:
            print(f"⚠️  {subject}: No documents found (not yet ingested)")

asyncio.run(verify_indices())
```

**Run**: `python backend/scripts/verify_pinecone_indices.py`

### 3.2 Test Shadow Rubric Generation

```python
# backend/scripts/test_shadow_rubric.py
import asyncio
from app.services.essay_evaluator import EssayEvaluationEngine
from app.db.mongo import db

async def test_shadow_rubrics():
    """Test shadow rubric generation for various questions"""
    engine = EssayEvaluationEngine(db)
    
    test_cases = [
        ("Discuss the role of Gandhi in Indian independence", "history"),
        ("Analyze the monsoon patterns in India", "geography"),
        ("Explain the federal structure of Indian governance", "political-science"),
        ("What are the factors affecting economic growth?", "economics"),
    ]
    
    for question, subject in test_cases:
        print(f"\n📝 Question: {question}")
        print(f"📚 Subject: {subject}")
        
        result = await engine.create_shadow_rubric(question, subject)
        
        concepts = result.get("concepts", [])
        print(f"✓ Concepts ({len(concepts)}): {', '.join(concepts[:5])}...")

asyncio.run(test_shadow_rubrics())
```

**Run**: `python backend/scripts/test_shadow_rubric.py`

### 3.3 Performance Benchmarks

```python
# backend/scripts/benchmark_evaluation.py
import asyncio
import time
from app.services.essay_evaluator import EssayEvaluationEngine
from app.db.mongo import db

async def benchmark_full_pipeline():
    """Measure evaluation time"""
    engine = EssayEvaluationEngine(db)
    
    essay = """
    The Indian Constitution is the longest written constitution in the world.
    It was drafted by a Constituent Assembly and adopted on January 26, 1950.
    The Constitution guarantees fundamental rights and establishes a democratic republic.
    Key features include federalism, separation of powers, and judicial review.
    The Constitution can be amended through a special procedure involving Parliament.
    """
    
    print("⏱️  Benchmarking essay evaluation pipeline...")
    
    start = time.time()
    result = await engine.grade_essay(
        essay_text=essay,
        question="Discuss the salient features of the Indian Constitution",
        subject="political-science"
    )
    elapsed = time.time() - start
    
    print(f"✓ Total time: {elapsed:.2f} seconds")
    print(f"✓ Score: {result['scoring']['final_score']:.2f}")
    print(f"✓ Grade: {result['grade']}")

asyncio.run(benchmark_full_pipeline())
```

**Run**: `python backend/scripts/benchmark_evaluation.py`

---

## PART 4: DEPLOYMENT CHECKLIST

### Pre-Production Testing

- [ ] All unit tests pass: `pytest backend/tests/ -v`
- [ ] Groq API rate limits verified (20 RPM safe)
- [ ] OpenAI embeddings working (test with `_query_pinecone`)
- [ ] Pinecone indices populated with NCERT content
- [ ] Kafka topics created and workers running
- [ ] MongoDB collections initialized
- [ ] Shadow rubrics generating correctly
- [ ] Essay evaluations persisting to DB
- [ ] End-to-end Kafka pipeline working

### Monitoring Commands

```bash
# Monitor Groq API calls (logs)
docker logs -f essay-evaluator-container | grep "Groq"

# Check Pinecone index stats
# Via Pinecone console: Projects → your-project → Indexes → stats

# Monitor Kafka topics
kafka-topics --list --bootstrap-server localhost:9092
kafka-consumer-groups --list --bootstrap-server localhost:9092

# Check MongoDB collections
mongo
> use essay_eval_db
> db.essay_evaluations.count()
> db.parent_docs.count()
> db.shadow_graphs.count()
```

---

## Summary

1. **Replace OpenAI with Groq** ✓ (Done - Mixtral-8x7b-32768)
2. **Keep embeddings with OpenAI** ✓ (Groq doesn't support embeddings)
3. **Run unit tests** → Test Groq integration first
4. **Ingest NCERT books** → Use `bulk_ingest_ncert.py` script
5. **Verify indices** → Run `verify_pinecone_indices.py`
6. **Test shadow rubrics** → Validate question understanding
7. **Benchmark** → Measure end-to-end latency
8. **Monitor** → Watch Groq/OpenAI API usage

