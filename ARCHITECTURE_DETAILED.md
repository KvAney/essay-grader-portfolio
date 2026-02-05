# System Architecture & Data Flow

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ESSAY GRADER API v3.0                            │
│                     UPSC AI Assistant System                             │
└─────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────┐
                              │   FastAPI    │
                              │  Gateway     │
                              └──────┬───────┘
                                     │
                 ┌───────────────────┼───────────────────┐
                 │                   │                   │
        ┌────────▼────────┐  ┌───────▼────────┐  ┌──────▼───────┐
        │   Module 1:     │  │   Module 2:    │  │  Legacy      │
        │   Ingestion     │  │   Evaluation   │  │  Endpoints   │
        │   Pipeline      │  │   Engine       │  │              │
        └─────────────────┘  └────────────────┘  └──────────────┘
               │                      │
       ┌───────┴──────┐        ┌──────┴────────┐
       │              │        │               │
    MongoDB        Pinecone  MongoDB       OpenAI
    (Parents)     (Vectors)  (Reports)    (LLM)
```

---

## Module 1: Ingestion Pipeline Architecture

### Data Flow Diagram

```
NCERT PDF File
      │
      ▼
┌─────────────────────────────────────────────┐
│  _extract_text_from_pdf()                   │
│  ├─ Opens PDF with PyMuPDF                  │
│  ├─ Extracts text from each page            │
│  └─ Returns combined full text              │
└────────┬────────────────────────────────────┘
         │
         │ Full Text (e.g., 500KB)
         ▼
┌─────────────────────────────────────────────┐
│  _create_parent_chunks()                    │
│  ├─ Splits into sentences                   │
│  ├─ Groups until ~1000 tokens               │
│  └─ Returns List[parent_chunk]              │
└────────┬────────────────────────────────────┘
         │
         │ Parent Chunks (25-50 chunks)
         │
    ┌────┴────┐
    │ For Each│
    │ Parent  │
    └────┬────┘
         │
         ├──────────┬──────────┐
         │          │          │
         │ Store    │ Create   │ Get
         │ in       │ Child    │ Embedding
         │MongoDB   │ Chunks   │
         │          │          │
         ▼          ▼          ▼
    ┌────────┐ ┌────────┐ ┌──────────┐
    │parent_ │ │_create_│ │_get_     │
    │docs    │ │child_  │ │embedding │
    │coll    │ │chunks()│ │()        │
    └────────┘ └───┬────┘ └──────┬───┘
                   │             │
                   │ 5-10 child  │ OpenAI
                   │ chunks      │ API
                   │ per parent  │
                   │             │
                   └──────┬──────┘
                          │
                   Vectors (150-500)
                   + metadata
                          │
                          ▼
                   ┌──────────────┐
                   │ Pinecone     │
                   │ Upsert       │
                   │ (Batched)    │
                   └──────────────┘
```

### Data Structure

```python
# Input: NCERT PDF File
file_path = "/path/to/ncert_history_10.pdf"
subject = "History"
grade = 10

# Step 1: Extract → Full Text
{
    "text": "Chapter 1: Medieval India...[500KB of text]...",
    "pages": 150
}

# Step 2: Parent Chunks → MongoDB
{
    "_id": ObjectId("507f1f77bcf86cd799439011"),
    "subject": "history",
    "grade": 10,
    "text": "Full context ~1000 tokens...",
    "token_count": 1024,
    "parent_index": 0,
    "created_at": 1704067200.123
}

# Step 3: Child Chunks + Embeddings → Pinecone
{
    "id": "507f1f77bcf86cd799439011_0",
    "values": [0.123, -0.456, ...],  # 1536-dim vector
    "metadata": {
        "parent_id": "507f1f77bcf86cd799439011",
        "grade": 10,
        "subject": "history",
        "child_index": 0,
        "text_preview": "First 100 characters..."
    }
}
```

---

## Module 2: Evaluation Pipeline Architecture

### 3-Phase Flow with Data

```
┌──────────────────────────────────────────────────────────────────────┐
│                      STUDENT ESSAY + QUESTION                        │
│  essay_text: "The Battle of Plassey was a crucial..."                │
│  question: "Discuss the significance of the Battle of Plassey"       │
│  subject: "history"                                                  │
└────────────────────┬─────────────────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────────┐
        │    PHASE 0: SHADOW RUBRIC      │
        │   (Generate Answer Key)        │
        └────────┬───────────────────────┘
                 │
      Query Pinecone with Question
      ↓
      ┌──────────────────────────┐
      │ Top 5 Matching Documents │
      │ (from history-index)     │
      └──────┬───────────────────┘
             │
             │ Fetch Parents from MongoDB
             ▼
      ┌──────────────────────────┐
      │ Combined Parent Texts    │
      │ (~5000 tokens of NCERT)  │
      └──────┬───────────────────┘
             │
             │ LLM: Extract 15 Key Concepts
             ▼
      ┌──────────────────────────────────┐
      │ Shadow Rubric (Answer Key)       │
      │ concepts: [                      │
      │   "Battle of Plassey",          │
      │   "Robert Clive",               │
      │   "British East India Company", │
      │   ... (12 more)                 │
      │ ]                               │
      └──────┬───────────────────────────┘
             │
             ▼
        ┌────────────────────────────────┐
        │    PHASE 1: EXTRACTION        │
        │   (Parse Essay Content)        │
        └────────┬───────────────────────┘
                 │
        ├─ LLM: Extract Atomic Claims
        │  Claims: [
        │    "Battle of Plassey was in 1757",
        │    "Robert Clive defeated Siraj-ud-Daulah",
        │    "It led to British dominance in Bengal"
        │  ]
        │
        └─ Regex: Extract Discourse Markers
           Markers: {
             "causative": 3,
             "contrastive": 2,
             "additive": 4,
             "conclusive": 2,
             "sequential": 1
           }
             │
             ▼
        ┌────────────────────────────────┐
        │   PHASE 2: PARALLEL AGENTS     │
        │  (Run 3 Agents Concurrently)   │
        └────────────┬───────────────────┘
                     │
        ┌────────────┼────────────┬─────────────┐
        │            │            │             │
        ▼            ▼            ▼             ▼
   ┌────────────┐┌────────────┐┌────────────┐
   │   AGENT    ││   AGENT    ││   AGENT    │
   │     1      ││     2      ││     3      │
   │  FACT      ││  CONTENT   ││ LINGUISTIC │
   │ CHECKER    ││ COVERAGE   ││ ANALYSIS   │
   └─────┬──────┘└─────┬──────┘└─────┬──────┘
         │             │             │
         │ For each    │ For each    │ Analyze:
         │ claim:      │ concept:    │ - Grammar
         │ 1. Query    │ 1. Search   │ - Vocabulary
         │    Pinecone │    essay    │ - Tone
         │ 2. Fetch    │ 2. Calculate│
         │    Parent   │    covered%  │
         │ 3. LLM:     │             │
         │    VERIFY   │ Result:     │ Result:
         │             │ {           │ {
         │ Result:     │   coverage_ │   grammar_: 85,
         │ {           │   score: 80 │   vocab_: 78,
         │   accuracy_ │ }           │   tone_: 82,
         │   score: 85,│             │   language_: 81.3
         │   contrad.: 0            │ }
         │ }                        │
         └────────┬───────┬─────────┘
                  │       │
                  │ Gather Results
                  │       │
                  ▼       ▼
        ┌────────────────────────────────────┐
        │    PHASE 3: HOLISTIC SCORING       │
        │    (Calculate Final Score)         │
        └────────┬───────────────────────────┘
                 │
    Content_Score = (85 + 80) / 2 = 82.5
    Logical_Flow = 78 (paragraph similarity)
    Language_Score = 81.3
    
    Raw_Score = (0.5 × 82.5) + (0.3 × 78) + (0.2 × 81.3)
              = 41.25 + 23.4 + 16.26
              = 80.91
    
    Penalty = 0 × 15 = 0
    Final_Score = 80.91 - 0 = 80.91
    
    Normalized_Score = (80.91 / 100) × 1600 = 1294.56
    Grade = "A"
    
                 │
                 ▼
        ┌────────────────────────────────────┐
        │    COMPREHENSIVE REPORT            │
        │  {                                 │
        │    evaluation_id: "...",          │
        │    grade: "A",                    │
        │    scoring: {...},                │
        │    phase_0: {...},                │
        │    phase_1: {...},                │
        │    phase_2: {...},                │
        │    feedback: "✓ Good..."          │
        │  }                                │
        │  → Stored in MongoDB              │
        └────────────────────────────────────┘
```

### Agent Details

#### Agent 1: Fact Checker Agent

```
Input: List of 5-10 Claims
       ["Claim 1", "Claim 2", ...]

Processing Loop (for each claim):
  1. Query Pinecone
     ├─ Embed claim using OpenAI
     ├─ Semantic search in history-index
     └─ Retrieve top 3 child vectors + metadata
  
  2. Fetch Parents from MongoDB
     └─ Use parent_id from metadata
  
  3. Verification with LLM
     ├─ Combine retrieved parent texts
     ├─ Ask: "Does content support/contradict the claim?"
     └─ Get response: SUPPORTED | CONTRADICTED | NEUTRAL
  
  4. Aggregate Results
     ├─ Count: supported claims
     ├─ Count: contradicted claims
     └─ Calculate: accuracy_score = (supported / total) × 100

Output: {
  verified_claims: [
    {claim: "...", status: "supported", confidence: 0.9},
    {claim: "...", status: "contradicted", confidence: 1.0},
    ...
  ],
  accuracy_score: 85.0,
  contradiction_count: 1,
  supported_count: 8,
  total_claims: 9
}
```

#### Agent 2: Content Coverage Agent

```
Input: Essay Text + Shadow Concepts
       essay = "The Battle of Plassey...",
       concepts = ["Battle of Plassey", "Robert Clive", ...]

Processing:
  For each concept in shadow_concepts:
    if concept appears in essay (case-insensitive):
      Mark as COVERED
    else:
      Mark as UNCOVERED
  
  Calculate: coverage_score = (covered / total) × 100

Output: {
  covered_concepts: [
    {concept: "Battle of Plassey", covered: True},
    {concept: "Robert Clive", covered: True},
    {concept: "Treaty of Paris", covered: False},
    ...
  ],
  coverage_score: 80.0,
  concepts_covered: 12,
  total_concepts: 15
}
```

#### Agent 3: Linguistic Agent

```
Input: Essay Text (first 500 words)

Processing:
  Send to LLM with prompt:
    "Analyze this essay for UPSC standards.
     Provide grammar_score (0-100),
             vocabulary_score (0-100),
             tone_score (0-100),
             overall_score (0-100)"
  
  Parse JSON response
  
  Calculate: language_score = 
    (grammar_score × 0.3) + 
    (vocabulary_score × 0.4) + 
    (tone_score × 0.3)

Output: {
  grammar_score: 85,
  vocabulary_score: 78,
  tone_score: 82,
  language_score: 81.3,
  overall_score: 82
}
```

---

## Database Architecture

### MongoDB Collections

```
essayEval Database
├── parent_docs
│   ├── Index on: subject, grade
│   └── Sample Doc:
│       {
│         _id: ObjectId,
│         subject: "history",
│         grade: 10,
│         text: "...",
│         token_count: 1024,
│         parent_index: 0,
│         created_at: timestamp
│       }
├── shadow_graphs
│   ├── Index on: question, subject
│   └── Sample Doc:
│       {
│         _id: ObjectId,
│         question: "Discuss significance...",
│         subject: "history",
│         concepts: ["Concept1", "Concept2", ...],
│         retrieved_docs: [...],
│         created_at: timestamp
│       }
└── essay_evaluations
    ├── Index on: evaluation_id, subject
    └── Sample Doc:
        {
          _id: ObjectId,
          evaluation_id: "timestamp",
          question: "...",
          subject: "history",
          grade: "A",
          scoring: {...},
          phase_0: {...},
          phase_1: {...},
          phase_2: {...},
          feedback: "..."
        }
```

### Pinecone Indices

```
history-index (1536-dim vectors)
├── Namespace: default
├── Vector Count: 150-500 (depends on NCERT size)
└── Sample Vector:
    {
      id: "ObjectId_0",
      values: [0.123, -0.456, ...],
      metadata: {
        parent_id: "ObjectId",
        grade: 10,
        subject: "history",
        child_index: 0,
        text_preview: "..."
      }
    }

Other indices:
├── geography-index
├── political-science-index
├── economics-index
└── general-studies-index
```

---

## Request/Response Flow

### Ingestion Request Flow

```
Client (FastAPI Request)
  │
  ├─ POST /ingest/textbook
  │  └─ IngestionRequest(subject, grade, file_path)
  │
  ▼
FastAPI Main.py
  │
  ├─ Instantiate: NCERTIngestionPipeline(mongodb)
  │
  ├─ Call: pipeline.ingest_textbook(file_path, subject, grade)
  │
  ▼
NCERTIngestionPipeline
  │
  ├─ _extract_text_from_pdf()
  │  └─ PyMuPDF library
  │
  ├─ _create_parent_chunks()
  │  └─ Token-based splitting
  │
  ├─ For each parent chunk:
  │  ├─ INSERT to MongoDB (parent_docs collection)
  │  ├─ _create_child_chunks()
  │  │  └─ Token-based splitting
  │  │
  │  └─ For each child chunk:
  │     ├─ _get_embedding() → OpenAI API
  │     └─ Prepare vector with metadata
  │
  ├─ BATCH UPSERT to Pinecone
  │  └─ 100 vectors per batch
  │
  ▼
Response: IngestionResponse
  {
    status: "success",
    subject: "History",
    grade: 10,
    parent_chunks_created: 25,
    child_vectors_created: 150,
    pinecone_index: "history-index"
  }
```

### Evaluation Request Flow

```
Client (FastAPI Request)
  │
  ├─ POST /grade_essay
  │  └─ GradeEssayRequest(essay_text, question, subject)
  │
  ▼
FastAPI Main.py
  │
  ├─ Instantiate: EssayEvaluationEngine(mongodb)
  │
  ├─ Call: engine.grade_essay(essay_text, question, subject)
  │
  ▼
EssayEvaluationEngine
  │
  ├─ PHASE 0: create_shadow_rubric(question, subject)
  │  ├─ _query_pinecone(question, subject, top_k=5)
  │  │  ├─ OpenAI: Embed question
  │  │  └─ Pinecone: Semantic search
  │  ├─ Fetch 5 parent documents from MongoDB
  │  ├─ _extract_concepts() from combined text
  │  └─ MongoDB: Store shadow_rubric
  │
  ├─ PHASE 1: Extraction & Parsing
  │  ├─ extract_atomic_claims(essay_text)
  │  │  └─ LLM: Extract 5-10 factual claims
  │  └─ extract_discourse_markers(essay_text)
  │     └─ Regex: Count logical connectives
  │
  ├─ PHASE 2: Parallel Agent Execution
  │  ├─ asyncio.gather(
  │  │  fact_checker_agent(),
  │  │  content_coverage_agent(),
  │  │  linguistic_agent(),
  │  │  calculate_logical_flow()
  │  │ )
  │  │
  │  └─ All agents run concurrently
  │
  ├─ PHASE 3: Holistic Scoring
  │  ├─ Calculate Content_Score
  │  ├─ Calculate Logical_Flow
  │  ├─ Calculate Raw_Score
  │  ├─ Apply Penalties
  │  ├─ Normalize to 0-1600
  │  ├─ Assign Letter Grade
  │  └─ Generate Feedback
  │
  ├─ MongoDB: Store essay_evaluation
  │
  ▼
Response: GradeEssayResponse
  {
    evaluation_id: "...",
    grade: "A",
    scoring: {...},
    phase_0: {...},
    phase_1: {...},
    phase_2: {...},
    feedback: "..."
  }
```

---

## Performance Characteristics

### Ingestion Pipeline

| Operation | Time | Resources |
|-----------|------|-----------|
| PDF Extraction | 1-5s | Memory: ~50MB |
| Parent Chunking | 0.5-1s | CPU |
| Child Chunking | 0.5-1s | CPU |
| OpenAI Embeddings | 3-10s | API calls (batched) |
| MongoDB Inserts | 0.5-2s | I/O |
| Pinecone Upsert | 2-5s | I/O + API |
| **Total per file** | **8-24s** | |

### Evaluation Pipeline

| Phase | Time | Resources |
|-------|------|-----------|
| Shadow Rubric | 2-3s | Pinecone + MongoDB |
| Extraction | 1-2s | LLM |
| Fact Checker | 5-10s | Pinecone + MongoDB + LLM (parallelized) |
| Content Coverage | 1-2s | Regex |
| Linguistic | 2-3s | LLM |
| Logical Flow | 2-3s | OpenAI Embeddings |
| Scoring | 0.5s | Calculation |
| **Total per essay** | **14-24s** | |

---

## Security Considerations

1. **API Keys**: Store in environment variables, never in code
2. **MongoDB**: Use connection strings with authentication
3. **Pinecone**: API key protected, index-level access controls
4. **OpenAI**: Rate limiting to prevent abuse
5. **CORS**: Configured for localhost only
6. **Input Validation**: Pydantic models validate all inputs
7. **Error Handling**: Never expose sensitive information in error messages

---

**Version:** 3.0.0  
**Last Updated:** January 2026
