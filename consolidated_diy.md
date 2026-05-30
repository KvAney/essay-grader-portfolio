# Consolidated DIY Deployment & Run Manual

This file contains the complete startup, configuration, and runtime instructions for the Essay Grader Portfolio application. It also includes the detailed feature-level data flow diagrams for all production capabilities.

---

## 1. Overview

This project provides an end-to-end essay grading platform that includes:

- **Textbook ingestion** for NCERT content.
- **OCR-based essay intake** from PDF or text submissions.
- **Parallel AI grading** using fact-checking, content coverage, and language evaluation.
- **Kafka-based streaming** for scalable request handling and worker orchestration.
- **Multi-tier storage** using PostgreSQL, MongoDB, and Pinecone-style vector storage.

The application is designed to start quickly and run reliably in a local or containerized environment.

---

## 2. Prerequisites

- Docker
- Docker Compose
- Python 3.11+ (for local backend development)
- Node.js 16+ (optional for frontend development)
- Groq API key

---

## 3. Initialization and Configuration

### 3.1 Clone the repository

```bash
git clone <repo-url> essay-grader-portfolio
cd essay-grader-portfolio
```

### 3.2 Create environment variables

Create `backend/.env` with the minimum required values:

```env
GROQ_API_KEY=gsk_YOUR_API_KEY_HERE
DATABASE_URL=postgresql://postgres:ppt@postgres_db:5432/essay_eval_db
MONGO_URL=mongodb://mongo_db:27017
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
```

### 3.3 Verify Docker Compose settings

Ensure `docker-compose.yml` defines the following services:

- `backend` / FastAPI API server
- `postgres_db` / PostgreSQL metadata store
- `mongo_db` / MongoDB document store
- `kafka` and required Kafka dependencies

If you need custom ports or credentials, update `docker-compose.yml` and `backend/.env` accordingly.

---

## 4. Start the Application

### 4.1 One-command startup

```bash
cd essay-grader-portfolio
docker-compose up --build
```

### 4.2 Confirm services are running

```bash
docker-compose ps
```

Expected services:

- `backend`
- `postgres_db`
- `mongo_db`
- `kafka`

### 4.3 Access the API

Open the API docs at:

```text
http://localhost:8000/docs
```

---

## 5. Running the Application

### 5.1 Ingest textbooks

Use the textbook ingestion endpoint to load NCERT content into the knowledge pipeline.

```bash
curl -X POST http://localhost:8000/ingest/textbook \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/ncert.pdf"}'
```

### 5.2 Grade an essay

Submit an essay for evaluation:

```bash
curl -X POST http://localhost:8000/grade_essay \
  -H "Content-Type: application/json" \
  -d '{"essay":"Your essay text here"}'
```

### 5.3 Check evaluation status

```bash
curl http://localhost:8000/status/{submission_id}
```

### 5.4 Use the web UI

If a frontend is installed, navigate to:

```text
http://localhost:3000
```

---

## 6. How the System Works

### 6.1 Textbook ingestion flow

The ingestion path takes NCERT source material, extracts text, chunks it for efficient retrieval, and saves knowledge for grading.

- `POST /ingest/textbook`
- `PyMuPDF` or PDF parser extracts raw text
- Text is split into hierarchical parent and child chunks
- Parent chunks are stored in MongoDB
- Child chunks are embedded and stored in Pinecone-style vector storage

### 6.2 Essay submission flow

When an essay is submitted:

- The API receives the essay payload
- The essay is enqueued into Kafka
- OCR and text extraction are performed if the input is a document file
- The essay body is stored and metadata is persisted in PostgreSQL

### 6.3 Grading flow

The grading engine uses a multi-agent pipeline:

- Generates a **shadow rubric** from textbook concepts
- Extracts **claims, discourse markers, and concept mentions**
- Executes parallel agents:
  - Fact Checker Agent
  - Content Coverage Agent
  - Linguistic Agent
- Aggregates scores into a holistic final grade

### 6.4 Result storage

- MongoDB stores raw and evaluated essay chunks
- PostgreSQL stores submission metadata and status
- Vector DB stores embeddings used for semantic retrieval

---

## 7. Feature-Level Data Flow Diagrams

### 7.1 Overall system diagram

```mermaid
flowchart TD
    subgraph Client [User Interface]
        A[UPSC Aspirant / Web UI / API Client]
    end

    subgraph API [FastAPI Gateway]
        B[app.main:app]
        B --> C[POST /ingest/textbook]
        B --> D[POST /grade_essay]
        B --> E[GET /status/{submission_id}]
    end

    subgraph Stream [Kafka Streaming]
        F[ingestion_topic]
        G[grading_topic]
    end

    subgraph Ingest [Textbook Ingestion Pipeline]
        H[NCERTIngestionPipeline]
        H --> I[PyMuPDF Text Extraction]
        I --> J[Parent/Child Chunker]
        J --> K[MongoDB (Parent Chunks)]
        J --> L[Embeddings Service]
        L --> M[Pinecone / Vector DB]
    end

    subgraph Grade [Essay Evaluation Engine]
        N[EssayEvaluationEngine]
        N --> O[Shadow Rubric Generator]
        N --> P[Parallel Agent Runner]
        P --> Q[Fact Checker]
        P --> R[Coverage Agent]
        P --> S[Linguistic Agent]
        Q --> K
        R --> O
        S --> N
        N --> T[Scoring Aggregator]
        T --> U[Final Grade]
    end

    subgraph Storage [Persistence Layer]
        V[PostgreSQL (Metadata)]
        W[MongoDB (Extracted Text & Evaluations)]
        X[Vector DB (Semantic Search)]
    end

    A --> B
    B --> F
    B --> G
    F --> H
    G --> N
    N --> V
    N --> W
    H --> W
    L --> X
    O --> X
```

### 7.2 Textbook ingestion feature flow

```mermaid
flowchart LR
    T1[POST /ingest/textbook] --> T2[Download PDF or load source]
    T2 --> T3[Extract text via PyMuPDF]
    T3 --> T4[Parent / Child Splitter]
    T4 --> T5[Store parent chunks in MongoDB]
    T4 --> T6[Embed child chunks]
    T6 --> T7[Store vectors in Vector DB]
    T7 --> T8[Enable semantic retrieval for grading]
```

### 7.3 Essay grading feature flow

```mermaid
flowchart LR
    G1[POST /grade_essay] --> G2[Receive essay text or file]
    G2 --> G3[Queue job in Kafka]
    G3 --> G4[AI Worker consumes grading job]
    G4 --> G5[Generate shadow rubric from textbook vectors]
    G5 --> G6[Extract claims and concepts]
    G6 --> G7[Run parallel agents]
    G7 --> G8[Aggregate scores]
    G8 --> G9[Normalize grade to 0-1600 and A+..F]
    G9 --> G10[Persist result in MongoDB and PostgreSQL]
```

### 7.4 Parallel grading and scoring flow

```mermaid
flowchart TD
    P1[Parallel Agent Runner] --> P2[Fact Checker Agent]
    P1 --> P3[Content Coverage Agent]
    P1 --> P4[Linguistic Agent]
    P2 --> P5[Verify claims against textbook evidence]
    P3 --> P6[Measure coverage of key concepts]
    P4 --> P7[Evaluate grammar, tone, style]
    P5 --> P8[Content score]
    P6 --> P9[Coverage score]
    P7 --> P10[Language score]
    P8 --> P11[Holistic aggregator]
    P9 --> P11
    P10 --> P11
    P11 --> P12[Final score with contradiction penalties]
```

---

## 8. Make It Work: Practical Notes

### 8.1 Common startup checklist

- `docker-compose up --build` completes without errors
- `backend` service starts and listens on port 8000
- `postgres_db` and `mongo_db` are healthy
- `kafka` service is running
- `/docs` page loads successfully

### 8.2 If the API does not respond

- Validate `backend/.env` exists and contains valid `GROQ_API_KEY`
- Confirm `docker-compose ps` shows all services healthy
- Check logs with `docker-compose logs backend`
- Inspect network ports to ensure 8000, 5432, 27017, and 9092 are free

### 8.3 If ingestion fails

- Verify the source PDF is accessible
- Confirm MongoDB connectivity in `backend/.env`
- Check logs for PyMuPDF or PDF parsing errors

### 8.4 If grading is slow

- Ensure Kafka queues are processing jobs
- Verify the AI worker uses the Groq API key
- Confirm any rate limiting logic is not throttling excessively

---

## 9. Cleanup and Shutdown

Stop all services cleanly:

```bash
docker-compose down
```

Remove volumes if needed:

```bash
docker-compose down -v
```

---

## 10. File Summary

Keep the project focused with only these two documentation sources:

- `README.md` — Project overview, feature list, and quick architecture summary.
- `consolidated_diy.md` — Complete start/run manual with the detailed feature data-flow diagrams.
